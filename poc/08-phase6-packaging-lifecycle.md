# Phase 6 Packaging, Lifecycle, and Optional-Component Evidence

Date: 2026-07-13

## Objective

Close the macOS Apple Silicon packaging rerun after the Phase 5 B1 `GO`:

1. preserve the complete source, frozen, and packaged process lifecycle;
2. produce a functional ad-hoc-signed Tauri app with a PyInstaller onedir base
   sidecar;
3. produce a separately distributed, hash-pinned PyInstaller onedir Deezer
   component that works without an external Python runtime;
4. prove that streamrip and real credential data remain outside the base
   artifact;
5. verify locked inputs, version alignment, native dependencies, licenses,
   archive equivalence, and packaged WKWebView loading.

No Developer ID, notarization, Keychain, Windows work, SoundCloud feature,
ffmpeg, real credential reuse, or private Rekordbox fixture was in scope.

## Owner decision

The owner selected a separate downloadable self-contained onedir component.
The rejected alternatives were a managed Python/uv runtime inside the app and
a system-Python dependency. This choice is required because PyInstaller defines
`sys.executable` in a frozen app as its bootloader, not as a reusable Python
interpreter.

The release channel is a versioned GitHub Release asset. The base sidecar
contains only a manifest with the exact URL, byte size, SHA-256, platform,
architecture, application version, streamrip commit, and certifi version.

## Risks tested

- duplicate shells or sidecars;
- unread stdout/stderr blocking the child;
- process-group escape, orphaning, or retained port 8765;
- crash loops, restart exhaustion, or a nonfunctional manual restart;
- killing an unrelated listener or failing to replace an exact stale sidecar;
- a frozen app trying to create a venv from its bootloader;
- archive traversal, symlink escape, duplicate paths, special files, expansion
  bombs, partial installs, or unverified component execution;
- streamrip, non-Deezer provider clients, ffmpeg, or credential data entering
  the base artifact;
- credential exposure through settings, export, logs, arguments, fixtures, or
  build artifacts;
- wrong architecture, deployment target, signature, version, or archive
  payload;
- dependency drift from either Python lock.

## Environment

```text
Host: macOS 26.5.1 (25F80), arm64
Application: Syncbox 0.2.1, minimum macOS 14.0
Base and component Python: CPython 3.14.2
uv: 0.9.28
PyInstaller: 6.21.0
Node.js: 24.13.0
pnpm: 11.0.0-dev.1005
Rust/Cargo: 1.96.1
Tauri CLI: 2.11.4
```

The exact Python graphs are in `sidecar/uv.lock` and
`optional-component/uv.lock`. JavaScript and Rust inputs remain locked by
`pnpm-lock.yaml` and `shell/src-tauri/Cargo.lock`.

## Exact build and verification commands

```sh
cd sidecar
UV_PYTHON_INSTALL_DIR=/tmp/syncbox-uv-python \
UV_PROJECT_ENVIRONMENT=/tmp/syncbox-phase6-venv \
UV_CACHE_DIR=/tmp/syncbox-uv-cache \
  uv lock --check
UV_PYTHON_INSTALL_DIR=/tmp/syncbox-uv-python \
UV_PROJECT_ENVIRONMENT=/tmp/syncbox-phase6-venv \
UV_CACHE_DIR=/tmp/syncbox-uv-cache \
  uv sync --locked --managed-python

cd ../optional-component
UV_PYTHON_INSTALL_DIR=/tmp/syncbox-uv-python \
UV_PROJECT_ENVIRONMENT=/tmp/syncbox-phase6-component-venv \
UV_CACHE_DIR=/tmp/syncbox-uv-cache \
  uv lock --check
UV_PYTHON_INSTALL_DIR=/tmp/syncbox-uv-python \
UV_PROJECT_ENVIRONMENT=/tmp/syncbox-phase6-component-venv \
UV_CACHE_DIR=/tmp/syncbox-uv-cache \
  uv sync --locked --managed-python

cd ../shell
pnpm bundle:macos

cd src-tauri/target/aarch64-apple-darwin/release/bundle/macos
COPYFILE_DISABLE=1 /usr/bin/zip -FS -qry -y \
  Syncbox-0.2.1-macos-arm64.zip Syncbox.app
```

