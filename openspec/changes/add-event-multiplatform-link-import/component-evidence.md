# Component boundary evidence — 2026-09-07

## Scope and status

Tasks 1.1, 1.2 and 1.4 passed on macOS arm64. The initial source proof used host
tools; the separate frozen-component proof below uses bundled runtimes. Deno's
dependency/native notice inventory was completed on 2026-09-07 (see below).
The owner approved Deno and the seven explicitly scoped MPL dependencies.
Initial component checks did not involve application data. Later integration
checks used an isolated temporary application database and a dummy Rekordbox
fixture; see [packaged-ui-verification.json](packaged-ui-verification.json).
Release readiness and the full native Tauri/Rekordbox workflow are not claimed.
The owner authorized selecting test content during this implementation session.
Only the selected individual items below were downloaded; collections were
enumerated without downloading their contents.

Host versions: yt-dlp 2026.08.19, Deno 2.9.5, FFmpeg/ffprobe 9.0.1 (Homebrew
9.0.1_1). These are observed proof versions, not a committed distribution lock.

## Web source proof

| Resource | Canonical identity | Enumeration | Selected child |
| --- | --- | --- | --- |
| YouTube single, Big Buck Bunny | `f7NwyBnIRTE` | Title and duration resolved | `f7NwyBnIRTE` |
| Official Blender Open Movies playlist | `PL6B3937A5D230E335` | 17/17 entries | Position 16: `YE7VzlLtp-4` |
| YouTube Music album | Browse ID `MPREb_gTAcphH99wE` → playlist `OLAK5uy_l1m0thk3g31NmIIz_vMIbWtyv7eZixlH0` | 50/50 entries | Position 1: `XNEnEBrHws8` |
| SoundCloud single, All This | `1757017227` | Title, duration, `cc-by` license resolved | `1757017227` |
| SoundCloud Folk Music set | `1752070992` | 21/21 entries | Position 1: `1706333112` |

Inputs:

- https://www.youtube.com/watch?v=f7NwyBnIRTE
- https://www.youtube.com/playlist?list=PL6B3937A5D230E335
- https://music.youtube.com/browse/MPREb_gTAcphH99wE
- https://soundcloud.com/trackistador/kevin-macleod-all-this
- https://soundcloud.com/trackistador/sets/folk-music-creative-commons-no

The collection selections were acquired through their individual canonical URLs,
without search or a title/ISRC fallback. Returned IDs equalled the selected IDs.
The SoundCloud child URL was
https://soundcloud.com/trackistador/kevin-macleod-angevin-b.

All five files passed complete decoding with `ffmpeg -v error -xerror -i FILE
-f null -`. The measured outputs and hashes are recorded in
[component-output-evidence.json](component-output-evidence.json).

| Item | Source reported by yt-dlp | Measured output | Duration | Size |
| --- | --- | --- | --- | --- |
| `f7NwyBnIRTE` | Opus, 128.612 kbps | MP3, 48 kHz, 117403 bps | 634.578146 s | 9313148 bytes |
| `YE7VzlLtp-4` | Opus, 130.501 kbps | MP3, 48 kHz, 109718 bps | 596.474208 s | 8181140 bytes |
| `XNEnEBrHws8` | Opus, 154.673 kbps | MP3, 48 kHz, 143776 bps | 267.053333 s | 4800308 bytes |
| `1757017227` | AAC, 160 kbps | MP3, 44.1 kHz, 129601 bps | 228.958458 s | 3709893 bytes |
| `1706333112` | AAC, 160 kbps | Native M4A/AAC, 44.1 kHz, 160000 bps | 129.404807 s | 2611406 bytes |

The first four checks explicitly requested MP3 conversion to exercise processing.
This is not the planned production format-selection policy: native supported
audio must be retained. Conversion does not improve source quality. The fifth
check retained native M4A. Original SoundCloud download-file availability was
not proved; no account/cookies were used.

