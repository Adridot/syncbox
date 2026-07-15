# Phase 2 Handoff — Event Ownership and Retained-Track Migration

Date: 2026-07-11

## Verdict

**READY FOR PHASE 3.**

The Phase 2 implementation, focused tests, UI, and real-fixture harness are complete. Phase 3 can now run the private-fixture and manual Rekordbox validation. This verdict does not claim production readiness: the real retained-track POC remains blocked until its private fixture is supplied and must pass before release acceptance.

## Completed Scope

### Ownership model

- Replaced the universal `protected` flag with the canonical ownership classes `app_managed`, `permanent_library`, and `external`.
- Classified only `<storage_root>/_syncbox/events/**` and `<storage_root>/_syncbox/inbox/**` as app-managed audio.
- Classified `<storage_root>/rekordbox/**` as the permanent library.
- Classified every other location, including backup directories, as external.
- Canonicalized absolute, volume-relative, missing, and symlinked path spellings before classification and comparison.
- Removed path ownership from duplicate keeper priority; keeper selection is now based on file presence, quality, date, and deterministic content ID.
- Kept metadata-only Smart Fixes ownership-neutral and removed former protected-track wording from touched code and UI.

### Exact event-delete planning

- Added a deterministic versioned deletion plan that lists, per track, content identity, title, artist, source path, ownership, retaining MyTags, action, destination, destination-reuse state, and ANLZ-update requirement.
- Added the four explicit actions: `already_permanent`, `migrate_to_collection`, `delete_with_event`, and `soft_delete_only`.
- Included the event MyTag, owned current/legacy smart playlists, XML artifacts, staging artifacts, and exact expected file deletions.
- Restricted playlist deletion to smart playlists below the active root-level `Event Imports` folder; unrelated homonymous playlists are not selected.
- Refused deletion when another Syncbox event shares the same default MyTag.
- Made execution require the exact preview payload. Database fingerprints, source state, destination collision state, active MyTags, support files, and cleanup files are revalidated server-side.
- Added explicit file-state hashes for cleanup safety and rejected replaced staging files before the Rekordbox mutation.

### Retained-track migration

- Migrated a staged track with another active MyTag to `<storage_root>/rekordbox/Collection/` before removing its event MyTag.
- Preserved the existing Rekordbox content ID and therefore its cues, beatgrid/analysis identity, non-event MyTags, and unrelated playlist memberships.
- Updated `FolderPath`, matching `OrgFolderPath`, `FileNameL`, and ANLZ PPTH values without allowing pyrekordbox to commit independently.
- Enumerated the exact ANLZ set using the same directory-level logic as installed pyrekordbox 0.4.4 and rejected changed or unsafe ANLZ paths.
- Reserved planned destinations across all tracks, preventing two same-name migrations from sharing one path accidentally.
- Implemented deterministic collision handling: reuse only identical unreferenced files; otherwise allocate ` - 2`, ` - 3`, and later suffixes.
- Implemented verified copy, flush, file and directory `fsync`, SHA-256 verification, and atomic no-overwrite publication using macOS `renamex_np(RENAME_EXCL)` with a same-directory hard-link fallback. Unsupported filesystems abort without overwriting.
- Kept every source file until the Rekordbox commit and destination verification completed.

### Backup, rollback, and cleanup

- Extended Rekordbox backups to include every affected ANLZ file and the playlist XML while preserving their relative layout.
- Added required-file validation and atomic support-file restoration.
- Pinned backups referenced by an unfinished event deletion so retention rotation cannot remove required recovery data. Pins are released only after the app-DB state is durably cleared or the event row is durably deleted.
- Added persisted event deletion phases (`planned`, `destinations_ready`, `backup_ready`, `mutating`, and `committed`) plus the exact plan and backup path.
- On precommit failure, restored modified support files, removed only destinations proven to have been published by the current attempt, kept all sources, and kept the event.
- Made interrupted precommit recovery conservative: ambiguous files are never deleted or overwritten; an exact existing destination is reused by hash, while ambiguous support changes abort with all audio and the event retained.
- Detected a committed Rekordbox transaction even if the app-DB journal update failed, and switched to cleanup-only retry without rolling back the committed destination.
- Revalidated every migration destination before any postcommit source deletion.
- Deleted only files present in the exact preview with the exact expected state. Partial cleanup and permanent-delete consent retries are idempotent.
- Reapplied the Rekordbox-running guard before recovery or cleanup writes.
- Kept Missing Files as an exceptional path for external loss, not a migration fallback.