```sh
APP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
APP_ZIP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.1-macos-arm64.zip
COMPONENT_ZIP=optional-component/dist/syncbox-deezer-component-0.2.1-macos-arm64.zip

codesign --verify --deep --strict "$APP"
PYI_ARCHIVE_VIEWER=sidecar/.venv/bin/pyi-archive_viewer \
  sidecar/.venv/bin/python poc/run_phase6_packaging.py \
  "$APP" --archive "$APP_ZIP" --component-archive "$COMPONENT_ZIP"
```

Lifecycle and optional-component commands from the repository root:

```sh
sidecar/.venv/bin/python shell/harness/driver_lifecycle.py
SYNCBOX_SIDECAR_BIN=sidecar/dist/syncbox-sidecar/syncbox-sidecar \
  sidecar/.venv/bin/python shell/harness/driver_lifecycle.py

sidecar/.venv/bin/python shell/harness/test_optional_component.py
SYNCBOX_SIDECAR_BIN=sidecar/dist/syncbox-sidecar/syncbox-sidecar \
  sidecar/.venv/bin/python shell/harness/test_optional_component.py
SYNCBOX_SHELL_BIN="$APP/Contents/MacOS/syncbox-shell" \
  sidecar/.venv/bin/python shell/harness/test_optional_component.py

SYNCBOX_SHELL_BIN="$APP/Contents/MacOS/syncbox-shell" \
  sidecar/.venv/bin/python shell/harness/test_single_instance.py
SYNCBOX_SHELL_BIN="$APP/Contents/MacOS/syncbox-shell" \
  sidecar/.venv/bin/python shell/harness/test_lifecycle_edges.py
SYNCBOX_SHELL_BIN="$APP/Contents/MacOS/syncbox-shell" \
  sidecar/.venv/bin/python shell/harness/test_supervisor_restart.py
```

