# Syncbox Phase 1 Baseline and Coverage Report

> Historical baseline only. Every use of “current,” every version, measurement,
> blocker, and verdict below describes the 2026-07-11 Phase 1 snapshot. The
> current implementation and release evidence are authoritative in
> [SPEC-UNIFIED.md](SPEC-UNIFIED.md) and
> [_handoffs/final-release-closure.md](_handoffs/final-release-closure.md).

Date: 2026-07-11  
Target: Syncbox v1, macOS on Apple Silicon

## Result

Phase 1 established the current Python, UI, and Rust baseline, reconciled the owner overrides at specification level, mapped specification sections 3–8 to current code and tests, indexed the nine required POCs, and added the minimum local real-Rekordbox fixture harness.

No event migration, Smart Fixes, acquisition, or packaging behavior was implemented or changed. No POC is marked GO because the repository contains no admissible POC evidence.

## Owner-decision reconciliation

`docs/SPEC-UNIFIED.md` section 3.0 now overrides conflicting v1 text in sections 3–8:

| Topic | Syncbox v1 decision |
|---|---|
| Platform | macOS only; Apple Silicon is the validated architecture. Windows is v2 and Linux is out of scope. |
| Distribution | No Developer ID and no notarization. Apple Silicon code remains ad-hoc signed as required for local execution. Stapling and auto-update are deferred. |
| Secrets | Keep the encrypted local store. Keychain migration is deferred until a stable Developer ID exists. |
| File ownership | Replace the universal `protected` boolean with `app_managed`, `permanent_library`, and `external`. Safety is operation-specific. |
| Event deletion | A retained app-managed staging track must migrate to `<storage_root>/rekordbox/Collection/` before cleanup. |
| Deferred POCs | Windows, Developer ID signing, notarization, and Chromaprint are deferred, not failed. |
| Ponytail | It guides implementation; add no new rationale markers, and remove every existing executable-source marker before overall completion. |

The current implementation does not yet satisfy the ownership and retained-event-track decisions. Those contradictions are recorded below and intentionally left unchanged in Phase 1.

## Baseline

### Host and toolchain

| Item | Observed value |
|---|---|
| Host | macOS 26.5.1, arm64 |
| Rust target | `aarch64-apple-darwin` |
| Python | 3.14.5 |
| Node.js | 24.13.0 |
| pnpm | 10.29.3 |
| rustc / Cargo | 1.96.1 / 1.96.1 |
| Application version | 0.2.1 in Python, UI, shell, Cargo, and the current `.app` plist |

Important installed Python versions: pytest 9.1.1, pyrekordbox 0.4.4, sqlcipher3-wheels 0.5.7, SQLAlchemy 2.0.51, psutil 7.2.2, NumPy 2.5.0, miniaudio 1.71, Starlette 1.3.1, sse-starlette 3.4.5, uvicorn 0.49.0, certifi 2026.6.17, and PyInstaller 6.21.0.

Important resolved UI/Rust versions: Vitest 3.2.6, Vite 6.4.3, TypeScript 5.8.3, vue-tsc 2.2.12, Tauri CLI 2.11.4, Tauri 2.11.5, tauri-build 2.6.3, single-instance plugin 2.4.2, opener plugin 2.5.4, and dialog plugin 2.7.1.

### Commands and results

| Command | Result |
|---|---|
| `cd sidecar && .venv/bin/python -m pytest -q -rs` | PASS — 401 passed, 10 skipped in 5.77 s |
| `cd ui && pnpm test` | PASS — 18 files, 58 tests in 4.99 s |
| `cd ui && pnpm typecheck` | PASS |
| `cd ui && pnpm build` | PASS — 194 modules transformed; Vite build completed in 1.52 s |
| `cd shell/src-tauri && cargo check` | PASS — dev check completed in 3.33 s |

Warnings were limited to UI tests: 12 vue-i18n messages about missing parent scope and 9 messages about HTML-like `<racine>` text in a French translation. Python, typecheck, build, and Cargo produced no warnings in the recorded baseline.

### Reproducibility and existing artifacts

