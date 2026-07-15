# Syncbox — Functional & Technical Specification (Phase 1/2)

> **Historical input only.** This document records the legacy Electron/Deemix
> implementation that was audited before the rewrite. It is not a statement of
> current release behavior. [SPEC-UNIFIED.md](SPEC-UNIFIED.md) and
> [DISTRIBUTION.md](DISTRIBUTION.md) are authoritative for the macOS v1 candidate.

> **Purpose.** Exhaustive reverse engineering of the **Syncbox** application for a rewrite that is *functionally identical, without inherited defects*. This document describes what the app **does** (observable), separates the **intentional** from **bugs/debt**, and records the **keep/remove/change decisions** validated with the owner. It is the input for Phase 2 (architecture & development approach — separate prompt).
>
> **Method.** Read-only review of the full codebase (Vue renderer, Electron main, Python service, test suite, docs). Every assertion points to evidence `file:line`. Detailed evidence by slice lives in `docs/_analysis/` (16 files, one per subsystem).
>
> **Registers** — to avoid any confusion, three registers are distinguished throughout:
> - *MUST* / *DOES* = observable behavior today;
> - `[intentional]` vs `[bug]`/`[debt]` = nature of the behavior;
> - **Decision Dx** = what is wanted in the rewrite (see §7).

---

## 0. Repository Map & Stack (P0)

**Three layers**, one Electron process orchestrating everything:

| Layer | Location | Role | Lines |
|---|---|---|---|
| Renderer (UI) | `src/renderer/` | Vue 3 `<script setup>` + Pinia + TanStack vue-query + Tailwind 4 + vue-i18n | ~8,900 |
| Electron main | `electron/` | Python service spawn, IPC bridge `window.desktop.*`, Deemix management, window | ~640 |
| Service | `service/app/` | FastAPI/uvicorn (Python ≥3.12), Rekordbox access via pyrekordbox, app SQLite | ~11,300 |
| Tests | `service/tests/` | pytest — **reference behavior contract** | ~4,500 |

**Entry points**: renderer `src/renderer/main.ts`; main `electron/main.ts`; service `service/run_service.py` → `app.main:app`.

**Build** (`package.json:9-22`): `electron-vite` (renderer+main+preload) + `PyInstaller --onedir` (service → standalone binary) + `electron-builder` (macOS DMG). The Python binary is embedded in `extraResources`, the seed DB copied on first launch.

**Essential external dependencies** (all driven locally):
- **pyrekordbox** (+ `sqlcipher3`) — read/write `master.db` (SQLCipher).
- **mutagen** — read/write audio tags.
- **rapidfuzz** — title/artist similarity (replaced `difflib`, cf. git `perf/phase-1-rapidfuzz`).
- **httpx** (+ `certifi`) — Spotify Web API, Deezer public API, local Deemix API.
- **Deemix Remastered** — external third-party app, local API `http://127.0.0.1:6595` (Deezer downloads via ARL). *Is not* a Python package; driven over HTTP (`README.md:206`).
- **Spotify Web API** — OAuth + playlist reading.

**Repository state**: `version 0.2.0` (`package.json:3`), but `service/pyproject.toml:3` = `0.1.0` (skew, cf. D-tech). Build **unsigned / unnotarized** (Gatekeeper blocks on first launch). electron-updater auto-update **present but dormant** (`publish:null`, `RBSYNC_ENABLE_UPDATES` required — `DISTRIBUTION.md:119-126`).

---

## 1. Executive Summary

Syncbox is a macOS desktop app (eventually **macOS + Windows**, cf. §7-D2) that maintains a DJ’s **Rekordbox** collection by synchronizing **Spotify playlists**, **downloading** missing tracks via **Deezer/Deemix**, and **maintaining the collection** (duplicates, missing files, tags). The guiding principle is **safety**: no write to `master.db` while Rekordbox is running, a **timestamped backup before every mutation**, **reversible** deletions (soft-delete + restore), and **files are never moved** (macOS TCC constraint on cloud folders).

The app exposes ~9 screens (Dashboard, My Library, Events, Download & Match, Duplicates, Missing Files, Untagged, Doctor, Settings) driven by Pinia state (no router). The Python service exposes **~70 REST endpoints** + **one SSE stream** for download progress. Application state (tracked sources, events, jobs, settings, tokens) lives in **SQLite**; Rekordbox is read **once** as an enriched snapshot, cached on the mtime of `master.db`.

The code was built through successive prompts: it works but carries characteristic debt — an **unfinished vue-query migration** (double data layer), a **configuration file hard-coded to the developer’s machine**, cleanup heuristics **customized to a French collection**, a contradictory **double Spotify authentication stack**, and **fragile reconstruction of the downloaded filename** (chronic source of “download stuck” bugs). The business core (Rekordbox safety, ISRC/fuzzy matching, dedup, soft-delete, path resolution) is nevertheless solid and **covered by a test suite** that constitutes the reference contract.

---

## 2. Functional Inventory (feature × screen × state × location)

State: **OK** = complete · **½** = half-finished / partially wired · **†** = dead/unused in its context.

### 2.1 Shell, Navigation, Dashboard
| Feature | Location | State |
|---|---|---|
| 9-screen navigation without router (`ui.activeView` state) | `stores/ui.ts:20,30-32`, `App.vue:58-66` | OK (Settings = catch-all `v-else`, cf. bug) |
| Lazy-loading of secondary views | `App.vue:8-17` | OK |
| Toasts (success/info/error, auto-dismiss 4/5/8 s) | `stores/ui.ts:13-46`, `ToastCenter.vue` | OK |
| Global error wrapper `withErrorToast`/`withLoading` | `stores/ui.ts:57-88` | OK (defects, cf. §5) |
| Dashboard: 4 cards + collection health + system status + recent events | `views/DashboardView.vue:84-272` | OK |
| Sidebar health banner (API/Rekordbox/Deemix + downloads chip) | `components/AppShell.vue:98-159` | OK |
| FR/EN i18n (OS detection, localStorage persistence) | `i18n/index.ts:21-63` | OK |

### 2.2 My Library (Permanent Spotify Sources)
| Feature | Location | State |
|---|---|---|
| Master/detail of tracked sources | `views/LibraryView.vue:120-358`, `stores/library.ts` | OK |
| Follow a playlist (Manage modal) + default MyTags | `components/LibrarySetupModal.vue`, `stores/library.ts:141-166` | OK |
| Remove a tracked source (RB tracks/tags preserved) | `stores/library.ts:117-136` | OK |
| Sync source / Sync all + auto-download missing tracks | `stores/library.ts:86-115,228-241` | OK |
| Review table (statuses new/matched/ready/imported/conflict/removed) | `components/TrackReviewTable.vue` | OK |
| Actionable/ready/all filters, virtualization | `TrackReviewTable.vue:27,81-82` | OK |
| Deezer search → download queue (per track) | `stores/library.ts:286-326` | OK |
| Ignore/restore track | `stores/library.ts:328-356` | OK (restore→"new", bug) |
| Bulk tag editing (bottom bar) | `LibraryView.vue:288-336` | OK (union semantics, bug) |
| Import to Rekordbox (gated RB closed) | `stores/library.ts:243-263` | OK |
| Accept-match / Assign-staged-file (table) | `TrackReviewTable.vue:278-296` | † in Library context (events-only) |
| “tag rules” concept (separate table + repo) | `stores/library.ts:23,56-60,272-284`; `repositories/tags.py` | ½/† (vestigial → **D9 REMOVE**) |

### 2.3 Events (Temporary DJ Sets)
| Feature | Location | State |
|---|---|---|
| Creation, 3 modes: from Spotify playlist / empty / by link | `components/EventCreatePanel.vue`, `stores/events.ts:128-221` | OK |
| Add-track inside the open event | `EventWorkspace.vue:51-72` | OK |
| Metrics (matched/ready/applied/missing/ambiguous) | `EventWorkspace.vue:141-152` | OK |
| Scan staging folder | `stores/events.ts:240-257` | OK |
| Download Missing (manual retry) | `stores/events.ts:293-304` | OK |
| Apply Ready Tracks (gated RB closed) | `stores/events.ts:306-324` | OK |
| Delete event (preview + protected preserved) | `stores/events.ts:326-355` | OK (no RB guard, bug) |
| Deezer search + audio preview + queue | `components/DeezerSearchPanel.vue`, `stores/events.ts:412-450` | OK |
| **Live Import (M3U8)** — playlist without DB write | `views/EventsView.vue:66-125`, `live_import.py` | OK → **D10 REMOVE** |

