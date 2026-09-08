## Why

Manual event additions currently accept Spotify track links only, although users receive requests as Deezer, YouTube, and SoundCloud links, including entire albums and playlists. They need to import those requests into the existing event workflow without losing the linked remix, edit, or live version.

## What Changes

- Accept individual tracks, albums, and playlists from Spotify, Deezer, YouTube/YouTube Music, and SoundCloud where the platform exposes that resource type.
- Preview collection contents and availability, select all or some tracks, and import a snapshot into an existing event. Imports do not create additional synchronized event sources.
- Preserve the exact linked item for Deezer, YouTube, and SoundCloud. Neither catalogue search nor fuzzy local matching may silently substitute another recording.
- Preserve the user-confirmed Spotify behavior: existing local matching, followed by Deezer acquisition through the existing ISRC association or manual Deezer selection. Spotify is the explicit exception to source fidelity.
- Reuse the persistent acquisition queue, staging publication, recovery, and guarded event apply/reapply. Report partial failures per track and avoid duplicate additions on retries.
- Keep streamrip for Deezer and add a separately installed yt-dlp component for YouTube and SoundCloud, including its pinned media-processing/runtime dependencies.
- Make source identity, component readiness, and actual audio quality provider-aware while retaining existing Deezer jobs and clients.
- Update the shared Spotify metadata resolution contract to support current Development Mode endpoints while preserving the existing API-to-oEmbed fallback and acquisition behavior.

## Capabilities

### New Capabilities

- `event-link-import`: Supported links, asynchronous collection previews, selection, snapshot imports, provenance, duplicate handling, and event lifecycle compatibility.
- `event-source-acquisition`: Exact-source enforcement, the Spotify exception, provider dispatch, optional components, output validation, and durable per-track downloads.

### Modified Capabilities

- `spotify-track-resolution`: Replace the mandatory 50-item batch API contract with bounded requests compatible with the current account's API capabilities; retain shared resolution and anonymous fallback.

## Impact

- UI: `EventsScreen.vue`, acquisition queue helpers, API types, source attribution, import preview, provider settings/readiness, and localized messages.
- Sidecar: event addition/matching/staging paths, Spotify metadata resolution, acquisition queue/worker and recovery, plus additive application-database migrations for import snapshots and source identity.
- Packaging: retain the isolated Deezer/streamrip component; add an optional web-audio component with yt-dlp, FFmpeg/ffprobe, and the supported JavaScript runtime/EJS dependencies required for YouTube. No new downloader dependency in the base sidecar.
- Regression boundaries: manual imports remain outside linked-playlist refresh ownership; staged-file adoption, removal, applied-event additions, library/collection Deezer acquisition, and Rekordbox write guards remain compatible.
- Documentation: revise the historical Deezer-only/SoundCloud-deferred scope in `docs/SPEC-UNIFIED.md` during implementation and document actual provider access limitations.
- Out of scope: Qobuz/Tidal/Apple Music integrations, arbitrary websites, artist discographies/channels, continuous playlist synchronization, direct Spotify audio acquisition, and changes to the Spotify-to-Deezer matching policy.
