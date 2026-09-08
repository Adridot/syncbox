# Distribution

This is the release contract for Syncbox. The supported v1 target is macOS 14
or later on Apple Silicon. Each published release contains three independent
ZIP artifacts, a convenience DMG installer, and `SHA256SUMS.txt`:

- `Syncbox-X.Y.Z-macos-arm64.zip`, containing the Tauri application and its
  base PyInstaller onedir sidecar;
- `syncbox-deezer-component-X.Y.Z-macos-arm64.zip`, a separately distributed
  optional PyInstaller onedir component;
- `syncbox-web-audio-component-X.Y.Z-macos-arm64.zip`, the separate optional
  YouTube/YouTube Music and SoundCloud component.

The base application is complete without either optional component. It neither
imports nor bundles streamrip or yt-dlp. Each component is disabled by default,
downloaded only after explicit enablement, and verified against its manifest
embedded in the base sidecar.

The artifacts are ad-hoc signed where macOS tooling requires a
signature. They have no Developer ID signature, notarization,
auto-update mechanism, Keychain dependency, or Windows build. Do not describe
them as trusted by Gatekeeper.

## Prerequisites

- Apple Silicon Mac running macOS 14 or later;
- Xcode Command Line Tools and Rust;
- Node.js, pnpm, and uv;
- committed `pnpm-lock.yaml`, `shell/src-tauri/Cargo.lock`,
  `sidecar/uv.lock`, `optional-component/uv.lock`, and `web-audio-component/uv.lock` files.

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

cd ../web-audio-component
uv lock --check
uv sync --locked --managed-python

cd ..
export SOURCE_DATE_EPOCH="$(jq -r .source_date_epoch release-build.json)"
uv run --project web-audio-component python scripts/build_web_audio_native.py
uv run --project web-audio-component python -m pytest web-audio-component/tests -q
uv run --project web-audio-component python scripts/package_web_audio_component.py

cd shell
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
5. freezes the base sidecar, including both small component manifests;
6. invokes Tauri with Cargo `--locked` and the explicit
   `aarch64-apple-darwin` target;
7. places `/usr/bin` and `/bin` first so Tauri uses Apple's `xattr`;
8. remaps the builder home prefix in Rust debug paths;
9. applies an ad-hoc signature through Tauri's `signingIdentity: "-"`;
10. creates the deterministic base ZIP and runs the complete artifact scanner
   against the app, base/Deezer ZIPs, locks, frozen package versions, license
   inventories, native payloads, and source tree.

The preceding web-audio packaging step verifies its native payloads, complete
notice inventory, deterministic archive and manifest before the base app embeds
that manifest. The release workflow repeats this whole recipe in two roots.

The optional component cannot reuse `sys.executable` from a frozen base app:
PyInstaller defines it as the bootloader executable, not as a general Python
interpreter. The separate self-contained onedir artifact is therefore the
owner-approved distribution boundary.

Build outputs:

```text
optional-component/dist/syncbox-deezer-component/
optional-component/dist/syncbox-deezer-component-X.Y.Z-macos-arm64.zip
web-audio-component/dist/syncbox-web-audio-component-X.Y.Z-macos-arm64.zip
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-X.Y.Z-macos-arm64.zip
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-X.Y.Z-macos-arm64.dmg
```

`scripts/package_base_app.py` creates the base ZIP as the final step of
`bundle:macos`. All release ZIPs use `scripts/reproducible_archive.py`; do not
recreate an archive with the system `zip` command because that would
discard the controlled entry order, modes, and `SOURCE_DATE_EPOCH` timestamps.

Build artifacts are ignored and must not be committed.

## Automated release (GitHub Actions)

`.github/workflows/release-pin.yml` is the authoritative preparation step for
both optional-component manifests. It runs on the same `macos-15` class as the
release, exports `optional-component-manifest` and `web-audio-component-manifest`,
and blocks a release PR when either committed manifest differs. A manual preparation run reports drift but
stays successful so its artifact can be downloaded and committed.

Do not use a local component build as the release pin. The archive contains
Mach-O binaries whose bytes depend on the Apple host image. GitHub-hosted
runner images and a developer Mac can therefore produce different valid
archives even with identical application, Python, Rust, Node, pnpm, uv, and
dependency pins. The release and pin workflows set
`SYNCBOX_RELEASE_HOST_TOOLCHAIN=unpinned`; Apple host fields are logged for
provenance while every project-controlled pin remains fail-closed.

### Release checklist

1. Create a release branch from the latest `master`. Confirm that the target
   `vX.Y.Z` tag and GitHub Release do not already exist.
2. Update the canonical version in `ui/package.json`, then align
   `sidecar/pyproject.toml`, `sidecar/uv.lock`,
   `optional-component/pyproject.toml`, `optional-component/uv.lock`,
   `web-audio-component/pyproject.toml`, `web-audio-component/uv.lock`,
   `web-audio-component/web_audio.py` (`VERSION`),
   `shell/package.json`, `shell/src-tauri/Cargo.toml`,
   `shell/src-tauri/Cargo.lock`, `release-build.json`, the README release
   links, and versioned reproducibility expectations. Regenerate the release
   license inventories (`release/licenses/*/texts/` is generated material,
   not committed: `generate_release_licenses.py --check` verifies the committed
   inventory and writes the texts the PyInstaller specs bundle). Do not edit any field in
   `sidecar/src/syncbox/optional_component.json` or `web_audio_component.json`;
   the hosted workflow replaces both whole files in step 4. Dependency versions
   remain independently pinned; they do not inherit the application version.
