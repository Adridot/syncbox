# Syncbox

> **DJ Playlist Sync for Rekordbox** — a local desktop app that turns Spotify playlists into a clean, tagged Rekordbox collection, with controlled downloads and guarded writes to `master.db`.

Syncbox sits between three worlds — **Spotify** (where you discover and curate), **Deezer/Deemix** (where tracks are legally acquired as files), and **Rekordbox** (where you actually DJ) — and keeps them in sync through an explicit, reviewable workflow. Nothing destructive ever happens automatically.

---

## Table of contents

1. [Core principles](#core-principles)
2. [Architecture](#architecture)
3. [Key concepts](#key-concepts)
4. [The app, tab by tab](#the-app-tab-by-tab)
5. [End-to-end workflows](#end-to-end-workflows)
6. [Rekordbox integration & safety](#rekordbox-integration--safety)
7. [Maintenance: cleaning the collection](#maintenance-cleaning-the-collection)
8. [Settings](#settings)
9. [Development](#development)
10. [Data & file locations](#data--file-locations)

---

## Core principles

- **Rekordbox writes are guarded.** Any mutation of `master.db` is blocked while `rekordbox` or `rekordboxAgent` is running, and is always preceded by a timestamped backup.
- **No silent deletions.** Destructive sync operations are never automatic — they are surfaced as *review proposals* you accept or reject.
- **Soft-delete everywhere.** Removing a track from Rekordbox sets `rb_local_deleted` (reversible from a backup); audio files on disk are never touched by Syncbox.
- **Files are never moved by the app.** macOS TCC blocks the service from moving/reading files inside Dropbox/iCloud CloudStorage. Apply references downloaded files in place; consolidation into `rekordbox/Collection` is a separate script (`migrate_collection.py`).
- **Spotify auth is secret-less.** OAuth uses the PKCE flow — no client secret stored on disk.
- **Legal acquisition only.** Downloads go through the local Deemix API; Syncbox never scrapes audio itself.
- **Local-first.** All app state lives in a local SQLite database; there is no cloud backend.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Electron desktop shell (electron/main.ts)                │
│  • spawns the Python service                             │
│  • hosts the renderer, exposes a tiny preload bridge     │
└───────────────┬─────────────────────────┬───────────────┘
                │                          │
   ┌────────────▼───────────┐   ┌──────────▼─────────────────┐
   │ Renderer (Vue 3 + Pinia)│   │ Local service (FastAPI)     │
   │  src/renderer/          │◀─▶│  service/app/  :8765        │
   │  • views/ components/   │   │  • REST API                 │
   │  • stores/ (state)      │   │  • SQLite (app state)       │
   │  • lib/api.ts (client)  │   │  • adapters ↓               │
   └─────────────────────────┘   └──┬─────────┬──────────┬─────┘
                                    │         │          │
                          ┌─────────▼──┐ ┌────▼─────┐ ┌──▼──────────────┐
                          │ Spotify    │ │ Deezer / │ │ Rekordbox       │
                          │ Web API    │ │ Deemix   │ │ (pyrekordbox)   │
                          │ (OAuth)    │ │ :6595    │ │ master.db       │
                          └────────────┘ └──────────┘ └─────────────────┘
```

**Stack**
- **Desktop shell** — Electron + electron-vite.
- **UI** — Vue 3 (`<script setup>`), Pinia stores, Tailwind CSS, Lucide icons.
- **Service** — FastAPI (Python ≥3.12), run with `uv`. Lives in `service/app/`.
- **App state** — SQLite at `service/.local/syncbox.sqlite3`. Schema is created idempotently (`CREATE TABLE IF NOT EXISTS`) with a `schema_migrations` marker row and additive `ALTER TABLE` steps for later columns.
- **External** — Spotify Web API, Deezer public API (`https://api.deezer.com`) for search, Deemix local API (`http://127.0.0.1:6595`) for downloads, `pyrekordbox` for reading and (closed-app) writing `master.db`.

### Service modules (`service/app/`)

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app + all HTTP routes |
| `config.py` | Paths & ports (`RBSYNC_*` env overrides) |
| `db.py` | SQLite schema, migrations, all queries |
| `models.py` | Pydantic request/response models |
| `spotify.py` | OAuth PKCE + playlist/track fetching |
| `matching.py` / `sync.py` | Spotify↔Rekordbox matching & proposal generation |
| `acquisition.py` | Deezer search + Deemix download client/queue |
| `audio.py` | Locating downloaded files (Dropbox-safe `Path.exists()` matching) |
| `library.py` | Permanent-library sync flow |
| `event_import.py` / `live_import.py` | Event playlist import flows |
| `rekordbox.py` | `pyrekordbox` adapter: backup, tags, playlists, apply, delete |
| `maintenance.py` | Pure collection-cleanup classifier (see [Maintenance](#maintenance-cleaning-the-collection)) |
| `safety.py` | Detects running Rekordbox; blocks mutations |

---

## Key concepts

- **Library source** — a Spotify playlist you follow *permanently*. Its tracks should end up tagged in your Rekordbox collection and stay in sync over time.
- **Event import** — a one-off playlist (e.g. a wedding) imported temporarily. Tracks get an event MyTag and a smart playlist; the whole event can later be removed in one click.
- **MyTag** — Rekordbox's tagging system, organized as **categories → tags** (e.g. `Genre → Rap`, `Situation → Entrée mariés`). Syncbox reads and writes these.
- **Smart playlist** — a Rekordbox playlist auto-populated from a MyTag condition. Your genre/situation playlists (Rap, Valse, Latino…) are smart playlists driven by tags — this is the "clean" library structure Syncbox aims to maintain.
- **Proposal** — a stored, reviewable suggestion (`add_to_rekordbox`, `remove_from_rekordbox`, `manual_match`, `protect_manual_track`) generated by a sync. You decide whether to apply it.
- **Staging** — a downloaded/manual file is "staged" (associated to a track) before being applied to Rekordbox.

---

## The app, tab by tab

The sidebar (`AppShell.vue`) exposes five views (`ViewKey`):

- **Dashboard** — at-a-glance status: number of permanent playlists, event imports, pending sync proposals, active download jobs, and live health of the Local API / Rekordbox / Deemix.
- **My Library** — manage permanent Spotify sources. Analyze a source, review each track's status (new / matched / ready / imported / conflict / removed), search Deezer and queue downloads, ignore/restore tracks, and manage **tag rules** (which MyTags a source's tracks should get) and **tag → playlist mappings**.
- **Event Imports** — create a temporary event from a Spotify playlist, match its tracks to Rekordbox, stage files, apply the event (tag + smart playlist), and later delete the whole event safely.
- **Download & Match** — the cross-cutting acquisition center: see Deemix download jobs and resolve matches between downloads and the tracks that requested them.
- **Settings** — Spotify credentials, Rekordbox database directory, storage root, and the permanent / manual-collection folders (see [Settings](#settings)).

Both **My Library** and **Event Imports** share the same generic `TrackReviewTable` (filter tabs *Actionable / Ready / All*, 20-per-page pagination, ignore/restore) and the same `DeezerSearchPanel` (album cover thumbnails + 30-second audio preview with play/pause).

---

## End-to-end workflows

### A. Permanent library sync (My Library)
1. **Connect Spotify** (Settings → OAuth PKCE).
2. **Add a library source** (a Spotify playlist) and assign **tag rules** (the MyTags its tracks should carry).
3. **Analyze** → Syncbox matches each Spotify track against your Rekordbox collection (ISRC, then title/artist). Results become track reviews.
4. For missing tracks: **Search Deezer** in the side panel, preview, and **Download** via Deemix. Syncbox records the pending Deezer track up-front so the finished download links back to the right Spotify track even across rapid downloads.
5. Downloaded files are located on disk and the track flips to **ready**.
6. **Apply to Rekordbox** (Rekordbox closed): files are added/reactivated in `master.db` **in place** and tagged with the source's MyTags. Syncbox **never moves audio files** itself — macOS TCC blocks file operations on Dropbox/iCloud CloudStorage from the service process — so a track is referenced where it was downloaded. Consolidating files into the canonical `rekordbox/Collection` folder is a separate, explicit step (`service/scripts/migrate_collection.py`), not part of apply.
7. On later re-syncs, tracks removed from the Spotify playlist surface as `remove_from_rekordbox` **proposals** (never auto-applied). Tracks living in the protected manual collection generate `protect_manual_track` instead.

### B. Event import (Event Imports)
1. Create an event from a Spotify playlist; choose its **event tag** (category `Situation`).
2. Match / stage tracks (download or assign existing files).
3. **Apply** → each track gets the event MyTag; a `"<event> - Smart"` smart playlist is created under the **Event Imports** folder.
4. After the gig, **Delete event** → removes the event tag, the smart playlist, and any tracks that *only* had that event tag and aren't in a protected folder. Tracks with other tags or in the permanent/manual collection are kept.

### C. Live import
Generates `.m3u8` playlist files instead of editing `master.db`, so it can run **while Rekordbox is open**.

---

## Rekordbox integration & safety

- **Database** — `pyrekordbox.Rekordbox6Database` against `…/Pioneer/rekordbox/master.db`. Reads work anytime; writes require Rekordbox closed.
- **Mutation guard** — `safety.assert_rekordbox_can_mutate()` runs `pgrep` for `rekordbox`/`rekordboxAgent` and raises if found. Every write path calls it first.
- **Backups** — before any mutation, `RekordboxAdapter.backup_database()` copies `master.db` (+ `-wal`/`-shm`) into `…/_rekordbox_sync/backups/rekordbox-db-<timestamp>/`. The playlist XML (`masterPlaylists6.xml`) is backed up alongside destructive playlist edits.
- **Soft-delete** — deletions set `rb_local_deleted = 1` (+ sync flags). Fully reversible by restoring a backup. Audio files are never deleted.
- **Dropbox quirk** — directory *listing* fails on macOS CloudStorage paths (TCC), but `Path.exists()` on a *specific* path works; file-matching is built around this.

---

## Maintenance: cleaning the collection

`service/scripts/cleanup_rekordbox.py` prunes accumulated cruft from the Rekordbox collection — **untagged junk**, **untagged duplicates of already-tagged tracks**, and **redundant alternate versions** — while keeping unique, taggable music. It is **dry-run-first and manifest-driven**, so you always review before anything is written.

Classification logic lives in `service/app/maintenance.py` (pure & unit-tested):

| Category | Meaning | Default action |
|---|---|---|
| `junk` | SFX, speeches, built-in `rekordbox` samples, `spotify:track:` phantom rows | delete |
| `dup_of_tagged` | a tagged track already covers this song | delete |
| `alt_version` | extra version of a song; the cleanest "base" is kept | delete |
| `unique_mainstream` | unique, taggable track with no tagged equivalent | **keep** |

```bash
cd service

# 1. Inspect — writes .local/cleanup-manifest.csv, mutates nothing
uv run python3 scripts/cleanup_rekordbox.py --dry-run

# 2. (optional) Review/edit the CSV — flip any row's `action` between delete/keep

# 3. Apply — backs up, then soft-deletes rows still marked action=delete
#    (Rekordbox MUST be closed)
uv run python3 scripts/cleanup_rekordbox.py --apply .local/cleanup-manifest.csv
```

The apply step also removes the configured **event playlists** (defined in `EVENT_PLAYLIST_NAMES`) and writes a `cleanup-report-<timestamp>.json`. Deleting a playlist never deletes its tracks.

---

## Settings

Stored in SQLite and editable in the **Settings** tab (`GET`/`POST /api/settings`):

| Setting | Purpose |
|---|---|
| `spotifyClientId` / `spotifyRedirectUri` | OAuth PKCE |
| `rekordboxDatabaseDir` | folder containing `master.db` |
| `storageRoot` | base of the managed `_rekordbox_sync` storage tree |
| `permanentPath` | your **collection** folder — tracks here are protected from sync deletion |
| `manualCollectionPath` | your **manual collection** folder — also protected |

`permanentPath` / `manualCollectionPath` feed `RekordboxAdapter`'s **protected roots**: tracks inside them are never auto-deleted and instead generate `protect_manual_track` proposals.

---

## Development

```bash
npm install
cd service && uv sync --group dev && cd ..

npm run test        # backend pytest + frontend typecheck
npm run dev         # service + Electron together
```

Run the pieces individually:

```bash
npm run dev:service   # FastAPI on http://127.0.0.1:8765 (uv + uvicorn --reload)
npm run dev:renderer  # Vite renderer on http://127.0.0.1:5173 (browser dev)
npm run dev:desktop   # Electron shell
npm run typecheck     # vue-tsc + tsc
cd service && uv run --group dev pytest   # backend tests only
```

The renderer can be driven entirely in a browser at `:5173` (talking to the service at `:8765`), which is the easiest way to iterate and inspect with DevTools.

---

## Data & file locations

| What | Where |
|---|---|
| App database | `service/.local/syncbox.sqlite3` |
| Service logs | `service/.local/logs/` |
| Cleanup manifest / reports | `service/.local/cleanup-*.{csv,json}` |
| Rekordbox database | `~/Library/Pioneer/rekordbox/master.db` |
| Managed storage tree | `<storageRoot>/_rekordbox_sync/` (`inbox`, `events`, `backups`; legacy `permanent`/`manual_collection`) |
| Canonical collection | `<storageRoot>/rekordbox/Collection` (permanent) and `…/Collection manuelle` (manual) — where `permanentPath`/`manualCollectionPath` point after `migrate_collection.py` |

Paths can be overridden with env vars: `RBSYNC_DATA_DIR`, `RBSYNC_SERVICE_PORT`, `RBSYNC_REKORDBOX_DATABASE_DIR`, `RBSYNC_STORAGE_ROOT`.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for the current workflow notes.