### 2.4 Collection Hygiene
| Feature | Location | State |
|---|---|---|
| Duplicates: ISRC/fuzzy scan + similarity slider | `views/DuplicatesView.vue`, `queries/useDuplicates.ts`, `dedup.py` | OK |
| Auto keeper + override + resolution (relink memberships) | `dedup.py:161-172`, `adapter.py:1197-1279` | OK → **D5/D6 CHANGE** |
| Bulk auto-resolve of ISRC groups ≥99% | `useDuplicates.ts:185-202` | OK → **D5 REMOVE (bulk)** |
| “Not a duplicate” (persistent dismiss) | `dedup.py`, `repositories/dedup.py` | OK |
| Missing Files: scan + re-download (ISRC/search) + re-link + remove | `views/MissingFilesView.vue`, `maintenance.py`, `collection_acquisition.py` | OK |
| Untagged: 4-category diagnostic + bulk tag/remove | `views/UntaggedView.vue`, `adapter.untagged_report`, `maintenance.py` | OK → **D7 KEEP-BUT-FIX** |
| CLI script `cleanup_rekordbox.py` (one-shot, manifest) | `service/scripts/`, `maintenance.py` | OK → **D8 REMOVE** |

### 2.5 Config, System, Safety
| Feature | Location | State |
|---|---|---|
| Settings: language, Spotify, Deemix/ARL, paths, backup/restore | `views/SettingsView.vue`, `stores/settings.ts` | OK |
| Spotify: app-only (secret+username) **and** OAuth PKCE | `spotify.py` | OK → **D3 SIMPLIFY (PKCE only)** |
| Deemix: status/launch/install (~140 MB GitHub dmg) + ARL | `electron/deemix.ts`, `acquisition.py:386-403` | OK → **D4 TO-RESEARCH** |
| Doctor: diagnostics + RB backups (list/prune/restore) + logs | `views/DoctorView.vue`, `diagnostics.py`, `adapter.py:171-318` | OK |
| Download & Match Center: job queue + conflicts + event context | `views/DownloadMatchCenterView.vue` | OK (fake progress bar, cf. §5) |
| Backup & restore (settings JSON / all-data sqlite VACUUM) | `repositories/_base.py:24-80`, `main.py:181-241` | OK |

---

## 3. Behavioral Specification by Domain (the Core to Preserve)

> This is the most valuable part: the **business rules, invariants, operation order, edge cases** that must survive regardless of the technology. Unless otherwise stated, everything below is `[intentional]` and **covered by a test** (cf. `service/tests/`).

### 3.1 Rekordbox Safety (NON-NEGOTIABLE)

