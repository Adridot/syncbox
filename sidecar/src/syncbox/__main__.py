"""Sidecar entrypoint (``python -m syncbox``) - the composition root.

Wires, exactly once, what the tests assemble by hand: app data dir ->
migrated app DB -> encrypted secrets store -> Spotify PKCE auth + client ->
api.Deps -> Starlette app -> permanent uvicorn API/SSE on 127.0.0.1:8766.
Spotify authorization temporarily opens its exact 127.0.0.1:8765 callback.
Logging goes to a rotating file in the app data dir (feeds GET
/api/doctor/logs) and to stderr for the shell supervisor, which always
consumes child output (6.6).
"""

import asyncio
import contextlib
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from syncbox import api, appdb, platform_os, quality, server
from syncbox.safety import backup as safety_backup
from syncbox.secrets import SecretsStore
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


def compose(data_dir=None, *, oauth_listener=None):
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
    db_file = data_dir / "syncbox.db"
    # A restore interrupted by a crash left a durable journal: finish or roll
    # back the whole Rekordbox + Syncbox pair BEFORE opening the app DB, so
    # the API never runs on a half-restored state.
    recovered = safety_backup.recover_restore(data_dir)
    if recovered:
        log.warning("interrupted backup restore was %s at startup", recovered)
    conn = appdb.open_app_db(db_file)
    secrets = SecretsStore(data_dir)
    deps = api.Deps(
        conn,
        log_path=log_path,
        app_db_path=db_file,
        data_dir=data_dir,
        secrets=secrets,
        oauth_listener=oauth_listener or server.OAuthCallbackListener(),
    )
    # The auth reads the client id THROUGH deps.settings, never a captured
    # Settings: the all-data import (5.10) swaps deps.conn/settings live.
    auth = SpotifyAuth(lambda: deps.settings.get("spotify_client_id"), secrets)
    deps.spotify_auth = auth
    deps.spotify_client = SpotifyClient(auth)
    app = api.build_app(deps)
    app.state.secrets = secrets  # closed on exit (6.6 handshake tail)
    return app


def _quality_analyze(path: str) -> int:
    """Print one read-only A3 result without composing the application."""
    result = quality.analyze(path)
    print(
        json.dumps(
            {
                "verdict": result.verdict,
                "cutoff_hz": result.cutoff_hz,
                "reason": result.reason,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _packaging_check() -> int:
    """Exercise packaged native/runtime dependencies without app data."""
    import importlib.metadata
    import importlib.util

    import certifi
    import miniaudio
    import numpy
    import pyrekordbox
    import send2trash
    import sqlcipher3

    conn = sqlcipher3.connect(":memory:")
    try:
        conn.execute("PRAGMA key = \"x'" + "00" * 32 + "'\"")
        conn.execute("CREATE TABLE packaging_check (value TEXT)")
        cipher_version = conn.execute("PRAGMA cipher_version").fetchone()[0]
        cipher_provider = conn.execute("PRAGMA cipher_provider").fetchone()[0]
        cipher_provider_version = conn.execute(
            "PRAGMA cipher_provider_version"
        ).fetchone()[0]
        cipher_status = conn.execute("PRAGMA cipher_status").fetchone()[0]
    finally:
        conn.close()
    ca_file = Path(certifi.where())
    if not ca_file.is_file():
        raise RuntimeError("certifi CA bundle is missing")
    packages = {
        name: importlib.metadata.version(name)
        for name in (
            "certifi",
            "miniaudio",
            "numpy",
            "pyrekordbox",
            "send2trash",
            "sqlcipher3-wheels",
        )
    }
    # Keep imports live: PyInstaller must collect each dependency above.
    assert miniaudio and numpy and pyrekordbox and send2trash
    print(
        json.dumps(
            {
                "ok": True,
                "architecture": os.uname().machine,
                "packages": packages,
                "sqlcipher": cipher_version,
                "sqlcipher_provider": cipher_provider,
                "sqlcipher_provider_version": cipher_provider_version,
                "sqlcipher_status": cipher_status,
                "api_port": server.PORT,
                "oauth_callback_port": server.OAUTH_CALLBACK_PORT,
                "streamrip_importable": importlib.util.find_spec("streamrip")
                is not None,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--legacy-metadata-backfill":
        from syncbox.legacy_metadata_backfill import main as backfill_main

        return backfill_main(argv[1:])
    if argv and argv[0] == "--quality-analyze":
        if len(argv) != 2:
            print("usage: syncbox-sidecar --quality-analyze PATH", file=sys.stderr)
            return 2
        return _quality_analyze(argv[1])
    if argv and argv[0] == "--packaging-check":
        if len(argv) != 1:
            print("usage: syncbox-sidecar --packaging-check", file=sys.stderr)
            return 2
        return _packaging_check()

    app = compose()
    # Single-instance ownership FIRST: the exclusive port bind is the lock.
    # Only after it is held may interrupted jobs be requeued and the worker
    # started — a second sidecar must fail here without touching the first
    # instance's live queue.
    try:
        api_socket = server.bind_api_socket()
    except server.PortInUseError as exc:
        log.error("%s", exc)
        app.state.secrets.close()
        app.state.deps.conn.close()
        return 1
    app.state.deps.acquisition_worker = api.AcquisitionWorker(app.state.deps)
    app.state.deps.acquisition_worker.start()
    log.info("syncbox sidecar starting on http://%s:%s", server.HOST, server.PORT)
    try:
        asyncio.run(server.serve(app, sockets=[api_socket]))
    finally:
        with contextlib.suppress(OSError):
            api_socket.close()
        worker_stopped = (
            app.state.deps.acquisition_worker is None
            or app.state.deps.acquisition_worker.stop()
        )
        app.state.deps.oauth_listener.stop()
        app.state.deps.oauth_listener.wait_closed()
        # 6.6 handshake tail: SQLCipher secrets store and app DB closed
        # before the process exits, so a clean stop never needs the shell's
        # kill of last resort to reclaim them.
        if worker_stopped:
            app.state.secrets.close()
            app.state.deps.conn.close()
        else:
            log.warning(
                "acquisition worker is still stopping; process exit will close its resources"
            )
    log.info("syncbox sidecar stopped (intentional=%s)", app.state.shutdown.intentional)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
