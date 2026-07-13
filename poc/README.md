# Syncbox v1 POC Evidence Index

Authoritative index date: 2026-07-13 (Phase 6)

This index follows the nine-item macOS v1 order in `docs/PROMPT-05-implementation.md`. Earlier POC numbers mentioned in source comments are historical claims, not evidence.

Status meanings:

- **GO** — reproducible evidence satisfies the objective and recorded acceptance criteria.
- **NO-GO** — reproducible evidence disproves viability and records the fallback.
- **BLOCKED** — required evidence, fixtures, credentials, hardware, or implementation is unavailable.

Phase 6 adds admissible evidence for POC #1, #2, and #3. Phase 5 left POC #5
BLOCKED because no authorized Premium ARL was available; B2 is the only v1
missing-track acquisition path.

| # | POC | Current evidence | State | GO condition | Fallback |
|---|---|---|---|---|---|
| 1 | Sidecar process lifecycle on macOS | [Phase 6 evidence](08-phase6-packaging-lifecycle.md) covers source, frozen, and packaged process groups; graceful/TERM/KILL shutdown; no orphan; port release; exact stale cleanup; foreign collision; 1/2/4 restart exhaustion; backend-down; manual restart; and single instance. | **GO** | Keep the complete harness matrix green on the exact release artifact. | Block the artifact on regression; retain the native supervisor until measured evidence requires a change. |
| 2 | PyInstaller onedir size and cold start | [Phase 6 evidence](08-phase6-packaging-lifecycle.md) records the final 62,160,929-byte app tree, 32,461,008-byte ZIP, 6.47-second final frozen start, 8.19-second observed cold maximum, arm64-only native tree, macOS 14 effective minimum, ad-hoc signature, native imports, exact archive match, and scans. | **GO for functional local artifact** | Re-run the scanner and lifecycle suite on every release candidate. Public redistribution has separate notice/signing gates. | Keep onedir; investigate another freezer only after a concrete measured failure. |
| 3 | SSE in the real macOS Tauri WebView | [Phase 6 evidence](08-phase6-packaging-lifecycle.md) shows packaged completion activity, EventSource reconnect after supervised sidecar restart, no-store loopback responses, and clean process shutdown. The system-browser OAuth boundary was exercised; live token exchange remains credential-limited. | **GO for SSE** | Keep packaged completion/reconnect behavior green; run full OAuth with owner consent before claiming live authorization evidence. | Investigate WebKit caching/buffering first; change transport only with owner approval. |
| 4 | pyrekordbox writes on Rekordbox 7.x | Ten integration tests exist; the local fixture is absent. | **BLOCKED** | Run all ten tests through `poc/run_real_rekordbox_tests.py` with zero skips and unchanged source fixtures, then cover the remaining Phase 3 cases. | Block claims of complete `master.db` write support. |
| 5 | Deezer full-track streamrip | Phase 5 found no Premium ARL in authorized local state, so no full-track POC ran and no B1 implementation was authorized. The Phase 6 base artifact contains no streamrip/Deezer component. | **BLOCKED** | Restart the dedicated Phase 5 gate only if the owner supplies a Premium ARL locally and consents to the complete POC. | B2 Beatport/Bandcamp browser searches and local relink are the only v1 path. |
| 6 | A3 bundle and audio calibration | The deterministic 12-case corpus ran identically in source, fresh PyInstaller onedir, and the sidecar embedded in a fresh app. Spectral-only detection cannot safely separate transcodes from legitimate band-limited masters. | **NO-GO for full A3** | No threshold-only detector may emit a keeper penalty until a real labeled corpus proves safe separation. | Conservative fallback active: sub-threshold is `incertain` and keeper-neutral; full detection is deferred. |
| 7 | B2 purchase-link browser behavior | Eight Beatport and Bandcamp searches loaded through browser tooling. Templates work, but first-result relevance is store/catalog dependent and intentionally not resolved by the sidecar. | **GO with documented relevance limits** | Keep both templates browser-only and rerun the sample when either store changes its search format. | Remove a broken store entry at build time; never add sidecar scraping. |
| 8 | Smart Fixes exact payload and idempotence | Synthetic catalog, API, mutation-order, backup, rollback, ownership-neutrality, and adversarial payload coverage passes. The copied-real-fixture test verifies exact written values and idempotence but remains skipped because the private fixture is absent. | **BLOCKED** | Run `tests/test_rb_write.py::test_smartfixes_runner_end_to_end` through the copied-fixture harness with zero skips, then verify the resulting metadata in Rekordbox 7.x. | Do not claim release readiness for Smart Fixes; disable or defer it if the real gate cannot run. |
| 9 | Retained-event-track migration with ANLZ preservation | A dedicated copied-fixture harness and manifest contract exist; no local fixture or execution evidence is recorded. | **BLOCKED** | Run `test_retained_track_migration_on_real_db` through `poc/run_event_migration_tests.py` with one pass, zero skips, and unchanged sources; then record the required macOS/Rekordbox evidence. | Keep deletion of affected retained staging tracks blocked until safe behavior exists. |

## Evidence README contract

Create a POC evidence directory only when the POC is actually executed. Its English README must contain:

1. objective;
2. risk being tested;
3. environment;
4. dependency versions;
5. exact commands;
6. expected result;
7. actual result;
8. measurements;
9. GO, NO-GO, or BLOCKED;
10. fallback;
11. date.

Do not commit real Rekordbox databases, user audio, ANLZ files, credentials, tokens, personal paths, or build artifacts.

## POC #4 real-Rekordbox harness

From the repository root:

```sh
sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py --list
sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py --check
sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py
```

Fixture preparation is documented in `poc/testdata/README.md`.

## POC #8 Smart Fixes evidence

The deterministic and safety behavior is reproducible without private data:

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  -p no:cacheprovider tests/test_smartfixes.py tests/test_api.py
```

This covers the fixed catalog, positive and negative examples, composition,
fixpoints, ownership neutrality, exact complete-payload revalidation,
Rekordbox-running behavior, freshness, backup-before-write, and rollback.

The real mutation gate is the existing selected node:

```text
tests/test_rb_write.py::test_smartfixes_runner_end_to_end
```

It runs only on a copied `poc/testdata/master.db` through
`poc/run_real_rekordbox_tests.py`. It now compares every previewed field to the
value read back from the copied database and requires the next preview to be
empty. POC #8 remains **BLOCKED** until that node passes and Rekordbox 7.x
opens the copied result successfully. Synthetic tests do not replace this
release gate.

## POC #9 retained-track migration harness

This harness is separate so the POC #4 runner remains an exact ten-test contract:

```sh
sidecar/.venv/bin/python poc/run_event_migration_tests.py --list
sidecar/.venv/bin/python poc/run_event_migration_tests.py --check
sidecar/.venv/bin/python poc/run_event_migration_tests.py
```

The runner validates and copies the declared local fixtures into a temporary
directory, points the selected test at the copied `event-migration.json` through
`SYNCBOX_EVENT_MIGRATION_FIXTURE`, disables inherited pytest customization, and
checks source hashes and metadata again after the run. A skipped test is a
failure. The source fixture layout and manifest schema are documented in
`poc/testdata/README.md`.

POC #9 remains **BLOCKED** until the real fixture test runs successfully and its
required macOS/Rekordbox evidence is recorded. The presence of this harness is
not evidence that migration has passed.