Reproduction: use `yt-dlp --ignore-config --no-cache-dir --socket-timeout 15
--retries 0 --extractor-retries 0` with `--flat-playlist --dump-single-json URL`
for collections, or `--skip-download --no-playlist` for individual metadata.
For selected-item acquisition use `--no-playlist -f bestaudio`, a dedicated
temporary `--paths` directory and `--output '%(id)s.%(ext)s'`; add
`-x --audio-format mp3` only for the conversion cases above. Use
`--print 'after_move:%(.{id,title,duration,acodec,abr,asr,ext,filepath})j'` to obtain
the effective identity and actual final path. Media remains under
`/tmp/syncbox-link-import-proof-20260907/`; no media is checked into the repository.

Observed limits:

- YouTube Music warns that it redirects album resolution to its equivalent
  YouTube playlist. The resulting immutable child video IDs are available.
- SoundCloud flat set entries can omit titles; resolving child `1706333112`
  returned its title and duration without changing its identity.
- Browsing SoundCloud sets emitted an optional impersonation-support warning,
  but the tested set and selected children succeeded without impersonation.
- Private resources, subscription restrictions, unavailable placeholders,
  geographic differences and SoundCloud album classification remain to be
  covered by later tasks. These public examples do not establish universal access.
- Host success does not prove packaging, transport destination enforcement,
  subprocess-tree cancellation, or application integration (tasks 1.3 onward).

