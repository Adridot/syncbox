## 1. Validate the component boundaries

- [x] 1.1 Prove metadata enumeration and exact-item acquisition for representative YouTube/YouTube Music and SoundCloud track/collection links using authorized samples; deliver an evidence note with tested IDs, selected identities, output properties, and known access limitations.
- [x] 1.2 Prove streamrip's requested-versus-effective Deezer item detection and strict rejection while retaining the existing Spotify fallback; verify separate strict/legacy cases with deterministic component checks.
- [x] 1.3 Pin a compatible web-audio runtime/dependency set and build a minimal frozen wrapper on the supported packaged macOS target; verify metadata-only and audio operations with FFmpeg/Deno absent from the host PATH and record archive size and dependency licenses.
- [x] 1.4 Prove bounded provider network handling, including share/child/media redirects, and subprocess-tree timeout/cancellation in the chosen wrapper; verify with controlled local fixtures rather than third-party probing, including refusal before a disallowed destination is fetched.

## 2. Add durable source and import state

- [x] 2.1 Add additive application-DB migrations for import snapshots, event source provenance, acquisition selectors/effective source, and measured output properties; verify fresh DB creation and migration of legacy Spotify rows and queued/failed/published Deezer jobs without losing state.
- [x] 2.2 Implement preview state transitions, bounded manifest storage, request identity, and result persistence; verify duplicate requests, dismissal, retry, and immutable committed snapshots with focused repository tests.
- [x] 2.3 Implement transactional import confirmation with stable selected entry keys and provider-item duplicate handling; verify rollback on failure, replay after a lost response, repeated occurrences, distinct remixes, and preservation of existing row origin/status/file.
- [x] 2.4 Integrate import ownership with event removal/deletion and application reset; verify late worker completion cannot recreate deleted data and removed/ignored items require explicit restoration or re-addition.

## 3. Resolve links and collection metadata

- [x] 3.1 Implement canonical parsing for the supported provider/resource matrix and share links, reusing Spotify helpers; verify track/album/playlist variants, tracking parameters, video-plus-playlist ambiguity, malformed URLs, unsupported types, and rejected redirect targets.
- [x] 3.2 Adapt the shared Spotify resolver to bounded authenticated individual track retrieval with partial-result preservation and the existing anonymous fallback; verify `test_spotify.py` and affected API/history tests for unavailable batch endpoints, no session, offline operation, and rate limits.
- [x] 3.3 Add Spotify album and playlist snapshot enumeration using existing client/pagination mapping and selected-track hydration; verify multi-page collections, simplified album entries without ISRC, inaccessible playlist items, and metadata failure without an empty-success result.
- [x] 3.4 Add Deezer track/album/playlist catalogue resolution and pagination; verify canonical child IDs, source positions, unavailable entries, and metadata responses without credentials.
- [x] 3.5 Implement the web-audio wrapper's metadata-only operation and stable child identities; verify YouTube Music album representation, SoundCloud albums/sets, flat metadata gaps, unavailable placeholders, and that preview creates no audio files.
- [x] 3.6 Add the bounded preview worker and start/list/read/retry/dismiss/commit endpoints using a separate DB connection and short lock sections; verify unrelated API responsiveness, pagination/time/size limits, process restart, concurrent confirmation, and client reopen.

## 4. Preserve linked versions through event matching

- [x] 4.1 Generalize event-row creation to accept resolved source metadata while keeping legacy Spotify/manual callers; verify manual origin, attribution fields, and additions to pending/applied/partially applied events.
- [x] 4.2 Apply one shared exact-source eligibility rule across event initial matching, rematching, staged claiming, and stale-readiness recovery; verify that a similar original or same-ISRC alternate cannot replace a direct linked remix, while Spotify matching remains unchanged.
- [x] 4.3 Preserve valid same-item provenance and explicit local-file associations through apply/reapply, adoption, and removal; verify integrity checks, manual selection, and that scans do not fabricate proof of identity.
- [x] 4.4 Guard acquisition selectors against server-owned source policy and keep the manual Deezer search path for Spotify/legacy rows only; verify rejected cross-source requests and existing Spotify manual selection behavior.

