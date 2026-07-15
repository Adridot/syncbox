# Distribution

This is the release contract for Syncbox 0.2.2. The supported v1 target is
macOS 14 or later on Apple Silicon. The published release consists of two
independent artifacts:

- `Syncbox-0.2.2-macos-arm64.zip`, containing the Tauri application and its
  base PyInstaller onedir sidecar;
- `syncbox-deezer-component-0.2.2-macos-arm64.zip`, a separately distributed
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
4. builds the locally inventoried `sqlcipher3-wheels` fork with SQLCipher
   4.12.0 and Apple's CommonCrypto provider; its extension must link only
   Security, CoreFoundation, and libSystem, never a separate OpenSSL library;
5. freezes the base sidecar, including only that small manifest;
6. invokes Tauri with Cargo `--locked` and the explicit
   `aarch64-apple-darwin` target;
7. places `/usr/bin` and `/bin` first so Tauri uses Apple's `xattr`;
8. remaps the builder home prefix in Rust debug paths;
9. applies an ad-hoc signature through Tauri's `signingIdentity: "-"`;
10. creates the deterministic base ZIP and runs the complete artifact scanner
   against the app, both ZIPs, locks, frozen package versions, license
   inventories, native payloads, and source tree.

The optional component cannot reuse `sys.executable` from a frozen base app:
PyInstaller defines it as the bootloader executable, not as a general Python
interpreter. The separate self-contained onedir artifact is therefore the
owner-approved distribution boundary.

Build outputs:

```text
optional-component/dist/syncbox-deezer-component/
optional-component/dist/syncbox-deezer-component-0.2.2-macos-arm64.zip
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.2-macos-arm64.zip
```

`poc/package_base_app.py` creates the base ZIP as the final step of
`bundle:macos`. Both release ZIPs use `poc/reproducible_archive.py`; do not
recreate either archive with the system `zip` command because that would
discard the controlled entry order, modes, and `SOURCE_DATE_EPOCH` timestamps.

Build artifacts are ignored and must not be committed.

## Automated release (GitHub Actions)

Pushing a tag `vX.Y.Z` runs `.github/workflows/release.yml`, which rebuilds
the artifacts on a hosted Apple Silicon runner through the same
`pnpm bundle:macos` entry point and publishes the GitHub release with both
ZIPs, the convenience DMG, and a `SHA256SUMS.txt`. The tag must match
`ui/package.json` and `release-build.json`; the sidecar and UI test suites
must pass; and two isolated absolute source roots are built in parallel —
the release is blocked unless their ZIPs are byte-identical.

Hosted runners cannot match the pinned Apple host toolchain, so the workflow
sets `SYNCBOX_RELEASE_HOST_TOOLCHAIN=unpinned`: the six Apple host fields
(`apple_clang`, `apple_ld`, `developer_dir`, `macos_build`, `macos_sdk`,
`macos_sdk_path`) are logged for provenance instead of enforced, and
`SDKROOT` is resolved from the runner's `xcrun`. Every other pin — rustc,
cargo, node, pnpm, uv, the Tauri CLI, both managed Python runtimes, locks,
licenses, and the full artifact scanner — remains fail-closed. CI artifacts
are therefore reproducible against themselves on the runner image, not
byte-identical to a build from the pinned local host.

## Verification

From the repository root:

```sh
APP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
APP_ZIP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.2-macos-arm64.zip
COMPONENT_ZIP=optional-component/dist/syncbox-deezer-component-0.2.2-macos-arm64.zip

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
- a SQLCipher provider other than CommonCrypto, missing `cipher_status`, an
  unexpected SQLCipher/OpenSSL native link, or local-source inventory drift;
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
`shell/harness/`. The Phase 7 release rerun is summarized in `poc/README.md`;
the baseline commands and detailed measurements are recorded in
`poc/08-phase6-packaging-lifecycle.md`.

The supervised API/SSE service owns `127.0.0.1:8766`. Spotify authorization
pre-binds only the exact `http://127.0.0.1:8765/callback` listener and releases
it after a terminal callback, timeout, disconnect, or shutdown. Lifecycle
validation must check the two ports independently and must preserve foreign
listeners on either port.

## Release publication

The base manifest for 0.2.2 pins the optional asset to:

```text
Name:   syncbox-deezer-component-0.2.2-macos-arm64.zip
Bytes:  17,340,644
SHA-256: 13976d4b49c345e241e0cac9a9465a06eeebafb97c36f246214b653785a7b9dd
URL:    https://github.com/Adridot/syncbox/releases/download/v0.2.2/syncbox-deezer-component-0.2.2-macos-arm64.zip
```

That exact byte stream is published in GitHub Release `v0.2.2`. Its public
HTTPS download passed byte equality, size/hash, scanner, and live packaged
installation checks. A differently rebuilt asset must receive a new version,
manifest, and rebuilt base application; never replace the published asset
while retaining the old manifest.

The published base ZIP is 29,296,019 bytes with SHA-256
`296fbece128497c8eb21a4000843805bf0ec858b3d250a3da8e7d3654346663c`.
Its strict scanner passes. The base contains 30 arm64 Mach-O files, has an
effective macOS 14.0 minimum, uses CommonCrypto for SQLCipher, and contains no
streamrip. The optional artifact contains 28 arm64 Mach-O files, has an
effective macOS 11.0 minimum, includes artwork-capable Pillow payloads, and
exposes only the Deezer provider. Real source, frozen, installed, and packaged
lanes embedded the artwork in a full-length audio file produced by these exact
optional bytes. Two isolated absolute source roots produced byte-identical
ZIPs and unpacked trees for both artifacts. The public downloads are
byte-identical to those validated streams and pass the downloaded scanner and
runtime matrix. The authoritative evidence is
`docs/_handoffs/final-release-closure.md` (archived in git history).

## Trust boundary and completed release gates

`spctl` is not an acceptance test for this artifact because there is no
Developer ID or notarization ticket. `codesign --verify --deep --strict`
passes. After the first blocked launch of an artifact they trust, local users
may use **System Settings → Privacy & Security → Open Anyway**, then confirm
**Open**, as described in Apple's
[unknown-developer guidance](https://support.apple.com/guide/mac-help/mh40616/mac).

The published release closed these gates:

- upload and revalidate the exact optional component Release asset;
- preserve the scanner-verified `io.github.adridot.syncbox` bundle identifier
  and close any older Syncbox process before replacing it; the sidecar
  continues to use `~/Library/Application Support/Syncbox`, so the identifier
  change does not relocate the existing database or secret store;
- preserve the proven byte-identical base and optional artifacts from two
  clean absolute source roots and the independent scanner pass in each root;
- keep the completed packaged Spotify PKCE, refresh, forged-state, revocation,
  encrypted-storage, listener-shutdown, and port-release evidence green;
- preserve the completed real artwork evidence through the exact source,
  frozen, installed, and packaged optional-component lanes;
- upload both exact validated byte streams and revalidate their public HTTPS
  downloads without silently replacing a published asset;
- add Developer ID signing/notarization only if a frictionless public install
  becomes a requirement.

The private automated Rekordbox fixtures and the owner-approved Rekordbox
7.2.16 disposable-copy walkthrough pass with the CommonCrypto runtime. The
untouched live directory was restored exactly after the Smart Fix and retained
event checks. No legal-compliance, Gatekeeper-acceptance, or notarization claim
is made. The final handoff records the completed two-root and public-download
proofs. Repository-wide immutable releases remain disabled; no asset rewrite
option was used, and any future byte change requires a new version and tag.
