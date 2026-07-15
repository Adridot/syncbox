# Syncbox v1 POC Evidence Index

Authoritative index date: 2026-07-15 (final release closure)

This index follows the nine-item macOS v1 order in `docs/PROMPT-05-implementation.md`. Earlier POC numbers mentioned in source comments are historical claims, not evidence.

Status meanings:

- **GO** — reproducible evidence satisfies the objective and recorded acceptance criteria.
- **NO-GO** — reproducible evidence disproves viability and records the fallback.
- **BLOCKED** — required evidence, fixtures, credentials, hardware, or implementation is unavailable.

Phase 5 returned `GO` for POC #5 after a real full-track Deezer run with a
local one-shot Premium credential. Phase 7 revalidated the exact final and
publicly downloaded bytes for POC #1, #2, #3, #5, and #6, including two-root
equality and the post-runtime scanner. B2 purchase links remain the primary v1
missing-track path; B1 is optional and disabled by default.

| # | POC | Current evidence | State | GO condition | Fallback |
|---|---|---|---|---|---|
| 1 | Sidecar process lifecycle on macOS | Source, frozen, app-embedded, optional source/frozen/packaged, single-instance, foreign/stale listener, immediate-failure, and supervisor exhaustion/recovery lanes pass on the exact reproducible and publicly downloaded bytes. Graceful, TERM, and KILL leave no orphan and release ports 8765/8766. | **GO** | Keep every lane green on future release bytes. | Block the artifact on regression; retain the native supervisor until measured evidence requires a change. |
| 2 | PyInstaller onedir size and cold start | The published base ZIP is 29,296,019 bytes (`296fbece…`); the optional ZIP is 17,340,644 bytes (`13976d4b…`). Two clean absolute roots produced byte-identical ZIPs and unpacked trees; the public downloads match and both strict scanners pass. | **GO** | Preserve both exact hashes for 0.2.2. | Keep onedir; investigate another freezer only after a measured failure. |
| 3 | SSE in the real macOS Tauri WebView | The exact final and public-download WKWebView navigation and normal-quit walkthroughs passed; UI completion/reconnect tests pass. Real packaged Spotify PKCE, refresh, forged-state rejection, invalid-grant recovery, listener shutdown, and port release pass with permanent SSE/API on 8766 and temporary callback on 8765. | **GO** | Keep packaged completion/reconnect and OAuth port behavior green on future bytes. | Investigate WebKit caching/buffering first; change transport only with owner approval. |
| 4 | pyrekordbox writes on Rekordbox 7.x | The ignored private CommonCrypto fixture passes all 10 integration nodes with zero skips; source size, timestamps, and hashes are unchanged. The owner-approved Rekordbox 7.2.16 CommonCrypto walkthrough passed on disposable Smart Fix and retained-event copies, then restored the untouched live directory exactly. | **GO** | Keep the exact automated and manual safety assertions green. | Block release on any mutation or safety regression; never weaken the guard. |
| 5 | Deezer full-track streamrip | [Phase 5](../docs/_handoffs/phase-05-b1-acquisition.md) proved a full 337.56-second track with a one-shot local Premium credential. The final artifact passed real artwork embedding through source, exact frozen, base-boundary installation, and packaged-app lanes; the byte-identical public ZIP passed scanner and packaged installation/runtime checks. | **GO** | Keep the exact optional hash and repeat the live credential gate only for changed bytes. | Keep B2 primary. If a future public asset fails validation, remove it; the base remains functional. |
| 6 | A3 bundle and audio calibration | The deterministic 12-case corpus ran identically in source, fresh PyInstaller onedir, and the sidecar embedded in a fresh app. Spectral-only detection cannot safely separate transcodes from legitimate band-limited masters. | **NO-GO for full A3** | No threshold-only detector may emit a keeper penalty until a real labeled corpus proves safe separation. | Conservative fallback active: sub-threshold is `incertain` and keeper-neutral; full detection is deferred. |
| 7 | B2 purchase-link browser behavior | Eight Beatport and Bandcamp searches loaded through browser tooling. Templates work, but first-result relevance is store/catalog dependent and intentionally not resolved by the sidecar. | **GO with documented relevance limits** | Keep both templates browser-only and rerun the sample when either store changes its search format. | Remove a broken store entry at build time; never add sidecar scraping. |
| 8 | Smart Fixes exact payload and idempotence | Synthetic coverage and the copied-real CommonCrypto node pass. Every previewed field matches the copied database, the second preview is empty, and all source fixtures remain unchanged. | **GO** | Keep exact payload, deterministic order, freshness, safety, and idempotence green. | Do not release Smart Fixes after any exact-payload, guard, or manual regression. |
| 9 | Retained-event-track migration with ANLZ preservation | The CommonCrypto copied-fixture harness passes once with zero skips across seven declared files; all sources remain unchanged. The derived database uses DELETE journal mode, so no empty or inapplicable WAL/SHM is retained. The owner-approved Rekordbox 7.2.16 CommonCrypto walkthrough passed playback, cues, beatgrid, analysis, non-event MyTags, playlists, volume path, and ANLZ PPTH on the disposable migrated copy. | **GO** | Keep the exact migration, source-integrity, and manual assertions green. | Keep deletion of affected retained staging tracks blocked after any regression; never weaken the guard. |

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

Fixture preparation is documented in `poc/testdata/README.md`. On 2026-07-15,
the exact ten-node run passed with zero skips and unchanged fixture sources.
Rekordbox 7.2.16 subsequently passed the complete CommonCrypto manual checklist
on the disposable Smart Fix and retained-event copies. The original 12,718-file
live directory was restored byte-for-byte with manifest SHA-256
`1b523e27bf96539f0d498a65a57240ff64eba7648c5d3810b107fee07042c074`
after the approved swap procedure.

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
empty. The node passed once with zero skips on 2026-07-15 and the source
fixture was unchanged. Rekordbox 7.2.16 displayed the expected Smart Fix
values on the CommonCrypto disposable mutated copy. POC #8 is **GO**.

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

The real fixture test passed once with zero skips on 2026-07-15 and all
declared sources were unchanged. Rekordbox 7.2.16 passed the required playback,
cue, beatgrid, analysis, non-event MyTag, playlist, volume-relative-path, and
ANLZ PPTH checks on the CommonCrypto disposable copy. POC #9 is **GO**.