- Before Phase 1 edits, the worktree had no tracked modifications. Pre-existing untracked `.idea/` files and `docs/PROMPT-05-implementation.md` were preserved.
- `pnpm-lock.yaml` and `shell/src-tauri/Cargo.lock` exist.
- Python has no lockfile, runtime requirements are not version-pinned, and pytest is installed but not declared in `sidecar/pyproject.toml`. Phase 1 records this only; dependency and packaging changes are out of scope.
- Existing artifacts: 51 MiB PyInstaller onedir, 1.2 MiB UI `dist`, 72 MiB `Syncbox.app`, and a 33 MiB stale `Syncbox-0.2.0-macos-arm64.zip` while manifests declare 0.2.1.
- The current shell and sidecar launchers are thin arm64 binaries.
- The app and sidecar are ad-hoc signed with no TeamIdentifier, which is expected for local Apple Silicon code without Developer ID. Gatekeeper rejection is also expected for an ad-hoc app and is not, by itself, proof that the app cannot launch. Independently, `codesign --verify --deep --strict` fails with `code has no resources but signature indicates they must be present`; this resource-seal failure means the current bundle is not yet a verified functional local deliverable.
- The app plist advertises macOS 10.13, the shell and sidecar launchers require macOS 11.0, and the embedded Python binary requires macOS 26.0. The current bundle is effectively macOS 26-only. The supported minimum macOS version requires an owner decision before packaging work.

Existing artifacts and source comments are observations, not POC evidence.

## Specification-to-code coverage matrix

Status meanings:

- **IMPLEMENTED** — current behavior and focused automated coverage exist; real-environment evidence may still be pending.
- **PARTIAL** — a meaningful path exists, but required behavior or real-environment evidence is incomplete.
- **ABSENT** — the required behavior or evidence structure does not exist.
- **CONTRADICTORY** — current behavior or tests enforce a rule superseded by the owner decisions or conflict with a load-bearing invariant.

