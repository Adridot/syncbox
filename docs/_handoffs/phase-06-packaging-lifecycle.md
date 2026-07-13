# Phase 6 Handoff — Packaging, Lifecycle, Secrets, and Reproducibility

Date: 2026-07-13

## Verdict

**READY FOR PHASE 7.**

**FUNCTIONAL APPLE SILICON ARTIFACT: READY.**

**PUBLIC RELEASE ACCEPTANCE: NOT READY.**

Phase 6 produced and validated the actual B2-only macOS v1 application as a
PyInstaller onedir embedded in a Tauri application and an exact ZIP archive.
Source, frozen, and packaged lifecycle gates pass. The repository dependency
inputs are locked and application version 0.2.1 is aligned. The base bundle
contains no B1/Deezer acquisition component or detected secret.

Phase 7 may proceed using this artifact and lifecycle contract. Public release
acceptance remains blocked by the explicit gates in this handoff; none is a
reason to reopen Phase 6 architecture.

## Scope and owner decisions preserved

- macOS 14+ on Apple Silicon only;
- ad-hoc local signature only, with no Developer ID or notarization claim;
- no Windows implementation, Keychain requirement, or auto-update;
- one local Tauri shell, one Python sidecar, fixed loopback port 8765;
- encrypted local secret store for the unsigned release;
- B1 remains BLOCKED from Phase 5, so B2 browser purchase links and local
  relink are the only v1 missing-track path;
- no streamrip, Deezer ARL setting, acquisition job/API/UI, or B1 claim;
- no commits, staging, history edits, or pushes were made in Phase 6;
- `.idea/` remained untracked and untouched.

The owner authorized Apple Silicon implementation and exact stale-Syncbox
cleanup. No permanent bundle identifier or licensing-policy choice was made
silently; both are recorded as release gates below.

## Final artifact

```text
App: shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
ZIP: shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.1-macos-arm64.zip
```

```text
Version:                     0.2.1
App file bytes:              62,160,929
ZIP bytes:                   32,461,008
Mach-O files:                30, all arm64
Declared/effective minimum:  macOS 14.0 / 14.0
Signature:                   ad-hoc, no Team ID or Developer ID
App tree SHA-256:            24f99ca26c5afa97d4904777f9f85ccceb9699a1fce0d41329c1881ac2e84008
ZIP SHA-256:                 7cd797bde87514600d15f2ba6743f5709db58003a72d3d687d241cf493030010
Shell SHA-256:               e55e920b9be3c7d7b8a3d3f28622d98cbdc571fb963d3b767d35c69f03bceffe
Sidecar SHA-256:             3d77136602631d4b5dde42c33703c6392c1972e4a609baae0bbed2a3a304ee4b
```

`codesign --verify --deep --strict` passes. The archive file set, file bytes,
modes, and symlink set exactly match the validated app tree. Build artifacts
remain ignored and are not intended for commit.

## Implementation delivered

### Shell lifecycle

The Tauri shell now enforces this order:

1. acquire the native single-instance guard before setup or sidecar spawn;
2. inspect port 8765 with the exact Syncbox health identity;
3. preserve a foreign listener and report an actionable collision;
4. stop only an exact stale Syncbox sidecar;
5. spawn the embedded sidecar as its own process-group leader;
6. continuously drain stdout and stderr as bytes;
7. supervise unexpected exits with 1/2/4-second bounded restarts;
8. emit backend-down after exhaustion and support a real manual restart;
9. on intentional exit, request `POST /shutdown`, wait, then use process-group
   SIGTERM and SIGKILL fallbacks;
10. finish with no listener, child, or orphan.

Output consumption does not assume UTF-8, so arbitrary native-library output
cannot stall or crash the drain tasks. Intent, spawn, and publication are
serialized to prevent shutdown/restart races.

### Loopback transport and WKWebView

`/health` now identifies the backend exactly as:

```json
{"ok":true,"service":"syncbox-sidecar","protocol":1}
```

API and OAuth responses carry `Cache-Control: no-store`. The no-store layer is
a pure ASGI wrapper and does not buffer `/events`, preserving SSE streaming.
OAuth callback handling is serialized and moved off the event loop so a token
exchange cannot block health/SSE handling.

