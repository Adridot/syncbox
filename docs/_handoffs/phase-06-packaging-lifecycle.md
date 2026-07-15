# Phase 6 Handoff — Packaging, Lifecycle, Secrets, and Reproducibility

Date: 2026-07-13

## Verdict

**READY FOR PHASE 7.**

**FUNCTIONAL LOCAL APPLE SILICON APP AND OPTIONAL COMPONENT: READY.**

**PUBLIC RELEASE ACCEPTANCE: NOT READY.**

Phase 6 rebuilt and validated Syncbox 0.2.1 after the Phase 5 B1 `GO`. The base
PyInstaller onedir remains isolated from streamrip and is embedded in a Tauri
application. Deezer acquisition uses a separate, exact-hash PyInstaller onedir
component and requires no external Python runtime. Source, frozen, packaged,
single-instance, restart, shutdown, secret, lock, native, and artifact gates
pass.

Phase 7 may proceed using the local artifact and contracts below. Public
distribution remains blocked by the explicit release gates; most importantly,
the pinned optional GitHub Release asset has not been uploaded or downloaded
back for verification.

## Scope and owner decisions

- macOS 14+ on Apple Silicon only;
- ad-hoc local signature only; no Developer ID or notarization claim;
- no Windows implementation, Keychain requirement, auto-update, SoundCloud
  feature, or ffmpeg;
- B2 purchase links remain primary and always available;
- B1 is optional, disabled by default, Deezer-only at the Syncbox interface,
  and subordinate to B2;
- the owner selected a separate self-contained onedir Release asset rather
  than managed Python/uv or system Python;
- the component is versioned with the app and verified by embedded size and
  SHA-256 before extraction or execution;
- no real ARL was requested, read, or used during Phase 6;
- no commit, staging, history edit, or push was performed;
- `.idea/` remained untracked and untouched.

The architecture choice follows PyInstaller's documented frozen runtime:
`sys.executable` points to the bootloader and cannot safely create the previous
source-style venv. The separate component is the approved distribution
boundary.

## Final artifacts

```text
Base app:
  shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
Base ZIP:
  shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox-0.2.1-macos-arm64.zip
Optional onedir:
  optional-component/dist/syncbox-deezer-component/
Optional ZIP:
  optional-component/dist/syncbox-deezer-component-0.2.1-macos-arm64.zip
```

Base application:

```text
Version:                     0.2.1
App file bytes:              62,179,355
ZIP bytes:                   32,479,713
Mach-O files:                30, all arm64
Declared/effective minimum:  macOS 14.0 / 14.0
Signature:                   ad-hoc, no Team ID or Developer ID
App tree SHA-256:            91a22f36eedd8085722a5fc8b8c7cf30e85002aca793bde2b0560ceab7d17062
ZIP SHA-256:                 851b6c98a49ec068671088dfd3577fe62df24cc5f7673bfd0141389b0192f091
Shell SHA-256:               8f1d68cb67789d1e9eb829a788960d379af6d006479077fffaf30afe147a759a
Sidecar executable SHA-256:  ea9e76f999004b6ba423d7d7adba702df63319d1eed01623d962e8a5790c1ff1
```

Optional component:

```text
Version:                     0.2.1
ZIP bytes:                   19,072,885
Mach-O files:                55, all arm64
Effective minimum:           macOS 11.0
ZIP SHA-256:                 92ccd44e07523818854d52926a6e479c798f2f324e27b3f997586b9d98e2a181
Executable SHA-256:          338ce9ab7f4391e0684c8660dea06b3fa061bee4d0cfe9da6e1a75faaab52ebc
streamrip:                   2.2.0 at 189acda489927719aa8591f6acdd7d67aecf929b
certifi:                     2026.6.17
```

`codesign --verify --deep --strict` passes. The base ZIP exactly matches the
validated app tree. Repacking the same component onedir reproduces its exact
ZIP bytes and hash. Generated artifacts remain ignored and are not intended
for commit.

## Implementation delivered

### Base/component boundary

- `optional-component/` is a separate Python project with CPython 3.14.2,
  its own `uv.lock`, PyInstaller spec, and third-party notice;
- streamrip 2.2.0 is pinned to commit
  `189acda489927719aa8591f6acdd7d67aecf929b`;
- certifi 2026.6.17 and PyInstaller 6.21.0 are pinned;
- the build creates the component first, generates its manifest, then freezes
  the base sidecar and Tauri app;
