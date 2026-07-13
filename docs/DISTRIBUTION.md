# Distribution

This is the release contract for Syncbox 0.2.1. The supported v1 target is
macOS 14 or later on Apple Silicon. Phase 6 produces two independent unsigned
artifacts:

- `Syncbox-0.2.1-macos-arm64.zip`, containing the Tauri application and its
  base PyInstaller onedir sidecar;
- `syncbox-deezer-component-0.2.1-macos-arm64.zip`, a separately distributed
  optional PyInstaller onedir component.

The base application is complete without the optional component. It neither
imports nor bundles streamrip. The optional component is disabled by default,
downloaded only after explicit enablement, and verified against the manifest
embedded in the base sidecar.

Both local artifacts are ad-hoc signed where macOS tooling requires a
signature. They have no Developer ID signature, notarization, installer,
auto-update mechanism, Keychain dependency, or Windows build. Do not describe
them as trusted by Gatekeeper.

## Prerequisites

- Apple Silicon Mac running macOS 14 or later;
- Xcode Command Line Tools and Rust;
- Node.js, pnpm, and uv;
- committed `pnpm-lock.yaml`, `shell/src-tauri/Cargo.lock`,
  `sidecar/uv.lock`, and `optional-component/uv.lock` files.

The build follows the current official guidance for
[Tauri macOS bundles](https://v2.tauri.app/distribute/macos-application-bundle/),
[Tauri resources](https://v2.tauri.app/develop/resources/),
[PyInstaller onedir bundles](https://pyinstaller.org/en/stable/usage.html),
[PyInstaller frozen runtime behavior](https://pyinstaller.org/en/stable/runtime-information.html),
[uv locked environments](https://docs.astral.sh/uv/concepts/projects/sync/),
and [GitHub Release assets](https://docs.github.com/en/rest/releases/assets).

## Build

Run from a clean source checkout on an Apple Silicon Mac:

```sh
pnpm install --frozen-lockfile

cd sidecar
uv lock --check
uv sync --locked --managed-python

cd ../optional-component
uv lock --check
uv sync --locked --managed-python

cd ../shell
pnpm bundle:macos
```

`bundle:macos` performs these ordered steps:

1. builds the Vue production bundle;
2. freezes the optional component with its own lock and PyInstaller 6.21.0;
3. creates its deterministic ZIP container and writes the exact size and
   SHA-256 to `sidecar/src/syncbox/optional_component.json`;
4. freezes the base sidecar, including only that small manifest;
5. invokes Tauri with Cargo `--locked` and the explicit
   `aarch64-apple-darwin` target;
6. places `/usr/bin` and `/bin` first so Tauri uses Apple's `xattr`;
7. remaps the builder home prefix in Rust debug paths;
8. applies an ad-hoc signature through Tauri's `signingIdentity: "-"`.

The optional component cannot reuse `sys.executable` from a frozen base app:
PyInstaller defines it as the bootloader executable, not as a general Python
interpreter. The separate self-contained onedir artifact is therefore the
owner-approved distribution boundary.

Build outputs:

```text
optional-component/dist/syncbox-deezer-component/
optional-component/dist/syncbox-deezer-component-0.2.1-macos-arm64.zip
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
```

Create the base application archive from the bundle directory:

```sh
cd shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos
COPYFILE_DISABLE=1 /usr/bin/zip -FS -qry -y \
  Syncbox-0.2.1-macos-arm64.zip Syncbox.app
```

Build artifacts are ignored and must not be committed.

## Verification

From the repository root:

```sh
APP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
APP_ZIP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.1-macos-arm64.zip
COMPONENT_ZIP=optional-component/dist/syncbox-deezer-component-0.2.1-macos-arm64.zip

codesign --verify --deep --strict "$APP"
PYI_ARCHIVE_VIEWER=sidecar/.venv/bin/pyi-archive_viewer \
  sidecar/.venv/bin/python poc/run_phase6_packaging.py \
  "$APP" --archive "$APP_ZIP" --component-archive "$COMPONENT_ZIP"
```

The scanner fails closed on:

- lock, distribution-version, or license-metadata drift;
- a streamrip or Deemix distribution inside the base artifact;
- missing required native packages, non-arm64 Mach-O files, or an effective
  deployment target above the declared minimum;
- a Developer ID signature, notarization claim, malformed resource, or app/ZIP
  payload drift;
- component size/hash drift, a missing streamrip license, an exposed
  SoundCloud interface, an ffmpeg binary, or a failing component self-check;
- real secret patterns, private-key material, credential-shaped values, or a
  local repository path in source or artifacts.

The base artifact legitimately contains `mutagen` 1.48.1 under
GPL-2.0-or-later. The exclusion gate is specifically for the separately
distributed streamrip component; it is not a claim that the base bundle has no
GPL-licensed dependency.

Run the source, frozen, packaged lifecycle, single-instance, supervisor, and
optional-component harnesses documented in `shell/README.md` and
`shell/harness/`. Exact Phase 6 commands and measurements are recorded in
`poc/08-phase6-packaging-lifecycle.md`.

## Release publication

The base manifest for 0.2.1 pins the optional asset to:

```text
Name:   syncbox-deezer-component-0.2.1-macos-arm64.zip
Bytes:  19,072,885
SHA-256: 92ccd44e07523818854d52926a6e479c798f2f324e27b3f997586b9d98e2a181
URL:    https://github.com/Adridot/syncbox/releases/download/v0.2.1/syncbox-deezer-component-0.2.1-macos-arm64.zip
```

Before making the B1 path available to users, publish that exact byte stream as
an asset of GitHub Release `v0.2.1`, then download the published asset and
repeat the size/hash and live installation checks. A differently rebuilt asset
must receive a new manifest and a rebuilt base application; never replace the
asset while retaining the old manifest.

The Phase 6 task did not create a release or upload either artifact. Until the
asset exists at the pinned URL, local/offline installation is proven but the
public online optional-component path is not release-ready.

## Current trust and release gates

`spctl` is not an acceptance test for this artifact because there is no
Developer ID or notarization ticket. `codesign --verify --deep --strict`
passes. Users may need to right-click the app and choose Open, or remove
quarantine explicitly:

```sh
xattr -dr com.apple.quarantine /path/to/Syncbox.app
```

Public binary distribution remains blocked until all applicable gates are
closed:

- upload and revalidate the exact optional component Release asset;
- choose a durable reverse-DNS bundle identifier; `dev.syncbox.app` ends in
  `.app` and triggers a Tauri warning;
- include the project license and a reviewed consolidated third-party notice
  in the base ZIP, and complete the streamrip component redistribution review;
- complete the private Rekordbox fixture gates listed in the Phase 6 handoff;
- perform live Spotify OAuth with owner consent before claiming complete OAuth
  evidence;
- add Developer ID signing/notarization only if a frictionless public install
  becomes a requirement.

No legal compliance, Gatekeeper acceptance, notarization, or two-root
bit-for-bit reproducibility claim is made by this document.
