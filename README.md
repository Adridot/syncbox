# Syncbox

> DJ Playlist Sync for Rekordbox

Local desktop app foundation for synchronizing Spotify playlists with a Rekordbox library through a controlled review workflow.

The app is designed around these constraints:

- Rekordbox mutations are blocked while `rekordbox` or `rekordboxAgent` is running.
- Live imports can run while Rekordbox is open because they generate `.m3u8` files instead of editing `master.db`.
- Destructive sync operations are never automatic; they are stored as review proposals.
- Spotify auth uses OAuth PKCE and does not require a desktop-stored client secret.
- The local SQLite database keeps track mappings, event imports, tag rules, and pending proposals.
- Audio acquisition is intentionally limited to local file staging and legal provider adapters.

## Stack

- Electron + Vite + Vue for the desktop UI.
- FastAPI for the local service.
- SQLite for app state.
- `pyrekordbox` integration is isolated behind an adapter and is used for Rekordbox reads and closed-app writes.

## Development

```bash
npm install
cd service && uv sync --group dev
cd ..
npm run test
npm run dev
```

The renderer runs on `http://127.0.0.1:5173` in development. The local API runs on `http://127.0.0.1:8765`.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for the current app workflow.

## Reference Repositories

Reference repositories are downloaded into `.references/` and are not used as runtime sidecars.

```bash
scripts/download-reference-repos.sh
```

## Safety

The active Rekordbox database is expected at:

```text
/Users/adriendidot/Library/Pioneer/rekordbox/master.db
```

The service only reads status by default. Any future mutation path must call the Rekordbox safety guard and create a timestamped backup first.