## 5. Extend provider acquisition and recovery

- [x] 5.1 Add provider-specific readiness and capability reporting while preserving existing Deezer endpoints; verify web-audio operation with Deezer disabled and explicit upgrade requirements for a legacy component without strict-item support.
- [x] 5.2 Extend the Deezer runner protocol with strict exact-item mode and effective item reporting; verify direct-link fallback refusal, unchanged Spotify fallback/quality preference, and compatibility with legacy jobs.
- [x] 5.3 Implement single-item web-audio acquisition with original-file preference, supported-native/remux output, and MP3 conversion only when required; verify actual final paths and exact returned item IDs for YouTube and SoundCloud.
- [x] 5.4 Add provider-aware output validation and source/output quality reporting; verify complete short tracks, missing artwork, unknown source bitrate, unsupported codecs, incomplete output, and workspace containment without applying Deezer preview rules to web audio.
- [x] 5.5 Dispatch providers through the existing FIFO acquisition worker and persist source intent before execution; verify batch jobs across providers retain owner correlation and one provider's failure does not block later jobs.
- [x] 5.6 Make active-job deduplication and published-output recovery compare source intent, and persist effective source/output properties durably; verify restart before/after publication, legacy recovery, and rejection of a changed selector on the same owner.
- [x] 5.7 Return explicit row ownership in acquisition batch results and preserve new-source scope restrictions; verify out-of-order response mapping and unchanged library/collection Deezer acquisition behavior.

## 6. Integrate the event UI

- [x] 6.1 Replace Spotify-only link validation with server resolution and provider attribution; verify supported single links, retained input on error, and the explicit YouTube video-versus-playlist choice in UI tests.
- [x] 6.2 Add the collection preview with source order, select-all/subset controls, duplicate/unavailable states, counts, dismissal, and confirmation; verify keyboard interaction and that preview/confirmation never implicitly downloads audio.
- [x] 6.3 Restore previews and committed results when the event UI reopens, and wire existing download actions to eligible provider rows; verify progress recovery, retry, partial success, no-ISRC direct links, and duplicate confirmation handling.
- [x] 6.4 Make component setup/readiness, badges, errors, quality labels, and manual Deezer actions source-aware; verify YouTube/SoundCloud work without Deezer credentials and Spotify retains its current acquisition controls.
- [x] 6.5 Add source/import types and localized UI messages following existing conventions; verify `pnpm --dir ui typecheck` and the focused event/acquisition UI tests.

## 7. Package and verify the integrated change

- [x] 7.1 Integrate the pinned optional web-audio archive and upgraded Deezer protocol into the existing manifest/install/update flow; verify checksums, runtime paths, supported target detection, license inventory, and applicable signing/notarization checks without adding downloader dependencies to the base bundle.
- [x] 7.2 Run backend regression checks for events, Spotify, acquisition API/worker/ownership, staging/adoption, refresh, removal, and guarded apply/reapply; verify a mixed-source collection with duplicate/unavailable entries through restart and event deletion.
- [x] 7.3 Run `pnpm --dir ui test` and `pnpm --dir ui build`, then verify the packaged event workflow for single tracks and albums/playlists on all four providers using authorized samples; record actual outcomes rather than treating upstream support as a successful packaged test.
- [x] 7.4 Update `docs/SPEC-UNIFIED.md` and relevant user/component documentation for the approved scope, exact-source versus Spotify policy, snapshot imports, access limits, and operational rollback; verify no current documentation still claims the new event flow is Spotify-only or excludes the shipped web-audio component.
- [x] 7.5 Validate all change artifacts with `openspec validate add-event-multiplatform-link-import --strict` and review the implementation against every scenario in the three delta specs; record remaining release limitations without marking unverified tasks complete.
