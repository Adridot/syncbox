# Event web-audio component

This optional macOS 14+ arm64 component resolves public YouTube/YouTube Music
and SoundCloud links and acquires an explicitly selected item. It is isolated
from the base application and the optional Deezer component. The Deno
dependency/native notice inventory was completed on 2026-09-07, so the packager
generates the installable manifest; the archive still has to be published as a
release asset before end users can install it.

## User workflow

In an existing event, paste a track, album or playlist link and choose **Preview**.
For a YouTube video with playlist context, select the video or the playlist.
Review the source order, unavailable entries and existing tracks, then confirm
the selected subset. Removed/ignored tracks require the explicit re-add option.
Confirmation saves a snapshot; it does not synchronize that playlist or download
any audio. Reopening the event restores the preview or committed result.

Download missing audio separately. Spotify keeps its existing Deezer ISRC/manual
association. Direct Deezer, YouTube and SoundCloud rows require the exact linked
item. An approximate local recording cannot replace it automatically. You can
explicitly select a local file in the Missing center; its path and hash are
recorded. Acquisition jobs persist source intent and publication hashes, so a
restart can finish publication without downloading a second copy. Source quality
and measured output properties remain distinct when a conversion is necessary.

YouTube and SoundCloud use their own enablement/component and require no Deezer
ARL. Private, authenticated, region-restricted, live and provider-blocked content
may fail; this component does not import browser cookies or credentials. Spotify
album/playlist metadata requires an authorized Spotify connection. Purchase
links and ordinary local-file workflows remain available without components.

## Build and verify

Python dependencies are pinned in `uv.lock`; native dependencies and checksums
are pinned in `native-lock.json`. Native build flags disable GPL/nonfree code,
video output and FFmpeg networking. FFmpeg/LAME sources, the LAME export-list
patch and library notices travel with the archive. Deno includes additional
Rust/native dependencies and must not be described as wholly MIT-licensed.

```sh
uv sync --project web-audio-component --locked --managed-python
uv run --project web-audio-component python scripts/build_web_audio_native.py
uv run --project web-audio-component python -m pytest web-audio-component/tests -q
SOURCE_DATE_EPOCH=1788739200 uv run --project web-audio-component python scripts/package_web_audio_component.py --draft
```

Notice texts are not committed. `licenses/deno-inventory.json` and
`licenses/deno-native/inventory.json` pin every text by source URL and SHA-256;
the packager materializes them into `licenses/` (crate archives and the Deno
source tarball are cached under `vendor/notice-cache/`, texts already present
with the right hash are kept) and refuses any text whose hash does not match.
Packaging therefore needs network access the first time. Without `--draft`, it
refuses an incomplete inventory; only a complete reviewed inventory permits
generation of `sidecar/src/syncbox/web_audio_component.json`. Draft archives are never accepted
as proof that the distribution gate passed. Release URLs and versions follow
the existing application release flow; do not replace an already published
asset under an existing checksum. No artifact was published by this change.

The wrapper accepts bounded JSON on stdin: `check`, `metadata`, or `download`.
Downloads require a canonical single-item URL, its provider item ID and an empty,
resolved absolute workspace directory. For example, resolve macOS `/tmp` to
`/private/tmp` before invocation. The base-side caller already does this.
Metadata returns canonical child identities and available fields without
inventing an artist from the uploader name. Downloads report `output_filename`,
`effective_item_id`, `source_properties`, `output_properties`, and `processing`.
Supported output is MP3, AAC/ALAC in M4A, FLAC, WAV or AIFF. The wrapper probes and
fully decodes the result, checks source duration when available, and rejects
output outside its workspace. Original supported SoundCloud downloads are
preferred, then native/remuxed audio, then MP3 conversion when necessary.

Network handling allows only provider hosts, validates every resolved socket
address and redirect, and bounds bytes, requests and elapsed time. FFmpeg has no
network protocols. A supervisor terminates the worker's process group on timeout
or cancellation, including descendants. The component ignores host FFmpeg/Deno
and uses fixed bundled paths. Provider exceptions are converted into bounded
error codes rather than persisting raw URLs, tokens or upstream diagnostic text.

## Rollback and release limitations

Disable web audio in Settings to prevent new web-audio work. Existing event rows,
source provenance and published files remain available to local workflows.
Component installation verifies the archive and protocol in a temporary directory
before replacing the current installation; a failed check preserves that install.
The additive database migration must be preserved when rolling code back, or a
pre-change application database backup restored through the existing data flow.
Do not manually downgrade `user_version` or delete provenance columns.

See the change's `component-evidence.md`, `frozen-verification.json` and
`verification.md` for actual outcomes. Apple Developer ID/notarization remain
outside the project's current ad-hoc-signed release scope. Real Rekordbox fixture
checks, connected Spotify collection access and the complete packaged application
workflow are not established by isolated wrapper/unit tests.
