# Syncbox 0.2.2 Final Release Closure

Date: 2026-07-15

## Current verdict

**FINAL CANDIDATE VALIDATION IN PROGRESS — NOT YET PUBLISHED.**

All source, real-Rekordbox, UI, Rust, lifecycle, bundle, identity, OAuth,
license, artwork, controlled local packaging, two-root reproducibility, and
exact-final-byte lifecycle gates listed below have executable evidence. The
remaining gates are GitHub Release publication followed by public
download-back validation.

No pending gate is reported as passed.

## Supported release boundary

- Version: `0.2.2`.
- Application identifier: `io.github.adridot.syncbox`.
- Platform: macOS 14 or later on Apple Silicon.
- Signing: ad-hoc only; no Developer ID and no notarization.
- Base artifact: complete without acquisition and contains no streamrip.
- B1: separately distributed Deezer-only component, disabled by default.
- B2: primary missing-track path; browser-only Beatport and Bandcamp searches.
- A3: full detector remains `NO-GO`; the conservative result is truthful,
  deterministic, and keeper-neutral.
- Deferred: Windows, Keychain, auto-update, SoundCloud, ffmpeg, Chromaprint,
  AcoustID, cloud backend, and all other v2 work.

## Source and dependency gates

- `uv lock --check` passes for the base and optional projects.
- Clean locked syncs pass with managed CPython 3.14.2 and 3.13.11.
- `uv pip check` passes for 37 base and 42 optional installed packages.
- The complete Python suite passes: `582 passed, 1 skipped`. The sole skip is
  the raw retained-event test when no private fixture is configured; its
  dedicated private harness passes separately with zero skips.
- UI: 22 Vitest files and 78 tests pass; typecheck passes; production build
  transforms 197 modules.
- Rust: 3 tests pass and the locked `aarch64-apple-darwin` check passes.
- The release environment pins Node 24.13.0, pnpm 10.29.3, Rust 1.96.1,
  Tauri CLI 2.11.4, uv 0.9.28, PyInstaller 6.21.0, macOS build 25F84,
  Apple clang 21.0.0, and macOS SDK 26.4.1.

## Real Rekordbox evidence

- The strict process guard confirmed that Rekordbox and rekordboxAgent were
  closed before every fixture operation.
- The private fixtures are regular files under ignored `poc/testdata/`; no
  private database, XML, audio, ANLZ, credential, token, or personal path is
  tracked.
- `poc/run_real_rekordbox_tests.py`: exactly 10 passed, zero skips, all three
  source fixtures unchanged by size, timestamps, and SHA-256.
- `poc/run_event_migration_tests.py`: exactly 1 passed, zero skips, all seven
  declared source files unchanged. The derived fixture was checkpointed and
  canonicalized to SQLite DELETE journal mode through CommonCrypto SQLCipher;
  no empty or inapplicable WAL/SHM file is retained.
- The ten-node run includes the real Smart Fix copied-fixture node. Every
  previewed value matched the copied database, execution was idempotent, and
  the next preview was empty.
- After an immediately preceding owner authorization, Rekordbox 7.2.16 passed
  the CommonCrypto disposable-copy walkthrough. The Smart Fix copy displayed
  the exact corrected metadata and preserved playback, cues, beatgrid,
  waveform, analysis, MyTags, and playlists. The retained-event copy preserved
  playback, cue, beatgrid, waveform, analysis, its non-event MyTag and playlist
  membership, the volume path, and ANLZ PPTH readability.
- The original live data directory was held untouched during both checks. Its
  12,718-file manifest had SHA-256
  `1b523e27bf96539f0d498a65a57240ff64eba7648c5d3810b107fee07042c074`
  before the swap and after restoration. The strict guard was closed before
  and after every transition, the hold directory was removed by the atomic
  restore, and the private test volume was detached.

## Identity and data compatibility

- Source configuration, generated `Info.plist`, executable resources, and the
  strict scanner use `io.github.adridot.syncbox` and contain no stale
  `dev.syncbox.app` value.
- Application data remains in `~/Library/Application Support/Syncbox`, so the
  identifier change does not relocate settings or encrypted secrets.
- A private regular copy of the existing encrypted secret store opened with
  the CommonCrypto build and returned `integrity_check=ok`; no secret value or
  key was recorded.

## License and redistribution evidence

- The base bundle contains 321 inventory entries and 588 redistribution files.
- The optional bundle contains 47 inventory entries and 87 redistribution
  files.
- Each bundle contains the Syncbox MIT license, a consolidated notice, exact
  versions and sources, machine-readable inventory, and all referenced license
  texts.
- The optional inventory records streamrip 2.2.0 at commit
  `189acda489927719aa8591f6acdd7d67aecf929b`, its exact GPL-3.0-only text,
  source availability, Pillow and native-library notices.
- The owner explicitly accepted these reviewed v1 distribution dependencies:
  mutagen 1.48.1 GPL-2.0-or-later; streamrip 2.2.0 GPL-3.0-only; deezer-py
  1.3.6 GPL-3.0-or-later; PyInstaller bootloader 6.21.0 GPL-2.0-or-later with
  Bootloader exception; and the exact MPL-2.0 dependencies `bidict`, `certifi`,
  `cssparser`, `cssparser-macros`, `dtoa-short`, `option-ext`, and `selectors`.
