"""Frozen entry point for the bundled Syncbox service.

PyInstaller packages this into a standalone executable that the Electron app
spawns in production (instead of `uv run uvicorn`). No --reload, no import
string: we pass the ASGI app object directly so the frozen binary needs no
filesystem module discovery at runtime.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    from app.logging_setup import configure_logging, log_file_path

    logger = configure_logging()
    logger.info("Frozen service entry point; logs at %s", log_file_path())

    from app.main import app

    port = int(os.environ.get("RBSYNC_SERVICE_PORT", "8765"))
    host = os.environ.get("RBSYNC_SERVICE_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
