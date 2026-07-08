# sidecar — Python domain engine

All of Syncbox's domain logic lives here: Spotify sync, matching, events,
duplicates/missing/untagged, Smart Fixes, quality verdicts, Doctor. It is a
Starlette app served by uvicorn on `127.0.0.1:8765` (REST + one SSE job
stream), spawned and supervised by the Tauri shell.

- Entry point: [src/syncbox/__main__.py](src/syncbox/__main__.py) (composition
  root, `python -m syncbox`).
- Every `master.db` mutation goes through the unit-of-work in
  [src/syncbox/safety/](src/syncbox/safety/) — Rekordbox-closed guard,
  timestamped backup, freshness fingerprint, soft-delete discipline.
- Rekordbox writes: [src/syncbox/rb_write.py](src/syncbox/rb_write.py)
  (pyrekordbox; also maintains `masterPlaylists6.xml`).
- App DB migrations: plain SQL in
  [src/syncbox/migrations/](src/syncbox/migrations/), applied via
  `PRAGMA user_version`.

```sh
uv sync                                       # venv + deps (Python 3.14)
.venv/bin/python -m pytest -q                 # test suite
PYTHONPATH=src .venv/bin/python -m syncbox    # run standalone (dev)
.venv/bin/pyinstaller --noconfirm sidecar.spec  # freeze (onedir, M5)
```

Rekordbox-integration tests skip unless `poc/testdata/master.db` exists
(a real Rekordbox 7 database, not committed).
