## Why

An event created from a Spotify playlist takes a one-shot snapshot of that playlist: `events_create` fetches `/playlists/{id}` once, imports the tracks, and never reads the playlist again. The stored `spotify_playlist_id` is only used afterwards to render the attribution link. A track added to the playlist after the event was created never reaches the event, and a track removed from it is never signalled.

The library side already has the machinery for this — `sync_one_source` re-fetches, diffs, and reconciles on every run — but events have none of it. Today the only way to pick up a playlist change is to retype the links by hand, or to delete and recreate the event.

## What Changes

- New `POST /api/events/{id}/refresh`: re-fetches the event's Spotify playlist and reconciles it against the event's tracks. Application database only, no Rekordbox write, so it stays available while Rekordbox is open.
- Tracks added to the playlist since the last look are added to the event and, on an already-applied event, flagged as pending additions — which feeds the existing pending-delta badge and the existing re-apply flow with no change downstream.
- Tracks that have left the playlist are **signalled, never acted on**: they move to a `removed_upstream` status that is visible and reversible. This change writes nothing to Rekordbox on their behalf; executing the removal is the separate `add-event-track-removal` change.
- A "keep" action clears the signal and returns the track to its previous status, so a track the user deliberately keeps is not re-signalled on every refresh.
- Metadata of tracks still in the playlist is refreshed from Spotify, as the library sync already does.
- **Schema migration**: `event_tracks` gains an `origin` column (`playlist` | `manual` | `adopted`). Only `playlist` rows take part in the diff, so tracks added by link, typed by hand, or adopted from a staged file are never mistaken for playlist removals.
- Manual events (`spotify_playlist_id` starting with `manual:`) reject the refresh.

## Capabilities

### New Capabilities
- `event-playlist-refresh`: an event backed by a Spotify playlist can be reconciled with that playlist on demand — additions imported, departures signalled — without deleting and recreating the event.

### Modified Capabilities

<!-- None: no existing spec's requirements change. -->

## Impact

- **Migration 0010** — `event_tracks.origin`, backfilled from existing rows: `spotify_track_id` present → `playlist`; absent but holding a `staging_file_path` → `adopted`; otherwise `manual`.
- `sidecar/src/syncbox/events_service.py` — the diff and the new statuses.
- `sidecar/src/syncbox/api.py` — the `refresh` and "keep" routes; `events_create` and `events_add_track` set `origin`; the `pending_delta` aggregate must exclude `removed_upstream`.
- `sidecar/src/syncbox/library_service.py` — `_collect_tracks` is reused verbatim for the fetch, as `events_create` already does.
- `ui/src/screens/EventsScreen.vue`, `ui/src/lib/events.ts`, `ui/src/api/types.ts`, `ui/src/i18n/*` — the refresh button, the departure signal and its keep action.
- `add-event-staged-file-adoption` has landed, so the `adopted` value is live from the start and the payload's `adopted` flag stops being inferred from `spotify_track_id`/`staging_file_path` and reads `origin` directly — which removes that inference's known false positive on a manually typed track that later claimed a staged file.
