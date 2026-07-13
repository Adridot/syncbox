# Phase 6 Packaging, Lifecycle, and WKWebView Evidence

Date: 2026-07-13

## Objective

Close POC #1, #2, and #3 for the actual B2-only v1 product:

1. prove the complete source, frozen, and packaged macOS process lifecycle;
2. produce and inspect a functional unsigned/ad-hoc PyInstaller onedir inside
   a Tauri application and exact ZIP archive;
3. prove canonical SSE behavior in the real packaged WKWebView and exercise
   the OAuth system-browser boundary as far as locally possible.

No Developer ID, notarization, Keychain, Windows work, B1 acquisition module,
credential, private Rekordbox fixture, or user data was in scope.

## Risks tested

- duplicate shells or sidecars;
- unread stdout/stderr blocking the child;
- child escape from process-group shutdown;
- crash loops, restart exhaustion, or a nonfunctional manual restart;
- killing an unrelated process that happens to own port 8765;
- leaving an orphan or retaining port 8765 after any shutdown rung;
- resource lookup or native extension failure inside the app bundle;
- wrong architecture, deployment target, signature, version, or ZIP payload;
- cached loopback API/OAuth responses or buffered SSE in WKWebView;
- secrets, acquisition code, local builder paths, or unexpected GPL packages
  entering the base bundle;
- dependency drift from the committed Python lock.

## Environment and dependency versions

```text
Host: macOS 26.5.1 (25F80), arm64
Application: Syncbox 0.2.1, minimum macOS 14.0
Clean packaging, full-test, and source lifecycle environment: CPython 3.14.2
uv: 0.9.28
PyInstaller: 6.21.0
Node.js: 24.13.0
pnpm: 10.29.3
Rust/Cargo: 1.96.1
Tauri CLI: 2.11.4
```

The complete Python runtime graph and exact versions are in
`sidecar/uv.lock`. The JavaScript and Rust graphs remain locked by
`pnpm-lock.yaml` and `shell/src-tauri/Cargo.lock`.

## Exact build and verification commands

```sh
pnpm install --frozen-lockfile
cd sidecar
UV_PYTHON_INSTALL_DIR=/tmp/syncbox-uv-python \
UV_PROJECT_ENVIRONMENT=/tmp/syncbox-phase6-venv \
UV_CACHE_DIR=/tmp/syncbox-uv-cache \
  uv lock --check
UV_PYTHON_INSTALL_DIR=/tmp/syncbox-uv-python \
UV_PROJECT_ENVIRONMENT=/tmp/syncbox-phase6-venv \
UV_CACHE_DIR=/tmp/syncbox-uv-cache \
  uv sync --locked --managed-python
cd ../shell
UV_PYTHON_INSTALL_DIR=/tmp/syncbox-uv-python \
UV_PROJECT_ENVIRONMENT=/tmp/syncbox-phase6-venv \
UV_CACHE_DIR=/tmp/syncbox-uv-cache \
  pnpm bundle:macos

cd src-tauri/target/aarch64-apple-darwin/release/bundle/macos
COPYFILE_DISABLE=1 /usr/bin/zip -FS -qry -y \
  Syncbox-0.2.1-macos-arm64.zip Syncbox.app
cd ../../../../../../..

APP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
ZIP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.1-macos-arm64.zip
codesign --verify --deep --strict "$APP"
PYI_ARCHIVE_VIEWER=/tmp/syncbox-phase6-venv/bin/pyi-archive_viewer \
  /tmp/syncbox-phase6-venv/bin/python poc/run_phase6_packaging.py \
  "$APP" --archive "$ZIP"
```

The isolated environment prevents an older compatible local `.venv` from
being reused and proves the clean Python 3.14.2 input selected by
`.python-version`. The documented relative `cd` above is not required by the
application build; the canonical scanner invocation is from the repository
root.

Lifecycle commands from the repository root:

```sh
sidecar/.venv/bin/python shell/harness/driver_lifecycle.py
SYNCBOX_SIDECAR_BIN=sidecar/dist/syncbox-sidecar/syncbox-sidecar \
  sidecar/.venv/bin/python shell/harness/driver_lifecycle.py

SYNCBOX_SHELL_BIN=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_single_instance.py
SYNCBOX_SHELL_BIN=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_supervisor_restart.py
SYNCBOX_SHELL_BIN=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_lifecycle_edges.py
```

Regression commands:

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 /tmp/syncbox-phase6-venv/bin/python \
  -m pytest -q -rs -p no:cacheprovider