3. Run the dependency lock checks, release-license check, Cargo metadata
   check, and `git diff --check`. Commit and push this initial release
   preparation. The full sidecar suite is expected to fail its version guard
   until the hosted manifest is committed.
4. Before opening or merging the release PR, generate the hosted-runner pin:

   ```sh
   release_branch="$(git branch --show-current)"
   gh workflow run release-pin.yml --ref "$release_branch"
   gh run list --workflow release-pin.yml --branch "$release_branch" --limit 1
   gh run watch RUN_ID --exit-status
   release_pin_dir="$(mktemp -d)"
   gh run download RUN_ID -n optional-component-manifest -D "$release_pin_dir"
   gh run download RUN_ID -n web-audio-component-manifest -D "$release_pin_dir"
   cp "$release_pin_dir/optional_component.json" \
      sidecar/src/syncbox/optional_component.json
   cp "$release_pin_dir/web_audio_component.json" \
      sidecar/src/syncbox/web_audio_component.json
   ```

5. Review the manifest diffs and commit them with the release branch. Run the
   complete locked sidecar suite, UI typecheck/tests, release-license check,
   Cargo metadata check, and `git diff --check`, then push. Open or update the
   PR. Do not merge until CI, CodeQL, and
   `Release Pin / component manifest` are green. If the hosted runner image
   changed, repeat step 4 on the same branch; never solve pin drift by creating
   a tag first. Run `gh workflow run release.yml --ref "$release_branch"` for
   a complete build-only preflight: both roots and their ZIP comparison must
   pass. Manual dispatch never publishes a release.
6. Review and merge the PR. Fetch `master`, recheck every version from the
   merged commit, then create and push one annotated `vX.Y.Z` tag on that exact
   commit. Never move or replace a published release tag.
7. Watch `.github/workflows/release.yml` through completion. It rebuilds two
   isolated absolute source roots, checks both manifests against the tagged
   source, requires byte-identical ZIPs, and publishes the GitHub Release with
   the application ZIP, convenience DMG, both optional components, and
   `SHA256SUMS.txt`.
8. Verify that the Release is public, non-draft, non-prerelease, points to the
   merged commit, and exposes uploaded assets whose size and SHA-256 match the
   committed manifests and `SHA256SUMS.txt`. Download the public assets and
   independently verify their hashes; do not rely only on the upload response.

## Verification

From the repository root:

```sh
APP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
APP_ZIP=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-X.Y.Z-macos-arm64.zip
COMPONENT_ZIP=optional-component/dist/syncbox-deezer-component-X.Y.Z-macos-arm64.zip

codesign --verify --deep --strict "$APP"
PYI_ARCHIVE_VIEWER=sidecar/.venv/bin/pyi-archive_viewer \
  sidecar/.venv/bin/python scripts/run_phase6_packaging.py \
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
`shell/harness/`. The Phase 7 release rerun is summarized in `docs/POC-EVIDENCE.md`;
the baseline commands and detailed measurements are recorded in
the phase 6 packaging-lifecycle evidence archived in git history.

The supervised API/SSE service owns `127.0.0.1:8766`. Spotify authorization
pre-binds only the exact `http://127.0.0.1:8765/callback` listener and releases
it after a terminal callback, timeout, disconnect, or shutdown. Lifecycle
validation must check the two ports independently and must preserve foreign
listeners on either port.

## Release publication

The manifests embedded in each base application pin the matching optional
asset names, URLs, byte sizes, and SHA-256 values. The release workflow publishes
those exact byte streams and a `SHA256SUMS.txt` generated from all final assets. A
differently rebuilt asset requires a new version, manifest, base application,
tag, and GitHub Release; never replace an asset behind an existing manifest or
move an existing release tag.

Version-specific sizes, hashes, test results, and build provenance belong to
the immutable GitHub Release and its workflow run, not this long-lived
document. Keeping the contract version-neutral prevents stale release values
from being copied into the next preparation branch.

## Trust boundary and release gates

`spctl` is not an acceptance test for this artifact because there is no
Developer ID or notarization ticket. `codesign --verify --deep --strict`
must pass. After the first blocked launch of an artifact they trust, local users
may use **System Settings → Privacy & Security → Open Anyway**, then confirm
**Open**, as described in Apple's
[unknown-developer guidance](https://support.apple.com/guide/mac-help/mh40616/mac).

Each release must preserve these gates:

- upload and revalidate both exact optional component Release assets;
- preserve the scanner-verified `io.github.adridot.syncbox` bundle identifier
  and close any older Syncbox process before replacing it; the sidecar
  continues to use `~/Library/Application Support/Syncbox`, so the identifier
  change does not relocate the existing database or secret store;
- require byte-identical base and both optional artifacts from two
  clean absolute source roots and the independent scanner pass in each root;
- keep the completed packaged Spotify PKCE, refresh, forged-state, revocation,
  encrypted-storage, listener-shutdown, and port-release evidence green;
- preserve the completed real artwork evidence through the exact source,
  frozen, installed, and packaged optional-component lanes;
- upload all exact validated byte streams and revalidate their public HTTPS
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
