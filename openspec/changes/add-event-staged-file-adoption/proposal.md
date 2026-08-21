## Why

A file dropped into an event's `audio/` staging folder is only ever seen if an event track is already waiting for it: `claim_staged_files` loops over tracks in `CLAIMABLE_STATUSES`, never over files. A file that matches no existing track is invisible — it appears nowhere in the UI, and `build_plan` still lists it in `expected_file_deletions`, so it is trashed with the event without ever having been shown.

This blocks a real workflow: tracks that do not exist on Spotify (speech beds, YouTube rips, personal MP3s) cannot be added to an event by dropping them next to the acquisition downloads, which is where the user expects to put them.

## What Changes

- `POST /api/events/{id}/claim` gains an adoption step: audio files under the event staging dir that are referenced by no `event_tracks.staging_file_path` become new event tracks.
- Adopted tracks take their metadata from the file's own audio tags (title, artist, duration, ISRC). When the file carries no usable title tag, the full file name (extension included) is used as the title and the artist is left unset.
- Adopted tracks are inserted with `spotify_track_id` NULL and status `missing`, so the existing automatic match step and the existing claim step converge on the correct outcome with no new write path: either the track matches an existing Rekordbox collection entry, or it claims the file it came from and becomes `ready` for the existing apply / re-apply flow.
- `DELETE /api/events/{id}/tracks/{track_id}` on an adopted track no longer deletes the row: it moves it to status `ignored` while keeping its `staging_file_path`, so the next claim does not re-adopt the same file.
- Scope is events only. The library `inbox` / Missing center flow is unchanged.

## Capabilities

### New Capabilities
- `event-staged-file-adoption`: audio files dropped into an event's staging folder become event tracks, with metadata read from the file and a stable outcome for files the user does not want.

### Modified Capabilities

<!-- None: no existing spec's requirements change. -->

## Impact

- `sidecar/src/syncbox/events_service.py` — new adoption pass alongside `claim_staged_files`; `ignored` handling.
- `sidecar/src/syncbox/api.py` — `events_claim` orchestration, `events_track_remove` outcome for adopted rows.
- `sidecar/src/syncbox/rb_write.py` — `_audio_metadata` promoted to a public helper so the adoption pass can reuse it verbatim.
- `ui/src/screens/EventsScreen.vue`, `ui/src/lib/events.ts`, `ui/src/i18n/*` — surfacing adopted tracks and the "already in your collection" case.
- No schema migration, no Rekordbox write, no new dependency (mutagen is already used).
