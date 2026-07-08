"""Sidecar entrypoint (``python -m syncbox``) - the composition root.

Wires, exactly once, what the tests assemble by hand: app data dir ->
migrated app DB -> encrypted secrets store -> Spotify PKCE auth + client ->
api.Deps -> Starlette app -> uvicorn on 127.0.0.1:8765 (server.serve, main
asyncio loop, SPEC-UNIFIED 6.3). Logging goes to a rotating file in the app
data dir (feeds GET /api/doctor/logs) and to stderr for the shell
supervisor, which always consumes child output (6.6).
"""

import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from syncbox import api, appdb, platform_os, server
from syncbox.secrets import SecretsStore
from syncbox.settings import Settings
from syncbox.spotify import SpotifyAuth, SpotifyClient

log = logging.getLogger("syncbox")


def _drop_playlist_xml_noise(record) -> bool:
    """Drop pyrekordbox's per-commit warning about playlists missing from
    masterPlaylists6.xml. Rekordbox removes the XML node when a playlist is
    deleted but keeps the DB row soft-deleted, so the warning re-fires forever
    for every playlist ever deleted (222 on the owner's library, one line each
    per mutation) and carries no signal - deleting playlists after gigs is
    normal use. Our own writes DO maintain the XML (rb_write playlist_xml.add),
    so a genuine miss on our side shows up in tests, not in this log."""
    return "not found in masterPlaylists6.xml" not in record.getMessage()


def compose(data_dir=None):
    """Build the fully wired Starlette app; ``data_dir`` overrides the OS
    app-data location (tests), as does SYNCBOX_DATA_DIR (regression harness)."""
    if data_dir is None:
        data_dir = os.environ.get("SYNCBOX_DATA_DIR") or platform_os.app_data_dir()
    data_dir = Path(data_dir)
    log_path = data_dir / "logs" / "syncbox.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(
                log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            ),
            logging.StreamHandler(sys.stderr),
        ],
        force=True,  # deterministic wiring even if logging was already touched
    )
    logging.getLogger("pyrekordbox.db6.database").addFilter(_drop_playlist_xml_noise)
    conn = appdb.open_app_db(data_dir / "syncbox.db")
    settings = Settings(conn)
    secrets = SecretsStore(data_dir)
    auth = SpotifyAuth(lambda: settings.get("spotify_client_id"), secrets)
    deps = api.Deps(
        conn,
        spotify_auth=auth,
        spotify_client=SpotifyClient(auth),
        log_path=log_path,
    )
    return api.build_app(deps)


def main() -> int:
    app = compose()
    log.info("syncbox sidecar starting on http://%s:%s", server.HOST, server.PORT)
    try:
        asyncio.run(server.serve(app))
    except server.PortInUseError as exc:
        log.error("%s", exc)
        return 1
    log.info(
        "syncbox sidecar stopped (intentional=%s)", app.state.shutdown.intentional
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
