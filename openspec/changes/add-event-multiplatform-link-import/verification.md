# Implementation verification — 2026-09-07

The current review outcome and regression results are recorded in
[review-followup.md](review-followup.md) (2026-09-08). The executed checks below
remain historical evidence for their original builds.
The installed native run and its remaining acceptance gaps are recorded in
[native-verification.md](native-verification.md).

## Outcome

The application implementation is present: persistent collection previews,
atomic selected-entry confirmation, canonical provider identities, exact-source
acquisition, provider-specific setup, durable publication recovery, and event UI
integration. Spotify keeps its existing Deezer association policy. Imports do
not create audio jobs or bypass the guarded Rekordbox apply/reapply flow.

This change is **not ready for distribution or archival**. Tasks 7.1 and 7.3
remain open (33/35 complete). The approved Deno runtime choice is retained;
notice inventories were subsequently completed. Component publication, final
native playlist inspection, and the observed SoundCloud title and stale-error
recovery defects remain outstanding. Native reapply succeeded. The native
report supersedes older statements below about which
real-provider paths have not yet been exercised.
The two defects now have source corrections and passing regressions; see the
native report's follow-up section and `native-fixes-verification.json` for the
rebuilt component proof. Installed native acceptance remains a separate gate.

## Executed checks

| Check | Outcome |
| --- | --- |
| `uv run --project sidecar python -m pytest sidecar/tests -q` | 795 passed, 11 skipped; skipped fixture-dependent checks are not claimed as passed |
| `corepack pnpm@10.29.3 --dir ui test` | 134 passed across 32 files |
| Focused event import, acquisition and virtualization UI checks after the final copy edit | 15 passed |
| `corepack pnpm@10.29.3 --dir ui build` | Vue/TypeScript checking and production build passed after the final edit |
| `uv run --project web-audio-component python -m pytest web-audio-component/tests -q` | 30 passed |
| Frozen base sidecar | Built on macOS arm64; packaging check passed without streamrip in the base runtime |
| Frozen Deezer component | Protocol 2 check passed, with strict/effective identity capabilities |
| Frozen web-audio component | Bundled runtime check and exact YouTube/SoundCloud audio operations passed with only `/usr/bin:/bin` in PATH |
| Native artifact checks | Strict ad-hoc signature verification passed; dynamic dependencies recorded in `artifact-checks.json`; no notarization claim |
| Default web component packaging | Refuses incomplete Deno inventories; no web install manifest generated |
| `openspec validate add-event-multiplatform-link-import --strict` | Passed |
| `git diff --check` | Passed |
| PR preparation: staged license inventory | All 1,445 collected notice references match the staged blob SHA-256; case aliases normalized to tracked filenames and verbatim bytes preserved with Git attributes |

The full UI suite preceded a singular/plural message edit; the affected tests
and production build were rerun afterward. The final backend suite includes the
shared DNS/connection deadline correction discovered during the real Deezer
preview test. Provider transport boundary tests use controlled local fixtures.
PR preparation subsequently changed only Git attributes and inventory filename
casing. The frozen archive evidence predates those metadata corrections; no
additional frozen build is claimed for that preparation step.

## Real provider and interface evidence

[frozen-verification.json](frozen-verification.json) records five successful
metadata cases: YouTube track and playlist, YouTube Music album, SoundCloud track
and set. Enumeration produced no audio. The final draft archive downloaded
YouTube `YE7VzlLtp-4` as MP3 and SoundCloud `1706333112` as native M4A/AAC,
returning the exact requested IDs and measured output properties. Conversion is
reported separately from source quality. Metadata and final audio archive hashes
are recorded separately; they are not presented as one identical build.

[packaged-ui-verification.json](packaged-ui-verification.json) records the built
Vue UI connected to the frozen sidecar with an isolated temporary application
database. A real Deezer album (`302127`, 14 entries) was previewed; positions 1
and 3 were selected by keyboard and confirmed. Reload restored the committed
result. An anonymous Spotify track (`4uLU6hMCjMI75M1A2tKUQC`) was also previewed
and confirmed. The resulting three manual rows retained their source identities;
there were zero audio jobs and zero audio files, and the dummy Rekordbox fixture
remained byte-for-byte unchanged. These checks did not exercise native Tauri or
a real Rekordbox library.

The dummy `master.db` is deliberately not a SQLCipher database. A background
library snapshot request therefore logged `file is not a database`; these
results establish the isolated link-import flow, not an error-free whole-app
smoke test. Test servers and the dedicated browser page were stopped afterward.

Screenshots timed out. Spotify pointer automation reported interception although
the DOM hit test identified the intended button; keyboard confirmation passed.
This is inconclusive pointer/visual evidence, not a diagnosed product defect or
a successful native visual review.

## Delta scenario review

Every scenario below was reviewed against the implementation and available
evidence. Automated coverage is distinguished from real-provider/native proof.
Test paths are relative to the repository root.

### Event link import — 18 scenarios

