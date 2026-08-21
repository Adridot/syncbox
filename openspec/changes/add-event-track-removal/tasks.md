## 1. Share the classification

- [ ] 1.1 Extract the four-way per-track decision from `event_delete.build_plan` into a pure `classify_removal(ownership, in_event_staging, retaining_ids)` and call it from `build_plan`; verify the full `sidecar/tests/test_event_delete.py` suite passes unchanged
- [ ] 1.2 Add direct unit tests for `classify_removal` covering all four outcomes, so the rule is tested once rather than only through the deletion path

## 2. The removal plan

- [ ] 2.1 Build `plan_removal(query, event, track_ids, storage_root, db_path, db_fingerprint)` returning a versioned plan with, per track, its action, its Rekordbox entry, its file and the file's expected state; verify with a unit test over a fixture event covering the untag-only and the delete-with-event outcomes
- [ ] 2.2 Group the batch by `content_id` and by `staging_file_path`, and mark an entry or file removable only when every event track holding it is in the batch; verify with a unit test using two tracks that share one non-empty ISRC and therefore one staged file and one content row
- [ ] 2.3 Report a staged track carrying another active MyTag as unresolved with kind `retained_by_other_mytag`, naming the tags and offering resolution options; verify with a unit test
- [ ] 2.4 Classify batch entries with no `content_id` as never-applied — row and staged file only, no Rekordbox write — and mark the plan as requiring no Rekordbox guard when the whole batch is of that kind; verify with a unit test

## 3. Execution

- [ ] 3.1 Implement `remove_tracks(...)` as a single `safety.mutate()` unit of work in the shape of `apply_event`: untag every planned entry, soft-delete the entries marked as brought in by the event, restore the playlist XML after commit; verify with a test against a fixture Rekordbox database that the event MyTag and smart playlist still exist afterwards
- [ ] 3.2 Refuse execution unless the echoed plan matches a freshly built one and the fingerprint is unchanged, refuse a plan for another event, and refuse a plan carrying unresolved cases; verify with three tests
- [ ] 3.3 Delete the planned staged files only after the Rekordbox commit, through `platform_os.delete_file` with the consent flag, verifying each file's recorded state first and keeping any file that changed; verify with a test that a mutated file is kept and reported
- [ ] 3.4 Verify with a test that the event's staging directory is not removed and that files belonging to remaining tracks survive
- [ ] 3.5 Update the removed tracks' application-database rows to status `removed` with `content_id` cleared and `staging_file_path` retained, and recompute the event status; verify with a test that the event stays applied when nothing pending remains
- [ ] 3.6 Verify with a test that a failure inside the Rekordbox write restores the backup and deletes no file

## 4. Routes

- [ ] 4.1 Add the preview route returning the plan plus its unresolved list, guarded on Rekordbox being closed only when the plan needs a Rekordbox write; verify with API tests for both cases
- [ ] 4.2 Add the execute route taking the echoed plan and the permanent-deletion consent, mirroring `events_delete`'s body contract; verify with an API test for the full round trip
- [ ] 4.3 Verify with an API test that a batch containing an unresolved track cannot be executed

## 5. UI

- [ ] 5.1 Add batch selection over the tracks signalled as having left the playlist, following the existing grouped-selection pattern; verify with a component test
- [ ] 5.2 Add the removal modal on `DeleteEventModal`'s preview-and-echo contract, listing per track what will happen — untagged, deleted from Rekordbox, file trashed — and verify with a component test that the CTA carries the exact counts
- [ ] 5.3 Render the unresolved list with its resolution options and disable the CTA while any remains; verify with a component test
- [ ] 5.4 Add the FR and EN strings for the modal, the per-track outcomes and the unresolved kinds, and verify both locales have every key

## 6. Verification

- [ ] 6.1 Run the sidecar test suite and the UI test + typecheck, and verify all pass
- [ ] 6.2 On a copy of a real event, remove a batch containing one track the user already owned and one the event brought in, then verify in Rekordbox that the first kept its entry and lost only the event tag, the second is gone, its file is in the trash, and the event's smart playlist still lists the remaining tracks
- [ ] 6.3 Verify that a full event deletion still behaves identically after the classification extraction, by running the deletion suite and one manual deletion of a fixture event that includes a retained track requiring migration