The Vue client uses no-store fetches, retries settings during the bounded
frozen cold-start window, exposes the backend-down reason, and invokes the real
shell manual-restart command. External OAuth and B2 links open in the system
browser; there is no embedded `window.open` fallback in Tauri.

### Secrets and persistence

- one SQLite settings source remains canonical, with defaults applied on read;
- blank credential writes preserve stored values;
- the fixed OAuth callback remains
  `http://127.0.0.1:8765/callback` and PKCE remains the only OAuth flow;
- the per-install secret key is exactly 32 random bytes represented as hex,
  created with no-follow semantics, verified as a regular file, and forced to
  mode 0600;
- OAuth tokens remain in the encrypted SQLCipher secret database and are
  excluded entirely from settings JSON and all-data exports;
- all-data import validates a staged absolute file, rejects future schemas,
  migrates the stage, compares the canonical schema, runs integrity and foreign
  key checks, makes a durable safety backup, fsyncs, then atomically replaces
  the live app database;
- no Keychain or keyring dependency was added.

A composed-application test exports settings and all-data while a real logger
captures output, then asserts a secret sentinel appears in none of them.

### Packaging and reproducibility

- `.python-version` selects CPython 3.14.2;
- `sidecar/uv.lock` locks 42 packages and includes runtime and development
  dependencies, including pytest, httpx, and PyInstaller 6.21.0;
- `uv lock --check`, locked managed sync, and the locked runtime tree pass;
- PyInstaller uses a clean arm64 onedir build and includes migrations;
- `--packaging-check` imports certifi, miniaudio, numpy, pyrekordbox,
  send2trash, and sqlcipher3 and opens an in-memory encrypted database;
- the Tauri build uses frozen pnpm input, Cargo `--locked`, an explicit
  `aarch64-apple-darwin` target, Apple `/usr/bin/xattr`, and builder-home path
  remapping;
- version 0.2.1 is aligned across UI, shell package, Rust package, sidecar,
  Tauri bundle metadata, README, and final Info.plist.

The scanner derives the applicable runtime graph from `uv.lock`, requires
every installed version and license to match, validates all Mach-O targets,
executes the packaged native check, verifies the ad-hoc seal, inspects the
PyInstaller archive, scans raw bytes, and compares the ZIP with the app tree.

## Validation results

Host:

```text
macOS 26.5.1 (25F80), arm64
Clean packaging, full-test, and source lifecycle CPython 3.14.2
uv 0.9.28; PyInstaller 6.21.0
Node.js 24.13.0; pnpm 10.29.3
Rust/Cargo 1.96.1; Tauri CLI 2.11.4
```

### Lifecycle measurements

| Lane | Initial ready | Warm respawn | Graceful shutdown | TERM release | Final state |
|---|---:|---:|---:|---:|---|
| Source sidecar, freshly synchronized lock | 6.47 s | 1.55 s | 303 ms | 252 ms | no listener/orphan |
| Frozen sidecar | 6.47 s final; 8.19 s observed cold maximum | 0.43 s | 284 ms | 236 ms | no listener/orphan |

The SIGKILL rung also released port 8765. The packaged application passed:

- second-instance self-exit with code 0 in 0.13 seconds;
- one primary setup and one sidecar whose process-group ID equals its PID;
- graceful handshake and clean port/process teardown;
- 1/2/4-second restart backoff, fourth-crash backend-down, then healthy manual
  restart;
- foreign-listener preservation with no shutdown POST and no sidecar spawn;
- exact stale-Syncbox replacement;
- five immediate exits with no listener or child left behind.

### Real packaged WKWebView

- the final app loaded at the Tauri origin and reported version 0.2.1;
- a synchronization job produced visible completion activity over real SSE;
- killing the temporary sidecar triggered supervised recovery, and a second
  job produced another activity row, proving EventSource reconnect;
- cold packaged launch reloaded configured settings after backend readiness;
- Spotify Connect opened the authorization endpoint in the system browser;
  the deliberately invalid test Client ID stopped before authorization, so no
  complete token exchange is claimed;
- no real personal path, token, authorization code, or credential is recorded
  in repository evidence.

### Test suites

