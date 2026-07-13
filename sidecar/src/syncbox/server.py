"""Loopback HTTP+SSE service (SPEC-UNIFIED 6.3/6.6/6.10, research 06, POC #4).

Hard transport rules implemented here:
- bind 127.0.0.1 only; CORS restricted to loopback http origins PLUS the
  shell webview's exact origins (tauri://localhost measured on macOS,
  http://tauri.localhost per Tauri v2 docs for Windows) - the 2026-07-02
  owner-approved amendment to 6.3; allow_credentials stays False, never a
  wildcard;
- ONE canonical SSE jobs stream (/events); no GZip on it (sse-starlette
  breaks under GZipMiddleware);
- uvicorn runs programmatically IN the main asyncio loop with 1 worker
  (signal handlers must live in the main thread or sse-starlette's clean
  SSE shutdown breaks), bounded graceful shutdown;
- /callback answers regardless of the incoming Host header (browsers may
  rewrite 127.0.0.1 to localhost; the OAuth redirect_uri is never derived
  from the request - see spotify.py);
- /shutdown implements the 6.6 handshake: intent flag first, then stop.
"""

import asyncio
import json
import socket

import uvicorn
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

HOST = "127.0.0.1"
PORT = 8765
SERVICE_NAME = "syncbox-sidecar"
PROTOCOL_VERSION = 1
LOOPBACK_ORIGIN_REGEX = r"http://(127\.0\.0\.1|localhost):\d+"
WEBVIEW_ORIGINS = ["tauri://localhost", "http://tauri.localhost"]


class NoStoreMiddleware:
    """Never reuse state or OAuth URLs from a previous loopback process."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_no_store(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_no_store)


class JobBus:
    """Canonical async event bus feeding the single SSE stream."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    async def publish(self, event_type: str, payload: dict) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait({"event": event_type, "data": json.dumps(payload)})

    async def stream(self):
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


class ShutdownController:
    """6.6 handshake, sidecar side: intent flag FIRST, then stop the server.

    The intent flag distinguishes a voluntary stop from a crash in logs
    (never classify by exit code/signal - POC #2).
    """

    def __init__(self):
        self.intentional = False
        self._trigger = None

    def bind(self, trigger) -> None:
        self._trigger = trigger

    def request(self) -> None:
        self.intentional = True
        if self._trigger is not None:
            self._trigger()


def create_app(
    *, bus: JobBus | None = None, oauth_callback=None, oauth_lock=None, routes=()
) -> Starlette:
    """App factory. oauth_callback(params: dict) -> dict is injected by the
    OAuth layer (spotify.SpotifyAuth.handle_callback); ``routes`` appends
    extra Route objects (the REST API layer, api.build_app) after the
    transport routes - /health, /events (SSE), /shutdown and /callback stay
    canonical and cannot be shadowed."""
    bus = bus if bus is not None else JobBus()
    shutdown = ShutdownController()

    async def health(request):
        return JSONResponse(
            {
                "ok": True,
                "service": SERVICE_NAME,
                "protocol": PROTOCOL_VERSION,
            }
        )

    async def events(request):
        return EventSourceResponse(bus.stream())

    async def request_shutdown(request):
        shutdown.request()
        return JSONResponse({"stopping": True}, status_code=202)

    async def callback(request):
        # Answer whatever the Host header says (browser may have rewritten
        # 127.0.0.1 -> localhost); the redirect_uri constant is never derived
        # from this request.
        if oauth_callback is None:
            return JSONResponse({"error": "oauth not configured"}, status_code=503)

        def exchange():
            if oauth_lock is None:
                return oauth_callback(dict(request.query_params))
            with oauth_lock:
                return oauth_callback(dict(request.query_params))

        # Spotify's stdlib HTTP transport is synchronous and may take up to
        # 30 seconds. Keep it off the main asyncio loop so SSE and /shutdown
        # remain responsive, and serialize SQLCipher access with REST routes.
        result = await run_in_threadpool(exchange)
        if result.get("ok"):
            return HTMLResponse(
                "<html><body><p>Spotify connected. You can close this window "
                "and return to Syncbox.</p></body></html>"
            )
        return JSONResponse(result, status_code=400)

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/events", events),
            Route("/shutdown", request_shutdown, methods=["POST"]),
            Route("/callback", callback),
            *routes,
        ],
        middleware=[
            Middleware(NoStoreMiddleware),
            Middleware(
                CORSMiddleware,
                allow_origins=WEBVIEW_ORIGINS,
                allow_origin_regex=LOOPBACK_ORIGIN_REGEX,
                allow_credentials=False,
                allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                allow_headers=["content-type"],
            )
        ],
    )
    app.state.bus = bus
    app.state.shutdown = shutdown
    return app


class PortInUseError(RuntimeError):
    """Port 8765 is taken. No rotation: the redirect_uri must stay exact
    (research 06) - fail clean with an actionable message instead."""

    def __init__(self, host: str, port: int):
        super().__init__(
            f"Syncbox could not start: {host}:{port} is already in use. "
            "Close the application holding it (another Syncbox instance?) "
            "and relaunch."
        )


def ensure_port_free(host: str = HOST, port: int = PORT) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR mirrors uvicorn's own bind: without it, server-side
    # TIME_WAIT remnants of closed /health connections (~15 s on macOS) make
    # the probe fail on a crash-restart (supervisor backoff is 1 s), even
    # though uvicorn itself would bind fine. The probe must answer "can
    # uvicorn bind?", not "does any TIME_WAIT remnant exist?" - found by the
    # shell/harness lifecycle driver (M4.3).
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise PortInUseError(host, port) from exc
    finally:
        probe.close()


async def serve(app, *, host: str = HOST, port: int = PORT, graceful_timeout: int = 3):
    """Run uvicorn programmatically in the CURRENT (main) asyncio loop.

    Never run this in a thread with signal handlers disabled: sse-starlette
    detects shutdown through uvicorn's main-thread signal handling, and the
    SSE generators would be cancelled brutally (research 06 hard rule).
    """
    ensure_port_free(host, port)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        timeout_graceful_shutdown=graceful_timeout,
    )
    server = uvicorn.Server(config)
    app.state.shutdown.bind(lambda: setattr(server, "should_exit", True))
    await server.serve()
