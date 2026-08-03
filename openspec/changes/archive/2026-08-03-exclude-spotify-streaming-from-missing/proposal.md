# Exclude Spotify streaming tracks from Missing + shared Spotify resolver

## Why

Rekordbox 7 collections contain Spotify streaming tracks (`FolderPath = spotify:track:<id>`, Title/Artist obfuscated as `$A7:v1:…`). The snapshot loader treats them as files whose path does not exist, so `file_missing=True` and they flood the Missing center's collection scope with garbage titles, nonsense purchase links, useless relink candidates, and inflated Missing counts in the HealthPill. By definition a streaming track has no file to be missing — it is not acquirable, relinkable, or convertible.

Separately, the Spotify ID→title conversion the app already performs is scattered: the full resolution ladder (batched `GET /tracks` + anonymous oEmbed fallback) is welded into the Prestations module, while event-track addition uses its own single-track call without the fallback, and the `spotify:track:` prefix is defined in three places.

## What Changes

- The Rekordbox snapshot recognizes streaming rows: `spotify_track_id` extracted from `FolderPath`, obfuscated `$A…` Title/Artist scrubbed to NULL, and the row is never reported as a missing file.
- Streaming rows disappear from `/api/missing/collection` (list AND counts), from collection-scope acquisition, and from missing-remove — they were never "missing".
- Streaming rows are excluded from file-centric features fed by the snapshot: duplicate detection input and library-sync match candidates (a streaming reference can never satisfy "this track exists as a local file").
- The Spotify ID→title resolution ladder (batch `GET /tracks`, oEmbed fallback) is extracted from `performances.py` into a shared, table-agnostic function in `spotify.py`; Prestations and the event-track resolver both consume it. One `SPOTIFY_TRACK_PREFIX` constant replaces the three scattered literals.
- No UI changes required: counts and lists self-correct because the backend stops emitting the rows.

## Capabilities

### New Capabilities

- `spotify-streaming-tracks`: how Rekordbox streaming rows are recognized in the snapshot and kept out of missing/acquisition/relink/dedup/matching flows; obfuscated metadata is never surfaced raw.
- `spotify-track-resolution`: single shared Spotify ID→title/artist resolver (API batch with oEmbed fallback) used by every conversion site (Prestations history, event track addition).

### Modified Capabilities

<!-- none: openspec/specs/ has no main specs yet; both capabilities are introduced by this change -->

## Impact

- `sidecar/src/syncbox/rb.py` — `load_snapshot`: streaming detection, metadata scrub, `spotify_track_id` field.
- `sidecar/src/syncbox/spotify.py` — new `resolve_track_meta()` + `SPOTIFY_TRACK_PREFIX`; restores the module's "only outbound network calls live here" claim (oEmbed moves in).
- `sidecar/src/syncbox/performances.py` — `resolve_spotify_titles` delegates the network ladder, keeps its `plays` UPDATEs; drops its private `_SPOTIFY_PREFIX`/oEmbed code.
- `sidecar/src/syncbox/missing_service.py` — collection scope filters streaming rows.
- `sidecar/src/syncbox/api.py` — collection acquisition/remove lookups ignore streaming rows; `_track_resolver` rides the shared resolver; `spotify:track:` literal replaced; dedup input and sync candidates filtered at their call sites.
- `sidecar/src/syncbox/untagged.py` — reuses the shared prefix constant (behavior unchanged: stubs stay junk).
- Tests: `test_missing_service.py`, `test_performances*.py`, `test_spotify.py`, plus new streaming-row snapshot fixtures.
- UI: no code change; Missing center, HealthPill and MissingTab counts self-correct.
