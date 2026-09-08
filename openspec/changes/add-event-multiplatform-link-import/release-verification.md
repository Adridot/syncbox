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
Preflight run `34210349336` exposed two packaging defects before any tag:

- The source scanner traversed generated web-audio dependencies and treated
  Deno's literal PEM parser marker as a private key. The scan now excludes only
  `web-audio-component/vendor`, consistent with its existing generated-directory
  exclusions. A regression keeps vendored project sources covered. A clean
  export passed the source scan (481 files); 45 release-focused tests passed.
- Installed `RECORD` entries for yt-dlp and websockets contained hashes of
  unbundled console scripts whose shebangs vary with the build venv path. The
  web-audio spec now follows the base bundle's existing omission of optional
  `RECORD` files, retaining runtime metadata and all notices. This matches the
  [installed-project metadata specification](https://packaging.python.org/en/latest/specifications/recording-installed-packages/).

Two local roots with independent locked Python environments then produced the
same 77,659,135-byte web-audio ZIP, SHA-256
`3425fc48f4614d338447625b6d15e6d6a5ead3efb08de4b2dd39a5f87e92e096`.
Both frozen protocol checks passed. This is local reproducibility evidence,
not the hosted release pin.

CodeQL alert #2 was reattached to the changed packaging scanner. Its SARIF flow
starts at the integer return value of `validate_source_secrets`, not file
contents or credentials. The unused scanned-file counter was removed from the
printed JSON report; the validation call and rejection behavior remain intact.
No alert suppression or dismissal was added.

Hosted Release Pin run `34212020132` rebuilt both corrected archives. The Deezer manifest
was unchanged; the web-audio manifest was replaced wholesale with the hosted
artifact (77,656,565 bytes, SHA-256
`bb2f76cf47fc78ba417bfd0a16ff609201c14ed031995cb648e7a20477fd59c6`).
Task 7.1 remains open until the hosted builds and public release downloads have
been verified. The release tag must not be created while a manifest or archive
comparison fails.