- the base app includes only `optional_component.json`, not the GPL component;
- the base boot check reports `streamrip_importable=false`;
- the frozen component exposes only the Deezer runner and excludes the
  SoundCloud, Qobuz, Tidal client modules and generic streamrip CLI;
- Pillow is locked upstream but excluded from the binary; artwork remains
  disabled and fails closed if invoked;
- no ffmpeg binary or interface is present.

The upstream streamrip core config schema still names unused providers. Those
fields are not reachable through the Syncbox runner, whose CLI requires an
ISRC, one-shot credential file, and output directory.

### Component installation

- installation requires explicit B1 enablement;
- the default URL is the versioned `v0.2.1` GitHub Release asset;
- certifi-backed HTTPS is required for the public path;
- the exact expected byte count and SHA-256 are embedded in the base;
- extraction rejects absolute/traversal paths, duplicate paths, special files,
  symlink escapes, content below symlinks, and excessive expansion;
- the staged executable must pass `--check` before activation;
- a 0600 marker binds the installed version, commit, certifi version, and hash;
- replacement is staged and atomically swapped with rollback;
- source, frozen, and packaged tests can use a local archive override but still
  apply the same size/hash/extraction/self-check gates;
- the base invokes the installed executable directly, never `sys.executable
  -m venv`, pip, Git, or a source-tree POC path.

### Credential boundary

- the Deezer credential is not a normal setting;
- only the encrypted SQLCipher `SecretsStore` persists it;
- status APIs and the UI expose only `has_arl`, never the value;
- settings and all-data exports, captured logs, fixtures, base bundle, and
  component bundle contain no real credential;
- subprocess arguments contain only the path of a new owner-only one-shot
  file, never the secret value;
- the runner opens that file with no-follow semantics, validates owner/mode,
  consumes and removes it, clears the value as soon as practical, and writes no
  user streamrip config or database;
- the scanner detects common token/private-key forms, generic long hex values,
  and structured ARL assignments beginning at 64 characters.

### Lifecycle retained

The Tauri shell still:

1. acquires the native single-instance guard before setup;
2. preserves a foreign port-8765 listener and replaces only an exact stale
   Syncbox sidecar;
3. starts the embedded sidecar as its own process-group leader;
4. continuously drains stdout and stderr as bytes;
5. restarts unexpected exits with 1/2/4-second backoff;
6. emits backend-down after exhaustion and supports a real manual restart;
7. uses `POST /shutdown`, then process-group TERM/KILL fallbacks;
8. exits with no child, orphan, or retained listener.

## Final validation

### Lifecycle measurements

| Lane | Initial ready | Warm respawn | Graceful shutdown | TERM release | Final state |
|---|---:|---:|---:|---:|---|
| Source sidecar | 0.59 s | 0.35 s | 309 ms | 257 ms | no listener/orphan |
| Frozen sidecar | 0.67 s | 0.40 s | 308 ms | 189 ms | no listener/orphan |

The packaged bundle passed:

- second-instance self-exit with code 0 in 0.15 seconds;
- one primary setup and one sidecar process group;
- foreign-listener preservation and exact stale-Syncbox replacement;
- immediate-exit cleanup;
- 1/2/4-second restart backoff, fourth-crash backend-down, and healthy manual
  restart;
- stdout/stderr consumption, graceful shutdown, no orphan, and port release.

### Optional installation measurements

| Host lane | Ready | Total | Credential | External Python | Final state |
|---|---:|---:|---|---|---|
| Source | 0.59 s | 5.30 s | absent | no | installed, port released |
| Frozen | 6.41 s | 12.22 s | absent | no | installed, port released |
| Packaged | 1.57 s | 31.39 s | absent | no | installed, port released |

The packaged total includes the harness's intentional 30-second lifetime.
Every lane verified the final component SHA-256 shown above.

### Artifact and license scan

- base native imports and in-memory SQLCipher open pass;
- base `uv.lock`, installed venv, PyInstaller module archive, app tree, and ZIP
  contain no streamrip or Deemix distribution;
- component module inventory contains only the Deezer provider client;
- all native files are arm64 and within their declared minimum macOS target;
- no ffmpeg binary, real credential, private key, common token, personal
  repository path, or executable-source implementation marker was detected;
- the base's expected GPL runtime is `mutagen` 1.48.1;
- streamrip's exact GPL license is present in the optional artifact;
- the optional notice is not a complete reviewed transitive redistribution
  inventory, so public licensing acceptance remains blocked.