| Invariant / decision | Current implementation | Current test evidence | POC | Status and remaining action |
|---|---|---|---|---|
| Strict Rekordbox and `rekordboxAgent` guard with hygienic message | `sidecar/src/syncbox/safety/process_guard.py:44,57,79` | Mocked process coverage in `sidecar/tests/test_process_guard.py:73,78,98,157,165,190` | #4 BLOCKED | **IMPLEMENTED** in code; live-process and real-fixture evidence remains. |
| Timestamped backup, WAL/SHM, collision suffix, rotation, traversal-safe restore, pre-restore snapshot | `sidecar/src/syncbox/safety/backup.py:40,88,124,138,163` | Dummy-file coverage in `sidecar/tests/test_backup.py`; no real fixture | #4 BLOCKED | **IMPLEMENTED**; Phase 3 must validate the complete sequence on real data. |
| Single mutation path: guard, freshness, backup, commit/invalidate, rollback/close | `sidecar/src/syncbox/safety/mutate.py:32,66` | Unit sequencing/failure coverage; real round trip skipped at `sidecar/tests/test_mutate.py:296` | #4 BLOCKED | **IMPLEMENTED**; preserve unchanged and enable the real test. |
| Load-bearing 256/258 status tuples and active-only reads | `sidecar/src/syncbox/safety/statuses.py:14-27,46`; `sidecar/src/syncbox/rb.py:64` | Unit integer coverage; real filter/round trip skipped | #4 BLOCKED | **IMPLEMENTED**; real on-disk proof remains. |
| Snapshot cache shares the mutation fingerprint | `sidecar/src/syncbox/rb.py:116`; `sidecar/src/syncbox/safety/mutate.py:32` | `sidecar/tests/test_rb.py:30,44,64,75`; two real tests skipped | #4 BLOCKED | **IMPLEMENTED**; real read-only and invalidation evidence remains. |
| Volume-relative storage, absolute equivalence, exact-path TCC checks | `sidecar/src/syncbox/safety/paths.py:53,76,94,106,127` | `sidecar/tests/test_paths.py:36,84,132,156,173` | #4 BLOCKED | **PARTIAL**; core rule is unit-covered, real volume equivalence is not. Manual relink discovery still uses bounded enumeration. |
| Local loopback HTTP and origin restriction | `sidecar/src/syncbox/server.py:82,151,168`; `ui/src/api/client.ts:7`; CSP in `shell/src-tauri/tauri.conf.json:23` | `sidecar/tests/test_server.py:22,40,62`; UI API tests | #3 BLOCKED | **IMPLEMENTED** at unit level; real WKWebView transport evidence is absent. |
| Encrypted local secrets for unsigned v1 | `sidecar/src/syncbox/secrets.py:23`; Spotify integration in `sidecar/src/syncbox/spotify.py:65` | Ciphertext, permissions, persistence, and thread tests in `sidecar/tests/test_secrets.py` | — | **IMPLEMENTED** for Spotify. No Keychain work is needed; acquisition/ARL remains absent. |
| FR/EN parity and persisted locale | `ui/src/i18n/index.ts`; `ui/src/stores/settings.ts:29-58` | `ui/src/i18n/__tests__/parity.spec.ts:14-29` | — | **IMPLEMENTED**; ownership wording still reflects the obsolete universal protected zone. |
| Explicit `app_managed` / `permanent_library` / `external` ownership | No classifier. Snapshot still derives `protected` at `sidecar/src/syncbox/rb.py:89`; UI exposes it in `ui/src/api/types.ts:102-113` | Tests in `test_rb.py`, `test_dedup.py`, `test_api.py`, and UI codify the old boolean | #9 BLOCKED | **ABSENT**; implement only in the later ownership phase. |
| Shared normalization and ISRC-first/fuzzy matching | `sidecar/src/syncbox/matching.py:42,58,82,105,119`; reused by dedup | `sidecar/tests/test_matching.py` | #4 BLOCKED | **IMPLEMENTED**; real library/event integration remains fixture-dependent. |
| Dedup grouping, per-group confirmation, path-neutral keeper, safe membership/file order | `sidecar/src/syncbox/dedup.py:56,135,161,179`; `sidecar/src/syncbox/rb_write.py:374`; resolution in `sidecar/src/syncbox/api.py` | Unit/API ordering coverage; real membership move skipped at `test_rb_write.py:164` | #4 BLOCKED | **CONTRADICTORY**; keeper selection still prioritizes path-derived `protected`, and the server validates submitted IDs individually without re-deriving the scanned group membership. |
| Library diff, snapshot, matching states, pre-existing MyTags, delta apply | `sidecar/src/syncbox/library_service.py:96,153,181` | Unit/fake coverage; two real apply tests skipped | #4 BLOCKED | **IMPLEMENTED**; real MyTag/write evidence remains. |
| Event create, match, apply/reapply/delete and retained staging migration | `sidecar/src/syncbox/events_service.py:93,187,317,471,534,564` | Unit/fake lifecycle; real lifecycle skipped at `test_events_service.py:609` | #9 BLOCKED | **CONTRADICTORY**; a row with another MyTag is kept, but staging cleanup still deletes every event file. Mandatory v1 migration and ANLZ handling are absent and intentionally out of Phase 1. |
| Missing-file scopes, relink, D22 restore, ANLZ consent, soft-delete regardless former location | `sidecar/src/syncbox/missing_service.py:87,141,184,219`; removal in `sidecar/src/syncbox/api.py` | Unit/fake coverage; real relink skipped at `test_missing_service.py:265` | #4 BLOCKED | **CONTRADICTORY**; collection removal still refuses path-derived protected rows. |
| Untagged structural rules; reversible soft-delete; never delete audio | `sidecar/src/syncbox/untagged.py:22,33,50`; deletion in `sidecar/src/syncbox/api.py` | `sidecar/tests/test_untagged.py`; API protected-skip test | — | **CONTRADICTORY**; soft-delete/no-audio is correct, but the obsolete location guard remains. |
| Spotify PKCE, read-only scopes, bounded retries, fixed callback | `sidecar/src/syncbox/spotify.py:65,150`; callback in `sidecar/src/syncbox/server.py:82` | `sidecar/tests/test_spotify.py`; server callback tests | — | **IMPLEMENTED** at unit level. |
| One SQLite settings source, read-time defaults, blank protection, path validation, transfer | `sidecar/src/syncbox/settings.py:65,109`; `ui/src/stores/settings.ts` | `sidecar/tests/test_settings.py`; UI settings tests | — | **PARTIAL**; only two path settings exist and transfer behavior is narrower than the spec. No Phase 1 change. |
| Smart Fixes exact payload, deterministic composition, freshness, mutation-only path, no location filter | `sidecar/src/syncbox/smartfixes.py:65,75`; `sidecar/src/syncbox/smartfixes_run.py:22,39` | Unit/API coverage; real end-to-end skipped at `test_rb_write.py:265` | #8 BLOCKED | **PARTIAL**; safety aligns with the owner override, but artist/remixer extraction and casing fixes are absent, and real evidence is missing. |
| A3 read-only audio-quality diagnosis and keeper signal | `sidecar/src/syncbox/quality.py:40,46,103`; keeper integration in `dedup.py:150` | Synthetic WAV and pure classification tests in `sidecar/tests/test_quality.py` | #6 BLOCKED | **PARTIAL**; no labeled real corpus, calibration, or admissible bundle delta. |
| B2 purchase links with no app-side network and system-browser opener | `sidecar/src/syncbox/purchase_links.py:26,39`; `ui/src/components/MissingEntryList.vue:126-135` | URL/status tests and UI button tests | #7 BLOCKED | **PARTIAL**; no real browser or shop-result evidence. |
| Ordered `PRAGMA user_version` app migrations | `sidecar/src/syncbox/appdb.py:40,57,79` | `sidecar/tests/test_appdb.py` | — | **IMPLEMENTED**. |
| Tauri v2 + Vue + fixed loopback client | `shell/src-tauri/Cargo.toml`; `shell/src-tauri/tauri.conf.json`; `ui/package.json` | UI baseline and Cargo check pass | — | **IMPLEMENTED** as the current architecture. |
| One canonical SSE stream with native reconnection | `ui/src/api/sse.ts:39-60`; `ui/src/stores/jobs.ts:28-51` | Fake-EventSource tests only | #3 BLOCKED | **PARTIAL**; real macOS WKWebView evidence is absent. |
| Bounded sidecar supervision, process group, output drain, graceful shutdown, single instance | `shell/src-tauri/src/main.rs:35-205,237-283`; reusable scripts in `shell/harness/` | Assert harnesses exist but have no admissible result record | #1 BLOCKED | **PARTIAL**; behavior is substantial, but the POC has not been run and recorded. |
| Fixed-port collision must fail without targeting unrelated services | `post_shutdown()` and `reap_stale_sidecar()` in `shell/src-tauri/src/main.rs:155-215` | No focused identity test | #1 BLOCKED | **CONTRADICTORY**; startup sends `/shutdown` to any service answering on port 8765. Fix requires later owner-approved lifecycle work. |
| SPEC-selected plugin-Shell/async runtime supervisor | Current code uses `std::process::Command` and OS threads; no shell plugin dependency | Current harnesses target the manual implementation | #1 BLOCKED | **PARTIAL**; retain versus migrate is an unresolved structural choice. No Phase 1 change. |
| PyInstaller onedir bundled in a functional local arm64 app without Developer ID | `sidecar/sidecar.spec`; Tauri resource mapping and release path | Artifacts exist, but the strict resource-seal check fails and no measurement record exists | #2 BLOCKED | **PARTIAL**; packaging changes are deferred. Minimum macOS and bundle validity remain unresolved. |
| Optional Deezer full-track acquisition | No streamrip dependency or acquisition implementation | None | #5 BLOCKED | **ABSENT** and explicitly out of Phase 1. |
| No inline Ponytail rationale markers | 22 matches remain under `sidecar/src`, `ui/src`, and `shell/src-tauri/src` | Static `rg` inventory | — | **CONTRADICTORY**; Phase 1 leaves them unchanged and adds none. The overall completion check must return zero matches. |
| Reproducible POC evidence | No prior `poc/` directory existed; comments claimed POC results | Comments are inadmissible | #1–#9 BLOCKED | **ABSENT** at baseline; Phase 1 adds only the index and fixture harness. |

