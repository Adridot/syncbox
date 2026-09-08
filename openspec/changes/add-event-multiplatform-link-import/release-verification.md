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

A retained archive comparison then isolated the remaining hosted discrepancy:
all entries matched except the frozen executable. Its only differing PYZ module
was `ctypes`: the deserialized code objects were equal, but their marshal data
differed after the release workflow's test run populated Python's bytecode cache.
Packaging now runs PyInstaller with `--clean` and a fresh temporary
`PYTHONPYCACHEPREFIX`, while disabling bytecode writes. Python therefore ignores
existing source-tree caches as documented for
[`sys.pycache_prefix`](https://docs.python.org/3/library/sys.html#sys.pycache_prefix).
With this isolation, both local roots produced the same 77,659,112-byte archive,
SHA-256 `a2aa8f1a6d8ce5ef31ef686b2e7a54f3e08a3a9d1f0496bd4d3459b680583a53`.
The 1,526 frozen Python module code objects compare equal to the earlier build;
the change affects serialization and cache reuse, not module behavior.

Hosted Release Pin run `34215403784` rebuilt both corrected archives. The Deezer manifest
was unchanged; the web-audio manifest was replaced wholesale with the hosted
artifact (77,656,560 bytes, SHA-256
`40b766dfe2e4c62edc828bab023103e79d6588e8be3dc785843ca665fc267ba0`).
Final preflight [34216084549](https://github.com/Adridot/syncbox/actions/runs/34216084549)
passed on `3d19a95`. Both applications passed the complete packaging scanner;
the three ZIPs were byte-identical across the isolated roots. The application
ZIP SHA-256 was `6b5f1ca3c21acd69ae30340aefe177e4010764d214379a92e8a39697a5edb01c`;
both component hashes matched the committed manifests. The hosted run passed
814 backend tests (11 skipped), 145 UI tests and all 33 web-audio tests.
CI, all CodeQL language checks and Release Pin were green before merging PR #59.

The squash merge `8177383e7de08e966c9754c3179066f9201a161b` has the same tree as
the validated branch. Version checks passed again on `master`. A new annotated
`v0.9.0` tag was pushed on that exact commit, triggering
[release run 34217432908](https://github.com/Adridot/syncbox/actions/runs/34217432908).
That attempt failed in the real cancellation test before publication. The
cancellation signal handler stopped the process group, then the `finally`
block stopped it again. macOS returned `EPERM` during the second cleanup.
The release run was cancelled; no GitHub Release or asset was published.

The follow-up removes the duplicate cleanup and tolerates a group permission
error only when the leader is already reaped, retaining failure for a live
leader. All 35 web-audio tests and five consecutive real cancellation tests
passed locally. The existing `v0.9.0` tag still points to the original merge;
the corrected component requires a new hosted pin and release validation.
Task 7.1 remains open pending the owner's tag/version decision, successful
publication and independent public download verification.