### Locks, versions, and tests

```text
Base lock:       42 packages resolved; 37 installed in an independent env
Optional lock:   48 packages resolved; 42 installed in an independent env
Python:          493 passed, 11 private-fixture skips in 2.52 s
UI:              20 Vitest files, 70 tests passed
UI:              typecheck and production build passed, 194 modules
Rust:            3 tests passed; locked arm64 cargo check passed
Version:         0.2.1 aligned across Python, Rust, JS, Tauri, manifest, plist
```

### Packaged WKWebView

The final bundle loaded `Syncbox v0.2.1` at `tauri://localhost`, showed the
optional controls disabled by default, and released the backend port after UI
close. The previous same-day packaged Phase 6 POC remains the functional proof
for SSE completion/reconnect and system-browser OAuth launch because the B1
rerun did not change transport or link-opening code. No new live account OAuth
or credential action was performed.

## Reproducibility contract

Dependency resolution, Python selection, target architecture, versions,
builder-path remapping, ZIP construction, and app/ZIP equivalence are
reproducible from committed inputs.

PyInstaller output was not bit-for-bit stable across clean rebuilds on this
host. The release order is therefore load-bearing:

1. build the component;
2. generate and review its manifest;
3. build the base app with that exact manifest;
4. upload that exact component byte stream;
5. download it back and repeat the hash and live install checks.

Replacing a Release asset without rebuilding the manifest-bearing base app is
forbidden.

## Residual limits and release gates

These do not block Phase 7, but they block the corresponding public claim:

1. **Release asset.** The exact optional ZIP is not yet published at the pinned
   GitHub URL. Public HTTPS installation has not been exercised.
2. **Third-party notices.** The base ZIP lacks the root project license and a
   reviewed consolidated notice. The optional notice does not cover every
   redistributed runtime/transitive dependency.
3. **Bundle identity.** This historical Phase 6 artifact still used
   `dev.syncbox.app`; final release work replaces it with the owner-approved
   `io.github.adridot.syncbox` identifier and must rebuild the bundle.
4. **Private Rekordbox fixtures.** Eleven real-data gates remain skipped.
5. **Signing/trust.** No Developer ID, notarization, or Gatekeeper acceptance
   claim exists.
6. **Live OAuth.** Complete Spotify authorization/token refresh still needs
   owner credentials and consent.
7. **Binary reproducibility.** A two-root bit-for-bit result is not claimed.
8. **Artwork.** Re-enabling streamrip artwork requires a new Pillow/minimum-OS
   packaging review.

## Root-thread integration notes

All Phase 6 changes are intentionally uncommitted. Before Phase 7, the root
thread should:

1. review the entire working-tree diff and preserve `.idea/` as unrelated;
2. rerun `git diff --check` and the scanner on the exact artifacts;
3. split component packaging, base integration/security, tests/harnesses, and
   documentation into intentional commits;
4. do not add generated app, ZIP, `dist`, `build`, `target`, venv, or private
   data;
5. publish nothing until the release gates above are explicitly accepted.

Primary documentation:

- `docs/DISTRIBUTION.md` — build, verification, and publication contract;
- `docs/USER_GUIDE.md` — user-visible optional B1 behavior;
- `poc/08-phase6-packaging-lifecycle.md` — exact evidence and measurements;
- `poc/README.md` — authoritative POC states.

Primary official sources:

- [Tauri macOS bundle](https://v2.tauri.app/distribute/macos-application-bundle/)
- [Tauri resources](https://v2.tauri.app/develop/resources/)
- [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html)
- [PyInstaller spec files](https://pyinstaller.org/en/stable/spec-files.html)
- [uv locking](https://docs.astral.sh/uv/concepts/projects/sync/)
- [GitHub Release assets](https://docs.github.com/en/rest/releases/assets)

## Final release closure update — 2026-07-15

This document remains the historical Phase 6 record for version 0.2.1. The
current 0.2.2 evidence, including re-enabled artwork, complete generated
license inventories, the durable bundle identifier, CommonCrypto SQLCipher,
real-Rekordbox automation and manual disposable-copy checks, four-lane live
artwork embedding, packaged OAuth, completed two-root equality, and the
remaining publication/download-back gates, is
recorded in
[`final-release-closure.md`](final-release-closure.md). Do not use the old
0.2.1 hashes, artwork-disabled statement, license gaps, identifier, or
reproducibility verdict as claims about the current candidate.