## Real-Rekordbox fixture inventory

The baseline has exactly ten conditional skips:

```text
tests/test_rb.py::test_snapshot_reads_real_db_readonly
tests/test_rb.py::test_snapshot_filters_soft_deleted
tests/test_mutate.py::test_integration_soft_delete_round_trip_on_real_db
tests/test_rb_write.py::test_full_write_flow_through_mutate
tests/test_rb_write.py::test_reassign_memberships_moves_active_links_to_keeper
tests/test_rb_write.py::test_smartfixes_runner_end_to_end
tests/test_library_service.py::test_apply_to_rekordbox_tags_and_imports
tests/test_library_service.py::test_apply_conflicts_on_missing_mytag_and_writes_nothing
tests/test_events_service.py::test_event_lifecycle_on_real_db
tests/test_missing_service.py::test_relink_collection_file_writes_stored_form_and_preserves_links
```

`poc/testdata/master.db` removes the skip condition. `poc/testdata/masterPlaylists6.xml` is also required for the complete set because three tests copy it unconditionally. WAL and SHM files are optional. Current tests do not consume ANLZ or audio fixtures.

All ten tests copy the source fixture into pytest temporary directories before writing. `poc/run_real_rekordbox_tests.py` fixes the test selection, rejects missing/empty/symlinked required files, uses an isolated base temp directory, fails on any remaining skip, and verifies fixture hashes and metadata before and after execution.

