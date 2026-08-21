## 1. Metadata helper

- [x] 1.1 Promote `rb_write._audio_metadata` to a public `audio_metadata` (keep the private alias if any internal caller reads better with it) and verify `sidecar/tests/test_rb_write.py` still passes unchanged
- [x] 1.2 Add a unit test covering the three tag cases the adoption pass relies on — complete tags, missing title tag, unreadable file returning `{}` — and verify it passes

## 2. Adoption pass

- [x] 2.1 Add `adopt_staged_files(conn, event)` to `events_service.py`: walk the staging dir with `relink.iter_audio_files`, skip every path already present in the event's `staging_file_path` values, and insert one `missing` event track per remaining file with metadata from `audio_metadata`; verify with a unit test that a dropped file produces exactly one track
- [x] 2.2 Implement the title fallback — full file name including extension, artist left unset — and verify with a unit test on a tagless fixture
- [x] 2.3 Verify with a unit test that a file already carried as another track's `staging_file_path` is not adopted
- [x] 2.4 Verify with a unit test that a nested subfolder's audio files are adopted and non-audio files are not

## 3. Wiring into claim

- [x] 3.1 Chain `events_claim` in `api.py` as claim → adopt → match → claim, and verify with an API test that a dropped file for a track absent from the collection ends `ready` with its `staging_file_path` set
- [x] 3.2 Verify with an API test that a dropped file whose metadata matches a collection entry ends `matched` on that entry and no second content row is created at apply
- [x] 3.3 Verify with an API test that a file satisfying an existing `missing` track is claimed by that track and not adopted
- [x] 3.4 Verify with an API test that claim (and therefore adoption) succeeds while Rekordbox is open, i.e. without `_require_rekordbox`

## 4. Rejecting an adopted track

- [x] 4.1 Change `events_track_remove` so a row with no `spotify_track_id` and a `staging_file_path` is set to `ignored` with its staged path retained instead of being deleted; verify with an API test
- [x] 4.2 Verify with an API test that a second claim after such a rejection does not re-adopt the file
- [x] 4.3 Verify with an API test that removing a Spotify-sourced unapplied track still deletes the row, and that removing an `applied` track is still refused
- [x] 4.4 Confirm `ignored` is excluded from `PENDING_STATUSES`, `REMATCHED_STATUSES`, `CLAIMABLE_STATUSES` and from the applicable set in `apply_event`, and verify with a test that an event whose only non-applied row is `ignored` computes as `applied`

## 5. UI

- [x] 5.1 Surface adopted tracks in the Events workspace with a marker distinguishing them from Spotify rows, and verify in the running app that the two files dropped into `jo-helo` appear after one Réclamer
- [x] 5.2 Surface the "already in your collection" outcome on a matched adopted track, and verify it renders in the component test
- [x] 5.3 Exclude `ignored` rows from `eventCounts` and from every filter chip except an explicit one if added, and verify `ui/src/lib/__tests__` covers it
- [x] 5.4 Add the FR and EN strings for the new marker, the duplicate notice and the rejection action, and verify both locales have every key

## 6. Verification

- [x] 6.1 Run the sidecar test suite and the UI test + typecheck, and verify all pass — sidecar 699 passed / 11 skipped (`test_readme_source_version_matches_canonical` deselected: pre-existing failure on `master`, the README rewrite dropped the `Current source version` line); UI 105 passed / 28 files, `vue-tsc --noEmit` clean
- [x] 6.2 Exercise the real `jo-helo` event end to end: click Réclamer, confirm both Via Con Me files become tracks, confirm the Ragna Schirmer track is untouched, and confirm the event's ready count moves by exactly the number of adopted files — done on a `.backup` copy of the production app DB, sidecar launched by the owner (TCC blocks the Dropbox listing for any process this session spawns): 27 -> 29 tracks, ready 12 -> 14, ids 28/29 adopted from the two Via Con Me files at confidence 100 with metadata read from the ID3 tags (no file-name fallback needed), track 19 (Ragna Schirmer) untouched at its original 16:39:07 claim, both rows rendered with the DÉPOSÉ marker in the running UI

## 7. Naming the duplicated entry (owner request)

- [x] 7.1 Add `duplicate_title` and `duplicate_artist` to the event track payload, resolved from the collection snapshot by the track's `content_id`, best-effort so a missing or unreadable snapshot leaves them null instead of failing the read; verify with API tests for both the resolved and the unavailable case
- [x] 7.2 Render the duplicate notice with the entry's title and artist when they are present, falling back to the current generic wording when they are not; verify with a component test for both

## 8. Consulting and undoing a rejection (owner request)

- [x] 8.1 Add `POST /api/events/{id}/tracks/{track_id}/restore`: set the row back to `missing` and run the same match-then-claim tail as `events_claim`, so the restored track re-derives its state; verify with an API test that a restored track returns `ready` and with another that a restored track whose file has since vanished returns `missing`
- [x] 8.2 Refuse the restore on a track that is not `ignored`, and verify with an API test
- [x] 8.3 Add an `ignored` filter chip to `EVENT_FILTERS` listing exactly the rejected rows and nothing else, keeping them out of every other chip and out of `eventCounts`; verify with unit tests in `ui/src/lib/__tests__/events.spec.ts`
- [x] 8.4 Keep the chip discreet when the event has no rejected track, and add the per-row restore action; verify with component tests
- [x] 8.5 Add the FR and EN strings for the chip, the restore action and the named duplicate notice, and verify both locales have every key

## 9. Verification (increment)

- [x] 9.1 Re-run the sidecar suite and the UI test + typecheck, and verify all pass — sidecar 704 passed / 11 skipped (same single pre-existing README failure deselected); UI 109 passed / 28 files, `vue-tsc --noEmit` clean