cd ../ui
pnpm test
pnpm typecheck
pnpm build
cd ../shell/src-tauri
cargo test --locked
cargo check --locked --target aarch64-apple-darwin
```

## Expected result

- one primary shell and one sidecar process group;
- consumed output, bounded 1/2/4-second restarts, backend-down notification,
  and a working manual restart;
- graceful shutdown followed by bounded TERM/KILL fallbacks, with no orphan
  and immediate port release;
- foreign listeners preserved, exact stale Syncbox listeners replaced;
- one arm64, macOS 14+ ad-hoc-signed app whose embedded native imports run;
- an archive exactly matching the validated app tree;
- canonical SSE completion and reconnect in the packaged WKWebView;
- OAuth authorization launched in the system browser, never an embedded
  window;
- no base-bundle secret, B1/Deezer component, personal path, or unexpected GPL
  runtime package.

## Actual result and measurements

### POC #1 — lifecycle

**GO.** All source, frozen, and packaged harness assertions passed.

| Lane | Initial ready | Warm respawn | Graceful shutdown | TERM release | Result |
|---|---:|---:|---:|---:|---|
| Source sidecar, freshly synchronized lock | 6.47 s | 1.55 s | 303 ms | 252 ms | PASS |
| Frozen sidecar | 6.47 s final run; 8.19 s observed cold maximum | 0.43 s | 284 ms | 236 ms | PASS |

The SIGKILL rung also released the port. Every checked final state had zero
listener and zero surviving child/orphan process. The packaged supervisor used
the required 1, 2, and 4 second backoff sequence; the fourth crash emitted
backend-down without an automatic fifth spawn, and the real manual restart
returned the exact packaged sidecar to health.

The second packaged application instance exited with code 0 in 0.13 seconds.
Only the primary reached setup and spawned a sidecar, whose process-group ID
equaled its PID. A foreign HTTP listener was neither killed nor sent
`POST /shutdown`. An exact Syncbox protocol listener was treated as stale,
reaped, and replaced. Five immediate shell exits left no listener.

### POC #2 — onedir and application bundle

**GO for the functional local ad-hoc artifact.** The final scanner and
`codesign --verify --deep --strict` passed.

```text
App file bytes:             62,160,929
ZIP bytes:                  32,461,008
Mach-O files:               30, all arm64
Declared/effective minimum: macOS 14.0 / 14.0
ZIP symlinks:               0
App tree SHA-256:           24f99ca26c5afa97d4904777f9f85ccceb9699a1fce0d41329c1881ac2e84008
ZIP SHA-256:                7cd797bde87514600d15f2ba6743f5709db58003a72d3d687d241cf493030010
Shell SHA-256:              e55e920b9be3c7d7b8a3d3f28622d98cbdc571fb963d3b767d35c69f03bceffe
Sidecar SHA-256:            3d77136602631d4b5dde42c33703c6392c1972e4a609baae0bbed2a3a304ee4b
```

The ZIP file set, payload bytes, modes, and symlink set exactly matched the
validated app. The in-bundle packaging check imported certifi, miniaudio,
numpy, pyrekordbox, send2trash, and sqlcipher3, then successfully opened an
in-memory SQLCipher database.

The lock-derived license inventory found one expected GPL runtime package:
`mutagen` 1.48.1 (`GPL-2.0-or-later`). No streamrip, Deemix, Deezer component,
ARL/config marker, secret-shaped value, or local repository path was found.
The base artifact remains fully functional without B1.

### POC #3 — real WKWebView SSE and OAuth boundary

**GO for SSE in the real packaged WKWebView.** The application loaded at the
Tauri custom origin with version 0.2.1. A real synchronization job produced a
visible completion activity through `/events`. After killing the temporary
sidecar, the supervisor restarted it and a second job produced another visible
activity row, proving EventSource reconnect against the packaged backend.

Loopback API responses now carry `Cache-Control: no-store`; this removed a
real WKWebView stale-response failure without buffering the SSE body. Packaged
cold start also reloaded configured settings after the bounded startup retry.

Choosing Spotify Connect opened the authorization URL in the system browser,
not the WKWebView. The test used an intentionally invalid public Client ID, so
Spotify rejected authorization before redirect and no token exchange occurred.
The fixed callback URI and no-store response behavior are covered by tests,
but complete live account authorization remains a credential-and-consent limit,
not a claimed POC result.

### Regression suites

```text
Python: 478 passed, 11 skipped in 6.02 s
UI:     20 Vitest files, 70 tests passed
UI:     typecheck and production build passed (194 modules)
Rust:   3 tests passed; locked arm64 cargo check passed
uv:     lock check, locked managed sync, and locked runtime tree passed
```

The 11 Python skips are explicit private-fixture gates for real Rekordbox data;
they are not packaging failures and are not counted as passes.

## Residual limits and release gates

- The artifact is ad-hoc signed, not Developer ID signed or notarized.
  `spctl` returned an internal Code Signing subsystem error on this host, so no
  Gatekeeper acceptance claim is made.
- A complete Spotify OAuth authorization/token refresh was not performed
  because no owner Client ID and consent were provided to this POC.
- Closing the app while an SSE client is active may emit a harmless Uvicorn
  shutdown warning that the ASGI response did not complete; shutdown, port
  release, and orphan assertions still pass.
- `cargo fmt --check` could not run because the rustfmt component is not
  installed in the local toolchain. Cargo test and check passed.
- Binary bit-for-bit reproducibility across two independent build roots is not
  claimed. Dependency resolution, target, input locks, archive equivalence,
  versions, and builder-path remapping are reproducible.
- Tauri warns that `dev.syncbox.app` ends in `.app`. Changing an application
  identifier affects identity and persisted paths, so the owner must choose a
  permanent reverse-DNS identifier before public release.
- The ZIP does not yet contain the root project license and a consolidated
  reviewed third-party notice. Public binary redistribution remains gated on
  that review.
- Private real-Rekordbox fixture gates remain blocked and prevent a complete
  public release-readiness claim for database mutations.

## Fallback

- If lifecycle assertions regress, block the artifact; do not replace the
  small native supervisor without a new measured POC.
- If PyInstaller onedir regresses, investigate the concrete native/resource
  failure before considering another freezer; onefile remains out of scope.
- If WKWebView SSE regresses, inspect HTTP caching and WebKit buffering first;
  changing transport requires a new owner decision.

The implementation follows the current official
[Tauri process model](https://v2.tauri.app/develop/sidecar/),
[Tauri macOS bundle guidance](https://v2.tauri.app/distribute/macos-application-bundle/),
[PyInstaller onedir guidance](https://pyinstaller.org/en/stable/usage.html),
and [uv lock/sync contract](https://docs.astral.sh/uv/concepts/projects/sync/).
