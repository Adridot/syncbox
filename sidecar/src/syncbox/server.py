"""Loopback HTTP+SSE services (SPEC-UNIFIED 6.3/6.6/6.10, research 06, POC #4).

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
- the permanent API/SSE service uses port 8766; Spotify's exact callback
  remains on a separate 8765 listener opened only during authorization;
- /shutdown implements the 6.6 handshake: intent flag first, then stop.
"""

import asyncio
import errno
import json
import socket
import threading

import uvicorn
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

HOST = "127.0.0.1"
PORT = 8766
OAUTH_CALLBACK_PORT = 8765
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

    _STOP = object()

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()
        self._closed = False

    async def publish(self, event_type: str, payload: dict) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait({"event": event_type, "data": json.dumps(payload)})

    def close(self) -> None:
        self._closed = True
        for queue in list(self._subscribers):
            queue.put_nowait(self._STOP)

    async def stream(self):
        if self._closed:
            return
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is self._STOP:
                    return
                yield event
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


def create_app(*, bus: JobBus | None = None, routes=()) -> Starlette:
    """Permanent API/SSE app factory.

    ``routes`` appends the REST API routes after the canonical transport
    routes. Spotify's callback deliberately does not exist on this service;
    :class:`OAuthCallbackListener` owns it on the exact temporary port.
    """
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
        async def stop_after_response():
            shutdown.request()

        return JSONResponse(
            {"stopping": True},
            status_code=202,
            background=BackgroundTask(stop_after_response),
        )

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/events", events),
            Route("/shutdown", request_shutdown, methods=["POST"]),
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
    """The permanent API/SSE port is taken; fail without touching its owner."""

    def __init__(self, host: str, port: int):
        super().__init__(
            f"Syncbox could not start: {host}:{port} is already in use. "
            "Close the application holding it (another Syncbox instance?) "
            "and relaunch."
        )


class OAuthCallbackPortInUseError(RuntimeError):
    """The exact Spotify callback port is unavailable for this auth attempt."""

    def __init__(self, host: str, port: int):
        super().__init__(
            f"Spotify authorization could not start: {host}:{port} is already "
            "in use. Close the application holding it and retry."
        )


class OAuthCallbackListener:
    """One temporary, access-log-free listener for Spotify's exact callback."""

    def __init__(self, host: str = HOST, port: int = OAUTH_CALLBACK_PORT):
        self.host = host
        self.port = port
        self._guard = threading.Lock()
        self._server = None
        self._socket = None
        self._thread = None
        self._timer = None

    @property
    def active(self) -> bool:
        with self._guard:
            return self._thread is not None and self._thread.is_alive()

    def start(self, oauth_callback, *, oauth_lock=None, timeout: float = 120) -> bool:
        """Bind before the authorize URL is returned; renew an active attempt.

        Returns ``True`` only when this call created the listener. A second
        authorization reuses the already-bound listener and renews its timer.
        """
        with self._guard:
            if self._thread is not None and self._thread.is_alive():
                self._arm_timer_locked(timeout)
                return False

        callback_app = self._callback_app(oauth_callback, oauth_lock)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind((self.host, self.port))
            listener.listen(128)
        except OSError as exc:
            listener.close()
            if exc.errno == errno.EADDRINUSE:
                raise OAuthCallbackPortInUseError(self.host, self.port) from exc
            raise

        # Port 0 is useful for isolated transport tests; production always
        # supplies the exact OAUTH_CALLBACK_PORT above.
        bound_port = listener.getsockname()[1]
        config = uvicorn.Config(
            callback_app,
            log_level="warning",
            access_log=False,
            proxy_headers=False,
            server_header=False,
            date_header=False,
            lifespan="off",
            timeout_graceful_shutdown=3,
        )
        callback_server = uvicorn.Server(config)
        thread = threading.Thread(
            target=self._run,
            args=(callback_server, listener),
            name="syncbox-oauth-callback",
            daemon=True,
        )
        with self._guard:
            self.port = bound_port
            self._server = callback_server
            self._socket = listener
            self._thread = thread
            thread.start()
            self._arm_timer_locked(timeout)
        return True

    def stop(self) -> None:
        """Request shutdown without joining (safe while the API lock is held)."""
        with self._guard:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._server is not None:
                self._server.should_exit = True

    def wait_closed(self, timeout: float = 4) -> None:
        with self._guard:
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def _arm_timer_locked(self, timeout: float) -> None:
        if self._timer is not None:
            self._timer.cancel()
        timer = threading.Timer(timeout, self.stop)
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _run(self, callback_server, listener) -> None:
        try:
            callback_server.run(sockets=[listener])
        finally:
            listener.close()
            with self._guard:
                if self._server is callback_server:
                    if self._timer is not None:
                        self._timer.cancel()
                    self._server = None
                    self._socket = None
                    self._thread = None
                    self._timer = None

    def _callback_app(self, oauth_callback, oauth_lock) -> Starlette:
        async def callback(request):
            # The exact redirect URI is a constant in spotify.py. Never derive
            # it from Host, which browsers and proxies may rewrite.
            def exchange():
                if oauth_lock is None:
                    return oauth_callback(dict(request.query_params))
                with oauth_lock:
                    return oauth_callback(dict(request.query_params))

            result = await run_in_threadpool(exchange)
            terminal = result.get("ok") or result.get("error") != "state_mismatch"
            background = BackgroundTask(self.stop) if terminal else None
            if result.get("ok"):
                return HTMLResponse(
                    "<html><body><p>Spotify connected. You can close this "
                    "window and return to Syncbox.</p></body></html>",
                    background=background,
                )
            return JSONResponse(result, status_code=400, background=background)

        return Starlette(
            routes=[Route("/callback", callback, methods=["GET"])],
            middleware=[Middleware(NoStoreMiddleware)],
        )


def bind_api_socket(host: str = HOST, port: int = PORT) -> socket.socket:
    """Exclusively bind the permanent API port and return the socket.

    The bind IS the single-instance lock: the kernel holds it until the
    owning process dies, so a caller that owns this socket is provably the
    only live sidecar. It must be acquired BEFORE any startup step that
    assumes exclusivity (resetting interrupted acquisition jobs, starting
    the worker), and then handed to :func:`serve` — binding for real, not
    probe-and-close, also removes the check/bind race window.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.listen(2048)
    except OSError as exc:
        sock.close()
        raise PortInUseError(host, port) from exc
    return sock


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


async def serve(
    app,
    *,
    host: str = HOST,
    port: int = PORT,
    graceful_timeout: int = 3,
    sockets=None,
):
    """Run uvicorn programmatically in the CURRENT (main) asyncio loop.

    Never run this in a thread with signal handlers disabled: sse-starlette
    detects shutdown through uvicorn's main-thread signal handling, and the
    SSE generators would be cancelled brutally (research 06 hard rule).

    ``sockets`` accepts sockets already bound by :func:`bind_api_socket`
    (the single-instance lock); without them the legacy probe is kept.
    """
    if sockets is None:
        ensure_port_free(host, port)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        timeout_graceful_shutdown=graceful_timeout,
    )
    server = uvicorn.Server(config)

    def stop() -> None:
        app.state.bus.close()
        server.should_exit = True

    app.state.shutdown.bind(stop)
    await server.serve(sockets=sockets)