Regression commands:

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -q -rs -p no:cacheprovider
cd ../ui
pnpm test
pnpm typecheck
pnpm build
cd ../shell/src-tauri
cargo test --locked
cargo check --locked --target aarch64-apple-darwin
```

## Results

### POC #1 — lifecycle

**GO.** Every final source, frozen, and packaged assertion passed.

| Lane | Initial ready | Warm respawn | Graceful shutdown | TERM release | Final state |
|---|---:|---:|---:|---:|---|
| Source sidecar | 0.59 s | 0.35 s | 309 ms | 257 ms | no listener/orphan |
| Frozen sidecar | 0.67 s | 0.40 s | 308 ms | 189 ms | no listener/orphan |

The process-group SIGKILL rung also released the port. Both lanes had one
listener process, no child process, and immediate port release after group
termination.

The final packaged app passed all of these cases:

- a second instance exited with code 0 in 0.15 seconds;
- only the primary ran setup and spawned one sidecar process-group leader;
- stdout and stderr drain tasks remained active;
- a foreign listener was preserved and received no shutdown request;
- an exact stale Syncbox sidecar was reaped and replaced;
- immediate shell exits left no listener or child;
- crashes used 1, 2, and 4 second backoffs;
- the fourth crash emitted `BACKEND_DOWN` without a fifth automatic spawn;
- manual restart returned the packaged sidecar to health.

Closing with an active SSE response can emit Uvicorn's incomplete-response
warning. The clean intent, process exit, orphan, and port assertions still
pass.

### POC #2 — base app and optional onedir

**GO for the functional local Apple Silicon artifacts.** The final scanner and
`codesign --verify --deep --strict` passed.

Base application:

```text
App file bytes:              62,179,355
App filesystem allocation:  60,912 KiB
ZIP bytes:                   32,479,713
Mach-O files:                30, all arm64
Declared/effective minimum:  macOS 14.0 / 14.0
ZIP symlinks:                0
App tree SHA-256:            91a22f36eedd8085722a5fc8b8c7cf30e85002aca793bde2b0560ceab7d17062
ZIP SHA-256:                 851b6c98a49ec068671088dfd3577fe62df24cc5f7673bfd0141389b0192f091
Shell SHA-256:               8f1d68cb67789d1e9eb829a788960d379af6d006479077fffaf30afe147a759a
Sidecar executable SHA-256:  ea9e76f999004b6ba423d7d7adba702df63319d1eed01623d962e8a5790c1ff1
```

Optional component:

```text
Onedir allocation:           34,520 KiB
ZIP bytes:                   19,072,885
Mach-O files:                55, all arm64
Effective minimum:           macOS 11.0
ZIP SHA-256:                 92ccd44e07523818854d52926a6e479c798f2f324e27b3f997586b9d98e2a181
Executable SHA-256:          338ce9ab7f4391e0684c8660dea06b3fa061bee4d0cfe9da6e1a75faaab52ebc
streamrip:                   2.2.0 at 189acda489927719aa8591f6acdd7d67aecf929b
certifi:                     2026.6.17
```

Recreating the ZIP from the same final onedir produced the same byte size and
SHA-256. The base ZIP file set, payload bytes, modes, and symlink set exactly
matched the validated app tree.

The base `--packaging-check` imported certifi, miniaudio, numpy, pyrekordbox,
send2trash, and sqlcipher3, opened an in-memory SQLCipher database, and
reported `streamrip_importable=false`. The base dependency graph, PyInstaller
archive, and app bundle contain no streamrip or Deemix distribution.

The optional PyInstaller module inventory contains the Deezer client and its
shared streamrip core only. `streamrip.client.soundcloud`,
`streamrip.client.qobuz`, `streamrip.client.tidal`, and the generic
`streamrip.rip` CLI are excluded. No ffmpeg binary is present and the exposed
help is Deezer-only. The upstream core configuration schema still contains
unused provider fields; they are not reachable Syncbox capabilities.

Artwork is disabled. Pillow remains an upstream locked dependency but is
excluded from the artifact, avoiding the locally built Pillow binary's macOS
26 deployment requirement. Enabling artwork later requires a new compatibility
and packaging review.

### Optional-component installation

**GO for local/offline source, frozen, and packaged installation.** All three
lanes installed the exact final archive, ran its self-check, wrote no external
Python environment, consumed no real credential, shut down cleanly, and
released port 8765.

| Host lane | Ready | Total | SHA-256 verified | External Python | Credential present |
|---|---:|---:|---|---|---|
| Source sidecar | 0.59 s | 5.30 s | yes | no | no |
| Frozen sidecar | 6.41 s | 12.22 s | yes | no | no |
| Packaged Tauri app | 1.57 s | 31.39 s | yes | no | no |

The packaged total includes the harness's 30-second intentional shell lifetime.
The installer validates size and SHA-256 before extraction, applies bounded
archive checks, runs `--check`, writes an owner-only marker, and atomically
swaps the installed component.

The GitHub Release asset does not yet exist. These runs used the explicit local
archive override with the same verification path. HTTPS retrieval from the
pinned public URL remains a release-publication gate.

### Secrets and licenses

The final source scan covered 221 text files. It detects common private key and
token forms, generic 96–512 character hex values, and structured ARL
assignments from 64 characters. The base and component artifacts passed the
same applicable scans. No real ARL was used during Phase 6.

Tests prove that a synthetic credential:

- is rejected as a normal setting;
- lives only in the encrypted secret store;
- is absent from settings and all-data exports and captured logs;
- is never included in a subprocess argument;
- is written to a 0600 one-shot file and removed after use.

The component self-check independently verifies owner/mode/symlink rejection,
one-shot deletion, TLS verification through certifi, and that no user
`config.toml` or streamrip database is written.

The base license inventory found one expected GPL runtime package: `mutagen`
1.48.1 under GPL-2.0-or-later. The optional artifact contains streamrip's exact
GPL license and a component notice. A complete reviewed notice covering its
Python runtime and every transitive dependency is not yet present, so public
redistribution remains blocked.

### Reproducibility and versions

- the base lock resolved 42 packages and independently installed 37 packages;
- the optional lock resolved 48 packages and independently installed 42;
- both clean environments selected CPython 3.14.2;
- streamrip is pinned to commit
  `189acda489927719aa8591f6acdd7d67aecf929b`;
- version 0.2.1 is aligned across the UI, shell package, Rust package, base
  Python project, optional Python project, Tauri metadata, manifest, and
  final Info.plist;
- Cargo check/test used `--locked` and the explicit arm64 target;
- the app ZIP exactly matches the validated app tree.

PyInstaller onedir bytes are not bit-for-bit stable across clean rebuilds on
this host because generated Mach-O/signature content changes. Each release
must therefore build the component first, generate its manifest, then rebuild
the base app and publish that exact asset. Dependency and build-input
reproducibility is proven; two-root binary reproducibility is not claimed.

### WKWebView and OAuth boundary

The final app was launched through macOS UI automation and loaded
`Syncbox v0.2.1` from `tauri://localhost`. The final optional-component controls
were visible and disabled by default. Closing the window stopped the sidecar
and released port 8765.

