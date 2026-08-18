## 1. Directory Deletion Policy

- [x] 1.1 Extend the existing trash-first filesystem deletion helper to accept validated directories while preserving file behavior, explicit permanent-delete consent, and propagated recursive-deletion errors.
- [x] 1.2 Add focused platform helper tests for directory trash success, trash failure without consent, and recursive permanent deletion after consent.

## 2. Migration Planning and Cleanup

- [x] 2.1 Version the storage-migration plan and add explicit cleanup-directory entries with canonical path and directory identity state.
- [x] 2.2 Discover safe cleanup targets for migrating jobs and previously completed inactive jobs, while reporting unverifiable, unowned, active, or unsafe directories as ignored.
- [x] 2.3 Revalidate job-directory containment, symlink status, identity, job state, owner, and published destination immediately before cleanup.
- [x] 2.4 Trash the complete job directory only after migration commits, clear the legacy cleanup checkpoint only after success, and make cleanup-only retries idempotent without repeating copies or Rekordbox mutations.
- [x] 2.5 Add acquisition migration regression tests covering artwork and unexpected files, historical residual directories, changed or missing destinations, active jobs, symlink/path escapes, consent retries, and successful checkpoint clearing.

## 3. Health UI Integration

- [x] 3.1 Extend the storage-migration plan/result types and Health migration card to display cleanup-only directories, enable execution when only cleanup remains, and report migrated files and cleaned directories distinctly.
- [x] 3.2 Add the required English and French localization strings while reusing the existing API consent flow and migration action.
- [x] 3.3 Add a focused UI test or equivalent component check proving a cleanup-only plan is visible and executable.

## 4. Verification

- [x] 4.1 Run the focused platform, acquisition migration, API, and Health UI checks for the changed behavior.
- [x] 4.2 Run the repository's relevant sidecar and UI quality gates and validate the OpenSpec change in strict mode.
