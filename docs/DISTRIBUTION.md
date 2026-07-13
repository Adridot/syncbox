# Distribution

This is the release contract for Syncbox 0.2.1. The supported v1 target is
macOS 14 or later on Apple Silicon. The deliverable is a PyInstaller onedir
sidecar embedded as a Tauri v2 application resource, plus a ZIP archive.

The local artifact is ad-hoc signed. It has no Apple Developer ID signature,
notarization, installer, auto-update mechanism, Keychain dependency, or Windows
build. Do not describe it as trusted by Gatekeeper.

## Prerequisites

- Apple Silicon Mac running macOS 14 or later;
- Xcode Command Line Tools and Rust;
- Node.js, pnpm, and uv;
- the committed `pnpm-lock.yaml`, `Cargo.lock`, and `sidecar/uv.lock`.

The build follows the current official guidance for
[Tauri macOS bundles](https://v2.tauri.app/distribute/macos-application-bundle/),
[Tauri external binaries](https://v2.tauri.app/develop/sidecar/),
[PyInstaller onedir bundles](https://pyinstaller.org/en/stable/usage.html), and
[uv locked environments](https://docs.astral.sh/uv/concepts/projects/sync/).

## Build

Run from a clean source checkout on an Apple Silicon Mac:

```sh
pnpm install --frozen-lockfile
cd sidecar
uv lock --check
uv sync --locked --managed-python
cd ../shell
pnpm bundle:macos
```

`bundle:macos` performs these reproducibility-sensitive steps:

- freezes the sidecar with `uv run --locked --managed-python` and PyInstaller
  `--clean`;
- builds the Vue production bundle;
- invokes Tauri with Cargo `--locked` and the explicit
  `aarch64-apple-darwin` target;
- places `/usr/bin` and `/bin` first so Tauri calls Apple's `/usr/bin/xattr`
  rather than an incompatible third-party executable;
- remaps the builder home prefix to `/Users/build` in Rust debug paths;
- applies an ad-hoc signature through Tauri's `signingIdentity: "-"` setting.

Output:

```text
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
```

Create the unsigned distribution archive from that directory:

```sh
cd shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos
COPYFILE_DISABLE=1 /usr/bin/zip -FS -qry -y \
  Syncbox-0.2.1-macos-arm64.zip Syncbox.app
```

Build artifacts are intentionally not committed.

## Verification

From the repository root, with the locked sidecar environment active:

```sh
APP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
ZIP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.1-macos-arm64.zip

codesign --verify --deep --strict "$APP"
PYI_ARCHIVE_VIEWER=sidecar/.venv/bin/pyi-archive_viewer \
  sidecar/.venv/bin/python poc/run_phase6_packaging.py \
  "$APP" --archive "$ZIP"
```

The scanner fails closed on:

- missing or version-mismatched runtime dependencies;
- missing license metadata or unexpected GPL runtime packages;
- non-arm64 Mach-O files or an effective deployment target above macOS 14;
- a non-ad-hoc signature, missing native package, or malformed app resource;
- archive payload, mode, or symlink drift from the validated app tree;
- streamrip, Deemix, Deezer acquisition components, ARL/config markers,
  private-key material, common token shapes, or local repository paths.

Run the lifecycle harnesses documented in `shell/README.md` against the same
app. Phase 6 evidence and measurements are recorded in
`poc/08-phase6-packaging-lifecycle.md`.

`spctl` is not an acceptance test for this artifact: the current build has no
Developer ID or notarization ticket. On the Phase 6 host it returned an
internal Code Signing subsystem error, while `codesign --verify --deep
--strict` passed. Users may need to right-click the app and choose Open, or
remove quarantine explicitly:

```sh
xattr -dr com.apple.quarantine /path/to/Syncbox.app
```

## Release gates

The functional local artifact is complete, but public binary distribution is
not approved until all of the following are resolved:

- choose a durable reverse-DNS bundle identifier; the current
  `dev.syncbox.app` triggers Tauri's warning because it ends in `.app`, and an
  identifier change affects application identity and persisted data paths;
- include the project license and a reviewed consolidated third-party notice
  in the distributed artifact;
- complete the private Rekordbox fixture gates listed in the Phase 6 handoff;
- if a frictionless public macOS install is required, obtain a Developer ID and
  add signing/notarization in a later phase.

No legal compliance, Gatekeeper acceptance, bit-for-bit reproducibility, or
notarization claim is made by this document.
