## 1. ISRC matching for exact-source rows

- [x] 1.1 In `events_service.match_event_tracks`, after the provenance lookup yields no candidate and no path, run `matching.match` and accept only `method == "isrc"`; verify with tests in `sidecar/tests/test_events_service.py` covering: ISRC hit → `matched`/confidence 100, fuzzy-only hit → stays `missing`, remix with a different ISRC → `missing`, provenance path still wins.
- [x] 1.2 In `events_service.apply_event`, accept an exact-source `matched` row whose current snapshot content has the same normalized ISRC before the `eligible_file` demotion; verify with a test that an ISRC-matched row is tagged on apply and that a row whose content lost its ISRC is reclassified `missing` without aborting the apply.
- [x] 1.3 Confirm `claim_staged_files` still skips metadata scoring for exact-source rows; verify the existing claim tests pass unchanged.

## 2. Reconciliation module

- [x] 2.1 Create `sidecar/src/syncbox/event_source_reconcile.py` with `build_plan` producing `plan_version`, fingerprint, items (`rematch`/`replace`), `skipped` with reasons, and `isrc_coverage`; verify with unit tests over a fixture app DB + Rekordbox fixture for each table row of design decision 3 (ready hit, applied hit, ambiguous, no candidate, file outside staging, duplicate tagged elsewhere, missing ISRC).
- [x] 2.2 Implement `execute`: stale-plan refusal, one `mutate()` for all `replace` items reusing `rb_write.tag_content`/`untag_content`/`soft_delete_content`, app-DB transaction for every item, trash-first cleanup via `platform_os.delete_file` with the consent contract and `cleanup_pending` reporting; verify with tests for the happy path, stale plan rejection, trash refused before any change (row and file unchanged, 428, retry with consent), and trash refused after the commit (row repaired, file kept, consent requested, `cleanup` item, retry with consent).
- [x] 2.3 Add `GET/POST /api/events/source-reconciliation` in `api.py` following `acquisition_storage_migration` (dry_run default, plan echo, consent flag); verify with an API test in `sidecar/tests/test_api.py` exercising preview then execute.

## 3. Production ISRC check

- [x] 3.1 Run the preview against the owner's production application DB and Rekordbox (read-only GET) and record in `verification.md`: counts with/without ISRC, candidates found, the list of managed Deezer downloads lacking ISRC, and the count of ISRCs containing non-alphanumerics; verify the "without ISRC" list is empty before any execution. If it is not empty, stop and report the affected files instead of executing.

## 4. UI

- [x] 4.1 Add the reconciliation block to `ui/src/screens/health/BackupsTab.vue` (preview counts per action, coverage figures, execute button, consent prompt, result toast) with API types and `en`/`fr` strings; verify with a spec in `ui/src/screens/__tests__/health-tabs.spec.ts` covering preview rendering, execute call with the plan, and the consent retry.

## 5. Verification and docs

- [x] 5.1 Run the full sidecar and UI test suites; verify green.
- [ ] 5.2 Execute the reconciliation on production after the task 3.1 check, confirm in Rekordbox that each replaced event track points at the original content and that duplicates are gone, and record the outcome in `verification.md`.
- [x] 5.3 Update `docs/SPEC-UNIFIED.md` and the user docs sentence on exact-source matching to state the ISRC rule; verify the docs mention both the ISRC proof and the fuzzy exclusion.
