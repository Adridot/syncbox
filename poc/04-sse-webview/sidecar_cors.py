"""POC #4 - venv-run SSE app (same topology as POC #3 app.py: Starlette + sse-starlette,
uvicorn 1 worker, programmatic, main asyncio loop) with CORS response headers so the
WKWebView page (origin tauri://localhost, NOT in the SPEC-UNIFIED 6.3 loopback allowlist)
can consume the stream. Every request's exact Origin header is logged to a jsonl file so
the spec-gap report is grounded in measured headers, not assumptions.

Endpoints (127.0.0.1:8897):
  /health      liveness for the orchestrator
  /sse         3 tick events, 400 ms apart  -> incremental-delivery probe
  /sse-padded  2 KB ':' comment preamble then the same 3 ticks -> WebKit padding probe
  /sse-long    tick every 500 ms 'forever'  -> kill-midstream probe

NOTE (faithful reporting): CORS here echoes the request Origin ONLY so the POC can
measure streaming; each request is logged with allowed_by_spec_6_3 so the verdict can
state exactly which origins the current spec allowlist would have rejected. This is a
disposable probe, not a proposal to widen production CORS.
"""

import asyncio
import json
import re
import sys
import time

import uvicorn
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

ORIGIN_LOG = sys.argv[1] if len(sys.argv) > 1 else "/tmp/poc4-origins.jsonl"
# Exact allowlist currently written in SPEC-UNIFIED 6.3.
SPEC_6_3_ORIGIN_RE = re.compile(r"^http://(127\.0\.0\.1|localhost):\d+$")


def log_origin(request):
    origin = request.headers.get("origin")
    rec = {
        "t_epoch": time.time(),
        "path": request.url.path,
        "origin": origin,
        "host": request.headers.get("host"),
        "user_agent": request.headers.get("user-agent"),
        "accept": request.headers.get("accept"),
        "allowed_by_spec_6_3": bool(origin and SPEC_6_3_ORIGIN_RE.match(origin)),
    }
    with open(ORIGIN_LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return origin


def cors(origin):
    # Echo for measurement purposes only (see module docstring). No credentials.
    return {"Access-Control-Allow-Origin": origin or "*"}


async def health(request):
    return JSONResponse({"ok": True}, headers=cors(request.headers.get("origin")))


def make_sse(padded: bool):
    async def endpoint(request):
        origin = log_origin(request)

        async def gen():
            if padded:
                # WebKit initial-buffering workaround probe (research 06, POC #2 note).
                yield {"comment": "x" * 2048}
            for i in range(3):
                yield {"event": "tick", "data": str(i)}
                await asyncio.sleep(0.4)

        return EventSourceResponse(gen(), headers=cors(origin))

    return endpoint


async def sse_long(request):
    origin = log_origin(request)

    async def gen():
        for i in range(600):  # ~5 min; the orchestrator SIGKILLs us mid-stream
            yield {"event": "tick", "data": str(i)}
            await asyncio.sleep(0.5)

    return EventSourceResponse(gen(), headers=cors(origin))


app = Starlette(
    routes=[
        Route("/health", health),
        Route("/sse", make_sse(padded=False)),
        Route("/sse-padded", make_sse(padded=True)),
        Route("/sse-long", sse_long),
    ]
)

if __name__ == "__main__":
    # Same non-negotiable topology as production (SPEC-UNIFIED 6.3): 1 worker,
    # programmatic, signal handlers in the main loop.
    uvicorn.run(app, host="127.0.0.1", port=8897, log_level="warning")
