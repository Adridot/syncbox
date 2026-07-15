# Syncbox 0.2.2 Final Release Closure

Date: 2026-07-15

## Current verdict

**FINAL CANDIDATE VALIDATION IN PROGRESS — NOT YET PUBLISHED.**

All source, real-Rekordbox, UI, Rust, lifecycle, bundle, identity, OAuth,
license, and deterministic-packaging gates listed below have executable
evidence. The remaining gates are the final two-root rebuild, live Deezer
artwork embedding on those exact optional bytes, the post-CommonCrypto manual
Rekordbox walkthrough if the owner authorizes another disposable swap, and
GitHub Release publication followed by public download-back validation.

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
- The complete Python suite passes: `580 passed, 1 skipped`. The sole skip is
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
- `poc/run_event_migration_tests.py`: exactly 1 passed, zero skips, all eight
  declared source files unchanged.
- The ten-node run includes the real Smart Fix copied-fixture node. Every
  previewed value matched the copied database, execution was idempotent, and
  the next preview was empty.
- Rekordbox 7.2.16 previously passed the approved disposable-copy walkthrough:
  reopen, playback, cues, beatgrid, waveform and analysis, MyTags, playlists,
  Smart Fix metadata, volume-relative paths, and ANLZ PPTH readability. That
  walkthrough predates the switch to CommonCrypto; a new data-directory swap
  requires a fresh exact procedure and owner confirmation immediately before
  it is attempted.

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
- This evidence is not legal advice and makes no claim beyond the assembled
  inventory, notices, source locations, and tested artifact boundaries.

## Optional artwork candidate

The exact final candidate is not yet the published proof:

```text
Name:    syncbox-deezer-component-0.2.2-macos-arm64.zip
Bytes:   17,340,517
SHA-256: 37fb7375a357a0fb218709a2092632fd18d99c828c541c341645969eda1fb39c
```

- Pillow 10.4.0 is pinned to the official CPython 3.13 macOS 11 arm64 wheel,
  SHA-256 `6209bb41dc692ddfee4942517c19ee81b86c864b626dbfca272ec0f7cff5d9fb`.
- The scanner passes 242 ZIP entries, 28 arm64 ad-hoc-signed Mach-O files,
  effective minimum macOS 11.0, 31 frozen runtime distributions, exact native
  payloads, certifi TLS, and Deezer-only provider exposure.
- The artifact contains no SoundCloud, Qobuz, Tidal, generic streamrip CLI,
  ffmpeg, streamrip database, generated `config.toml`, credential, or token.
- Two consecutive clean freezes in the same controlled root produced the exact
  candidate bytes above. Independent-root equality and live artwork embedding
  remain required.

## Base application candidate

The exact final candidate is not yet the published proof:

```text
Name:    Syncbox-0.2.2-macos-arm64.zip
Bytes:   29,295,890
SHA-256: 454043354c97b7de03b2858503c0e2b0754432a81bbaaa0dfdd015fef4482e4c
```

- The strict scanner passes with 30 arm64 ad-hoc-signed Mach-O files,
  effective minimum macOS 14.0, 155 sorted base-library modules, 23 frozen
  runtime distributions, CommonCrypto SQLCipher, and exact app/ZIP equality.
- The scanned application tree is 59,244,723 bytes with normalized digest
  `7eff8bc22eefacffb7967dd76523d9ee11aa44a9e777bcfa77fcb0231f514d7c`.
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

- Source: ready 0.67 s; respawn 0.40 s; HTTP shutdown 292 ms; TERM 238 ms;
  KILL released the port; no child or orphan remained.
- Frozen: ready 5.82 s; respawn 0.38 s; HTTP shutdown 291 ms; TERM 186 ms;
  KILL released the port.
- App-embedded sidecar: ready 0.56 s; respawn 0.39 s; HTTP shutdown 289 ms;
  TERM 181 ms; KILL released the port.
- Optional source/frozen/packaged installation lanes pass. Ready/install
  measurements are 0.56 s/5.95 s, 0.44 s/5.44 s, and 1.32 s/31.11 s.
- A second packaged launch exits 0 in 0.13 s and leaves one sidecar.
- Foreign listeners are preserved, stale listeners are reaped and replaced,
  five immediate failures leave no listener, and supervisor backoff is exactly
  1/2/4 seconds before `BACKEND_DOWN`; manual recovery returns healthy.
- Graceful, TERM, and KILL shutdowns leave no orphan and release ports 8765 and
  8766. SSE completion and reconnect pass in the UI suite.
- The packaged WKWebView walkthrough covered onboarding, Settings, Library,
  the connected Spotify state and playlist list, and displayed version 0.2.2.

## Remaining release gates

1. Build the exact frozen source from two clean, different absolute roots;
   require identical base and optional ZIP bytes and unpacked trees, and run
   the complete scanner independently in both roots.
2. Run real full-track Deezer acquisition with a local one-shot credential
   through source, frozen, installed, and packaged lanes; prove the artwork is
   embedded in the resulting audio and no credential/config/database remains.
3. If the owner authorizes it immediately beforehand, repeat the exact safe
   disposable Rekordbox data-directory swap and manual walkthrough with the
   CommonCrypto candidate.
4. Commit and push the exact release source, create `v0.2.2` without replacing
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

Exact source URLs and immutable hashes for every inventoried dependency and
bundled native library are stored in the two dependency inventories.