1. **Block mutations if Rekordbox is running.** `assert_rekordbox_can_mutate()` runs `pgrep -fl "rekordbox|rekordboxAgent"`, strictly re-filters (path must contain `/rekordbox.app/`/`/rekordboxagent.app/` or end with `/rekordbox`/`/rekordboxagent`) and raises `RekordboxRunningError` if found · `safety.py:20-80`, tested `test_safety.py:26-58`. **Every write goes through this guard.** The error message is “friendly”: contains no PID, no `/Applications/` path, no `--type=` flag; mentions “Rekordbox” and “rekordboxAgent” (which survives window close).
2. **Unit-of-work `_mutate()`.** Enforced order: (a) assert mutation-ready (RB closed + DB exists) → (b) **timestamped backup** → (c) open DB → (d) yield → (e) commit + **invalidate snapshot cache**; on exception: rollback + re-raise; `finally` close · `adapter.py:505-534`.
3. **Backup before every mutation.** Copy `master.db` (+ `-wal`/`-shm`) to `…/_rekordbox_sync/backups/rekordbox-db-<timestamp>/`; same-second collision → suffix `-<n>` · `adapter.py:171-193`. **Rotation**: keep the N most recent (default **15**, `0` = unlimited) · `adapter.py:52,202-210`.
4. **Reversible restore.** `restore_backup` validates the name (rejects empty/`/`/`\`/`.`/`..` and any path outside backups root), **snapshots the current DB first** (so the restore is itself reversible → leaves 2 backups), deletes WAL/SHM then copies · `adapter.py:274-318`, tested `test_rekordbox.py:176-231,330-339`. **Requires RB closed.**
5. **Deletions = soft-delete.** `rb_local_deleted=1`, `rb_local_synced=0`, `rb_data_status=258`, `rb_local_data_status=0` · `content.py:350-356`. Reactivation: `256` instead of `258`, `rb_local_deleted=0` · `content.py:341-347`. **These magic integers are load-bearing** (Rekordbox 6/7 sync semantics) — reproduce identically or risk corrupting the user’s sync · tested `test_rekordbox.py:385-450`. All reads filter soft-deleted rows.
6. **Files are never moved.** macOS TCC blocks file operations on cloud folders (Dropbox/iCloud) from the service; apply references files **in place** · `adapter.py:758-761`. Consolidation to `rekordbox/Collection` is a separate script (`migrate_collection.py`).
7. **Dropbox/TCC quirk.** *Listing* a cloud folder fails, but `Path.exists()` on a precise path works; **all file-matching is built around `Path.exists()`** and a `fresh=True` that bypasses the cache · tested `test_event_import.py:344-390`, `test_audio.py:68-90`.

### 3.2 Rekordbox Path Resolution (Load-Bearing)

- **Relativization rule**: a file **under `<storage_root>/rekordbox/…`** is stored **volume-relative** (`/<VolumeName>/…`, volume name = basename of `storage_root`); **everything else** (event staging under `_rekordbox_sync/events/`, permanent, imported from a device, or no storage_root) is stored as **absolute** — otherwise Rekordbox displays “file could not be found” · `paths.py:58-74`, `content.py:294-297`, `adapter.py:1318-1321`, tested `test_rekordbox.py:49-58,493-516`. *(Cf. project memory “rekordbox-path-resolution”.)*
- **Path equality**: volume-relative and absolute are treated as **equal and hash-equal**; `path_lookup_keys` emits raw / volume-resolved / expanduser / `.resolve()` / volume-relative forms so an absolute staging path matches a volume-relative DB row · `paths.py:138-174`, tested `test_rekordbox.py:342-382`.

### 3.3 Spotify → Rekordbox Matching

- **Order**: exact ISRC **first**, then fuzzy · `matching.py:83-85`.
- **ISRC**: compared uppercase; match → `confidence=100`, `method="isrc"`, `status="matched"`. **Collision guard**: an ISRC match is **rejected only if** `|duration Δ| > 15000 ms` **AND** title similarity `< 82`; therefore same-title/different-duration remains matched (other edit), and missing duration (`0`/`None`) trusts the ISRC blindly · `matching.py:64-101`, tested `test_matching.py:9-116`.
- **Fuzzy**: `confidence = title*0.52 + artist*0.36 + duration*0.12`, rounded; default threshold `minimum_confidence=82`; below it → `status="missing"`, `confidence=0` · `matching.py:109-120`.
- **Ambiguity**: if `(best − second) < 6` → `status="ambiguous"` (still returns the best `content_id`, but flagged for manual review) · `matching.py:124-132`.
- **Duration buckets**: ≤1500 ms→100, ≤5000→80, ≤12000→55, otherwise 0 · `matching.py:47-57`.
- **Normalization (matching side)**: NFKD→ASCII (accents removed), lowercase, parentheses/brackets removed, `&`→`and`, non-alphanumeric→space; similarity `fuzz.token_sort_ratio` (word-order insensitive) · `matching.py:27-44`.
- ⚠️ **Two divergent normalizations** coexist (matching vs dedup) — cf. §5 [debt] and **D19 SIMPLIFY**.

### 3.4 Duplicate Detection (Dedup)

- **Strategies** selected by caller (`isrc` and/or `fuzzy`) · `dedup.py:238-249`.
- **ISRC**: bucket by strip+upper ISRC (empty ignored). Confidence: all-ISRC + coherent titles → **99**; all-ISRC + divergent titles → **60 + warning note** (bad shared ISRC); fuzzy → **80** · `dedup.py:302-315`, tested `test_dedup.py:48-73`. Groups at 60 are **excluded from bulk** and flagged in the UI.
- **Fuzzy**: default threshold `0.87`, duration tolerance 2000 ms; if one duration is unknown the threshold rises to `max(threshold, 0.93)`; signature = `normalized_artist + " " + normalized_title` · `dedup.py:106-107,210-271`. Bucketing by duration (size `max(tol,1000)`, compare bucket + right neighbor); tracks without duration compared to **all** (O(n²), cf. §5).
- **Normalization (dedup side)**: ligature map (`œ`→`oe`, `ø`, `ß`…), strip `feat.`, selective drop of “noise” parentheses, `&`→`and` · `dedup.py:67-115`, tested `test_dedup.py:33-42`.
- **Group key** (and dismiss key) = sorted unique set of contentIds joined by `|` (order-independent) · `dedup.py:201-203`. Groups with <2 members dropped; dismissed groups dropped. Sort: confidence desc then size desc; intra-group: keeper first then `qualityScore` desc · `dedup.py:318-334`.
- **“Not a duplicate”** persisted in `dedup_dismissed(group_key)`, idempotent insert · `repositories/dedup.py:20-31`.
- **Keeper choice (TODAY)**: `max` by `quality_score` then **oldest** date then contentId. `quality_score` is a **weighted sum**: lossless +300, bitRate/10, sampleRate/1000, bitDepth×5, fileSize/1 MB, analysed +50, bpm>0 +20, cueCount×10, playlistCount×15, tagCount×8, rating×5, **protected +500**, **fileMissing −1000** · `dedup.py:125-172`. ⚠️ The sum does not guarantee the documented order “lossless > cues > permanent”: a large file or many playlists can dominate (cf. §5 [bug]). → **D6: replace with an explicit priority scale, without lossless preference (quality = bitrate)**.
- **Resolution plan / file safety**: never delete the keeper; file deletion only if `allow_file_delete` AND not fileMissing AND not protected (otherwise `skipped_protected`) AND has a `filePath` · `dedup.py:402-412`. **Resolution order**: relink memberships → soft-delete losers (inside txn) → **delete files only AFTER successful commit** · `adapter.py:1254-1277`. Relink reassigns playlists+MyTags from loser to keeper (if already a member, soft-delete the membership row) · `adapter.py:1349-1395`.

### 3.5 Acquisition / Downloading (Deezer + Deemix)

- **Three job scopes**: `event` / `library` / `collection` (re-download of missing file), unified into a global list and the SSE stream · `repositories/acquisition.py:260-384`.
- **Statuses** (event/library): `pending → resolved → queued → downloading → downloaded → ready`, plus `acquisition_failed`, `acquisition_ambiguous` · `acquisition.py:599,767-784`. Collection: same without `ambiguous`.
- **Deezer resolution**: ISRC first (`GET /track/isrc:{isrc}` → confidence 100, method `isrc`); otherwise metadata search. Two queries attempted (`artist:"X" track:"Y"` then `X Y`, limit 10); best score wins. Weighting: `title 0.55 + artist 0.35 + duration 0.10`. **Thresholds**: ≥85 → resolved; 70–85 → **ambiguous (manual review)**; <70 → failed · `acquisition.py:32-33,268-349`, tested `test_acquisition.py:250-308`.
- **Deemix control** (local API `:6595`): `POST /api/auth/login {arl}`, `POST /api/settings` (downloadPath, `quality=MP3_320`, flat folders, `overwriteFiles:"rename"`, template `%artist% - %title%`), `POST /api/download/batch {trackIds, playlistName}`, `GET /api/queue` · `acquisition.py:164-202,834-849`. Retry 3× backoff 0.5→4 s ±jitter on transport errors + {429,500,502,503,504}.
- **ARL applied once per process** (`_applied_arl` global); Deemix status cached 25 s; 429 → keep last known authenticated state · `acquisition.py:103-162,386-403`.
- **`downloaded → ready` requires folder scan + file located on disk** (`mark_ready_tracks_after_scan` / `find_downloaded_file`+relink) · `acquisition.py:624-625`, `collection_acquisition.py:170-189`.
- **Collection re-download + relink**: resolves (ISRC), downloads into the **permanent** folder, then **re-links the existing Rekordbox row** (preserves cues/tags/playlists); if relink fails (RB open) the job remains `downloaded` and is retried later (file is kept) · `collection_acquisition.py:31-191`, tested `test_collection_acquisition.py:86-128`.
- **Idempotent reconciliation**: a `ready` track with file forces its job to `ready`; a `ready` job whose file disappeared goes back to `acquisition_failed` (“Downloaded file is missing…”) · `acquisition.py:701-719`. Job recreation is allowed only if absent or status ∈ {pending, failed, ambiguous}; in-flight and `ready` jobs are never re-resolved · `acquisition.py:781-784`.
- ⚠️ **Downloaded file location = manual reconstruction of Deemix filename** (`%artist% - %title%`, illegal characters→`_`, dash suffix→parentheses, final dot removed, suffixes `(1)`, prefixes `001/002/003`…) · `audio.py:58-195`. This is the **chronic source of “download stuck” bugs** → **D18 CHANGE** (read the real output path from the downloader).

### 3.6 Library Sync (Permanent Sources)

- **Diffing & status transitions** per track during sync · `library.py:45-263`:
  - Duplicate Spotify track in the same playlist → `ignored` (1st occurrence processed);
  - Existing `ignored`/`ready`: carried over as-is (never re-matched);
  - `imported`/`matched`: **reconciled** (re-checks RB link);
  - fresh match: `matched`→`matched`, `ambiguous`→**`conflict`**, otherwise→`new` (unless existing was `missing` → preserved);
  - track absent from active playlist → `removed_from_source` (idempotent).
- **Default tags**: `new`/`conflict`/`matched` inherit `source.tags`; carried-over tracks keep their tags · `library.py:164-191`.
- **Spotify snapshot**: `snapshot_id` stored on source; used to detect changes and count `removedTracks` · tested `test_library.py:36-74`.
- **Download**: eligible = status ∈ {new, missing} AND no active job (resolved/queued/downloading/downloaded/ready); if Deemix unavailable → all become `acquisition_failed`; quality **hard-coded MP3_320**; output folder = **permanent** · `library.py:400-549`.
- **Apply to Rekordbox**: only statuses `matched`/`ready` are imported/tagged (otherwise 409); returns `{imported, tagged, warnings}` · `adapter.py:918-973`, `main.py:715-722`. **Library MyTags must already exist** (raises listing the missing ones, no auto-creation — unlike events/untagged) · `adapter.py:938-945`.
- **Remove a source**: stops tracking only; imported RB tracks and their MyTags are **preserved** · `repositories/library.py:148-159`.

### 3.7 Events (Temporary DJ Sets)

- **3 creation modes**: from Spotify playlist / empty / by link. Event scaffold always creates a **unique folder** (slug collision → `-2`, `-3`…) via atomic `mkdir(exist_ok=False)` · `event_import.py:43-128`, `live_import.py:30-39`.
- **`default_tag` = event name** (MyTag auto on apply, **“Situation”** category); manual event → `spotify_playlist_id = "manual:<slug>"` (will never match a permanent source) · `event_import.py:54,116-122`.
- **Event matching ≠ library**: `ambiguous`→`ambiguous` (not `conflict`), no default tags · `event_import.py:190-227` (→ **D-tech: unify vocabulary**).
- **Staging / file claiming**: an already claimed file can be shared only between two tracks with the **same non-empty ISRC** (true duplicate listed 2×); two distinct tracks never share a file · `event_import.py:305-345`, tested `test_event_import.py:524-642`. Auto-match metadata at `minimum_confidence=85`.
- **Apply event** (`adapter.apply_event_import`): resolves/imports `matched`/`ready` tracks, assigns the event MyTag, **creates/repairs a smart playlist** under an “Event Imports” folder (placed seq 1), restores the XML; returns `{imported, tagged, smart_playlist}` · `adapter.py:793-849`. Event status after apply: `applied` if no matched/ready/missing/ambiguous remain, otherwise `partially_applied`.
- **Delete event**: read-only preview (works with RB open) then deletion. **Protection**: tagged content is protected (not deleted) if it carries **another non-event MyTag** OR if its path is under permanent/manual_collection; only *event-only* and unprotected contents are soft-deleted · `content.py:431-442`, `adapter.py:851-916`. Playlist cleanup by current name **and** legacy `"<name> - Smart"`. ⚠️ The preview must be read **inside** the mutation session (reading `.Title` after commit raises “instance not bound to a Session” — historical regression that turned every deletion into 409, tested `test_rekordbox.py:61-122`).
- **Smart playlist**: `SmartList = "<playlistId>:<tagId>"` (operator 8 = “contains”); IDs > 2³¹ are converted to **signed 32-bit** (`"2662450573"`→`"-1632516723"`) — load-bearing · `content.py:185-189`, tested `test_rekordbox.py:461-463`.
- **Rekordbox writes**: new content/artist/playlist rows created with a **string ID** (pyrekordbox `generate_unused_id` returns an int, but mixed int+string PKs crash SQLAlchemy on flush); `add_rekordbox_content` sets `ID=MasterSongID=rb_file_id`; self-heal of a soft-deleted artist on every apply (“hidden artist” bug) · `content.py:240-277`, `adapter.py:787-790`, tested `test_rekordbox.py:466-489`. `masterPlaylists6.xml` is snapshotted before apply and rewritten after commit (pyrekordbox can overwrite it).

### 3.8 Untagged & Missing Files

- **Untagged report**: lists tracks with `tagCount==0`, classified into 4 categories sorted **junk(0) < dup_of_tagged(1) < alt_version(2) < review(3)** then artist, title · `adapter.py:561-647`, tested `test_rekordbox.py:854-873`. Classification (`maintenance.py`):
  - **junk**: `folder_path` not starting with `/` (`spotify:track:` stub), artist == `rekordbox` (demo samples), empty title, + **personal/French** patterns (`discours`, `psg`, `bereal`, `cash machine`, cue regex `(\d+s)`…) → **D7: replace these patterns with structural + configurable rules**;
  - **dup_of_tagged**: same `song_key` as an already tagged track → whole group deleted;
  - **alt_version**: keep one “base” (cleanest title), delete the rest;
  - **review/unique_mainstream**: unique track with no tagged equivalent → keep.
- ⚠️ `song_key = (normalize_artist, normalize_title)` where **artist keeps only the 1st token** (“Daft Punk”→“Daft”) — over-groups different artists (cf. §5 [bug]).
- **Tag untagged**: applies/creates a MyTag (default category “Genre”); backup first.
- **Delete untagged**: **soft-delete**; ⚠️ **does NOT apply protected guard** (returns hard-coded `skipped_protected:0`) → **D15 KEEP-BUT-FIX**.
- **Missing Files**: lists rows whose file disappeared (`fileMissing`), sorted artist/title · `adapter.py:1027-1068`. Actions per track: **re-download** (collection job, cf. §3.5), **re-link** (searches for a file on disk, score ISRC→100 then title/name ≥70, cap 8 candidates), **remove** (soft-delete). Relink preserves cues/tags/playlists · `adapter.py:1099-1195`.

### 3.9 Spotify (Auth & Reading)

- **Two modes coexist TODAY** (→ **D3: keep only PKCE**):
  - **App-only (Client Credentials)**: `client_id`+`client_secret` → bearer token, **public** catalog/playlists only, via `/users/{username}/playlists`;
  - **User OAuth (Authorization Code + PKCE, S256)**: unlocks private/collaborative/followed, via `/me/playlists`. **Read-only** scopes (`playlist-read-private`, `playlist-read-collaborative`) — the app never writes to Spotify.
- **Token selection**: `use_user_token=None` → user token if an account is connected, otherwise app token · `spotify.py:317-340`. “Connected account” = non-empty `spotify_user_refresh_token`.
- **Conditional auth endpoint**: if `client_secret` present → HTTP Basic (confidential client, stable refresh token); otherwise public PKCE (rotating refresh token). On refresh, a `refresh_token` absent from the response is **preserved** · `spotify.py:485-513`.
- **HTTP retry** (4 attempts): 429 → sleep `Retry-After + attempt`; 401 → force refresh once (only `attempt==0`); ≥400 → raise with status_code; 204 → `{}`.
- **404 = private/inaccessible playlist** (Spotify returns 404, not 403) → translated into actionable message “connect your account” (HTTP 404, not 401) · `spotify.py:215-234`, `main.py:123-129`, tested `test_main_routing.py:16-60`.
- **Redirect URI**: forced to local service callback, ignores client value · `main.py:850-872`. ⚠️ Documented callback is `http://127.0.0.1:8765/...` (fixed port) while “the port is not a setting, Electron chooses it” — contradiction (§5).

### 3.10 Settings, Persistence, Backup/Restore

- **Settings** persisted in **SQLite** (`settings(key,value)`), exposed via `GET/POST /api/settings`. **Never re-saved on startup** (defaults are applied only on read, to avoid blanking credentials) · `main.py:136-138`. **Blank protection**: a POST with an empty credential field **preserves** the stored value (`spotify_client_id/secret/username`, `deemix_arl`) · `repositories/settings.py:103-137`, tested `test_db.py:25-55`. ⚠️ **Paths** are NOT blank-protected (a partial save can erase them — §5).
- **electron-store mirror**: `electron/settings-store.ts` keeps a durable JSON copy of 9 fields, read instantly at boot. **Reconciliation**: first launch → *pull* from service (migration); afterwards → *push* electron-store→service. `settings:set` does **not** write to the service (renderer is expected to have already POSTed) · `main.ts:80-105,239-246`. → **D-tech: single source of truth** (cf. §10).
- **Export/import settings** (JSON, type `syncbox-settings`): excludes transient OAuth state, **includes** Spotify tokens · `repositories/settings.py:16-57`, tested `test_data_backup.py`. **Export/import all-data**: `VACUUM INTO` (1 coherent file), validated (must contain a `settings` table), **safety backup before replacement** · `repositories/_base.py:24-69`.

---

## 4. Technical Map & Internal Contracts

### 4.1 IPC Renderer ↔ Main (`window.desktop.*`, preload `electron/preload.ts`)

| Channel | Args | Return | Source |
|---|---|---|---|
| `app:get-api-base-url` | — | `string` (service base URL) | `main.ts:231` |
| `settings:get` | — | `AppConfig` (9 fields) | `main.ts:234-238` |
| `settings:set` | `Partial<AppConfig>` | `AppConfig` | `main.ts:239-246` |
| `settings:reload` | — | `AppConfig` | `main.ts:247-256` |
| `app:open-external` | `url` (http/https only) | `void` | `main.ts:257-263` |
| `app:open-path` | `path` (absolute only) | `void` | `main.ts:264-272` |
| `app:open-logs` | — | `string` (logs dir) | `main.ts:273-278` |
| `deemix:status` | — | `{installed, running, appPath, port}` | `main.ts:281` |
| `deemix:launch` | — | `DeemixStatus` | `main.ts:282-287` |
| `deemix:install` | — | `DeemixStatus` | `main.ts:288-296` |
| `deemix:progress` (push) | — | `{stage, percent\|null}` | `main.ts:291-293` |

**`AppConfig`** (camelCase, electron-store + `/api/settings` wire): `spotifyClientId, spotifyClientSecret, spotifyUsername, rekordboxDatabaseDir, storageRoot, permanentPath, manualCollectionPath, deemixArl` (string) + `backupRetention` (number) · `settings-store.ts:15-25`.

### 4.2 Spawn Main → Service

- Dev: `uv run uvicorn app.main:app`; packaged: PyInstaller binary `process.resourcesPath/syncbox-service/syncbox-service` · `main.ts:131-189`.
- **Env passed**: `RBSYNC_DATA_DIR` (=userData), `RBSYNC_SERVICE_PORT` (default 8765), `RBSYNC_APP_VERSION` (=`app.getVersion()`), `RBSYNC_LOG_DIR` · `main.ts:138-146`.
- `waitForService` polls `GET /api/health` every 500 ms up to 30 s; timeout → continues silently (no degradation signal to renderer — §5).
- Killed by **SIGTERM** only on `before-quit` (no SIGKILL fallback — §5).
- Other service env: `RBSYNC_REKORDBOX_DATABASE_DIR`, `RBSYNC_STORAGE_ROOT`, `RBSYNC_LOG_LEVEL`, `RBSYNC_SERVICE_HOST`, `RBSYNC_EXTERNAL_SERVICE=1` (dev escape hatch) · `config.py:36-46`, `run_service.py`.

### 4.3 HTTP Renderer ↔ Service (~70 Endpoints, base `/api`)

Port `config.api_port`; CORS limited to loopback origins (`http://(127.0.0.1|localhost):\d+`, `allow_credentials=False`); `lifespan`: `database.migrate()` + `ensure_deemix_authenticated` on startup · `main.py:132-158`. Error mapping **per route** (try/except → HTTPException); **RB-running / conflict → 409** everywhere (restore/resolve/remove/relink/redownload/tag/delete/apply).

Master table (method · path · → response · delegate) — representative excerpt, full table in `docs/_analysis/07_S1.md`:

| Domain | Key Endpoints |
|---|---|
| System | `GET /health`, `GET /rekordbox/status`, `GET /rekordbox/collection-stats`, `GET /diagnostics` |
| Settings/data | `GET·POST /settings`, `GET /settings/export`·`POST /settings/import`, `GET /data/export` (sqlite FileResponse)·`POST /data/import` (octet-stream) |
| Backups | `GET /rekordbox/backups`, `POST /rekordbox/backups/prune`, `POST /rekordbox/backups/{name}/restore` |
| Duplicates | `GET /rekordbox/duplicates?strategies=&fuzzyThreshold=` (clamped 0.5–1.0, default 0.87), `POST /rekordbox/duplicates/resolve` |
| Missing | `GET /rekordbox/missing`, `POST …/{cid}/remove`, `GET …/{cid}/relink-candidates`, `POST …/{cid}/relink`, `POST …/{cid}/redownload` |
| Untagged | `GET /rekordbox/untagged`, `POST …/tag`, `POST …/delete` |
| Storage | `POST /storage/ensure`, `GET /storage/layout`, `GET /storage/validate-path?path=` |
| Library | `GET·POST /library/sources`, `DELETE …/{id}`, `POST …/{id}/sync`, `POST …/sync-all`, `GET …/{id}/review`, `POST /library/tracks/update`, `POST /library/tracks/download`, `GET /library/search-deezer`, `POST …/{id}/tracks/{tid}/queue-deezer`, `POST …/{id}/apply` |
| Rekordbox tags | `GET /rekordbox/tags` |
| Deemix | `GET /providers/deemix/status`, `POST /providers/deemix/login` |
| Acquisition | `GET /acquisition/jobs?scope=&status=&source=`, `DELETE /acquisition/jobs/clear?scope=`, **`GET /acquisition/stream` (SSE)** |
| Spotify | `POST /spotify/test`, `GET /spotify/status`, `POST /spotify/auth-url`, `POST /spotify/disconnect`, `GET /spotify/callback`, `GET /spotify/playlists?limit=&offset=` |
| Events | `GET /events`, `POST /events/spotify/analyze`, `POST /events`, `POST …/{id}/tracks/spotify`, `GET …/{id}/review`, `GET …/{id}/delete-preview`, `POST …/{id}/delete`, `POST …/{id}/staging/scan`, `POST …/{id}/acquisition/auto`, `GET …/{id}/acquisition/jobs`, `POST …/{id}/matches`, `POST …/{id}/apply`, `GET …/{id}/search-deezer`, `POST …/{id}/tracks/{tid}/queue-deezer` |
| Live import | `POST /live-imports` → **D10 REMOVE** |

### 4.4 SSE — `GET /api/acquisition/stream` · `main.py:802-837`

- `Content-Type: text/event-stream`; headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Event: `event: jobs\ndata: <json>\n\n` where `<json>` = array of `GlobalAcquisitionJob.model_dump(by_alias=True)`. Keepalive `: keepalive\n\n` when unchanged. **Tick = 4 s** (`ACQUISITION_STREAM_INTERVAL_S`). Exits on `request.is_disconnected()`; refresh errors do not interrupt the stream (re-emits last payload or `"[]"`).
- ⚠️ Client (`useAcquisitionStream.ts`) parses without schema validation, fixed reconnect 3 s without jitter, and **writes only to the `events` store** (the `library` store has its own copy not fed by SSE — §5).

### 4.5 External APIs

- **Spotify**: `accounts.spotify.com` (token/authorize), `api.spotify.com/v1` (playlists/tracks/search).
- **Deezer public**: `api.deezer.com` — `GET /track/isrc:{isrc}`, `/track/{id}`, `/search?q=&limit=`.
- **Deemix Remastered**: `127.0.0.1:6595` — health/auth/settings/download.batch/queue (cf. §3.5).

### 4.6 App SQLite Schema (`repositories/_base.py:84-313`)

Tables: `settings(key,value)` · `tag_rules` *(legacy → **D9**)* · `spotify_tracks` · `rekordbox_tracks` · `track_links` · `event_playlists` *(distinct from `event_imports`, possibly dead)* · `event_imports` · `event_import_tracks` (FK CASCADE, UNIQUE(event,track)) · `event_staging_files` · `event_acquisition_jobs` · `schema_migrations` · `library_sources` (UNIQUE spotify_playlist_id) · `library_source_runs` · `library_tracks` (+ ALTER `pending_deezer_track_id`, `pending_deezer_isrc`) · `library_acquisition_jobs` · `dedup_dismissed(group_key)` · `collection_acquisition_jobs`. The 3 job tables share an almost identical shape (uniqueness key `(fk, spotify_track_id, provider)` or `(content_id, provider)`).

⚠️ **No versioned migration beyond v1**: `CREATE TABLE IF NOT EXISTS` + ad-hoc ALTER via `PRAGMA table_info`, `schema_migrations` contains only v1; and **the seed `tag_rules → library_sources` reruns on EVERY `migrate()`** (therefore every boot), overwriting user edits (§5).

### 4.7 Payload Models (pydantic, `models.py`)

~50 models, camelCase aliases. Families: `AppSettings`, `SettingsBackup`, `StorageLayout`, `RekordboxStatus`/`…CollectionStats`, `RekordboxBackup(s)`/`BackupPrune/Restore`, `Diagnostic(s)`, `Duplicate(Track/Group/ScanResult/Resolution…)`, `Missing(Track/Report/Relink/Action)`, `Untagged(Track/Report/Tag/Delete)`, `Spotify(Connection/AuthUrl/Playlist…)`, `Library(Source/TrackReview/Review/Download/Apply)`, `Event(Review/TrackReview/Apply/Delete/Acquisition/Summary)`, `AcquisitionJob`/`GlobalAcquisitionJob`, `LiveImport*`, `SpotifyTrack`, `RekordboxTrack`, `ProposalType`. Exhaustive field detail: `docs/_analysis/13_S7.md`.

> **Note `ProposalType`** (`models.py:504`) enumerates `add_to_rekordbox | add_to_spotify | remove_from_rekordbox | remove_from_spotify | manual_match | protect_manual_track`. The `*_to_spotify` variants are **dead** (read-only Spotify scopes). “Proposals” documented in the README are **not** materialized by a dedicated table (no `repositories/proposals.py`; concept diluted into library/acquisition) — cf. §5 docs-vs-code.

---

## 5. Defect Catalog (What MUST NOT Be Reproduced)

`bug` = incorrect behavior · `fragile` = race/unhandled error/hidden assumption · `debt` = inconsistency/duplication · `unfinished` = half done.

### 5.1 Correctness (Confirmed Bugs — High Priority)

| # | Type | Symptom · `file:line` · cause · impact |
|---|---|---|
| B1 | bug | **Collection re-download takes the 1st Deezer hit without threshold** and auto-relinks it to a real collection row · `collection_acquisition.py:60-62` · `results[0]` when ISRC fails · wrong audio replaces the reference of an existing track (cues/playlists preserved but pointing to the wrong file). → **D14** |
| B2 | bug | **`delete_untagged` ignores protection** (hard-coded `skipped_protected:0`) · `adapter.py:716-723` · a permanent/manual track can be soft-deleted without guard. → **D15** |
| B3 | bug | **Batch “remove tag” can ADD the tag to other selected tracks** · `LibraryView.vue:84-116`, `library.ts:180-193` · `selectedTagNames` = union, and update overwrites each selected track’s tags with the union. → **D16** |
| B4 | bug | **`library_sources` seed reruns on every `migrate()`** and force-upserts name/tags/enabled from `tag_rules` · `_base.py:339-371` · user edits (rename/tags/disable) are **reverted on next boot**. → **D9** |
| B5 | bug | **`song_key` keeps only the 1st artist token** · `maintenance.py:89-93` · conflates “David Bowie” and “David Guetta”; risk of classifying/deleting a legitimately different title. → **D7** |
| B6 | bug | **ISRC fallback to `barcode` tag** · `audio.py:35` · a barcode (UPC/EAN) is stored as “ISRC”, polluting all ISRC matching. → **D20** |
| B7 | bug | **`feat.*$` greedy on lowercased text** · `maintenance.py:83` · “Defeat”, “Feather” truncated → corrupted song key. → **D7** |
| B8 | bug | **Apply displayed in red as “error” as soon as there are warnings**, even on success · `events.ts:315-322`, `library.ts:254-261` · tone derived only from `warnings.length`. → **D17** |
| B9 | bug | **`restore (unignore)` sets status back to `new`** · `library.ts:343-356` · a track that was matched/ready before ignore returns as “new” → forced re-resolution/re-download. |
| B10 | bug | **Dedup confirm can promise the opposite of the action** · `DuplicatesView.vue:34-44` vs `useDuplicates.ts:128` · text calculates deletion eligibility but payload sends the raw flag. |
| B11 | bug | **Event deletion mutates the collection without `mutationAllowed` guard** · `EventWorkspace.vue:128-136`, `events.ts:326-355` · can attempt a write while RB is open. |
| B12 | bug | **Shared `importForm.eventName` field** between create-from-playlist form and live-import · `EventsView.vue:93-94` · typing in one pollutes the other. *(Resolved by **D10**, which removes live import.)* |

### 5.2 Fragile (Races, Swallowed Errors, Assumptions)

| # | Symptom · `file:line` |
|---|---|
| F1 | **File location by filename reconstruction** (prefixes `001-003`, copies `(1)-(7)`, dash→parentheses…) · `audio.py:58-195` · each new edge = a “download stuck” bug. → **D18** |
| F2 | **Download-id ↔ track mapping by list index** · `acquisition.py:537-544`, `library.py:534-549` · assumes Deemix returns ids in 1:1 order; overflow → `download_id=None`. |
| F3 | **Process globals** (`_applied_arl`, `_STATUS_CACHE`, `_SCAN_CACHE`) + Deemix `downloadPath` mutated by batch · `acquisition.py:59,104-111,522-524` · races between concurrent downloads (file in wrong folder). |
| F4 | **Heuristic parsing of Deemix payload** (`queue`/`items`/`downloads`, status substrings) · `acquisition.py:899-920` · a Deemix version change silently freezes jobs in `queued`. |
| F5 | **SSE feeds only the events store** · `useAcquisitionStream.ts:49` vs `library.ts:24` · the Library view job list stops updating live (poll suspended during SSE). |
| F6 | **Double polling**: `useRefreshManager` (setInterval) + `useSystemStatusQuery` (vue-query) cover overlapping data · `useRefreshManager.ts:49-98`, `useSystemStatusQuery.ts:24-34`. |
| F7 | **`parse` returns `null` typed as `T`** on non-JSON/empty/204 body · `client.ts:417-422` · silent downstream null dereference. |
| F8 | **SSE reconnect without jitter/backoff** (fixed 3 s, only on CLOSED) · `useAcquisitionStream.ts:55-63`. |
| F9 | **Inconsistent path/query escaping** (`queueDeezerTrack`/`clearAcquisitionJobs` interpolate raw) · `client.ts:265,286,385`. |
| F10 | **Event race**: `summaries`/`globalAcquisitionJobs` assigned BEFORE `requestedEventId` guard; no abort of in-flight fetches · `events.ts:78-79,97-98`. |
| F11 | **`find_relink_candidates` = unbounded `rglob("*")`** over 5 roots (reads metadata of every file) · `adapter.py:1155-1193` · slow on large cloud libraries. |
| F12 | **Reads without retry**: `list_tags`, `content_meta`, `preview_event_delete` open the DB outside `_read_rekordbox` · `adapter.py:542,861,1078` · can fail “database is locked” where the snapshot would retry. |
| F13 | **Service killed SIGTERM-only, without timeout/SIGKILL**; no restart on crash · `main.ts:183-189` · orphaned binary, port 8765 blocked. |
| F14 | **Invisible boot migration if service down**: `settingsReady` resolved in `finally` → UI unblocked with empty fields, migration silently not done · `main.ts:95-104`. |
| F15 | **Path validation only on permanent/manual (on blur)**; rekordbox-dir and storage-root (the 2 most critical) **not validated** · `SettingsView.vue:339-352`. |
| F16 | **Fake Download Center progress bar** (width derived from tone, not real %) · `DownloadMatchCenterView.vue:136-139`. |
| F17 | **Audio deletion = irreversible `unlink()`** (only non-reversible operation; DB is backed up, audio is not) · `adapter.py:1270-1277`. → **D12** |

### 5.3 Debt (Inconsistencies, Duplication, Hardcoding)

| # | Symptom · `file:line` |
|---|---|
| T1 | **Hard-coded developer paths**: `DEFAULT_REKORDBOX_DIR=/Users/<user>/…`, `DEFAULT_STORAGE_ROOT=<cloud-storage>/Music` · `config.py:15-19`; also `settings.ts:14-17` and `.env.example:3-4`. → **D1** |
| T2 | **Personal/French junk heuristics** · `maintenance.py:103-114`. → **D7** |
| T3 | **Two divergent normalizations** matching vs dedup · `matching.py:27-44` vs `dedup.py:67-115` · judge “identical” differently, double maintenance. → **D19** |
| T4 | **Double data layer** (partial vue-query + Pinia+manual HTTP) = unfinished migration · git `phase-2a→2d` · 2 polling models, ambiguous source of truth. → §10 |
| T5 | **Double settings store** (electron-store JSON + SQLite) with manual push/pull reconciliation, `settings:set` does not push the service · `main.ts:80-105,239-246`. → §10 |
| T6 | **`tag_rules` (table+repo) vestigial** superseded by `source.tags` · `repositories/tags.py`, `library.ts:23`. → **D9** |
| T7 | **Divergent matching vocabulary** library `conflict` vs event `ambiguous` for the same phenomenon; quasi-duplicated row builders · `library.py` vs `event_import.py`. |
| T8 | **`delete_event_import` leaves event folder/audio/`.m3u8` orphaned on disk** · `events.py:63-80`. |
| T9 | **`formatBytes` without GB tier**; **`formatDate` assumes epoch seconds** while API mostly returns ISO/ms · `format.ts:16,21`. |
| T10 | **English strings hard-coded** in `window.confirm` dialogs despite i18n (delete source/event) · `library.ts:121-125`, `events.ts:333-340`. |
| T11 | **`backupRetention` without Settings UI control** (edited only via Doctor) · `settings.ts:20`. |
| T12 | **`.xml.bak-<ts>` never pruned** on every delete event · `adapter.py:1403-1404`. |
| T13 | **Unsynchronized triple-source version**: `package.json`=0.2.0, `pyproject.toml`=0.1.0, `version.py` · README claims “single-source”. |
| T14 | **`StatusBadge` 6 tones, 2 used**; `body{min-width:980px}` + sidebar `md:hidden` contradictory · `StatusBadge.vue`, `styles.css:61`, `AppShell.vue:37`. |
| T15 | **Docs-vs-code**: README references `sync.py` and a `proposals` repo that **do not exist**; `migrate_collection.py`/`cleanup_rekordbox.py` to confirm; fixed OAuth callback `:8765` vs “dynamic port”. |

### 5.4 Unfinished

| # | Symptom · `file:line` |
|---|---|
| I1 | **Dormant electron-updater auto-update** (`publish:null`, env required) · `DISTRIBUTION.md:119-126`. → §7-D (remove) |
| I2 | **No DELETE route for `tag-rules`** (incomplete CRUD) · `main.py:508-517`. *(resolved by D9)* |
| I3 | **`clearDownloads`/`globalJobStats`/`updateTrackTags`** exported but not wired in their slice · `events.ts:44-52,371-396`, `library.ts:195-209`. |
| I4 | **Re-download in Missing Files locks into “queued” forever** (no completion signal returns to the view) · `useMissing.ts:103-114`. |
| I5 | **Partial Pinia→vue-query migration**: `useSystemStatusQuery` writes to the store as a facade · `useSystemStatusQuery.ts:14-17,41-50`. |

---

## 6. Domain & Data Model (Reusable Foundation)

Entities that survive regardless of technology:

- **Library source** (`library_sources`) — Spotify playlist tracked *permanently*. Attributes: `spotify_playlist_id` (identity), name, `snapshot_id` (change detection), `tags` (default MyTags), `enabled`, `status`. Cycle: `pending → synced`; runs historized (`library_source_runs`).
- **Library track** (`library_tracks`) — 1 row per (source, spotify_track_id). **Statuses**: `new → matched|conflict|ready|imported`, `missing`, `removed_from_source`, `ignored`, `acquisition_failed`. Carries Rekordbox link (`rekordbox_content_id`), `match_method`, `confidence`, `staging_file_path`, tags, `pending_deezer_*`.
- **Event** (`event_imports`) — temporary import (wedding, party). Attributes: name, slug, `default_tag` (= name, “Situation” category), `spotify_playlist_id` (or `manual:<slug>`), `event_dir`/`audio_dir`/`playlist_path`, `status` (`pending → applied|partially_applied`). Tracks (`event_import_tracks`, statuses `matched/ambiguous/missing/ready/applied/ignored`) + staging files (`event_staging_files`).
- **Acquisition job** — 3 scopes (`event`/`library`/`collection`), unified into `GlobalAcquisitionJob`. **Lifecycle**: `pending → resolved → queued → downloading → downloaded → ready`; failures `acquisition_failed`/`acquisition_ambiguous`. Key: (fk, spotify_track_id|content_id, provider). Provider = `deemix`.
- **Rekordbox track** (snapshot, non-persistent) — `content_id`, title, artist, isrc, durationMs, filePath, fileType, bitRate/sampleRate/bitDepth/fileSize, bpm, rating, analysed, cueCount, playlistCount, tagCount, `protected` (under permanent/manual), `fileMissing`, dateCreated. Read **once**, cached on `(mtime,size)` of `master.db(+wal)`.
- **MyTag** — Rekordbox tag system (categories → tags). “Situation” category for events, “Genre” by default for library/untagged.
- **Duplicate group** — ≥2 contents = same recording (ISRC) or close metadata (fuzzy), with a *keeper* (to choose). Group identity = sorted set of contentIds.
- **Dedup dismiss** (`dedup_dismissed`) — “not a duplicate”, key = set of contentIds.
- **Rekordbox backup** — timestamped folder under `_rekordbox_sync/backups/`, contains `master.db(+wal/shm)`. Rotation N.
- **Settings** (`settings` k/v) — Spotify credentials, Deemix ARL, 4 paths, `backup_retention`, OAuth tokens.

**Matching identities**: (1) **ISRC** (exact, priority); (2) **fuzzy** (normalized title/artist + duration compatibility, `rapidfuzz.token_sort_ratio`). Both require a single **normalization** (to unify, D19).

**Storage layout**: `<storage_root>/rekordbox/{Collection, Collection manuelle}` (protected) + `<storage_root>/_rekordbox_sync/{inbox, events, backups, manual_collection}`. App DB: `~/Library/Application Support/Syncbox/syncbox.sqlite3` (packaged).

---

## 7. Decision Log (Keep / Remove / Change)

Taxonomy: `KEEP` · `KEEP-BUT-FIX` · `SIMPLIFY` · `CHANGE` · `REMOVE` · `TO-RESEARCH` (Phase 2).

### 7.1 Decisions Validated with Owner (P6)

| # | Topic | Decision | Detail / justification |
|---|---|---|---|
| **D1** | Target audience | **CHANGE** | **Open-source / public**. Mandatory consequences: remove all personal paths (`config.py:15-19`, `settings.ts:14-17`, `.env.example`), make everything configurable, secrets/`.env` hygiene, license. |
| **D2** | Platform | **CHANGE (expand)** | **macOS + Windows**. Linux excluded (Rekordbox does not run there). Abstract by OS: path resolution, Rekordbox process detection (pgrep → Windows equivalent), file operations, system folders (`~/Library` vs `%APPDATA%`), `hdiutil`/Deemix install. |
| **D3** | Spotify auth | **SIMPLIFY** | **OAuth PKCE only**. Remove app-only mode (Client Secret + username, `/users/{username}/playlists`) and all conditional Basic-vs-PKCE logic (`spotify.py:485-498`). Also fixes `connection_status` (B-spotify). |
| **D4** | Downloading / Deemix | **TO-RESEARCH (Phase 2)** | Goal: “everything in one place, in the best way.” Study: **package/embed** the downloader, or **reimplement** Deezer acquisition natively, instead of driving an external Deemix app on `:6595`. Includes the **legal dimension** (ARL/Deezer, Deemix GPL license) to document. De facto removes unverified dmg auto-install (`deemix.ts`). |
| **D5** | Duplicates — automation | **CHANGE** | Keep the **suggested** keeper but **confirmation per group**; **remove 1-click bulk auto-resolve** (`useDuplicates.ts:185-202`). |
| **D6** | Keeper choice | **CHANGE** | **Explicit priority scale + displayed reason** (predictable, explainable). **Remove lossless/FLAC preference**: quality is measured by **bitrate** (FLAC not always supported by DJ hardware). Replaces weighted sum `dedup.py:125-172`. |
| **D7** | Untagged diagnostic | **KEEP-BUT-FIX** | Keep the **4 categories** (junk / dup_of_tagged / alt_version / review). Replace personal/French junk vocabulary with **universal structural rules** (`spotify:track:` stub, empty title, artist `rekordbox`) **+ user-configurable patterns**. Also fix B5 (1-token artist) and B7 (feat regex). |
| **D8** | Cleanup CLI script | **REMOVE** | `cleanup_rekordbox.py` removed — covered by Duplicates + Untagged (with backups/soft-delete). |
| **D9** | `tag_rules` (legacy table) | **REMOVE** | Remove legacy table/bridge (cause of B4). **Preserve the concept**: default MyTags carried by source (`source.tags`). |
| **D10** | Live Import M3U8 | **REMOVE** | Remove entirely (`live_import.py`, live import UI, `POST /live-imports`). Always require Rekordbox closed and write the collection directly. Also eliminates B12. |
| **D11** | Event deletion | **CHANGE** | **Always ask, with exact preview** (tracks + files that will be deleted). Server preview already exists (`delete-preview`). |
| **D12** | Audio file deletion | **CHANGE** | **OS trash** (macOS Trash / Windows Recycle Bin) instead of `unlink()` (F17). Reversible via the OS. Applies to dedup and delete-event. |
| **D13** | i18n | **KEEP** | FR/EN preserved, locale files structured for adding languages. |

### 7.2 Decisions Made Without Question (Unambiguous Evidence — Bug Fixes)

| # | Topic | Decision | Detail |
|---|---|---|---|
| **D14** | Collection re-download (top hit) | **KEEP-BUT-FIX** | Apply 70/85 threshold + `ambiguous` state like the event flow; never auto-relink below threshold (B1). |
| **D15** | `delete_untagged` protection | **KEEP-BUT-FIX** | Apply permanent/manual guard (skip + real report) (B2). |
| **D16** | Bulk tags | **KEEP-BUT-FIX** | **Add/remove by delta** semantics, never overwrite by union (B3). |
| **D17** | Apply with warnings | **KEEP-BUT-FIX** | Distinct “applied with warnings” state (not red/error) (B8). |
| **D18** | Download location | **CHANGE** | **Read the real output path** from the downloader; locator by reconstruction only as fallback (F1). |
| **D19** | Matching/dedup normalization | **SIMPLIFY** | **One shared normalization pipeline** (ligatures, feat, parentheses), tested (T3). |
| **D20** | ISRC fallback barcode | **REMOVE** | Never use the `barcode` tag as ISRC; absent → `None` (B6). |
| **D21** | Global reversibility | **KEEP** | Preserve soft-delete + backups + Doctor restore; **extend** to file trash (D12). |
| **D22** | Restore `unignore` | **KEEP-BUT-FIX** | Restore previous status, not “new” (B9). |
| **D23** | RB guard on delete event | **KEEP-BUT-FIX** | Gate deletion on `mutationAllowed` like apply (B11). |
| **D24** | Auto-update | **REMOVE** | Remove dormant electron-updater scaffolding (consistent with memory “no auto build/release”) (I1). |
| **D25** | Dead tables/fields | **REMOVE** | `event_playlists` (legacy), `ProposalType.*_to_spotify`, unused `StatusBadge` tones, responsive branch `md:hidden` — after confirming no consumer. |

---

## 8. UI/UX — Current State + Open Directions

> **UI/UX is an OPEN topic** (golden rule 5). Everything below is *the existing state* + *hypotheses to challenge in design phase*, not constraints.

### 8.1 Current State

- **9 screens, navigation by Pinia state** (`ui.activeView`), no router, no deep-link, no browser back, no persistence of current screen across launches. Settings is the catch-all `v-else` (an invalid `activeView` silently lands there).
- **Sidebar**: 7 primary items + Doctor/Settings at bottom + health banner (API/Rekordbox/Deemix + downloads chip). Window non-resizable below 980 px, scroll by panel.
- **Two shared components**: `TrackReviewTable` (filters, virtualization, ignore/restore) and `DeezerSearchPanel` (covers + 30 s preview) between Library and Events.
- **Observed UI inconsistencies**: divergent download counters sidebar vs dashboard; different “Deemix ready” condition (sidebar `available` only vs dashboard `available && authenticated`); divergent event status tones card vs workspace; fake progress bar; cross-filter selection in Untagged can act on hidden rows.

### 8.2 Open Directions (to Validate in Design, NOT Decided)

- **Direction A — keep 9 screens + state navigation**, but: persist current screen, replace Settings `v-else` with an explicit default, derive all health counters from a single canonical selector.
- **Direction B — group by task**: merge “Download & Match”, “Missing”, and the acquisition part of Library/Events into **one acquisition center** (jobs are already unified on the data side); group Duplicates/Untagged/Missing under a **“Collection Health” hub** (Doctor).
- **Direction C — guided flows**: an “onboarding” path (connect Spotify → Deemix → paths → green Doctor) and linear “sync source” / “create event” flows instead of drawer-like screens.
- **Open design questions**: is a real router needed (deep-link/back)? is the bulk tag bar the right editing model? do the Download Center and event context overlap unnecessarily? does system health deserve a dedicated screen or a simple indicator?

---

## 9. Constraints & Non-Negotiables (Respect No Matter What)

1. **Rekordbox safety** (§3.1): block if RB/`rekordboxAgent` is running, `_mutate` unit-of-work, **backup before every mutation**, reversible soft-delete, restore with prior snapshot. **Status integers** (256/258, `rb_data_status`) are load-bearing.
2. **Path resolution** (§3.2): volume-relative under `rekordbox/`, absolute elsewhere; equality of both forms. Reproduce exactly (project memory).
3. **Never move files**; handle TCC quirk (cloud listing KO but `Path.exists()` OK).
4. **Essential external dependencies**: pyrekordbox (+ sqlcipher3) for `master.db`; Spotify Web API (OAuth PKCE); Deezer/Deemix for acquisition (form to decide, D4); mutagen; rapidfuzz.
5. **Packaging**: embedded standalone Python service (binary), seed DB copied on first launch, CA bundle (certifi) embedded for TLS. **Cross-OS** (D2): Windows equivalent of spawn/binary and system paths.
6. **Local-first**: no cloud backend; all state in local SQLite; settings in a folder that survives updates.
7. **Spotify identities**: OAuth tokens stored locally — **protect at rest** (open-source ⇒ no cleartext secret in a repo; encrypted/keychain refresh tokens, cf. §10).
8. **FR/EN i18n** maintained (D13).
9. **Behavior contract**: the `service/tests/` suite encodes invariants — any rewrite must reproduce these guarantees (or explicitly amend them via the log).

---

## 10. Open Questions for Phase 2 (Architecture & Product)

> **⚠️ CLOSED — resolved in [SPEC-UNIFIED.md](SPEC-UNIFIED.md) §7.2.** The 10 questions below have been decided (8 by sourced research + validation, 2 — §10.9 UI/UX and §10.10 configurable matching — delegated to the design phase). This section is kept as **Phase 1 history**; the authoritative decision is in SPEC-UNIFIED. Do not re-decide here.

**Undecided** decisions (original state, before unification):

1. **Target stack** — not decided here (golden rule 1). To choose in Phase 2: service language/runtime, UI framework, desktop mechanism (Electron or alternative), taking **macOS + Windows** into account (D2).
2. **Deezer/Deemix acquisition (D4)** — **the big question**: embed/package the downloader, reimplement Deezer acquisition natively, or continue driving an external app? Evaluate technical feasibility, **legality (ARL, Deemix GPL)**, robustness (read real output path — D18), and download concurrency (remove process globals, F3).
3. **Data layer / source of truth** — the double layer (vue-query + Pinia, T4) and double settings store (electron-store + SQLite, T5) must **converge** to a single source of truth. Polling vs push model (one canonical job stream fed by SSE, F5/F6).
4. **Protection of secrets at rest** — Spotify OAuth tokens and ARL: OS keychain vs encrypted DB vs plaintext (unacceptable in open-source). To decide in Phase 2.
5. **Schema migration strategy** — replace `IF NOT EXISTS` + ad-hoc ALTER (T-migration) with ordered versioned migrations.
6. **Multi-OS abstraction** — portable model for Rekordbox process detection, system paths, trash operations (D12), and file operations, macOS/Windows.
7. **Service port & OAuth callback** — reconcile “dynamic port” and fixed redirect URI `:8765` (T15): fixed port for OAuth, or registered dynamic redirect.
8. **Service robustness** — supervise/restart service (F13), expose “backend unavailable” state to renderer (F14).
9. **UI/UX** — screen structure, navigation (router?), groupings (§8.2): entirely open, to design in design phase.
10. **Configurable matching model** — expose (or not) thresholds (82 / margin 6 / weightings); unify normalization (D19); single ISRC collision policy between matching and dedup.

---

## Appendices

- **Detailed evidence by subsystem**: `docs/_analysis/00_R1.md` … `15_D1.md` (16 files, each assertion anchored `file:line`).
- **TO CONFIRM** (not verifiable read-only without execution): existence/content of `service/scripts/cleanup_rekordbox.py` and `migrate_collection.py`; uvicorn host/port binding (outside `main.py`); external consumers of `move_to_permanent`/`playlist_exists`; real usage of `event_playlists` table; behavior of Spotify `items.total` field in prod.
