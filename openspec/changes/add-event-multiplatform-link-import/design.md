## Context

See [proposal.md](proposal.md) for motivation and scope. The owner confirmed exact linked versions, albums/playlists as well as tracks, and unchanged Spotify-to-Deezer association on 2026-09-07.

The current event UI extracts only a Spotify track ID. `events_add_track` resolves metadata and runs event-wide matching; `match_event_tracks` and `claim_staged_files` can later associate files by metadata. Source fidelity therefore cannot be implemented solely in the download button.

`acquisition_jobs` already has `provider`, durable ownership, claims, publication hashes, and recovery. Execution and readiness are nevertheless Deezer-specific. Its single FIFO worker owns a separate SQLite connection and releases the application lock during acquisition. Ordinary API handlers hold that lock, making synchronous playlist enumeration unsuitable.

The optional Deezer component is separately distributed and uses streamrip v2.2.0 at commit `189acda489927719aa8591f6acdd7d67aecf929b`. The runner deliberately accepts Deezer fallback item substitution for existing acquisition. Direct Deezer links need a stricter mode without changing that legacy behavior. The base sidecar uses Python 3.14; the existing optional component has its own Python 3.13 runtime.

Existing event refresh owns only `origin='playlist'` rows. The event is a set of requested tracks, not a source playlist playback-order mirror. Staged adoption, removal, and applied-event deltas already have independent state that imports must preserve.

## Goals / Non-Goals

**Goals:** Keep one acquisition queue and one publication/apply path; preserve explicit source intent throughout matching and recovery; isolate new runtime weight; make collection confirmation atomic and repeatable.

**Non-Goals:** A generic plugin framework, a new task broker, replacing the Spotify client, changing library/collection acquisition policy, changing Rekordbox playlist ordering, and promising access to private or unavailable resources. Supported public web-audio resources are the initial access surface; browser-cookie import is not introduced.

## Decisions

### 1. Two acquisition engines with a small fixed provider dispatch

| Input | Metadata / enumeration | Acquisition target | Engine |
| --- | --- | --- | --- |
| Spotify track/album/playlist | Existing authenticated Spotify client and shared track resolver | Existing Deezer ISRC association or manual selection | Existing streamrip component |
| Deezer track/album/playlist | Public catalogue endpoints, including paginated child tracks | Exact Deezer item ID | streamrip component with exact-item capability |
| YouTube video, YouTube Music album, playlist | yt-dlp extraction | Exact child video ID | New optional web-audio component |
| SoundCloud track, album, set | yt-dlp extraction | Exact child track ID | New optional web-audio component |

