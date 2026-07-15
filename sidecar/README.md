# sidecar — Python domain engine

All of Syncbox's domain logic lives here: Spotify sync, matching, events,
duplicates/missing/untagged, Smart Fixes, quality verdicts, Doctor. It is a
Starlette app served by uvicorn on `127.0.0.1:8766` (REST + one SSE job
stream), spawned and supervised by the Tauri shell. Spotify PKCE uses a
separate access-log-free listener on the exact
`http://127.0.0.1:8765/callback`; it exists only during an authorization
attempt and closes after a terminal response, timeout, disconnect, or process
shutdown.

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
uv lock --check
uv sync --locked --managed-python             # exact Python 3.14.2 environment
uv run --locked --managed-python pytest -q -rs
PYTHONPATH=src uv run --locked --managed-python python -m syncbox
uv run --locked --managed-python pyinstaller --noconfirm --clean sidecar.spec
```

`.python-version` selects Python 3.14.2 and `uv.lock` records the complete
runtime and development dependency graph. The PyInstaller spec emits an arm64
onedir at `dist/syncbox-sidecar/`. Validate the frozen native dependency set
without creating application data:

```sh
dist/syncbox-sidecar/syncbox-sidecar --packaging-check
```

That check imports the packaged CA bundle, audio/native stack, Rekordbox
reader, Trash integration, and the local SQLCipher CommonCrypto extension,
then opens an in-memory encrypted database and reports the provider/status.
The release scanner in `poc/run_phase6_packaging.py`
performs the complementary app-tree, lock, license, architecture, signature,
secret, and archive checks.

Rekordbox-integration tests skip unless `poc/testdata/master.db` exists
(a real Rekordbox 7 database, not committed).
