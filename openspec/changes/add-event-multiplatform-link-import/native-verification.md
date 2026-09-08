# Installed native verification — 2026-09-08

Tested commit `4527e057990fb5a632e19f5af754dfaf8998105b` in the installed
Tauri 0.9.0 application against the existing Rekordbox library. Structured,
redacted observations are in [native-verification.json](native-verification.json).
This is an incomplete native acceptance run, not release certification.

## Follow-up corrections

The defects recorded below describe the original tested build. Subsequent
source changes hydrate SoundCloud references that lack titles using the same
bounded, metadata-only yt-dlp session. Child identity is checked before accepting
the result; failed hydration cannot return a successful partial preview.
The rebuilt frozen component returned all 21 real set titles, including entry
6 (`565801467`), `Market Day (Free Download, CC0 license)`, artist `RandomMind`,
and its public permalink. No audio download was requested.

Synchronous progress operations now terminate with `job.done` and failed status
when an exception escapes, retaining the original HTTP error and all mutation
guards. Apply/reapply, source sync/apply, and duplicate scans share this cleanup.
Failed completions are excluded from the dashboard's successful activity feed.
Backend and UI regressions verify busy-state release and a later retry.

Validation: 811 backend tests passed (11 skipped), 145 UI tests passed, 33
web-audio tests passed, and the production UI build passed. The frozen component
check, complete license inventory validation, and the real metadata test passed
with only `/usr/bin:/bin` in PATH. The generated install manifest matches archive
SHA-256 `e5c90e063b278838d4514bc3a3e5850354bc9f8bc740f109a3eec349511f4772`.
See [native-fixes-verification.json](native-fixes-verification.json).

Existing committed snapshots are immutable and were not rewritten by this fix.
The installed QA application and web component were subsequently updated. A
new preview in the native UI displayed all 21 titles and correctly disabled the
already-imported sixth item. Selection was cleared; no new rows or audio jobs
were added. The original QA event still has nine applied tracks. Its one blank
event row was repaired from the verified metadata for the same SoundCloud ID
after an application-database backup; committed snapshots and acquisition jobs
were preserved. Both installed components report ready. Strict deep ad-hoc
signature verification passed for the QA app; its previous local Deezer archive
pin was retained only inside the QA bundle. The source manifest keeps the hosted
Deezer pin. This local build is not a signed/notarized release certification.

These follow-up checks do not replace the remaining native acceptance and
release gates recorded below.

## Scope and safeguards

The dedicated event `QA Multiplatform 2026-09-08` contains all test additions.
The application database and Rekordbox database were backed up before testing;
the normal guarded Apply flow also created its own backup. Existing events
were not edited. The original installed 0.8.0 application was retained, with
the QA build installed separately. Test files and the QA event are retained
for inspection. Private Spotify playlist metadata, credentials, and local
library paths are omitted from this report.

## Actual native outcomes

| Case | Preview | Selected and acquired |
| --- | --- | --- |
| SoundCloud track | One titled entry | `1757017227`; native AAC/M4A |
| YouTube track | One titled entry | `f7NwyBnIRTE`; Opus source converted to MP3 |
| Deezer track | Carefree | `3919489571`; exact requested identity |
| Spotify track | Carefree, authenticated session | `3DaGnKmAAmyZGIbC0KjmxT`; existing Deezer association policy |
| Spotify album | 25 entries | Position 1, Aces High; one selected |
| Deezer album | 25 entries; existing Carefree disabled | Position 2, Aurea Carmina; one selected |
| SoundCloud set | 21 entries, titles missing | Position 6, `565801467`; native AAC/M4A |
| YouTube playlist | 17 entries | Position 16, `YE7VzlLtp-4`; one selected |
| YouTube Music album | 50 entries | Position 1, The Chill Zone; one selected |
| Authenticated owned Spotify playlist | 11 titled entries | Dismissed; no rows or jobs added |

