"""POC #3 - minimal sidecar used to measure honest PyInstaller onedir size + cold-start.

Imports the full lawful v1 dependency surface (SPEC-UNIFIED 3.4) so the bundle matches
what production ships, then serves /health and /sse with the production topology:
uvicorn, 1 worker, started programmatically in the main asyncio loop (SPEC-UNIFIED 6.3).
"""

import time

T0 = time.perf_counter()

# Full v1 dependency surface - imported so PyInstaller bundles what production bundles.
import numpy  # noqa: F401,E402
import miniaudio  # noqa: F401,E402
import mutagen  # noqa: F401,E402
import rapidfuzz  # noqa: F401,E402
import psutil  # noqa: F401,E402
import sqlalchemy  # noqa: F401,E402
import sqlcipher3  # noqa: F401,E402
import pyrekordbox  # noqa: F401,E402

import asyncio  # noqa: E402

import uvicorn  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402


async def health(request):
    return JSONResponse({"ok": True, "import_to_ready_s": round(time.perf_counter() - T0, 3)})


async def sse(request):
    async def gen():
        for i in range(3):
            yield {"event": "tick", "data": str(i)}
            await asyncio.sleep(0.05)

    return EventSourceResponse(gen())


app = Starlette(routes=[Route("/health", health), Route("/sse", sse)])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8899, log_level="warning")
