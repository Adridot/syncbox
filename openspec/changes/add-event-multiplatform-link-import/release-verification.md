# 0.9.0 release verification

This delivery record supersedes the pending native-test status and manual
web-audio upload instructions in earlier reports. Historical reports retain
their original build hashes and observations.

## Native acceptance

Task 7.3 is complete. The installed Tauri application was exercised with real
single tracks and collections on Spotify, Deezer, YouTube/YouTube Music and
SoundCloud. Nine selected acquisitions, Apply, reapply, restart persistence,
authenticated Spotify collections and the Rekordbox-open write guard passed.
The resulting Rekordbox database passed `quick_check`, with nine matching event
links and 1,465 collection records. The specific QA playlist was verified in
the database; its visual navigation and the native history dropdown could not
be established through the automation tool. These are recorded verification
limits, not claims of successful UI interaction.

The two defects found during that run were corrected: SoundCloud collection
stubs now hydrate titles and canonical links, and failed jobs emit a terminal
progress event so the UI can recover. The corrected installed preview showed
21 titled entries and disabled the existing entry. Regression checks passed:
811 backend tests (11 skipped), 145 UI tests, 33 web-audio tests, and the UI
production build. See `native-verification.md` and
`native-fixes-verification.json` for the actual scoped evidence.

## Distribution preparation

The application, shell, sidecar, both optional components, lockfile package
entries and component URLs use 0.9.0. Third-party dependency versions remain
independently pinned. The release workflow builds both optional components,
checks their committed manifests, builds the application, and compares all
three ZIPs across two isolated source roots. Manual dispatch runs the complete
preflight without publication; a new version tag triggers publication.

Local workflow validation and 17 version/publication regression checks passed.
Hosted Release Pin run `34209757477` rebuilt both archives. The Deezer manifest
was unchanged; the web-audio manifest was replaced wholesale with the hosted
artifact (77,708,570 bytes, SHA-256
`46996c97a428a63c401de8099d21c7b9ab205e32cd606a81f1370639e81b1ac6`).
Task 7.1 remains open until the hosted builds and public release downloads have
been verified. The release tag must not be created while a manifest or archive
comparison fails.