Use simple functions and a fixed dispatch, not a provider registry framework. yt-dlp already handles both web-audio sources, including SoundCloud originals when exposed; use its Python API inside a small JSON-reporting subprocess wrapper. Retain the existing streamrip library wrapper rather than parsing its human CLI output. [Streamrip](https://github.com/nathom/streamrip), [yt-dlp embedding and extractors](https://github.com/yt-dlp/yt-dlp).

Alternatives: streamrip for SoundCloud is viable but creates two web-audio paths once YouTube is included; spotDL duplicates existing Spotify resolution and chooses audio by search, contrary to direct-source intent. One universal downloader cannot replace both current Deezer acquisition and exact YouTube links.

### 2. Parse links once in the sidecar, then enumerate into a durable preview

Add a narrow link-resolution module. Parse provider/resource IDs with the standard URL parser, normalize known share URLs, remove tracking parameters, and validate redirects and resource types before extraction. Preserve existing Spotify URI/ID helpers rather than introducing another prefix definition. A YouTube URL containing both video and collection identity requires an explicit scope choice. Reject channels, artist pages, search URLs, live streams, and arbitrary websites.

Introduce one `event_link_imports` table holding event ownership, request token, canonical source/resource identity, state, bounded preview JSON, selected entry keys, committed result, error, and timestamps. Preview JSON contains child provider IDs, canonical child URLs, source positions, metadata, availability, and omission notices. It contains neither credentials nor expiring media URLs. A bounded JSON document avoids a second per-entry table for data that is committed as a single snapshot.

Proposed endpoints:

- `POST /api/events/{id}/link-imports`: validate and persist a queued preview; return its identity promptly.
- `GET /api/events/{id}/link-imports` and `GET /api/events/{id}/link-imports/{import_id}`: restore current/recent previews and read progress/results.
- `POST /api/events/{id}/link-imports/{import_id}/commit`: confirm stable selected entry keys; return added row identities and duplicate/unavailable outcomes.
- `POST /api/events/{id}/link-imports/{import_id}/retry`: retry failed, uncommitted resolution without replacing a committed snapshot.
- `DELETE /api/events/{id}/link-imports/{import_id}`: dismiss an uncommitted preview and stop outstanding resolution.

Use one bounded metadata-resolution worker alongside the existing acquisition worker, following its single-instance startup, separate-connection, short-transaction pattern. Do not build a shared broker or perform network calls under `deps.lock`. Preview state is `queued -> resolving -> ready|failed`, then `ready -> committed`; any uncommitted state can become `dismissed`. Interrupted resolution returns to queued after verified process ownership transfer. Explicit retry restarts a failed preview; committed snapshots never re-enumerate. Deleting the event invalidates outstanding work, and late completion must verify ownership/state before persisting.

Fetch every page within declared item/byte/time limits. A mid-page failure fails the preview instead of committing a prefix. Unavailable placeholders returned by a provider stay visible; omissions the provider hides cannot be reconstructed and must not be invented. Flat extraction can populate an initial listing, but missing child metadata is resolved as needed before acquisition, without replacing child identity. [yt-dlp playlist extraction](https://github.com/yt-dlp/yt-dlp#usage-and-options).

Alternative: enumerate synchronously inside the current add endpoint. Rejected because the global lock would block unrelated requests and a lost response would make collection confirmation ambiguous.

### 3. Additive provenance and atomic confirmation

Add nullable `source_provider`, `source_item_id`, `source_url`, `source_import_id`, and `source_position` fields to event tracks. Preserve `spotify_track_id` for existing consumers and attribution. Fill new source fields for known legacy Spotify rows without changing statuses, origins, or duplicates. Do not infer provenance for arbitrary local files.

Commit selected entries and the import's result in one application-DB transaction under the existing serialization discipline. Deduplicate by `(event_id, source_provider, source_item_id)` against active rows, with legacy `spotify_track_id` compatibility; first occurrence wins. Existing rows retain origin/status/file. Removed and ignored entries are shown separately and use existing restore behavior only after explicit choice. Do not add a uniqueness constraint that breaks legacy duplicate rows or collapses different releases by ISRC.

The import ID plus its stored selection is the confirmation idempotency boundary: identical replay returns the original result; a different selection after commit is a conflict. A new import can select additional items. Preserve all collection-entry provenance in the manifest, even when multiple imports reference one existing row. New rows get `origin='manual'` and the usual `added_after_apply` value. No automatic refresh subscription is introduced. Source positions are retained for preview/provenance, while event application retains its current ordering rules.

Keep the existing single-track API contract for older callers. The updated UI can use the same preview model for a single item without requiring a collection-selection screen. Confirmation adds rows; the existing explicit download action queues missing items, preserving current separation between adding and acquiring.

### 4. Enforce fidelity across all file association paths

Derive exact-source policy from a direct-link row's persisted provider, with Spotify explicitly exempt. Factor only the shared eligibility check needed by event matching, rematching, staged claims, readiness recovery, and acquisition validation. Do not change the global similarity algorithm used by Spotify/library workflows.

For a direct-link row, automatically reuse a file only when persisted acquisition provenance proves the same provider item and the file still passes ownership/integrity checks. A fuzzy match or matching ISRC alone is insufficient. An explicit existing local-file choice remains possible and is recorded as a user decision; generic staging scans cannot manufacture that decision. The manual Deezer search action stays available for Spotify and legacy manual metadata rows, but must not redirect an exact-source row to Deezer.

Extend the Deezer wrapper with an explicit exact-item mode. Compare the requested item with the effective downloadable item and refuse substitution for direct Deezer links. Keep the currently accepted catalogue fallback for Spotify/legacy requests. Lower bitrate for the same item is separate from changing item identity. Expose this mode as a component protocol capability; an installed legacy component cannot claim exact-link support until upgraded.

Alternative: enforce fidelity only in the downloader. Rejected because initial matching or a later staged-file claim could silently mark a different recording ready before the downloader runs.

### 5. Extend existing jobs rather than creating a second download queue

Persist a normalized selector alongside the existing job `provider`: direct provider item ID/URL, or the existing Spotify/legacy Deezer association inputs. Retain `deezer_track_id` compatibility and store effective acquired item identity separately when Spotify accepts a Deezer fallback. Newly queued jobs obtain their source selector from server-owned event state, not arbitrary client-provided URLs.

Dispatch readiness and execution per provider. YouTube and public SoundCloud require the web-audio component, never a Deezer ARL. Return explicit owner identities in batch responses and map UI badges by row identity rather than list position.

Keep the FIFO acquisition worker, per-job workspace, hash-before-publication, destination reservation, owner checks, and existing status lifecycle. Active-job deduplication and published-output recovery must compare source intent as well as owner. Reusing a failed earlier job with a different selector is forbidden. Persist normalized selector/effective source and output properties before a crash can lose them. Do not rewrite in-flight legacy jobs; interpret absent new fields as the existing Deezer contract.

### 6. Package web audio independently and verify real output

Add an optional `syncbox-web-audio-component`, using the existing installation/checksum/manifest approach without bundling it into the base sidecar. Pin compatible yt-dlp, FFmpeg/ffprobe, Deno, EJS, and Python runtime versions together. Use fixed installed executable paths and controlled configuration, with no arbitrary user extractor arguments, downloaded plugins, or unpinned runtime self-updates. YouTube currently requires an external JavaScript runtime and EJS; Deno is the documented recommendation. [yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

Owner decision (2026-09-07): build a focused LGPL FFmpeg/ffprobe distribution from pinned sources, without GPL/nonfree options or video encoders. Include the LGPL MP3 encoder configuration, exact source archives, build flags and license notices. Do not redistribute the host Homebrew GPL build. This decision authorizes the corresponding LGPL dependency inventory for the isolated web-audio component; the existing base/Deezer inventories remain separately scoped. Disable FFmpeg network protocols: it processes local files supplied by the controlled downloader only.

Further owner decision (2026-09-07): retain Deno 2.9.5 and approve the enumerated MPL dependencies for this isolated component: cooked-waker 5.0.0, smartstring 1.0.1, webpki-root-certs 0.26.6, webpki-roots 0.26.1, cssparser 0.36.0, cssparser-macros 0.6.1 and dtoa-short 0.3.5. Complete exact dependency notices and source attribution before release; this approval does not waive the inventory checks or expand the base/Deezer scope.

Give the wrapper metadata-only and single-item acquisition operations, structured JSON results, and bounded execution. Resolve fresh media URLs from immutable item identity on each attempt. Apply network destination validation to redirects and untrusted child/media references, not merely to the original pasted URL; the exact transport integration must be exercised in the component proof of concept. Terminate the child process tree on timeout/cancellation and retain only sanitized errors.

Prefer SoundCloud's offered original; otherwise select the best accessible audio for the exact item. Retain supported native audio where possible; remux without re-encoding when that produces a supported format. Transcode unsupported codecs to MP3 only when required for the existing importer. The current importer accepts MP3, M4A, FLAC, WAV, and AIFF; Opus/WebM must not be published as ready without compatible conversion. Do not introduce a quality preference screen in this change. Keep existing Deezer MP3 preference and fallback behavior unchanged.

Return the actual postprocessed output path, source/effective item identity, measured duration, codec/container, bitrate and sample rate when available, and whether processing changed the encoding. Unknown source bitrate stays unknown. Metadata/artwork is best effort for web sources; uploader names must not be invented as musical artists. Validate complete decodable audio and bounded expected-duration consistency when meaningful, rather than applying the existing Deezer 35-second preview rejection to web tracks.

Alternative: install FFmpeg/Deno globally or bundle all engines in the app. Rejected because it introduces machine setup requirements or increases base application weight for users who do not acquire web audio.

### 7. Preserve Spotify behavior using supported metadata endpoints

Keep `resolve_track_meta` as the single consumer entry point. Prefer individual authenticated track requests with bounded work rather than adding an access-mode detection subsystem solely for batching. Preserve completed results, the anonymous title-only fallback, and later enrichment. Queue substantial metadata hydration outside the application lock. Spotify album pages return simplified tracks, so hydrate selected entries through the shared resolver when ISRC or other required metadata is absent.

Retain playlist pagination/mapping already present in `library_service`; reuse its interpretation of inaccessible `items` rather than reporting an empty import. Development Mode now restricts playlist item access to owned/collaborative playlists and removes multi-track batch retrieval. These are API compatibility changes, not changes to the approved Spotify-to-Deezer policy. [Spotify migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide), [album tracks](https://developer.spotify.com/documentation/web-api/reference/get-an-albums-tracks), [track metadata](https://developer.spotify.com/documentation/web-api/reference/get-track).

## Risks / Trade-offs

- [Provider support is documented, not proven in the shipped bundle] -> Start implementation with source/frozen-component proofs using authorized sample content; record versions, outcomes, artifact size, and limitations before enabling the UI capability.
- [Exact Deezer links now reject substitutions accepted by legacy acquisition] -> Gate strict behavior by direct-link policy and component capability; retain Spotify regressions for accepted fallback.
- [Web extraction breaks as providers change] -> Independently version the optional component and expose actionable update/unavailable errors, without silent source switching.
- [Large or changing collections] -> Bounded asynchronous enumeration and immutable confirmation snapshot; show limits rather than silently truncating.
- [Old clients or binaries misread new source rows/jobs] -> Preserve old API shapes, add explicit protocol capability checks, and treat binary downgrade after new-source imports as requiring a compatible DB backup or a forward fix.
- [More optional runtime weight and redistribution obligations] -> Measure archives, inventory the actual dependency licenses/build configuration, and verify signing/notarization on supported release targets. Do not infer licenses solely from the parent project.
- [Weak metadata for web audio] -> Preserve source IDs and supplied metadata, allow existing manual correction, and never fabricate ISRC or artist identity.

## Migration Plan

1. Run component and source-fidelity proofs on the currently supported packaged macOS target; pin tested artifacts and expose a protocol version/capability for strict Deezer item selection.
2. Add application-DB migrations, legacy interpretation, and source-aware backend behavior before exposing new UI actions. Keep all downloader defaults optional/off for users who have not enabled them.
3. Add preview/confirmation endpoints and worker lifecycle, then integrate event UI and existing acquisition controls. Test fresh install and upgrade from a DB containing active/failed/published legacy jobs.
4. Update `docs/SPEC-UNIFIED.md` and component/user documentation to replace the historical SoundCloud/FFmpeg deferral for this feature and disclose actual supported resource/access types.
5. Verify source and packaged flows, restart recovery, event removal/adoption/refresh/reapply, and base-bundle exclusion. Generalized code paths must not broaden new-source support into library/collection scope.
6. Operational rollback disables new link creation and web acquisition while retaining imported rows and files. Never drop provenance or delete completed downloads to roll back. A binary downgrade needs a compatible application-DB backup; keep acquired files for recovery and do not modify Rekordbox as part of rollback.