Even ten green tests do not complete all Phase 3 evidence. Live `rekordboxAgent` detection, real backup collision/rotation/restore/rollback, retained-track ANLZ preservation, and some snapshot/path edge cases remain unproved.

## Phase 2 handoff

1. Execute POCs only through their documented commands and add an English evidence README only when a POC is actually run.
2. Record objective, risk, environment, dependency versions, exact commands, expected and actual result, measurements, GO/NO-GO/BLOCKED, fallback, and date.
3. Keep all nine POCs BLOCKED until reproducible evidence exists. Do not promote source comments or existing artifacts to GO.
4. For POC #4, obtain a user-owned Rekordbox 7.x fixture, place regular copies in `poc/testdata/`, close Rekordbox and `rekordboxAgent`, then run the fixture harness.
5. Do not commit fixtures, credentials, personal paths, build outputs, or logs containing them.
6. Do not implement ownership, retained-event migration, Smart Fixes completion, acquisition, or packaging as part of POC restoration.

Owner decisions required before later structural work:

- **Minimum macOS version.** Project recommendation: macOS 14 or later as a reach-versus-maintenance compromise. Alternatives are macOS 15+ (smaller support surface) or macOS 26-only (least build work, narrowest reach). Apple documents the deployment targets supported by current Xcode, but does not prescribe this product policy. The current bundle cannot support the first two without rebuilding Python and native dependencies against the chosen target.
- **Sidecar supervisor architecture.** Recommended option: retain the smaller existing `std::process::Command` supervisor if POC #1 validates it, then repair the unsafe stale-port identity behavior. Alternative: migrate to the official Tauri shell plugin and async event stream selected by the current spec, accepting a larger rewrite and capability configuration.

No decision is made in this report.

## Final Phase 1 verification

- Python: 401 passed, 10 skipped; the same ten fixture-gated node IDs remain.
- UI: 18 files and 58 tests passed; typecheck and production build passed.
- Rust: `cargo check` passed.
- Harness: syntax parse and `--list` passed; `--check` returned the documented code 2 because `master.db` is absent.
- Harness safety branches: inherited collect-only options are removed, a simulated collect-only success is rejected, and a simulated interrupt is propagated only after fixture verification.
- Repository checks: `git diff --check` passed; executable-source Ponytail inventory remains 22 and no new marker was added.

## Current official sources consulted

- [pytest invocation and node IDs](https://docs.pytest.org/en/stable/how-to/usage.html)
- [pytest result summaries and `-rs`](https://docs.pytest.org/en/stable/how-to/output.html)
- [Python `subprocess.run`](https://docs.python.org/3/library/subprocess.html)
- [Python `pathlib` file and symlink checks](https://docs.python.org/3.14/library/pathlib.html)
- [Git ignore pattern rules](https://git-scm.com/docs/gitignore)
- [pyrekordbox upstream repository](https://github.com/dylanljones/pyrekordbox)
- [pyrekordbox 0.4.4 release metadata](https://pypi.org/project/pyrekordbox/)
- [Tauri v2 external binary and sidecar guidance](https://v2.tauri.app/develop/sidecar/)
- [Cargo `check`](https://doc.rust-lang.org/cargo/commands/cargo-check.html)
- [Apple guidance on minimum deployment targets](https://developer.apple.com/documentation/xcode/running-code-on-a-specific-version/)
- [Apple Xcode deployment-target support](https://developer.apple.com/support/xcode/)
- [Apple Silicon local code-signing requirement](https://developer.apple.com/documentation/Xcode/embedding-a-helper-tool-in-a-sandboxed-app)