All nine explicitly requested acquisitions completed successfully. The nine
published files exist and match their recorded SHA-256 values. Direct-source
jobs returned their requested identities; Spotify used its existing Deezer
association behavior. Preview/confirmation did not implicitly acquire audio.
The UI remained responsive while an acquisition and another preview overlapped.

The first native Apply added four tracks: collection count increased from
1,456 to 1,460. A read-only SQLCipher check returned `quick_check = ok`, with
one QA playlist and one QA MyTag. Five subsequent collection selections are
ready and marked as additions after Apply.

A clean application quit and normal relaunch restored all nine tracks, the
latest committed preview, source/output properties, and the four-applied /
five-ready state. Full persisted track, import, and job records were unchanged;
no new download job was created by the restart.

With real Rekordbox running, Syncbox displayed the open-library warning and
disabled Apply and removal. Rekordbox then stopped responding to the native
control tool after its automatic-analysis dialog. Normal closure was requested
from the user; no process was forcibly terminated and no write guard bypassed.
After the user closed Rekordbox normally, the first reapply attempt correctly
refused a stale snapshot and reported no write or backup. The UI nevertheless
kept `Local jobs Running` and disabled mutation controls after this error.
A clean Syncbox quit/relaunch restored idle state and refreshed the snapshot.
A new native preview and explicit confirmation successfully applied all five
pending additions: the UI now shows nine applied, zero ready, zero missing,
and zero pending.

The resulting database passes `quick_check`. Collection count is 1,465; the
original QA playlist and MyTag IDs are unchanged, with exactly nine tag links
matching the nine event content IDs. The original four content IDs remain in
the event, all nine files exist, and acquisition job records remain unchanged.
Rekordbox reopened successfully and visibly reported 1,465 collection tracks.
Its playlist browser is absent from the accessibility tree, and coordinate
clicks repeatedly failed with `noWindowsAvailable`. The specific QA playlist
was therefore verified in the database, but not visually opened in Rekordbox.
The original two-deck layout was restored and Rekordbox quit normally. A final
read-only check after closure again returned `quick_check = ok`, 1,465 tracks,
and nine QA tag links. Native history-dropdown selection was also inconclusive
through automation; restart restoration was independently verified.

## Confirmed product defect

All 21 SoundCloud set entries lacked title metadata. The native preview showed
numeric item IDs, and the selected entry remained a blank title in the event
even after successful acquisition. Its provider identity and file are correct,
but this prevents a satisfactory collection-selection experience. The final
Rekordbox record correctly has the title `Market Day` from the audio file tags;
the missing title persists specifically in the import/event metadata. Enrich the
metadata and verify a useful title throughout preview, confirmation, and
acquisition before declaring native acceptance complete. An API URL also remains
the external link for the selected stub. No metadata fix is claimed by this run.

The stale-snapshot error also needs a terminal progress event so that the UI
returns to idle and allows recovery without an application restart. The write
guard itself worked; this run does not claim its error-recovery UI is complete.

## Build and delivery limits

The UI production build, frozen components, and Tauri bundle were built locally;
strict deep signature verification of the QA bundle passed. The local host is
outside the pinned release toolchain, so its explicitly unpinned build and local
Deezer archive must not replace the hosted manifest or release evidence.
The committed hosted Deezer manifest was restored after the local build.

The full packaging command failed on the source-path check because `.mcp.json`
contains a local home path. No final DMG or release was published. Optional
archives were installed using local archive overrides, then retained through a
normal relaunch without those overrides. This proves local installation and
runtime behavior, not hosted download availability or notarization.

PR #59 checks were green at the tested commit. CodeQL alerts #1, #3 and #4 are
dismissed; alert #2 remains open on `master` and is not a failing PR check.
Tasks 7.1 and 7.3 remain open (33/35 complete). Complete the remaining visual
inspection, correct the SoundCloud metadata and stale-error recovery defects,
and resolve the distribution gates
before final acceptance.