- Build-only PyInstaller packages are marked `distributed: false`.
- The policy still fails closed on any unlisted non-permissive license.
- The scanner aligns every frozen Python distribution in both artifacts with
  its locked runtime graph and embedded license inventory.
- Native coverage is exhaustive and fail-closed: all 30 base Mach-O files map
  to 29 inventoried third-party/license owners plus one project-owned shell,
  and all 28 optional Mach-O files map to inventoried owners. Any additional,
  removed, or renamed native artifact fails the scanner.
- This evidence is not legal advice and makes no claim beyond the assembled
  inventory, notices, source locations, and tested artifact boundaries.

## Optional artwork candidate

The exact local final candidate is not yet the published proof:

```text
Name:    syncbox-deezer-component-0.2.2-macos-arm64.zip
Bytes:   17,340,644
SHA-256: 13976d4b49c345e241e0cac9a9465a06eeebafb97c36f246214b653785a7b9dd
```

- Pillow 10.4.0 is pinned to the official CPython 3.13 macOS 11 arm64 wheel,
  SHA-256 `6209bb41dc692ddfee4942517c19ee81b86c864b626dbfca272ec0f7cff5d9fb`.
- The scanner passes 242 ZIP entries, 28 arm64 ad-hoc-signed Mach-O files,
  effective minimum macOS 11.0, 31 frozen runtime distributions, exact native
  payloads, certifi TLS, and Deezer-only provider exposure.
- The artifact contains no SoundCloud, Qobuz, Tidal, generic streamrip CLI,
  ffmpeg, streamrip database, generated `config.toml`, credential, or token.
- A real one-shot-credential run passed through source, the exact frozen
  component, installation through the base boundary, and the packaged app.
  Every lane resolved ISRC `USQX91300105` to Deezer track `67238732`, returned
  `track.download_path`, produced a 337.56-second 13,540,687-byte MP3, and
  verified an embedded 500x500 JPEG cover in ID3 APIC metadata. The output,
  one-shot credential, encrypted-store test value, and temporary case data
  were deleted; no generated streamrip configuration or database remained.
- The frozen runner now verifies that streamrip artwork uses the actual
  `BasicDownloadable` implementation loaded by the constrained component
  rather than its import-time placeholder. Independent-root equality is
  proven below.

## Base application candidate

The exact local final candidate is not yet the published proof:

```text
Name:    Syncbox-0.2.2-macos-arm64.zip
Bytes:   29,296,019
SHA-256: 296fbece128497c8eb21a4000843805bf0ec858b3d250a3da8e7d3654346663c
```

- The strict scanner passes with 30 arm64 ad-hoc-signed Mach-O files,
  effective minimum macOS 14.0, 155 sorted base-library modules, 23 frozen
  runtime distributions, CommonCrypto SQLCipher, and exact app/ZIP equality.
- The scanned application tree is 59,245,018 bytes with normalized digest
  `e034f55644c9c4d2772c706ce59fc7ebe62b4ad46fe2c3a0ad3c0fd9390fa5c1`.
- The base imports and contains no streamrip, Deezer acquisition runtime,
  external Python dependency, secret, local installation metadata, or legacy
  bundle identifier.

## SQLCipher evidence

- The owner selected Apple CommonCrypto.
- The local inventoried binding is
  `sqlcipher3-wheels 0.6.2+syncbox.commoncrypto.1`, containing SQLCipher 4.12.0
  community and SQLite 3.51.1.
- Runtime reports `cipher_provider=commoncrypto`, `cipher_status=1`, and a
  non-empty provider version.
- The extension links Security, CoreFoundation, and libSystem; it does not link
  OpenSSL or `libcrypto`.
- Release builds remove only the local fork's generated `build/` and
  `sqlcipher3_wheels.egg-info/` before source hashing and in a `finally` block.

## Packaged Spotify OAuth evidence

- The owner selected permanent API/SSE on `127.0.0.1:8766` and a temporary
  exact callback listener at `http://127.0.0.1:8765/callback`.
- The packaged app launched the system browser with Authorization Code + PKCE,
  S256, a fresh verifier and state, and only
  `playlist-read-private playlist-read-collaborative`.
- Owner-approved authorization succeeded and 27 playlists were accessible.
- A forced real 401 refreshed the access token, preserved the refresh token,
  and again returned 27 playlists.
- A forged state returned HTTP 400, left the valid listener active, and did not
  alter token hashes.
- An isolated encrypted-store copy with an invalid refresh token returned
  `spotify_not_connected`, deleted both invalid tokens, kept source stores
  unchanged, and logged no token sentinel.
- The callback listener stopped and port 8765 was released after success,
  timeout, and terminal recovery. The secrets database is not plaintext SQLite
  and its key file mode is 0600. No client secret is requested or stored.
- Browser accessibility exposed one single-use authorization code after the
  redirect; it had already been exchanged and was not recorded in repository,
  app logs, fixtures, screenshots, exports, or this report.

## Lifecycle evidence