References: [Blender license](https://peach.blender.org/about/),
[SoundCloud sample license](https://soundcloud.com/trackistador/kevin-macleod-all-this),
[upstream YouTube Music album fixture](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_tab.py),
[EJS runtime requirements](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## Strict Deezer identity proof

Pinned streamrip 2.2.0 at `189acda489927719aa8591f6acdd7d67aecf929b` returns
the effective item as `track.downloadable.id`; metadata alone is insufficient.
The runner now accepts opt-in `--exact-item` with a positive `--track-id`, checks
the effective ID before `track.rip()`, and reports it separately from the legacy
`deezer_track_id` result field. Missing identity fails closed. Default acquisition
still accepts the existing Spotify/legacy fallback and lower-quality same-item
audio. Protocol version 2 advertises `exact_deezer_item` and
`effective_deezer_item`. Application capability gating and local component packaging
are implemented; the rebuilt protocol-2 component passed its frozen check.
Task 5.2 is complete. No upgraded archive has been published.

Verification from the repository root:

```sh
uv run --project sidecar python -m pytest sidecar/tests/test_optional_component_runner.py sidecar/tests/test_acquisition.py -q
uv run --project optional-component python scripts/run_b1_deezer_acquisition.py --check
uv run --project optional-component python openspec/changes/add-event-multiplatform-link-import/checks/deezer_identity.py
```

Results: 57 tests passed; component `CHECK_PASSED`; pinned streamrip's real
`get_downloadable` implementation selected fixture item 202 for requested item
101, the legacy guard accepted 202, and the strict guard rejected it. The
fixture replaces catalogue/URL responses and performs no network or audio work.
Wrapper tests also assert refusal before audio creation, credential clearing,
session closure, preserved quality preference and explicit strict selectors.

## Packaging decision and frozen proof — task 1.3

The owner selected a focused LGPL audio build on 2026-09-07. The build is now
implemented by `scripts/build_web_audio_native.py`; the following investigation
records why the host executable is not redistributed.

The repository's current `docs/SPEC-UNIFIED.md:83` policy says: "Any additional
unlisted copyleft dependency fails closed." The packaging checker enforces
per-package reviewed license entries. The owner's focused LGPL decision covers
the selected FFmpeg and LAME configuration.

The host FFmpeg reports `--enable-gpl --enable-version3`, GPL-3.0-or-later and
Homebrew dylib dependencies including x264/x265. Copying that executable alone
would not provide a standalone component. It is not included in the new archive.

Pinned sources and runtimes:

- Python 3.13.11, yt-dlp 2026.08.19, yt-dlp-ejs 0.8.0, PyInstaller 6.21.0.
- FFmpeg/ffprobe 9.0.1, LGPL-2.1-or-later, built with GPL/nonfree/network disabled.
- LAME 3.100 encoder, LGPL-2.0-or-later, with the optional decoder disabled.
- Deno 2.9.5 macOS arm64 release; its project MIT license is not the license
  inventory of the complete executable.
- Exact Python dependencies are in `web-audio-component/uv.lock`; native source
  URLs and SHA-256 pins are in `web-audio-component/native-lock.json`.
- The archive includes FFmpeg/LAME original source tarballs, the LAME export-list
  patch needed by the encoder-only build, build flags, license texts, and Python
  dependency notices. Packaging checks notice paths and hashes; with the
  completed inventories it generates `sidecar/src/syncbox/web_audio_component.json`.

Build command from the repository root:

```sh
uv run --project web-audio-component python scripts/build_web_audio_native.py
SOURCE_DATE_EPOCH=1788739200 uv run --project web-audio-component python scripts/package_web_audio_component.py --draft
```

The initial experimental archive was
`web-audio-component/dist/syncbox-web-audio-component-0.8.0-macos-arm64.zip`:
73,792,234 bytes (70.37 MiB), SHA-256
`56dff5d2c3615fed6524bd806231b85f7a47cf5109cdf0b885cdfd2af9c9895a`.
The final archive supersedes it: **77,520,063 bytes**, SHA-256
`065cc3dbd491c6b77923d19fd821bf86237a0bf2d8bdce990683896b3d7886b4`.
[frozen-verification.json](frozen-verification.json) distinguishes the metadata
proof archive from the final archive used for both audio checks.
No release manifest or installation endpoint references the draft archive.

The frozen executable's `check` operation passed with `PATH=/usr/bin:/bin`,
reporting the pinned yt-dlp/EJS, FFmpeg and Deno versions. Its bundled FFmpeg
reports LGPL-2.1-or-later and only `file`/`pipe` input and output protocols.
The metadata and audio operations below also used `PATH=/usr/bin:/bin`, without
host FFmpeg or Deno. SoundCloud checks used an environment containing only PATH.

| Frozen operation | Result |
| --- | --- |
| SoundCloud single metadata `1757017227` | Passed; exact item returned |
| SoundCloud single download `1706333112` | Passed; native `audio.m4a`, AAC 44.1 kHz, 160000 bps, 129.404807 s, 2611406 bytes |
| YouTube single download `YE7VzlLtp-4` | Passed; `audio.mp3`, MP3 48 kHz, 174564 bps, 596.474208 s, 13016396 bytes |
| YouTube Music album `MPREb_gTAcphH99wE` | Passed; canonical playlist `OLAK5uy_l1m0thk3g31NmIIz_vMIbWtyv7eZixlH0`, 50 entries, no audio |

Both audio results returned the requested effective item identity and passed
full decoding inside the wrapper. SoundCloud source properties were AAC/160 kbps;
YouTube source properties were Opus/130.501 kbps/48 kHz, converted with libmp3lame.
Conversion does not improve source quality. Test workspaces were temporary and
removed after verification. An earlier frozen metadata request for `f7NwyBnIRTE`
failed with `provider_operation_failed` after approximately 100 seconds while a
build overlapped the test; the cause was not established. Later successful checks
do not establish that every YouTube request is reliable.

### Approved dependencies and remaining distribution work

The owner approved retaining Deno 2.9.5 with these seven additional packages in
the isolated web-audio component: `cooked-waker` 5.0.0, `smartstring` 1.0.1,
`webpki-root-certs` 0.26.6, `webpki-roots` 0.26.1, `cssparser` 0.36.0,
`cssparser-macros` 0.6.1 and `dtoa-short` 0.3.5. Their verified crate source
archives are included alongside the native build sources. This decision is
recorded in `docs/SPEC-UNIFIED.md`; no further runtime-choice approval is pending.

The exact Deno tag's conservative macOS runtime graph contains 834 package
entries, including proc macros. The original [deno-license-review.json](deno-license-review.json)
is historical investigation evidence. The current inventories are
`web-audio-component/licenses/deno-inventory.json` and
`web-audio-component/licenses/deno-native/inventory.json`.
All 775 registry source archives were checked against Cargo.lock checksums;
59 workspace packages were also inventoried. The 41 packages that initially
lacked notices were completed on 2026-09-07: 30 root LICENSE files were retrieved
from the declared repositories' default branch (their declared VCS commits are not
retrievable, e.g. SWC `00ec64fe9a4da0973f14721d7b6dc1f13cd75413`; the
checksum-verified crate archives contain no notice file). The remaining 11 crates
(`aead-gcm-stream`, `deno_native_certs`, `deno_tunnel`, `derive-io`,
`derive-io-macros`, `fqdn`, `rustls-tokio-stream`, `sacabase`, `sptr`,
`sys_traits`, `sys_traits_macros`) ship no notice text at all — neither in the
crate archive nor in their repositories (listings checked 2026-09-07) — so the
SPDX 3.28.0 text of their declared license is attached and the declared license
and authors are recorded in `license_evidence`, following the existing
`release/license-overrides/rust` practice.

The native inventory now holds 32 notices. libc++, libc++abi, libunwind and
dragonbox notices were added (rusty_v8 uses its custom libc++; the shipped binary
links no system libc++ and carries libc++/libunwind strings; dragonbox is a
header-only `v8_base` dependency). llvm-libc's notice is attached although no
symbols appear in the binary. `partition_alloc` (off for standalone V8, no
strings in the binary), `third_party/rust` (V8 Temporal is compiled from the
Cargo graph: `temporal_capi`/`temporal_rs` 0.2.3 and icu4x are in the Deno
inventory) and the build-only submodules are recorded as not distributed with
their evidence. Both inventories are `complete: true`; the default packager
generates `web_audio_component.json`. The notice texts themselves are no longer
committed: the inventories pin each text by source and SHA-256 and the packager
materializes them (checksum-verified) before bundling.

The native build now uses a temporary cache path instead of a personal checkout
path, and its dynamic libraries use loader-relative or system paths.
[artifact-checks.json](artifact-checks.json) records successful strict ad-hoc
signature verification and the bundled runtime check. Developer ID signing and
notarization were not performed. These successful artifact checks do not resolve
the missing notices or establish a complete packaged application workflow.
Tasks 1.3 and 7.1 remain open for the complete distribution inventory and gate.

References: [FFmpeg licensing](https://ffmpeg.org/legal.html),
[official source distribution](https://ffmpeg.org/download.html) and
[LAME licensing](https://lame.sourceforge.io/license.txt),
[Deno source tag](https://github.com/denoland/deno/tree/v2.9.5),
[upstream binary-notices issue](https://github.com/denoland/deno/issues/13515),
[yt-dlp supported JS runtimes](https://github.com/yt-dlp/yt-dlp/wiki/EJS),
[QuickJS-ng license](https://github.com/quickjs-ng/quickjs/blob/master/LICENSE).

## Network and process boundary proof — task 1.4

`uv run --project web-audio-component python -m pytest web-audio-component/tests -q`
passed **30 tests** in the final run. Controlled local fixtures verify share, child and media
redirect refusal before the disallowed path is fetched, cumulative byte/request
budgets, and compressed-response rejection before reading. The pinned yt-dlp
transport tests verify refusal before DNS for a disallowed host and before socket
connection for a private resolved address. No third-party probing is used.

Process fixtures verify timeout cleanup, process-group cleanup including a
grandchild, and a real SIGTERM sent to the supervisor while the worker is active.
The cancelled worker's grandchild cannot create its scheduled output. Production
uses the sole bounded urllib handler, fixed runtime paths, no proxy, no external
downloader and FFmpeg without network protocols. Application worker ownership,
share normalization and cancellation are covered by the backend/UI suites.
The catalogue transport also shares one deadline across DNS and all address
attempts, verified by controlled fixtures after a real Deezer request exposed
an excessive connection delay. See [verification.md](verification.md) for the
complete scenario review and the remaining native UI limitations.
