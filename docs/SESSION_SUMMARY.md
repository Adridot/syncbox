# Session Summary

## Project Goal

Build a local desktop application to synchronize Spotify playlists with Rekordbox while keeping permanent library curation separate from temporary event imports.

The application should:

- use Spotify playlists as sources;
- match tracks against the Rekordbox collection;
- acquire missing audio files through an authorized local Deemix workflow;
- stage and validate files before import;
- apply Rekordbox MyTags and smart playlists;
- keep temporary event playlists separate from permanent synced playlists;
- avoid destructive writes unless explicitly approved;
- block normal Rekordbox database mutations while Rekordbox is running.

All repository code, documentation, comments, config keys, and internal names must remain in English. User-facing conversation remains in French.

## Architecture Decisions

- Desktop shell: Electron/Vite/Vue.
- Backend service: Python/FastAPI.
- Local app database: SQLite.
- Rekordbox integration: `pyrekordbox` for closed-database writes.
- Spotify integration: Spotify Web API with PKCE, playlist snapshots, pagination, and rate-limit handling.
- Deemix integration: isolated local provider workflow; no ARL/token storage in the app.
- Storage root:
  `/Users/adriendidot/Library/CloudStorage/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique`
- Managed storage:
  `_rekordbox_sync/`
- Rekordbox live DB:
  `/Users/adriendidot/Library/Pioneer/rekordbox/master.db`

## Core Safety Model

Normal app behavior must not mutate Rekordbox when either `rekordbox` or `rekordboxAgent` is running.

Before Rekordbox mutation, the app creates a backup under:

`/Users/adriendidot/Library/CloudStorage/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique/_rekordbox_sync/backups`

Live-write experiment result:

- A manual test was attempted with Rekordbox open for `Rallye Nanteuil`.
- The app guard was bypassed only inside a one-off script.
- `pyrekordbox` itself refused `commit()` while Rekordbox was running.
- No partial import remained after rollback.
- Conclusion: direct live writes through `pyrekordbox` are not viable.
- Live performance additions should use a non-DB workflow, such as `.m3u8`, Rekordbox XML/Bridge, or watched folder style import, then apply tags and smart playlists after Rekordbox is closed.

## Implemented Features

### Spotify Auth And Playlists

- Spotify PKCE auth flow.
- Spotify playlist fetching.
- Playlist cards with cover artwork in the event import flow.
- Dropdowns/selectors for playlist use in library and mapping screens.

### Event Imports

- Event import from Spotify playlist.
- Review table with statuses:
  - `matched`
  - `missing`
  - `ambiguous`
  - `ready`
  - `applied`
- Track comparison shows requested Spotify metadata and matched Rekordbox metadata.
- Manual staging scan.
- `Refresh Folder` button for manually added or removed files.
- Removed staging files are reconciled back to `missing`.
- Partial apply is allowed for currently `matched` and `ready` tracks.
- Temporary event deletion flow exists.
- Event deletion protects tracks that have other tags or are under permanent/manual collection paths.

### Permanent Library

- Permanent Spotify sources are separate from temporary events.
- Permanent curation is tag-first.
- Sources can show new-track badges from Spotify snapshot diff.
- Permanent imports move validated files into `_rekordbox_sync/permanent`.
- Permanent tag-to-Spotify-playlist mappings exist.

### Acquisition / Deemix

- Acquisition is manual through `Download`, not automatic.
- Global Download & Match Center exists conceptually and in UI.
- Acquisition jobs are persisted.
- Payload persistence was reduced to avoid oversized Deezer/queue objects and track tokens.
- Staging scan reconciles downloaded or deleted files.

### UI/UX

- Renderer was refactored toward the `new_ui_ux` prototype.
- Vue was kept.
- Tailwind was added.
- Dark studio-style shell was added.
- Navigation was reorganized around:
  - Dashboard
  - My Library
  - Event Imports
  - Download & Match Center / Sync Hub
  - Settings

## Rekordbox Structure Decisions

Event MyTags:

- Temporary event tags go under the Rekordbox MyTag category `Situation`.

Event smart playlists:

- Temporary event smart playlists go into a Rekordbox playlist folder named `Event Imports`.
- Event smart playlists should be placed at the top of that folder.

Smart playlist rule format:

- Rekordbox smart playlist conditions for `myTag` must use the MyTag numeric ID, not the tag name.
- Large Rekordbox IDs may need signed 32-bit conversion for smart playlist XML compatibility.

## Important Bug Fixes

### Event Smart Playlist Bug

Problem:

- `Nouvel an St Sulpice - Smart` was created at the bottom of root.
- The event MyTag was created as an orphan with `ParentID='0'`.
- The smart playlist condition used `ValueLeft="Nouvel an St Sulpice"` instead of the MyTag ID.

Fix:

- Event MyTags are created or repaired under `Situation`.
- Event smart playlists are created or repaired under `Event Imports`.
- Smart playlist conditions now use the Rekordbox MyTag ID.
- Existing event structure can be repaired through:
  `POST /api/events/{event_id}/repair-rekordbox-structure`

### SQLAlchemy Primary Key Sort Bug

Problem:

- `pyrekordbox.generate_unused_id()` returns `int`.
- Rekordbox ID columns are `VARCHAR`.
- Mixing `int` and `str` primary keys caused:
  `Could not sort objects by primary key; primary key values must be sortable in Python`.

Fix:

- Added `generated_rekordbox_id(...)` to coerce generated IDs to strings.
- Applied to:
  - `DjmdMyTag`
  - `DjmdSongMyTag`
- Replaced direct `database.add_content()` calls with local `add_rekordbox_content(...)` so `DjmdContent.ID`, `MasterSongID`, `rb_file_id`, `DeviceID`, and `MasterDBID` are strings before flush.

### Rekordbox XML Crash Recovery

Problem:

- Rekordbox opened into a broken-looking/empty interface after prior structure changes.
- The DB itself was still readable via `pyrekordbox`.
- `masterPlaylists6.xml` still contained deleted broken smart playlist nodes.

Fix performed:

- Created backup:
  `/Users/adriendidot/Library/CloudStorage/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique/_rekordbox_sync/backups/manual-xml-repair-20260529-081050`
- Removed deleted/broken XML nodes for:
  - old `Nouvel an St Sulpice - Smart`
  - old `Spéciales - Smart`
- Verified:
  - XML remained valid.
  - active `Nouvel an St Sulpice - Smart` remained in `Event Imports`.
  - active `Spéciales` remained intact.

## Current Known State

### Nouvel an St Sulpice

- Event structure was repaired.
- MyTag:
  - name: `Nouvel an St Sulpice`
  - parent: `Situation`
  - ID: `153200749`
- Active smart playlist:
  - name: `Nouvel an St Sulpice - Smart`
  - parent folder: `Event Imports`
  - position: `Seq=1`
  - condition: `myTag contains 153200749`
- Last observed smart playlist count after XML repair: `56`.

### Spéciales

- Active smart playlist remains intact.
- Rule uses MyTag ID `91698384`.
- Last observed count: `17`.

### Rallye Nanteuil

- Local event ID: `7`.
- Status before live-write experiment: `review`.
- Tracks:
  - `11` total.
  - `8` ready.
  - `3` matched.
  - `0` applied.
- Manual live-write experiment while Rekordbox was open:
  - backup created:
    `/Users/adriendidot/Library/CloudStorage/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique/_rekordbox_sync/backups/live-rekordbox-open-experiment-20260529-082023`
  - `pyrekordbox` refused commit.
  - no MyTag, smart playlist, or event-file content rows remained.
  - local event remained unchanged.

## Verification Commands Previously Passing

- `npm run test:service`
  - latest observed: `51 passed`
- `npm run typecheck`
  - passed
- `npm run build`
  - passed

## Highest-Risk Areas

- Direct Rekordbox DB writes remain risky and should stay behind the closed-app guard.
- `masterPlaylists6.xml` must stay synchronized with playlist DB rows.
- Deleted Rekordbox playlist rows can still appear in XML and destabilize Rekordbox.
- Any new direct table creation must coerce Rekordbox string IDs before SQLAlchemy flush.
- Copying `master.db` while Rekordbox is open is not a reliable backup in WAL mode; backup handling should be improved before any future live experiments.

## Recommended Next Steps

1. Keep direct DB mutation disabled while Rekordbox is running.
2. Build a proper live-performance workflow that does not write `master.db`:
   - generate or update `.m3u8` live playlists;
   - optionally use Rekordbox XML/Bridge;
   - optionally use a watched folder workflow;
   - apply MyTags and smart playlists only after Rekordbox is closed.
3. Add automated consistency checks before and after every Rekordbox mutation:
   - DB playlist rows vs `masterPlaylists6.xml`;
   - deleted playlists still present in XML;
   - smart playlist `myTag` conditions using tag names instead of numeric IDs;
   - mixed `int`/`str` IDs in pending SQLAlchemy objects where possible.
4. Add a safer backup strategy:
   - closed-app file copy for normal writes;
   - investigate SQLCipher-compatible online backup only if live backup is needed.
5. Add a dedicated repair command in the app UI for event playlist structure and XML cleanup, with preview and backup.
6. Improve user-facing error messages around Rekordbox running, backup reliability, and unsupported live DB writes.

## Useful References

- pyrekordbox database API:
  https://pyrekordbox.readthedocs.io/en/stable/generated/pyrekordbox.db6.database.html
- SQLite WAL:
  https://www.sqlite.org/wal.html
- SQLite Online Backup API:
  https://www.sqlite.org/backup.html
- SQLAlchemy session state management:
  https://docs.sqlalchemy.org/en/21/orm/session_state_management.html
