# Syncbox v1 POC Evidence Index

Authoritative index date: 2026-07-12

This index follows the nine-item macOS v1 order in `docs/PROMPT-05-implementation.md`. Earlier POC numbers mentioned in source comments are historical claims, not evidence.

Status meanings:

- **GO** — reproducible evidence satisfies the objective and recorded acceptance criteria.
- **NO-GO** — reproducible evidence disproves viability and records the fallback.
- **BLOCKED** — required evidence, fixtures, credentials, hardware, or implementation is unavailable.

No POC is GO at the Phase 1 baseline.

| # | POC | Current evidence | State | GO condition | Fallback |
|---|---|---|---|---|---|
| 1 | Sidecar process lifecycle on macOS | Reusable scripts exist in `shell/harness/`; no complete evidence record. Startup can send `/shutdown` to an unrelated service on port 8765. | **BLOCKED** | Record clean shutdown, TERM/KILL fallback, port release, bounded restart, backend-down, and single-instance behavior on macOS arm64 without targeting an unrelated service. | Keep lifecycle delivery blocked; do not replace the supervisor without owner approval. |
| 2 | PyInstaller onedir size and cold start | A 51 MiB arm64 onedir and a 72 MiB app exist, but no admissible cold-start record. Strict resource-seal verification fails and minimum macOS is inconsistent. | **BLOCKED** | Rebuild and record size, repeated cold starts, architecture, effective minimum OS, and functional local launch without Developer ID. | Keep PyInstaller; investigate another freezer only after measured evidence shows a decisive need. |
| 3 | SSE in the real macOS Tauri WebView | Unit tests use a fake `EventSource`. | **BLOCKED** | Demonstrate connection, progress events, reconnect, and graceful shutdown in the packaged WKWebView. | Investigate WebKit buffering first; change transport only with owner approval. |
| 4 | pyrekordbox writes on Rekordbox 7.x | Ten integration tests exist; the local fixture is absent. | **BLOCKED** | Run all ten tests through `poc/run_real_rekordbox_tests.py` with zero skips and unchanged source fixtures, then cover the remaining Phase 3 cases. | Block claims of complete `master.db` write support. |
| 5 | Deezer full-track streamrip | No implementation, pinned dependency, credentials, or evidence exists. | **BLOCKED** | With owner-provided credentials, prove a complete full-track download, real output path, in-memory secret handling, TLS verification, and packaging boundary. | Use the legal B2 purchase-link path; defer acquisition without blocking v1. |
| 6 | A3 bundle and audio calibration | Synthetic WAV unit tests exist; no labeled real corpus or admissible bundle delta. | **BLOCKED** | Record bundle delta and calibrated results on labeled real audio, including boundary and false-positive cases. | Use A3-lite or defer A3 if calibration is not reliable. |
| 7 | B2 purchase-link browser behavior | URL generation and UI wiring have unit coverage; no real browser/shop evidence. | **BLOCKED** | Open Beatport and Bandcamp searches through the macOS system browser for 5–10 labeled tracks and record result quality. | Remove a broken store entry at build time. |
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
