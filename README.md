# Syncbox

> **DJ Playlist Sync for Rekordbox** — a local desktop app that turns Spotify playlists into a clean, tagged Rekordbox collection, with controlled downloads and guarded writes to `master.db`.

Syncbox sits between three worlds — **Spotify** (where you discover and curate), **Deezer/Deemix** (where tracks are legally acquired as files), and **Rekordbox** (where you actually DJ) — and keeps them in sync through an explicit, reviewable workflow. Nothing destructive ever happens automatically.

---

## Table of contents

1. [Install](#install)
2. [Core principles](#core-principles)
3. [Architecture](#architecture)
4. [Key concepts](#key-concepts)
5. [The app, tab by tab](#the-app-tab-by-tab)
6. [End-to-end workflows](#end-to-end-workflows)
7. [Collection hygiene: duplicates & missing files](#collection-hygiene-duplicates--missing-files)
8. [Rekordbox integration & safety](#rekordbox-integration--safety)
9. [Deemix downloader](#deemix-downloader)
10. [Settings, backup & restore](#settings-backup--restore)
11. [Maintenance script](#maintenance-script)
12. [Development](#development)
13. [Data & file locations](#data--file-locations)

---

## Install

Download the latest `Syncbox-<version>-arm64.dmg` from the
[**Releases**](https://github.com/Adridot/syncbox/releases) page, open it, and drag
**Syncbox** into Applications.

> The build is **unsigned / un-notarized**. On first launch macOS Gatekeeper will
> block it — **right-click → Open** once (or run
> `xattr -dr com.apple.quarantine "/Applications/Syncbox.app"`).

Syncbox needs two things to do its job:

- **Spotify** — connect once in Settings (OAuth PKCE, no secret stored).
- **Deemix Remastered** — the downloader Syncbox drives over its local API. Syncbox
  can **install and launch it for you** from Settings → *Deemix downloader* (see
  [below](#deemix-downloader)).

---

## Core principles

- **Rekordbox writes are guarded.** Any mutation of `master.db` is blocked while `rekordbox` or `rekordboxAgent` is running, and is always preceded by a timestamped backup.
- **No silent deletions.** Destructive sync operations are never automatic — they are surfaced as *review proposals* you accept or reject.
- **Soft-delete everywhere.** Removing a track from Rekordbox sets `rb_local_deleted` (reversible from a backup); audio files on disk are only ever deleted when you explicitly opt in (e.g. an event folder, or an unprotected duplicate copy).
- **Files are never moved by the app.** macOS TCC blocks the service from moving/reading files inside Dropbox/iCloud CloudStorage. Apply references downloaded files in place; consolidation into `rekordbox/Collection` is a separate script (`migrate_collection.py`).
- **Spotify auth is secret-less.** OAuth uses the PKCE flow — no client secret stored on disk.
- **Legal acquisition only.** Downloads go through the local Deemix API; Syncbox never scrapes audio itself.
- **Local-first.** All app state lives in a local SQLite database; there is no cloud backend.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Electron desktop shell (electron/)                       │
│  • spawns the bundled Python service                     │
│  • auto-launches / installs Deemix Remastered            │
│  • hosts the renderer, exposes a tiny preload bridge     │
└───────────────┬─────────────────────────┬───────────────┘
                │                          │
   ┌────────────▼───────────┐   ┌──────────▼─────────────────┐
   │ Renderer (Vue 3 + Pinia)│   │ Local service (FastAPI)     │
   │  src/renderer/          │◀─▶│  service/app/  :8765        │
   │  • views/ components/   │   │  • REST API + SSE stream    │
   │  • stores/ (state)      │   │  • SQLite (app state)       │
   │  • lib/api/ (client)    │   │  • rekordbox/ adapter ↓     │
   └─────────────────────────┘   └──┬─────────┬──────────┬─────┘
                                    │         │          │
                          ┌─────────▼──┐ ┌────▼─────┐ ┌──▼──────────────┐
                          │ Spotify    │ │ Deezer / │ │ Rekordbox       │
                          │ Web API    │ │ Deemix   │ │ (pyrekordbox)   │
                          │ (OAuth)    │ │ :6595    │ │ master.db       │
                          └────────────┘ └──────────┘ └─────────────────┘
```

**Stack**
- **Desktop shell** — Electron + electron-vite (`electron/main.ts`, `preload.ts`, `deemix.ts`).
- **UI** — Vue 3 (`<script setup>`), Pinia stores, Tailwind CSS, Lucide icons. Secondary views are lazy-loaded (code-split).
- **Service** — FastAPI (Python ≥3.12), run with `uv` in dev and bundled as a standalone PyInstaller binary in the packaged app.
- **App state** — SQLite. Dev: `service/.local/syncbox.sqlite3`; packaged: `~/Library/Application Support/Syncbox/syncbox.sqlite3`. Schema is created idempotently with a `schema_migrations` marker + additive `ALTER TABLE` steps.
- **External** — Spotify Web API, Deezer public API for search, Deemix Remastered local API (`http://127.0.0.1:6595`) for downloads, `pyrekordbox` for reading and (closed-app) writing `master.db`.

### Service modules (`service/app/`)

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app + all HTTP routes (incl. the SSE job stream) |
| `config.py` / `version.py` / `logging_setup.py` | Paths & ports, single-source version, rotating file logging |
| `db.py` + `repositories/` | SQLite facade composed of per-context repository mixins (settings, tags, library, acquisition, events, proposals, dedup) |
| `models.py` | Pydantic request/response models |
| `spotify.py` | OAuth PKCE + playlist/track fetching (HTTPS-failure tolerant) |
| `matching.py` / `sync.py` | Spotify↔Rekordbox matching & proposal generation |
| `acquisition.py` | Deezer search + Deemix download client/queue |
| `collection_acquisition.py` | Missing-file re-download as a first-class acquisition job |
| `dedup.py` | Pure duplicate detection (ISRC + fuzzy) + keeper scoring |
| `diagnostics.py` | Doctor health checks |
| `audio.py` | Locating downloaded files (Dropbox-safe `Path.exists()` matching) |
| `library.py` / `event_import.py` / `live_import.py` | Permanent-library + event import flows |
| `rekordbox/` | `pyrekordbox` adapter package: `adapter.py` (backup, tags, apply, delete, dedup, missing, `_mutate()` unit-of-work), `content.py`, `paths.py` |
| `maintenance.py` | Pure collection-cleanup classifier (see [Maintenance](#maintenance-script)) |
| `safety.py` | Detects running Rekordbox; blocks mutations |

The whole Rekordbox collection is read **once** into a single enriched snapshot, cached on the `master.db` mtime, and reused by the library view, collection stats, duplicate detection and missing-file detection.

---

## Key concepts

- **Library source** — a Spotify playlist you follow *permanently*. Its tracks should end up tagged in your Rekordbox collection and stay in sync over time.
- **Event import** — a one-off playlist (e.g. a wedding) imported temporarily. Tracks get an event MyTag and a smart playlist; the whole event can later be removed in one click.
- **MyTag** — Rekordbox's tagging system, organized as **categories → tags** (e.g. `Genre → Rap`, `Situation → Entrée mariés`). Syncbox reads and writes these.
- **Smart playlist** — a Rekordbox playlist auto-populated from a MyTag condition. Your genre/situation playlists are smart playlists driven by tags — the "clean" library structure Syncbox maintains.
- **Proposal** — a stored, reviewable suggestion (`add_to_rekordbox`, `remove_from_rekordbox`, `manual_match`, `protect_manual_track`) generated by a sync. You decide whether to apply it.
- **Staging** — a downloaded/manual file is "staged" (associated to a track) before being applied to Rekordbox.
- **Acquisition job** — a download tracked through `resolved → queued → downloading → downloaded → ready`. Jobs come in three **scopes** — `event`, `library`, and `collection` (missing-file re-downloads) — and all surface in **Download & Match** and the live SSE stream.
- **Duplicate group** — two or more collection entries detected as the same recording (shared ISRC) or near-identical metadata, with one auto-chosen *keeper*.
- **Missing file** — a collection entry whose audio file no longer exists on disk (Rekordbox would mark it with a `!`).

---

## The app, tab by tab

The sidebar (`AppShell.vue`) exposes these views (`ViewKey`):

- **Dashboard** — at-a-glance status: permanent playlists, event imports, pending proposals, active download jobs, and live health of the Local API / Rekordbox / Deemix.
- **My Library** — manage permanent Spotify sources: analyze, review each track (new / matched / ready / imported / conflict / removed), search Deezer + queue downloads, ignore/restore, and manage **tag rules** and **tag → playlist mappings**.
- **Events** — create a temporary event from a Spotify playlist, match/stage tracks, apply (tag + smart playlist), and later delete the whole event safely (optionally deleting its audio folder).
- **Download & Match** — the cross-cutting acquisition center: every download job (event / library / collection) with live progress, plus match resolution between downloads and the tracks that requested them.
- **Duplicates** — scan the collection for duplicate tracks Rekordbox's native tool misses, pick a keeper, and resolve (see [below](#collection-hygiene-duplicates--missing-files)).
- **Missing Files** — find collection entries whose audio is gone, and re-download / re-link / remove them per track.
- **Doctor** — diagnostics (Rekordbox DB, storage, disk space, Deemix, Spotify, backups), restore from a Rekordbox backup, clean up old backups, and open the logs folder.
- **Settings** — Spotify, paths, Deemix provisioning, backup & restore (see [below](#settings-backup--restore)).

Both **My Library** and **Events** share the generic `TrackReviewTable` (filter tabs, pagination, ignore/restore) and the `DeezerSearchPanel` (album covers + 30-second preview).

---

## End-to-end workflows

### A. Permanent library sync (My Library)
1. **Connect Spotify** (Settings → OAuth PKCE).
2. **Add a library source** and assign **tag rules** (the MyTags its tracks should carry).
3. **Analyze** → Syncbox matches each Spotify track against your Rekordbox collection (ISRC, then title/artist).
4. For missing tracks: **Search Deezer**, preview, and **Download** via Deemix. The pending Deezer track is recorded up-front so the finished download links back to the right Spotify track.
5. Downloaded files are located on disk and the track flips to **ready**.
6. **Apply to Rekordbox** (Rekordbox closed): files are added/reactivated in `master.db` **in place** and tagged. Syncbox **never moves audio** itself; consolidating into the canonical `rekordbox/Collection` is a separate step (`service/scripts/migrate_collection.py`).
7. On later re-syncs, tracks removed from the Spotify playlist surface as `remove_from_rekordbox` **proposals**; protected-collection tracks generate `protect_manual_track` instead.

### B. Event import (Events)
1. Create an event from a Spotify playlist; choose its **event tag** (category `Situation`).
2. Match / stage tracks (download or assign existing files).
3. **Apply** → each track gets the event MyTag; a smart playlist is created under the **Event Imports** folder.
4. After the gig, **Delete event** → removes the event tag, the smart playlist, and any tracks that *only* had that event tag and aren't protected. The event's on-disk folder (and its audio) is deleted; permanent/manual files are always kept.

### C. Live import
Generates `.m3u8` playlist files instead of editing `master.db`, so it can run **while Rekordbox is open**.

---

## Collection hygiene: duplicates & missing files

### Duplicates
Rekordbox's "Display Duplicated Tracks" only matches identical `Title + Artist` text. Syncbox's **Duplicates** view does better:

- **ISRC** match (same recording — the signal Rekordbox ignores) and **fuzzy** match (normalized title/artist similarity + compatible durations).
- ISRC groups whose **titles disagree** (mis-tagged/bootleg ISRCs) are downgraded, flagged, and excluded from the one-click bulk action.
- A **keeper** is auto-chosen per group by quality (format, bitrate, sample depth, file size) and work already done (analysis, cue points, playlist memberships, tags, protected/permanent location, file-exists). You can override it.
- **Resolve** soft-deletes the other copies, **re-links their playlist & MyTag memberships onto the keeper** (so nothing drops out of a playlist), and — only if you opt in and the file is *not* under a protected root — deletes the loser's file on disk. **Dismiss** marks a group "not a duplicate" so it never resurfaces. Every action backs up the DB first.

### Missing files
The **Missing Files** view lists collection entries whose audio is gone (Rekordbox's "Display All Missing Files", but actionable). Per track you can:

- **Re-download** — resolves the track on Deezer (ISRC first) and queues a **real acquisition job** (visible in Download & Match) that downloads into your permanent folder and **re-links the existing entry** onto it — keeping its cues/tags/playlists — when Rekordbox is closed.
- **Re-link** — find a moved/renamed file already on disk (matched by ISRC or title) and point the entry at it.
- **Remove** — soft-delete an orphaned entry (e.g. junk `spotify:track:` stubs).

---

## Rekordbox integration & safety

- **Database** — `pyrekordbox.Rekordbox6Database` against `…/Pioneer/rekordbox/master.db`. Reads work anytime; writes require Rekordbox closed.
- **Mutation guard** — `safety.assert_rekordbox_can_mutate()` runs `pgrep` for `rekordbox`/`rekordboxAgent` and raises if found. Every write path calls it first.
- **Unit of work** — all mutations go through `RekordboxAdapter._mutate()`: it asserts it's safe, snapshots a **backup**, opens the DB, commits (or rolls back) and invalidates the snapshot cache.
- **Backups & rotation** — before any mutation, `master.db` (+ `-wal`/`-shm`) is copied into `…/_rekordbox_sync/backups/rekordbox-db-<timestamp>/`. Backups are **rotated** to the newest *N* (default 15, configurable; `0` = unlimited) and can be pruned/restored from the **Doctor** page.
- **Soft-delete** — deletions set `rb_local_deleted = 1`. Fully reversible by restoring a backup.
- **Dropbox quirk** — directory *listing* fails on macOS CloudStorage paths (TCC), but `Path.exists()` on a *specific* path works; file-matching is built around this.

---

## Deemix downloader

Syncbox downloads audio through **[Deemix Remastered](https://github.com/DRAZY/deemix-remastered)**, which serves a local API on port `6595`. Syncbox manages it for you (Settings → *Deemix downloader*):

- **Auto-launch** — on startup, if Deemix Remastered is installed but not running, Syncbox launches it **in the background** so its API is ready. You never have to start it by hand.
- **One-click install** — if it isn't installed, *Install Deemix* downloads the latest release `.dmg` from GitHub (arch-aware), mounts it, copies the app into `~/Applications`, and launches it.

The card shows **Running / Installed / Not installed**. You still paste your Deezer **ARL** into Deemix itself the first time.

> Deemix Remastered is GPL-3.0 and distributed separately; Syncbox launches/installs it, it does not bundle it.

---

## Settings, backup & restore

Settings live in SQLite (`GET`/`POST /api/settings`) and survive app updates (they're in `Application Support`, never overwritten by a reinstall).

| Setting | Purpose |
|---|---|
| `spotifyClientId` / `spotifyRedirectUri` | OAuth PKCE |
| `rekordboxDatabaseDir` | folder containing `master.db` |
| `storageRoot` | base of the managed `_rekordbox_sync` storage tree |
| `permanentPath` | your **collection** folder — protected from sync deletion |
| `manualCollectionPath` | your **manual collection** folder — also protected |
| `backupRetention` | how many Rekordbox backups to keep (rotation; `0` = unlimited) |

The managed storage folders are created automatically on save (and lazily on the first download) — the *Storage locations* panel just shows where things land.

**Backup & Restore** (Settings) makes your config portable — for a clean reinstall or a new Mac:

- **Settings only** — a small JSON file with paths, Spotify client id **+ tokens**, and retention (transient OAuth handshake values are excluded).
- **All data** — a consistent single-file copy of the whole app database (sources, events, tag rules, mappings + settings) via `VACUUM INTO`. Restore validates the file and snapshots a safety backup of the current data first.

> The **Local API port** is **not** a setting: Electron picks the service port at launch and passes it to the service.

---

## Maintenance script

`service/scripts/cleanup_rekordbox.py` prunes accumulated cruft — **untagged junk**, **untagged duplicates of already-tagged tracks**, and **redundant alternate versions** — while keeping unique, taggable music. It is **dry-run-first and manifest-driven**.

Classification logic lives in `service/app/maintenance.py` (pure & unit-tested):

| Category | Meaning | Default action |
|---|---|---|
| `junk` | SFX, speeches, built-in `rekordbox` samples, `spotify:track:` phantom rows | delete |
| `dup_of_tagged` | a tagged track already covers this song | delete |
| `alt_version` | extra version of a song; the cleanest "base" is kept | delete |
| `unique_mainstream` | unique, taggable track with no tagged equivalent | **keep** |

```bash
cd service
uv run python3 scripts/cleanup_rekordbox.py --dry-run                       # inspect → .local/cleanup-manifest.csv
# (optionally edit the CSV: flip any row's action between delete/keep)
uv run python3 scripts/cleanup_rekordbox.py --apply .local/cleanup-manifest.csv  # Rekordbox MUST be closed
```

> The **Duplicates** view (above) is the interactive, per-track equivalent for everyday dedup; this script is for a bigger one-shot sweep.

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

> Building the packaged app requires **Node ≥ 20** (the bundler uses `crypto.hash`).

Packaging (see [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)):

```bash
npm run dist          # release/mac-arm64/Syncbox.app   (unsigned, fast)
npm run dist:dmg      # release/Syncbox-<version>-arm64.dmg
```

---

## Data & file locations

| What | Dev | Packaged app |
|---|---|---|
| App database | `service/.local/syncbox.sqlite3` | `~/Library/Application Support/Syncbox/syncbox.sqlite3` |
| Service logs | `service/.local/logs/` | `~/Library/Logs/Syncbox/` (Help → Open Logs) |
| Rekordbox database | `~/Library/Pioneer/rekordbox/master.db` | same |
| Managed storage tree | `<storageRoot>/_rekordbox_sync/` (`inbox`, `events`, `backups`) | same |
| Canonical collection | `<storageRoot>/rekordbox/Collection` (+ `Collection manuelle`) — where `permanentPath`/`manualCollectionPath` point after `migrate_collection.py` | same |

Paths can be overridden with env vars: `RBSYNC_DATA_DIR`, `RBSYNC_SERVICE_PORT`, `RBSYNC_REKORDBOX_DATABASE_DIR`, `RBSYNC_STORAGE_ROOT`, `RBSYNC_LOG_DIR`.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for the day-to-day workflow and
[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for building, signing & auto-update.