### API and UI

- The event-delete API now accepts the echoed plan and forwards it unchanged to execution.
- The FR/EN confirmation modal renders the per-track action, ownership, retaining MyTags, source, destination, ANLZ consequence, playlists, XML artifacts, staging artifacts, and exact deletions.
- Ownership labels and help text are aligned across event deletion, duplicates, Untagged, and Settings.
- FR/EN key parity and the exact preview-to-execution payload are tested.

### Real-fixture hook

- Added `poc/run_event_migration_tests.py` and a strict `event-migration.json` manifest contract.
- The runner validates paths and symlinks, copies the fixture into an isolated temporary directory, runs one exact pytest node, rejects skips, and verifies that the original fixture's mode, size, mtime, and SHA-256 remain unchanged.
- The real POC test checks content-ID stability, cues, playlists, MyTags, database path fields, audio identity, ANLZ PPTH, non-PPTH ANLZ payload, backup coverage, and event cleanup.

## Phase 2 Files Changed

### Backend

- `sidecar/src/syncbox/event_delete.py`
- `sidecar/src/syncbox/events_service.py`
- `sidecar/src/syncbox/api.py`
- `sidecar/src/syncbox/rb.py`
- `sidecar/src/syncbox/rb_write.py`
- `sidecar/src/syncbox/dedup.py`
- `sidecar/src/syncbox/platform_os.py`
- `sidecar/src/syncbox/smartfixes.py`
- `sidecar/src/syncbox/smartfixes_run.py`
- `sidecar/src/syncbox/safety/paths.py`
- `sidecar/src/syncbox/safety/backup.py`
- `sidecar/src/syncbox/safety/mutate.py`
- `sidecar/src/syncbox/migrations/0004_event_delete_state.sql`

### Backend tests

- `sidecar/tests/test_event_delete.py`
- `sidecar/tests/test_events_service.py`
- `sidecar/tests/test_api.py`
- `sidecar/tests/test_rb.py`
- `sidecar/tests/test_rb_write.py`
- `sidecar/tests/test_dedup.py`
- `sidecar/tests/test_paths.py`
- `sidecar/tests/test_backup.py`
- `sidecar/tests/test_mutate.py`
- `sidecar/tests/test_smartfixes.py`

### UI

- `ui/src/api/types.ts`
- `ui/src/components/DeleteEventModal.vue`
- `ui/src/components/DuplicateGroupCard.vue`
- `ui/src/screens/SettingsScreen.vue`
- `ui/src/screens/health/UntaggedTab.vue`
- `ui/src/screens/health/SmartFixesTab.vue`
- `ui/src/i18n/en.ts`
- `ui/src/i18n/fr.ts`
- `ui/src/components/__tests__/delete-event-modal.spec.ts`
- `ui/src/screens/__tests__/health-tabs.spec.ts`
- `ui/src/screens/__tests__/settings.spec.ts`

### POC and handoff

- `poc/run_event_migration_tests.py`
- `poc/README.md`
- `poc/testdata/README.md`
- `docs/_handoffs/phase-02-event-migration.md`

Phase 1 artifacts already present in the working tree were preserved and are not attributed to Phase 2 here.

## Exact Validation Performed

- `cd sidecar && .venv/bin/python -m pytest -q`
  - Result: **447 passed, 11 skipped**.
  - The full run was allowed to open its required local ephemeral socket for the server collision test.
- Focused Phase 2 safety run:
  - `cd sidecar && .venv/bin/python -m pytest tests/test_event_delete.py tests/test_backup.py -q`
  - Result: **57 passed**.
- `cd ui && npm test`
  - Result: **19 test files passed, 59 tests passed**.
- `cd ui && npm run typecheck`
  - Result: passed.
- `cd ui && npm run build`
  - Result: passed; Vite production build completed.
- `cd shell/src-tauri && cargo test`
  - Result: passed; 0 Rust tests defined.
- `sidecar/.venv/bin/python -m compileall -q sidecar/src sidecar/tests poc`
  - Result: passed.
- `sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py --list`
  - Result: listed the ten Phase 1 real-fixture nodes, including the updated event lifecycle node.
- `sidecar/.venv/bin/python poc/run_event_migration_tests.py --list`
  - Result: listed exactly `tests/test_events_service.py::test_retained_track_migration_on_real_db`.