The earlier Phase 6 packaged POC on the same transport implementation proved a
visible SSE completion event, EventSource reconnect after supervised restart,
and system-browser OAuth launch. The B1 rerun changed no SSE, OAuth, or external
link code. A new real Spotify authorization was deliberately not started, so
complete account authorization/token refresh is not claimed by this rerun.

### Regression suites

```text
Python: 493 passed, 11 skipped in 2.52 s
UI:     20 Vitest files, 70 tests passed in 5.48 s
UI:     typecheck passed
UI:     production build passed, 194 modules
Rust:   3 tests passed
Rust:   cargo check --locked --target aarch64-apple-darwin passed
uv:     both lock checks and clean managed locked syncs passed
```

The 11 Python skips are explicit private-fixture gates for real Rekordbox data.
They are not counted as passes.

## Residual limits and release gates

- The exact optional asset must be uploaded to GitHub Release `v0.2.1` and
  downloaded back for size/hash/live-HTTPS validation.
- The base ZIP lacks the project license and a reviewed consolidated notice.
  The optional notice does not yet cover every redistributed runtime and
  transitive dependency.
- The artifact is ad-hoc signed, not Developer ID signed or notarized.
- this historical Phase 6 artifact used `dev.syncbox.app`; the final bundle
  must use and verify `io.github.adridot.syncbox`.
- Private real-Rekordbox fixture gates remain blocked.
- Complete live Spotify OAuth requires owner credentials and consent.
- Binary bit-for-bit reproducibility across independent clean roots is not
  claimed.

## Fallback

- Block any artifact if lifecycle, base isolation, component integrity, or
  provider-module assertions regress.
- Keep the base app functional without B1 and preserve purchase links as the
  primary missing-track path.
- Keep PyInstaller onedir; investigate another freezer only after a concrete
  measured failure.
- If the optional component cannot meet its license/publication gates, do not
  publish it. The base B2 product remains valid.

Primary sources:

- [Tauri macOS bundles](https://v2.tauri.app/distribute/macos-application-bundle/)
- [Tauri resources](https://v2.tauri.app/develop/resources/)
- [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html)
- [PyInstaller spec files](https://pyinstaller.org/en/stable/spec-files.html)
- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [GitHub Release assets](https://docs.github.com/en/rest/releases/assets)

## Final release closure update — 2026-07-15

This POC remains the historical Phase 6 evidence for version 0.2.1 and its
measured lifecycle baseline. It is not the current artifact manifest. The
final-candidate optional 0.2.2 ZIP is 17,340,517 bytes with SHA-256
`37fb7375a357a0fb218709a2092632fd18d99c828c541c341645969eda1fb39c`.
It includes scanner-verified Pillow artwork support, frozen-runtime license
alignment, and complete generated redistribution material. The final-candidate base
0.2.2 ZIP is 29,295,890 bytes with SHA-256
`454043354c97b7de03b2858503c0e2b0754432a81bbaaa0dfdd015fef4482e4c`.
Clean locked environments, every lifecycle edge, and real packaged Spotify
PKCE/refresh/recovery now pass. Independent-root equality, final artwork
embedding, any owner-approved post-provider manual Rekordbox walkthrough, and
public Release download-back remain pending as listed in
`docs/_handoffs/final-release-closure.md`.
