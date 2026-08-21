## 1. Schema

- [x] 1.1 Add migration `0010_event_track_origin.sql` introducing `event_tracks.origin` with a default, and backfill existing rows (`spotify_track_id` set → `playlist`, else `manual`); verify by running the migration against a copy of a real app DB and checking the resulting distribution
- [x] 1.2 Verify with a migration test that the backfill leaves no NULL and that a fresh database and a migrated one end with the same schema

## 2. Origin at every creation site

- [x] 2.1 Set `origin='playlist'` on the tracks imported by `events_create` and `origin='manual'` on tracks created by `events_add_track`, and verify with API tests that each path stores the expected value
- [x] 2.2 Expose `origin` on the event track payload and in `ui/src/api/types.ts`, and verify the UI typecheck passes — split across both halves: the payload carries it through `list_event_tracks`, `EventTrack.origin` is typed, `vue-tsc --noEmit` clean

## 3. Status vocabulary

- [x] 3.1 Introduce `removed_upstream` and exclude it from `PENDING_STATUSES`, `REMATCHED_STATUSES` and `CLAIMABLE_STATUSES`; verify with a unit test that an applied event with one `removed_upstream` row still computes as `applied`
- [x] 3.2 Exclude `removed_upstream` from the `pending_delta` aggregate in `events_list`, and verify with an API test that the badge count is unchanged by a departure
- [x] 3.3 Verify with a unit test that a `removed_upstream` track is not re-matched and does not claim a staged file

## 4. The diff

- [x] 4.1 Add `refresh_from_playlist(conn, event, spotify_client, ...)` to `events_service.py`: fetch via `library_service._collect_tracks`, collapse duplicate occurrences on `spotify_track_id`, and bucket the playlist-sourced rows into updated / added / departed; verify with a unit test over a fabricated playlist payload
- [x] 4.2 Implement the metadata update for surviving tracks and verify with a unit test that status, `content_id` and `staging_file_path` are untouched
- [x] 4.3 Implement the addition path reusing `add_track` with `origin='playlist'`, and verify with a unit test that on an applied event the new row carries `added_after_apply`
- [x] 4.4 Implement the departure path writing `removed_upstream` and saving `prior_status`, and verify with a unit test
- [x] 4.5 Verify with a unit test that `manual` and `adopted` rows are absent from all three buckets

## 5. Routes

- [x] 5.1 Add `POST /api/events/{id}/refresh` wired to the diff plus the existing `_try_match_event`, returning the three counts; verify with an API test that a playlist gaining and losing a track produces the expected counts
- [x] 5.2 Refuse the refresh on an event whose `spotify_playlist_id` starts with `manual:` and verify with an API test that the error is explicit
- [x] 5.3 Verify with an API test that a Spotify failure leaves every event track unchanged
- [x] 5.4 Verify with an API test that the route does not require Rekordbox to be closed
- [x] 5.5 Add `POST /api/events/{id}/tracks/{track_id}/keep` restoring `prior_status` and setting `origin='manual'`; verify with an API test that a second refresh does not re-signal the track

## 6. UI

- [x] 6.1 Add the refresh button to the Events workspace with its result summary, and verify in the running app against the real `jo-helo` event
- [x] 6.2 Add a departure signal — count and a `removed` filter chip — kept visually distinct from the pending-delta badge, and verify with a component test
- [x] 6.3 Add the per-row keep action and verify with a component test that it clears the signal
- [x] 6.4 Exclude `removed_upstream` from `eventCounts` in `ui/src/lib/events.ts` and verify the existing unit tests plus a new one for the departure case
- [x] 6.5 Add the FR and EN strings for the button, the summary, the signal and the keep action, and verify both locales have every key

## 7. Verification

- [x] 7.1 Run the sidecar test suite and the UI test + typecheck, and verify all pass — sidecar 719 passed / 11 skipped (same single pre-existing README failure deselected); UI 117 passed / 29 files, `vue-tsc --noEmit` clean
- [ ] 7.2 DEFERRED (owner, 2026-08-21) — on the real `jo-helo` event, refresh and verify the summary matches the actual Spotify playlist contents, that no Rekordbox write occurred (unchanged master.db fingerprint), and that the `+n` badge only moved by the number of added tracks. Blocked on test setup, not on the code: the owner does not have write access to that playlist, so the add / remove / put-back cases cannot be provoked. Covered by tests (14 sidecar + 8 UI). Needs either a playlist the owner owns, or a collaborator making the change. NOTE: not owning the playlist is the feature's primary use case, not a limitation — refresh only READS the playlist, and the point is to pick up changes someone else made.