- `sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py --check`
  - Result: expected exit code 2 because `poc/testdata/master.db` is absent.
- `sidecar/.venv/bin/python poc/run_event_migration_tests.py --check`
  - Result: expected exit code 2 because `poc/testdata/event-migration.json` is absent.
- `git diff --check`
  - Result: passed.
- Read-only independent backend safety review
  - Final result: **READY**, with all reported blockers resolved.

No inline Ponytail debt markers remain in any Phase 2 file touched by this work.

## Remaining Skips and Blockers

- Ten tests are skipped because the private Phase 1 Rekordbox fixture `poc/testdata/master.db` and its companion XML are not present.
- One test is skipped because the private Phase 2 manifest `poc/testdata/event-migration.json` and its declared audio/ANLZ files are not present.
- POC #9 is therefore still **BLOCKED BY FIXTURE AVAILABILITY**. The runner and test hook are ready; no implementation blocker remains.
- No packaging, minimum-macOS-version, supervisor, signing, Windows, Keychain, Smart Fixes expansion, A3/B2, or B1 acquisition work was performed.

## Unresolved Risks for Phase 3

1. The real retained-track workflow has not yet been exercised against private Rekordbox data. Phase 3 must verify Rekordbox reopen, playback, cues, beatgrid, playlists, MyTags, PPTH readability, and byte-stable non-PPTH ANLZ data.
2. Pyrekordbox is an independent project and its stable 0.4.4 documentation warns that it can contain breaking or data-affecting defects. The implementation constrains its commit behavior and backs up every affected file, but target Rekordbox compatibility still needs real validation.
3. A destination volume that supports neither `renamex_np(RENAME_EXCL)` nor same-directory hard links will reject migration. This is a safe abort, but Phase 3 should record behavior on the intended APFS and any supported external volume format.
4. An externally changed support file during an ambiguous interrupted phase is intentionally not overwritten automatically. The event and all audio remain in place, and the user receives an actionable recovery error.
5. A process crash in the tiny interval after creating a pending-backup pin but before journaling its path can leave an extra backup pinned from rotation. This is a bounded storage-retention issue, not a collection or audio-loss risk; Phase 3 should include crash-state inventory in its recovery checks.
6. Events sharing the same default MyTag are refused at preview/execution time. A future product flow may offer an explicit disambiguation UI, but silent shared-tag deletion is not allowed.

## Research Basis

- [pyrekordbox 0.4.4 database API](https://pyrekordbox.readthedocs.io/en/stable/generated/pyrekordbox.db6.database.html) documents `update_content_path`, its ANLZ PPTH update, and the independent `commit` option used here with `commit=False`.
- [pyrekordbox ANLZ documentation](https://pyrekordbox.readthedocs.io/en/stable/tutorial/anlz.html) documents analysis-file parsing and saving.
- [Python 3.14 `os` documentation](https://docs.python.org/3.14/library/os.html) is the basis for file descriptors, hard links, replacement semantics, and `fsync`.
- The installed macOS `renamex_np(3)` manual was checked for `RENAME_EXCL` no-overwrite behavior and unsupported-filesystem errors.
- [pytest usage documentation](https://docs.pytest.org/en/stable/how-to/usage.html) is the basis for exact node-ID runner execution and exit handling.

## Phase 3 Entry Conditions

1. Supply the private Phase 1 fixture set and run `poc/run_real_rekordbox_tests.py` successfully.
2. Supply the Phase 2 `event-migration.json` fixture set and run `poc/run_event_migration_tests.py` successfully.
3. Perform the manual Rekordbox reopen/playback/analysis checks on a disposable copy.
4. Record actual filesystem behavior and any required recovery action without broadening Phase 2 into packaging or deferred features.

## Final release closure update — 2026-07-15

The historical fixture blockers above are closed. The private ten-node
Rekordbox harness and the dedicated retained-event migration harness passed
with their exact required pass counts, zero skips, and unchanged source
fixtures. Rekordbox 7.2.16 then passed the approved CommonCrypto manual
validation on the disposable event copy: reopen, playback, cues, beatgrid,
analysis, the non-event MyTag, playlist membership, volume-relative audio path,
and ANLZ PPTH readability. The live
Rekordbox directory was restored to its exact pre-validation 12,718-file
snapshot. POC #9 is **GO**; the original Phase 2 verdict and measurements above
remain the historical implementation handoff.