| Scenario | Implementation and verification evidence |
| --- | --- |
| Shared track link | `music_links.py` canonical parsing; `test_link_imports.py::test_canonical_links` and share redirect fixtures in `test_link_resolution.py` |
| Video within a playlist | Explicit scope required, including shorts links; parser, wrapper boundary and EventLinkImport UI tests |
| Unsupported resource | Parser rejects unsupported hosts/resource types; wrapper rejects live/unavailable items; no commit before a valid completed snapshot |
| Multi-page album or playlist | Spotify and Deezer pagination tests in `test_link_resolution.py`; real web collections enumerated; real Deezer album preview |
| Unavailable entries | Normalized manifests and wrapper media tests retain unavailable children without invented metadata; UI prevents selection |
| Enumeration fails midway | `test_spotify_missing_items_and_mid_page_failure_never_succeed` and pagination/byte-limit tests; failed snapshots cannot commit |
| Dismissed preview | Repository dismissal/late-completion test and UI tests; preview operations do not add rows or audio |
| Playlist changes after preview | Commit consumes stored manifest entries without provider calls; atomic snapshot/replay test exercises persisted selection |
| Import into a playlist-backed event | New rows have manual origin; `test_events_service.py::test_refresh_ignores_manual_and_adopted_rows` verifies refresh exclusion |
| Lost confirmation response | `test_atomic_snapshot_deduplicates_identity_and_replays`; same stored result returned with no extra rows/jobs |
| Repeated track and distinct remix | Same test uses repeated identity and a distinct item with identical title/ISRC; first position retained and distinct item added |
| Existing playlist-owned row | Existing-row repository test verifies unchanged origin, status and path; identity lookup preserves Spotify playlist-owned rows |
| UI closes during import | Worker reopen/restart tests and UI history restoration; real built UI reload restored committed results |
| One failed download | Provider FIFO test leaves individual failed/downloaded outcomes and preserves owner correlation; publication recovery avoids repeat downloads |
| Applied event receives an album | New rows use the existing added-after-apply delta; repository tests cover partially applied additions and existing API reapply tests cover the guard; full native album reapply remains unverified |
| Event deleted during preview resolution | Import cascade/late completion and reset-generation tests; acquisition rejects removed owners before publication |
| Spotify playlist content is not accessible | Missing-items and mid-page failure tests; inaccessible contents fail instead of succeeding empty; connected real collection access remains unverified |
| Optional component is absent | Resolver/readiness errors preserve the input in EventLinkImport UI tests; a draft web component has no installable release manifest |

### Event source acquisition — 14 scenarios

| Scenario | Implementation and verification evidence |
| --- | --- |
| Remix resembles a local original | Shared `source_identity` eligibility; `test_direct_source_never_claims_similar_audio_without_identity` rejects title/ISRC similarity without valid provenance |
| Exact Deezer item is unavailable | Strict runner tests and pinned streamrip identity fixture reject effective item substitution before audio; legacy Spotify fallback remains accepted |
| Subsequent rematch or staged-file scan | Same exact-source test covers rematch, staged claiming and stale-readiness recovery; changed file bytes invalidate provenance |
| Spotify track with an ISRC | Existing acquisition/API regression suite preserves the Spotify-to-Deezer association path; selectors distinguish association from exact direct sources |
| Spotify track without an ISRC | Existing manual Deezer acquisition tests and source-aware UI controls; no fabricated automatic association |
| YouTube with Deezer disabled | `test_web_download_needs_no_deezer_or_isrc_and_restores_measured_identity`; frozen wrapper works without credentials, while install distribution remains gated |
| No optional components | Existing local/API regressions and explicit provider prerequisites; base packaging check excludes downloader dependencies |
| Restart during publication | Provider recovery test and existing acquisition crash-before-ready test reuse verified published output without a new download |
| Different selector on the same row | Changed-source and client-selector tests reject replacement/reuse; late completion cannot publish to a changed owner |
| Valid short track | Wrapper fully decodes a generated 20-second file without artwork; backend accepts measured short output; this is a controlled fixture, not a real 20-second SoundCloud proof |
| Lossy source is converted | Real frozen YouTube conversion records Opus source separately from MP3 output; acquisition UI reports conversion and unknown source properties without quality uplift claims |
| Invalid output | Wrapper media and base installer/runner tests reject missing, non-audio, unsupported-codec, symlink, escaped and incomplete outputs before readiness |
| Share link redirects outside permitted destinations | Local share/child/media redirect fixtures and socket tests reject destinations before fetching or connecting |
| Provider or component stalls | Supervisor timeout and descendant cancellation tests; bounded DNS/address attempts and pagination; worker tests verify unrelated API responsiveness |

### Spotify track resolution — 5 scenarios

| Scenario | Implementation and verification evidence |
| --- | --- |
| Connected session | `test_spotify.py` checks individual authenticated requests, available metadata and the 50-item operation bound |
| Batch retrieval unavailable | Authenticated test transport accepts only `/tracks/{id}` and verifies no multiple-track endpoint dependency |
| No session | oEmbed-only tests verify bounded title-only results; real anonymous Spotify track preview/commit also passed |
| Partial authenticated failure | Successful authenticated prefix retained; remaining IDs use bounded fallback; rate-limit tests retain retry guidance without sleeping |
| Offline | Offline resolver test returns partial/empty results without raising; existing consumers remain covered by backend regression tests |

## Remaining release work

1. **Task 7.1 (remaining part):** the Deno/native notice inventory was completed
   on 2026-09-07 (see `component-evidence.md`) and the packager now generates
   `sidecar/src/syncbox/web_audio_component.json`. The archive it describes still
   has to be uploaded as the release asset named in the manifest; developer ID
   signing/notarization remain out of scope.
2. **Task 7.3:** exercise the installed native Tauri/Rekordbox workflow for single
   items and collections on all four providers, including authenticated Spotify
   collections and native pointer/visual interaction. The isolated wrapper and
   browser tests above do not satisfy that requirement. The draft distribution
   gate currently also prevents a normal installed web-component proof.

No archive was published, no release was created, and the change was not archived.
For local testing before publication, point `SYNCBOX_WEB_AUDIO_COMPONENT_ARCHIVE`
at the locally packaged archive; the manifest checksum must match it.
The updated local Deezer manifest must follow the normal release version/checksum
flow before publication; an existing published asset must not be overwritten.
Rollback guidance is in `web-audio-component/README.md`. Unrelated archived user
documentation under `docs/_archive-v0.2/` was left unchanged.