- Source: ready 4.21 s; respawn 0.39 s; HTTP shutdown 289 ms; TERM 186 ms;
  KILL released the port; no child or orphan remained.
- Frozen: ready 5.90 s; respawn 0.38 s; HTTP shutdown 351 ms; TERM 180 ms;
  KILL released the port.
- App-embedded sidecar: ready 0.55 s; respawn 0.39 s; HTTP shutdown 289 ms;
  TERM 173 ms; KILL released the port.
- Optional source/frozen/packaged installation lanes pass. Ready/install
  measurements are 0.45 s/8.81 s, 0.45 s/5.75 s, and 1.32 s/30.94 s.
- A second packaged launch exits 0 in 0.13 s and leaves one sidecar.
- Foreign listeners are preserved, stale listeners are reaped and replaced,
  five immediate failures leave no listener, and supervisor backoff is exactly
  1/2/4 seconds before `BACKEND_DOWN`; manual recovery returns healthy.
- Graceful, TERM, and KILL shutdowns leave no orphan and release ports 8765 and
  8766. SSE completion and reconnect pass in the UI suite.
- The packaged WKWebView walkthrough covered onboarding, Settings, Library,
  the connected Spotify state and playlist list, and displayed version 0.2.2.
  The exact final bundle rerun additionally covered all six routes, the five
  Collection Health tabs, Spotify and optional-Deezer settings, and a normal
  menu quit with an intentional sidecar handshake and no remaining process or
  listener.
- The post-runtime strict scanner and `codesign --verify --deep --strict`
  remain green on the exact reproducible bytes.

## Two-root artifact reproducibility

- Two isolated source roots at different absolute paths contained the same
  1,024-file release-source manifest. The final comparator output records its
  digest without introducing a self-referential digest into that manifest.
- Each root built and independently scanned the base and optional artifacts
  under the pinned release environment.
- Both base ZIPs are byte-identical at 29,296,019 bytes with SHA-256
  `296fbece128497c8eb21a4000843805bf0ec858b3d250a3da8e7d3654346663c`.
  Their unpacked trees are identical with normalized digest
  `2d5b36a6113fa61f8693dcd6318bcb793373d3219583521095dd6a2da662fb0d`.
- Both optional ZIPs are byte-identical at 17,340,644 bytes with SHA-256
  `13976d4b49c345e241e0cac9a9465a06eeebafb97c36f246214b653785a7b9dd`.
  Their unpacked trees are identical with normalized digest
  `21e62e890ee4e86317d82a56b7cee14faecb26d48ad452499ae177c925103810`.
- The comparator reported no source, ZIP-entry, or unpacked-tree difference.
  No binary patch or mismatch exception was used.

## Remaining release gates

1. Commit and push the exact release source, create `v0.2.2` without replacing
   any existing public asset, upload the validated bytes, publish, download
   both assets through public HTTPS URLs, and repeat size, SHA-256, scanner,
   installation, and live runtime validation on the downloaded bytes.

## Material primary sources

- [RFC 8252: OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [Spotify PKCE flow](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)
- [Spotify redirect URI requirements](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)
- [SQLCipher community source](https://github.com/sqlcipher/sqlcipher)
- [SQLCipher provider diagnostics](https://www.zetetic.net/sqlcipher/sqlcipher-api/)
- [PyInstaller reproducible builds](https://pyinstaller.org/en/v6.21.0/advanced-topics.html#creating-a-reproducible-build)
- [PyInstaller license and bootloader exception](https://pyinstaller.org/en/v6.21.0/license.html)
- [PyPA installed-project metadata (`RECORD` is optional)](https://packaging.python.org/en/latest/specifications/recording-installed-packages/)
- [Tauri macOS bundles](https://v2.tauri.app/distribute/macos-application-bundle/)
- [Tauri configuration](https://v2.tauri.app/reference/config/)
- [uv locked sync](https://docs.astral.sh/uv/concepts/projects/sync/)
- [Reproducible Builds `SOURCE_DATE_EPOCH`](https://reproducible-builds.org/docs/source-date-epoch/)
- [GitHub Release assets](https://docs.github.com/en/rest/releases/assets)
- [GitHub immutable releases](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/immutable-releases)
- [deezer-py 1.3.6 metadata](https://pypi.org/pypi/deezer-py/1.3.6/json)
- [Python `os.replace`](https://docs.python.org/3/library/os.html#os.replace)
- [Python `shutil.copy2`](https://docs.python.org/3/library/shutil.html#shutil.copy2)
- [Rekordbox 7.2.14 manual: backup and restore](https://cdn.rekordbox.com/files/20260409151936/rekordbox7.214_manual_EN.pdf)
- [streamrip pinned artwork implementation](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/media/artwork.py)
- [Pillow installation guidance](https://pillow.readthedocs.io/en/stable/installation/index.html)
- [SQLite write-ahead logging](https://sqlite.org/wal.html)
- [SPDX package/file relationships](https://spdx.github.io/spdx-spec/v2.3/relationships-between-SPDX-elements/)

Exact source URLs and immutable hashes for every inventoried dependency and
bundled native library are stored in the two dependency inventories.
