# Syncbox v1 POC Evidence Index

Authoritative index date: 2026-07-14 (final release closure)

This index follows the nine-item macOS v1 order in `docs/PROMPT-05-implementation.md`. Earlier POC numbers mentioned in source comments are historical claims, not evidence.

Status meanings:

- **GO** — reproducible evidence satisfies the objective and recorded acceptance criteria.
- **NO-GO** — reproducible evidence disproves viability and records the fallback.
- **BLOCKED** — required evidence, fixtures, credentials, hardware, or implementation is unavailable.

Phase 5 returned `GO` for POC #5 after a real full-track Deezer run with a
local one-shot Premium credential. Phase 7 revalidated the exact local candidate
for POC #1, #2, #3, #5, and #6. B2 purchase links remain the primary v1
missing-track path; B1 is optional and disabled by default.

| # | POC | Current evidence | State | GO condition | Fallback |
|---|---|---|---|---|---|
| 1 | Sidecar process lifecycle on macOS | Source, frozen, app-embedded, optional source/frozen/packaged, single-instance, foreign/stale listener, immediate-failure, and supervisor exhaustion/recovery lanes pass. Graceful, TERM, and KILL leave no orphan and release ports 8765/8766. | **GO on the diagnostic candidate; final-byte rerun required** | Keep every lane green on the two-root final base bytes and on the public download. | Block the artifact on regression; retain the native supervisor until measured evidence requires a change. |
| 2 | PyInstaller onedir size and cold start | The final-candidate base ZIP is 29,295,890 bytes (`45404335…`); the optional ZIP is 17,340,517 bytes (`37fb7375…`). Both strict scanners pass and two consecutive optional freezes match. | **BLOCKED for independent-root proof** | Require byte-identical ZIPs and unpacked trees from two clean absolute source roots, then validate public downloads. | Keep onedir; investigate another freezer only after a measured failure. |
| 3 | SSE in the real macOS Tauri WebView | Packaged WKWebView navigation passed; UI completion/reconnect tests pass. Real packaged Spotify PKCE, refresh, forged-state rejection, invalid-grant recovery, listener shutdown, and port release pass with permanent SSE/API on 8766 and temporary callback on 8765. | **GO on the diagnostic candidate; final-byte rerun required** | Keep packaged completion/reconnect and OAuth port behavior green on final and downloaded bytes. | Investigate WebKit caching/buffering first; change transport only with owner approval. |
| 4 | pyrekordbox writes on Rekordbox 7.x | The ignored private CommonCrypto fixture passes all 10 integration nodes with zero skips; source size, timestamps, and hashes are unchanged. Rekordbox 7.2.16 previously passed every manual check on disposable copies before the provider switch. | **GO for automated CommonCrypto evidence; manual provider rerun pending owner-approved swap** | If authorized immediately beforehand, repeat the safe disposable data-directory swap and walkthrough. | Block release on any mutation or safety regression; never weaken the guard. |
| 5 | Deezer full-track streamrip | [Phase 5](../docs/_handoffs/phase-05-b1-acquisition.md) proved a full 337.56-second track with a one-shot local Premium credential. The current Deezer-only optional ZIP includes pinned Pillow artwork support and passes strict license, frozen-runtime, native, provider, signature, and secret scans. | **BLOCKED for final artwork/public evidence** | Prove embedded artwork in source, frozen, installed, and packaged lanes on the final hash, then repeat on the public download. | Keep B2 primary. If the live gate fails, do not publish the component; the base remains functional. |
| 6 | A3 bundle and audio calibration | The deterministic 12-case corpus ran identically in source, fresh PyInstaller onedir, and the sidecar embedded in a fresh app. Spectral-only detection cannot safely separate transcodes from legitimate band-limited masters. | **NO-GO for full A3** | No threshold-only detector may emit a keeper penalty until a real labeled corpus proves safe separation. | Conservative fallback active: sub-threshold is `incertain` and keeper-neutral; full detection is deferred. |
| 7 | B2 purchase-link browser behavior | Eight Beatport and Bandcamp searches loaded through browser tooling. Templates work, but first-result relevance is store/catalog dependent and intentionally not resolved by the sidecar. | **GO with documented relevance limits** | Keep both templates browser-only and rerun the sample when either store changes its search format. | Remove a broken store entry at build time; never add sidecar scraping. |
| 8 | Smart Fixes exact payload and idempotence | Synthetic coverage and the copied-real CommonCrypto node pass. Every previewed field matches the copied database, the second preview is empty, and all source fixtures remain unchanged. | **GO** | Keep exact payload, deterministic order, freshness, safety, and idempotence green. | Do not release Smart Fixes after any exact-payload, guard, or manual regression. |
| 9 | Retained-event-track migration with ANLZ preservation | The CommonCrypto copied-fixture harness passes once with zero skips across eight declared files; all sources remain unchanged. The earlier Rekordbox 7.2.16 disposable-copy walkthrough passed playback, cues, beatgrid, analysis, MyTags, playlists, paths, and ANLZ PPTH. | **GO for automated provider evidence; manual provider rerun pending owner-approved swap** | If authorized, repeat the exact manual walkthrough with the CommonCrypto candidate. | Keep deletion of affected retained staging tracks blocked after any regression; never weaken the guard. |

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

Fixture preparation is documented in `poc/testdata/README.md`. On 2026-07-14,
the exact ten-node run passed with zero skips and unchanged fixture sources.
Rekordbox 7.2.16 subsequently passed the complete manual checklist on the
disposable copies; the live library was restored byte-for-byte after the
approved swap procedure.

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
empty. The node passed once with zero skips on 2026-07-13 and the source
fixture was unchanged. On 2026-07-14, Rekordbox 7.2.16 displayed the expected
Smart Fix values on the disposable mutated copy. POC #8 is **GO**.

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

The real fixture test passed once with zero skips on 2026-07-13 and all
declared sources were unchanged. On 2026-07-14, Rekordbox 7.2.16 passed the
required playback, cue, beatgrid, analysis, MyTag, playlist,
volume-relative-path, and ANLZ PPTH checks on the disposable copy. POC #9 is
**GO**.