```text
Python: 478 passed, 11 skipped in 6.02 s
UI:     20 Vitest files, 70 tests passed
UI:     typecheck passed
UI:     production build passed, 194 modules
Rust:   3 tests passed
Rust:   cargo check --locked --target aarch64-apple-darwin passed
uv:     lock check, managed locked sync, and locked runtime tree passed
```

The 11 skips are the established private-fixture gates for real Rekordbox event
migration, library, missing, mutation, and write cases. They are reported as
gates, not converted into passes.

### Bundle and license scan

- 30 Mach-O files are arm64 and valid under the declared macOS 14 minimum;
- packaged resource lookup and all required native imports pass;
- no unexpected absolute native dependency path was found;
- no streamrip, Deemix, Deezer component, ARL/config marker, secret-shaped
  value, personal home/repository path, or inline implementation marker was
  found in the base artifact;
- the only GPL runtime package is the expected `mutagen` 1.48.1 under
  GPL-2.0-or-later;
- no claim is made that identifying the package alone completes redistribution
  compliance.

The full reproducible commands and measurements are in
`poc/08-phase6-packaging-lifecycle.md`.

## Residual limits and release gates

These do not block Phase 7, but they block the corresponding broader claim:

1. **Public binary license notices.** The ZIP does not include the repository
   `LICENSE` or one reviewed consolidated third-party notice. The owner must
   choose and approve the redistribution-notice approach before publication.
2. **Permanent bundle identifier.** Tauri warns because `dev.syncbox.app` ends
   in `.app`. An identifier change affects application identity and persisted
   data paths; the owner must choose the durable reverse-DNS identifier before
   public release.
3. **Private Rekordbox fixtures.** POC #4, #8 real mutation, and #9 retained
   event migration remain BLOCKED until their local fixtures run with zero
   skips and the resulting databases open in Rekordbox 7.x.
4. **Signing and trust.** The app is ad-hoc signed and not notarized. `spctl`
   returned an internal Code Signing subsystem error on the Phase 6 host.
   `codesign --verify --deep --strict` passes, but Gatekeeper acceptance is not
   claimed.
5. **Live OAuth completion.** System-browser launch and callback transport are
   covered, but a complete Spotify authorization/token refresh needs the
   owner's valid Client ID and consent.
6. **Binary reproducibility.** Inputs, locks, target, versions, path remapping,
   and archive equivalence are reproducible; a two-root bit-for-bit build was
   not performed and is not claimed.
7. **Tooling.** `cargo fmt --check` could not run because rustfmt is absent from
   the installed toolchain. Cargo test/check pass. A packaged shutdown with an
   active SSE client can emit a harmless Uvicorn incomplete-response warning;
   all process and port assertions still pass.

Phase 4's A3 conclusion is unchanged: the conservative keeper-neutral
uncertain verdict remains accepted, while confident full spectral
classification is NO-GO without a reliable labeled corpus. Phase 5's B1
verdict is unchanged: BLOCKED, not NO-GO, and no B1 work is authorized.

## Root-thread integration notes

All Phase 6 changes are intentionally uncommitted. Before splitting commits,
the root thread should:

1. review the full working-tree diff and preserve `.idea/` as unrelated;
2. rerun `git diff --check` and the packaging scanner on the exact artifact;
3. split implementation, tests/harnesses, locks/packaging, UI transport, and
   documentation into intentional commits;
4. do not add generated app, ZIP, `dist`, `target`, venv, or private data;
5. keep the release gates above visible rather than converting them into
   unsupported claims.

Current primary documentation:

- `docs/DISTRIBUTION.md` — build and verification contract;
- `docs/USER_GUIDE.md` — truthful B2-only user behavior;
- `poc/08-phase6-packaging-lifecycle.md` — POC evidence;
- `poc/README.md` — authoritative POC states.

The packaging choices follow current official
[Tauri macOS bundle](https://v2.tauri.app/distribute/macos-application-bundle/),
[Tauri sidecar](https://v2.tauri.app/develop/sidecar/),
[PyInstaller](https://pyinstaller.org/en/stable/usage.html), and
[uv locking](https://docs.astral.sh/uv/concepts/projects/sync/) guidance.
