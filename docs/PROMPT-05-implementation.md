# Syncbox v1 macOS — Remaining Implementation

> Run this prompt from the repository root with `ultracode` enabled and `/ponytail full` active.

---

ultracode — `/ponytail full`

## Mission

Complete the remaining Syncbox v1 features from the exact state of the current workspace.

The project is not a clean-room rewrite anymore. A substantial implementation already exists and must be preserved. Implement only missing, incomplete, or contradictory behavior.

Authority order:

1. `docs/SPEC-UNIFIED.md`;
2. the owner decisions embedded in this prompt, which override conflicting parts of `SPEC-UNIFIED`;
3. `docs/PROMPT-03-build.md`;
4. `docs/PROMPT-04-reunification.md`, only as historical coverage context.

Do not inspect Git history, previous commits, deleted implementations, tags, remote branches, or any branch other than the currently available workspace.

Do not use historical code as an architectural source. Analyze only the files currently present.

All code, tests, comments, and repository documentation created or modified during this task must be written in English. Communication with the owner remains in French.

Before starting development on any area, consult current official documentation and well-known upstream repositories. Do not make a structural decision from memory when the relevant technology may have changed.

Any structural choice not explicitly covered by this prompt must be presented to the owner with:

- the recommended option first;
- realistic alternatives;
- official sources;
- safety, size, performance, and maintenance trade-offs.

Do not make crucial product or safety decisions alone.

---

## Owner Decisions Overriding the Existing Specification

### Platform Scope

Syncbox v1 targets:

- macOS;
- Apple Silicon as the primary validated architecture.

Windows is explicitly deferred to v2.

For v1:

- do not implement `taskkill /T`;
- do not create a Windows installer;
- do not block delivery on WebView2 testing;
- do not create a full Windows process abstraction “for later”;
- keep OS boundaries clean enough that a future Windows implementation remains possible without introducing unused infrastructure now.

Linux remains out of scope.

### macOS Signing

The owner does not currently have an Apple Developer ID.

For v1:

- produce a functional unsigned macOS application;
- do not block the release on Developer ID signing;
- do not block the release on notarization or stapling;
- do not implement Keychain/keyring integration yet;
- keep the existing encrypted local secret-store path for unsigned builds;
- document the unsigned launch process honestly.

Developer ID signing, notarization, and the migration from the encrypted store to Keychain are deferred until the owner decides whether to purchase an Apple Developer account.

### Deferred Features

Do not implement in v1:

- Windows;
- Developer ID signing;
- notarization;
- Keychain migration;
- Chromaprint fingerprint deduplication;
- SoundCloud acquisition;
- ffmpeg bundling;
- AcoustID/MusicBrainz enrichment;
- automatic cues;
- beatgrid editing;
- cloud backend;
- mobile app;
- auto-update.

### File Protection Model

Do not implement `protected` as a universal track-level safety rule.

Replace the ambiguous boolean with an explicit ownership classification:

- `app_managed`: files inside Syncbox working directories such as event staging and inbox;
- `permanent_library`: files under `<storage_root>/rekordbox/`;
- `external`: every other user-owned location.

Apply safety according to the operation:

- event deletion may delete app-managed event artifacts;
- permanent or external files must not be deleted merely because an event is deleted;
- duplicate resolution can operate on any ownership class after exact per-group confirmation;
- keeper selection must not prefer a track solely because of its path;
- untagged removal remains a reversible Rekordbox soft-delete and never deletes audio;
- missing-file removal may soft-delete the Rekordbox row regardless of its former location;
- Smart Fixes must not filter tracks by file location.

### Event Retained-Track Migration

When an event is deleted, a staging track carrying at least one active Rekordbox MyTag other than the event MyTag is intentionally retained.

Such a file must be migrated to:

`<storage_root>/rekordbox/Collection/`

before the event and its temporary files are deleted.

This is the single intentional v1 exception to the general rule that Syncbox does not move user files.

---

## Ponytail Development Discipline

Ponytail is a design and implementation discipline, not a code-annotation system.

Use `/ponytail full` throughout the task.

For every implementation decision:

1. verify that the behavior belongs in v1;
2. prefer the standard library;
3. reuse existing dependencies and abstractions;
4. avoid registries, frameworks, and generic engines without a current need;
5. implement the smallest solution satisfying the invariant;
6. leave one focused runnable test for every non-trivial branch;
7. remove accidental duplication before adding an abstraction.

Do not add:

- `# ponytail:`;
- `// ponytail:`;
- block comments carrying Ponytail rationale;
- comments that merely justify why the implementation is small.

When touching existing files, remove nearby `ponytail` markers. Preserve meaningful technical information only when it explains a load-bearing invariant that cannot be expressed clearly by naming and tests.

Ponytail must never simplify away:

- the Rekordbox-running guard;
- timestamped backups;
- rollback;
- snapshot freshness;
- exact-payload confirmation;
- reversible database deletion;
- status integers;
- path representation rules;
- secret protection;
- ANLZ preservation where ANLZ files are modified.

At completion, executable source directories must contain no Ponytail marker:

```sh
rg -n "ponytail" sidecar/src ui/src shell/src-tauri/src
```

The expected result is empty.

Material architectural trade-offs may be recorded in the final implementation report or the relevant architecture document, not as recurring inline code comments.

---

## Ultracode Orchestration

Use one coordinator and at most three parallel agents.

Parallel work is allowed only for independent tasks with explicit file ownership.

No two agents may edit the same file concurrently.

Shared integration files must be owned by the coordinator:

- `sidecar/src/syncbox/api.py`;
- `sidecar/src/syncbox/settings.py`;
- app database migrations;
- `ui/src/api/types.ts`;
- shared UI stores;
- repository-level documentation;
- version and lock files.

### Initial Read-Only Parallel Audit

Start three agents in parallel.

#### Agent A — Specification Coverage

Read-only mission:

- map `SPEC-UNIFIED` sections 3–8 to current code and tests;
- identify implemented, partial, absent, and contradictory behavior;
- focus on safety, matching, dedup, events, missing files, Smart Fixes, backups, and settings;
- produce a matrix: invariant → implementation → test → POC → remaining action;
- do not modify files.

#### Agent B — Acquisition B1

Read-only mission:

- inspect the current absence of streamrip acquisition;
- inspect research files 10 and 14;
- verify the current upstream streamrip API from official sources;
- determine the exact Git revision to pin;
- design the smallest full-track Deezer POC;
- identify licensing and packaging boundaries;
- identify the minimum domain model, API, and UI changes;
- do not modify files.

#### Agent C — Event Migration and macOS Validation

Read-only mission:

- audit current event deletion;
- confirm the risk where a retained Rekordbox row loses its staging file;
- inspect pyrekordbox 0.4.4 path and ANLZ update capabilities;
- audit the skipped real-Rekordbox tests;
- audit the unsigned PyInstaller and Tauri bundle;
- inventory missing POC evidence;
- do not modify files.

The coordinator must consolidate all three audits before starting changes.

---

## Phase 0 — Baseline

Run and record the exact baseline:

```sh
cd sidecar
.venv/bin/python -m pytest -q -rs

cd ../ui
pnpm test
pnpm typecheck
pnpm build

cd ../shell/src-tauri
cargo check
```

Record:

- passed tests;
- skipped tests and reasons;
- warnings;
- bundle artifacts already present;
- current application versions;
- current Python, Rust, Node, and pnpm versions.

Do not hide existing failures.

---

## Phase 1 — Reconcile Current Documentation

Update the authoritative documents to record the owner decisions in this prompt.

At minimum, record:

- macOS-only v1;
- Windows deferred to v2;
- unsigned v1;
- Developer ID and notarization deferred;
- encrypted store retained until signing exists;
- removal of the universal `protected` rule;
- explicit ownership classification;
- retained event tracks migrated to the main Collection directory;
- no inline Ponytail markers.

When editing an existing French document, rewrite the complete touched section in English rather than introducing mixed-language sentences inside the same section.

Do not rewrite unrelated documentation.

---

## Phase 2 — Restore POC Evidence

Create a `poc/` directory containing lightweight, reproducible evidence.

Each relevant POC must include an English README with:

- objective;
- risk being tested;
- environment;
- dependency versions;
- exact commands;
- expected result;
- actual result;
- measurements;
- GO / NO-GO / BLOCKED;
- fallback;
- date.

Do not commit:

- real `master.db`;
- user audio;
- Spotify tokens;
- Deezer ARL;
- personal paths;
- build artifacts;
- credentials.

The following are explicitly deferred, not failed:

- Windows validation;
- Developer ID signing;
- notarization;
- Chromaprint.

Required v1 POC evidence:

1. sidecar process lifecycle on macOS;
2. PyInstaller onedir size and cold start;
3. SSE in the real macOS Tauri WebView;
4. pyrekordbox writes on Rekordbox 7.x;
5. Deezer full-track streamrip, only if credentials are available;
6. A3 bundle and audio calibration;
7. B2 purchase-link browser behavior;
8. Smart Fixes exact-payload and idempotence;
9. retained-event-track migration including ANLZ path preservation.

Existing source comments claiming a POC succeeded do not count as evidence.

---

## Phase 3 — Real Rekordbox Validation

Provide a harness that executes the currently skipped Rekordbox integration tests when this local fixture exists:

`poc/testdata/master.db`

Associated local files may include:

- `master.db-wal`;
- `master.db-shm`;
- `masterPlaylists6.xml`;
- ANLZ files;
- small labeled audio fixtures.

Keep all user fixtures ignored by Git.

Validate on a real Rekordbox 7.x fixture:

- strict process guard;
- `rekordboxAgent` detection;
- timestamped backup;
- backup collision suffix;
- rotation;
- restore-before-current-snapshot;
- rollback;
- active/deleted status integers;
- MyTag creation and links;
- smart-playlist creation and repair;
- signed 32-bit IDs;
- string primary keys;
- playlist XML restoration;
- event apply/reapply/delete;
- relink;
- soft-deleted artist self-heal;
- snapshot invalidation;
- volume-relative versus absolute path equivalence.

No feature writing `master.db` is complete while its real-fixture test remains untested.

---

## Phase 4 — Ownership Classification

Replace the ambiguous path-derived `protected` boolean with an explicit ownership value.

Recommended domain vocabulary:

```text
app_managed
permanent_library
external
```

Classification:

```text
<storage_root>/_syncbox/events/...  → app_managed
<storage_root>/_syncbox/inbox/...   → app_managed
<storage_root>/rekordbox/...        → permanent_library
everything else                     → external
```

Do not classify backups as audio content.

The classification must support:

- absolute paths;
- Rekordbox volume-relative paths;
- `~` expansion;
- canonical equality;
- missing paths;
- exact TCC-safe existence checks.

Update:

- Rekordbox snapshot DTO;
- sidecar API payloads;
- TypeScript types;
- duplicate UI;
- untagged UI;
- event delete preview;
- relevant i18n strings.

Remove location-based keeper priority.

The keeper priority becomes:

1. present file over missing file;
2. quality verdict and bitrate bucket;
3. stable creation-date tie-break;
4. stable content-ID tie-break.

A `lossy_source_probable` verdict remains below any non-flagged copy of equal or better declared bitrate.

Keep per-group confirmation. Do not restore one-click automatic bulk resolve.

---

## Phase 5 — Event Retained-Track Migration

### Functional Rule

When deleting an event, inspect every active Rekordbox content linked to the event MyTag.

For each content, choose exactly one action.

#### `already_permanent`

Use when the physical path is already under:

`<storage_root>/rekordbox/`

Behavior:

- leave the file in place;
- preserve the Rekordbox content row;
- preserve other MyTags;
- preserve playlist memberships;
- remove only the event MyTag.

#### `migrate_to_collection`

Use when:

- the physical file is inside the staging directory of this event; and
- the content carries at least one other active Rekordbox MyTag.

Destination:

`<storage_root>/rekordbox/Collection/<original filename>`

Behavior:

- migrate the file safely;
- update the same Rekordbox content row;
- preserve content ID;
- preserve cues;
- preserve beatgrid and analysis;
- preserve other MyTags;
- preserve playlist memberships;
- remove the event MyTag.

#### `delete_with_event`

Use when:

- the file is inside this event’s staging directory; and
- the content carries no active MyTag other than the event MyTag.

Behavior:

- remove the event MyTag;
- soft-delete the Rekordbox content row;
- delete the staging audio only after the database commit;
- use Trash first;
- require explicit consent before irreversible deletion.

#### `soft_delete_only`

Use when the database row should be removed but no owned physical artifact can safely be deleted.

### Exact Preview

The dry-run must list for every track:

- content ID;
- title;
- artist;
- source path;
- ownership;
- retaining MyTags;
- planned action;
- destination path when migrating;
- whether an ANLZ update is required.

It must also list:

- event MyTag removal;
- smart-playlist removal;
- XML artifacts;
- staging artifacts;
- expected file deletions.

The confirmation UI must execute exactly that payload.

A change in:

- `master.db`;
- WAL;
- source file existence;
- source size;
- source modification time;
- destination collision state;
- active MyTags;

must invalidate the preview and require a new dry-run.

### Collision Policy

Never overwrite an existing destination.

When the original filename already exists:

1. compare file size;
2. if sizes match, compare SHA-256;
3. if the content is identical and the destination is not already referenced by another active Rekordbox content, reuse it;
4. otherwise allocate a deterministic suffix: `Track - 2.mp3`, `Track - 3.mp3`, and so on.

Only compute SHA-256 when a collision exists.

### Safe File Sequence

Do not rename or move the source before the Rekordbox mutation.

For each migration:

1. verify that the source still exists using an exact-path check;
2. ensure the destination Collection directory exists;
3. resolve the final filename;
4. copy the source to a temporary file inside the destination directory;
5. flush and close the temporary file;
6. verify size;
7. verify SHA-256;
8. atomically publish the destination;
9. retain the original staging file;
10. enter the guarded Rekordbox mutation;
11. update the existing Rekordbox content path;
12. update affected ANLZ PPTH values;
13. remove only the event MyTag;
14. commit;
15. after commit, send the original staging file to Trash;
16. remove empty staging directories.

Use standard-library file operations unless a native API is proven necessary.

### Rekordbox and ANLZ Update

The installed pyrekordbox version exposes a content-path update operation that can update:

- `DjmdContent.FolderPath`;
- `OrgFolderPath`;
- `FileNameL`;
- the PPTH path in corresponding ANLZ files.

Use this capability without allowing pyrekordbox to perform an independent commit. The guarded Syncbox mutation remains the database transaction owner.

Validate through a real POC:

- the database must keep the required volume-relative representation for files under `<storage_root>/rekordbox/`;
- the ANLZ PPTH representation must remain readable by Rekordbox;
- cues and beatgrid must survive;
- playback must work after reopening Rekordbox.

Because this workflow modifies ANLZ files, extend the operation’s backup scope to include every ANLZ file it will modify.

On failure before the durable commit:

- roll back the database;
- restore affected ANLZ files;
- remove incomplete destination files;
- keep every source file;
- keep the event;
- return a per-track actionable error.

### Failure Policy

A required retained-track migration failure aborts the complete event deletion.

The event must not disappear while a retained file remains unsecured.

If cleanup fails after a successful commit:

- keep the committed Rekordbox destination;
- do not roll the database back to the staging path;
- report the old staging artifact as an orphan;
- keep the operation idempotent;
- allow a retry to finish cleanup only.

Missing Files is an exceptional recovery path for external loss or a crash. It is not the normal fallback for failed migration.

### Final Event Cleanup

Only after every required migration has committed successfully:

- remove the event MyTag;
- remove current and legacy event smart playlists;
- restore or update playlist XML as required;
- soft-delete event-only contents;
- delete event-only staging audio;
- remove XML snapshots;
- remove other event artifacts;
- remove the staging directory when empty;
- delete the application-database event row.

Do not blindly delete every file discovered in the staging directory. Every file must be tied to an explicit preview action.

---

## Phase 6 — Smart Fixes Completion

Preserve the current safety model:

- dry-run is read-only;
- dry-run may run while Rekordbox is open;
- execute requires Rekordbox closed;
- exact payload confirmation;
- snapshot freshness;
- server-side payload revalidation;
- guarded `_mutate`;
- timestamped backup;
- rollback;
- deterministic ordering;
- idempotence;
- fixed rule catalog;
- no generic user rule engine.

Smart Fixes must not filter by ownership or former `protected` state.

Complete the safe structural catalog with evidence-backed rules for:

- trailing URL and site junk;
- Unicode whitespace;
- mojibake;
- safe artist/remixer extraction from titles;
- non-greedy feat/remix parsing;
- safe separator cleanup;
- safe casing normalization where it cannot damage intentional stylization.

Do not introduce naive title-casing that changes legitimate names such as:

- DAKITI;
- SNAP;
- #SELFIE;
- stylized artist names;
- acronyms;
- mixed-case branding.

Every rule requires:

- positive examples;
- counterexamples;
- no-op tests for clean data;
- composition tests;
- fixpoint/idempotence tests;
- exact dry-run-to-execution tests.

If a rule cannot be made conservatively safe, leave it out and report the unsupported case instead of adding a risky heuristic.

---

## Phase 7 — A3 Audio-Quality Validation

Preserve:

- read-only analysis;
- exact-path TCC-safe access;
- no directory enumeration;
- no network;
- no file movement;
- no persistence of the verdict;
- no call from `_mutate`;
- `ok`, `incertain`, `lossy_source_probable`;
- neutral fallback on decode or I/O failure;
- neutral treatment of `incertain`;
- binary keeper penalty only for `lossy_source_probable`.

Validate:

- miniaudio;
- cffi;
- `_cffi_backend`;
- numpy;
- PyInstaller onedir;
- packaged Tauri app.

Create a small labeled POC corpus covering:

- genuine 320 kbps;
- V0;
- 256 kbps;
- 192 kbps;
- lower bitrate;
- genuine lossless;
- lossy-to-FLAC transcode;
- band-limited legitimate masters;
- silence;
- very short files;
- undecodable formats.

Document false-positive boundaries honestly.

If calibration is not reliable enough, apply the documented A3-lite fallback or defer A3 rather than shipping confident-looking incorrect verdicts.

---

## Phase 8 — B2 Legal Purchase Links

Preserve the pure URL-template approach:

- Beatport;
- Bandcamp;
- `urllib.parse`;
- shared D19 normalization;
- no store API;
- no scraping;
- no HTTP request from the sidecar;
- no secret;
- browser opens the link.

Test the templates manually in the browser with 5–10 representative tracks.

Record:

- whether the search page loads;
- whether the correct track appears;
- whether the first result is usually relevant;
- behavior for unavailable tracks;
- behavior for non-ASCII metadata.

If B1 acquisition is implemented, include `acquisition_failed` among the statuses exposing purchase links.

The legal purchase path remains available and visually primary whether B1 is enabled or not.

---

## Phase 9 — B1 Streamrip Acquisition Gate

B1 remains conditional.

Start with the full-track Deezer POC. It requires a real Premium ARL supplied locally by the owner.

Never expose the ARL in:

- source code;
- Git;
- logs;
- exception messages;
- screenshots;
- POC reports;
- fixtures;
- settings JSON;
- `config.toml`;
- environment dumps.

Possible outcomes:

### GO

Implement B1 in v1.

### NO-GO

Document the failure and defer B1 to v1.1. B2 remains the missing-track path.

### BLOCKED

If no Premium ARL is available, report the external dependency honestly. Do not claim B1 works.

### Architecture if GO

Implement B1 as a separate optional component:

- OFF by default;
- Deezer-only;
- lazy import;
- no streamrip import at application boot;
- exact Git v2.2.0 revision pinned by SHA;
- GPL-3 code absent from the base artifact;
- base app fully functional without the component;
- no SoundCloud;
- no ffmpeg.

Interface:

```python
DeezerAcquirer.download(track_id) -> Path
```

Requirements:

- resolve ISRC to a numeric Deezer ID;
- use the supported streamrip resolution flow;
- obtain the real output path from the downloader;
- never reconstruct the filename unless an explicitly tested fallback is unavoidable;
- hold ARL and output directory per job;
- no mutable process-global acquisition state;
- create streamrip configuration in memory;
- do not call file-based configuration loaders;
- do not call configuration save methods;
- neutralize the streamrip config directory;
- TLS through certifi;
- never disable certificate validation.

### Domain Model

Add one unified acquisition-job table with scopes:

- `library`;
- `event`;
- `collection`.

Statuses:

```text
pending
resolved
queued
downloading
downloaded
ready
acquisition_failed
acquisition_ambiguous
```

Transitions must be validated and idempotent.

`downloaded → ready` requires:

- a real output path;
- a file present on disk;
- successful scan;
- successful claim or relink.

If Rekordbox is open or relink fails:

- retain the downloaded file;
- keep the job `downloaded`;
- retry later;
- do not report `ready`.

### Secrets

For unsigned v1:

- retain the encrypted SQLCipher secret store;
- store ARL there only;
- preserve blank credentials on settings update;
- never include ARL in settings export;
- never include ARL in all-data plaintext exports;
- never write ARL to streamrip configuration.

Do not implement Keychain yet.

### API and UI

Add:

- job creation;
- resolution;
- start;
- retry;
- cancellation where safe;
- status read;
- canonical SSE progress;
- per-track actionable failure messages.

In the UI:

- acquisition is visibly optional;
- OFF means no acquisition controls and no module error;
- purchase links remain primary;
- progress comes from SSE;
- no fake percentage;
- no provider registry;
- no SoundCloud placeholder.

---

## Phase 10 — macOS Sidecar and Application Validation

Keep the current macOS lifecycle small and explicit:

- single instance before sidecar spawn;
- sidecar in its own process group;
- stdout consumed;
- stderr consumed;
- bounded restart;
- backend-down event;
- intentional-shutdown flag;
- `POST /shutdown`;
- bounded graceful wait;
- SIGTERM fallback;
- SIGKILL final fallback;
- SQLCipher connections closed before exit;
- permanent API/SSE port 8766 released;
- temporary Spotify callback port 8765 released after a terminal callback,
  timeout, disconnect, or shutdown;
- no orphan.

Do not build a Windows implementation.

Produce:

- PyInstaller onedir sidecar for macOS Apple Silicon;
- production Vue build;
- Tauri `.app` bundle;
- unsigned distribution archive.

Run lifecycle harnesses against:

- source sidecar;
- frozen sidecar;
- packaged Tauri application.

Validate:

- cold start;
- warm start;
- shutdown;
- crash restart;
- restart exhaustion;
- manual restart;
- stale-sidecar cleanup;
- port collision message;
- resource lookup inside the app bundle;
- OAuth callback;
- SSE in the actual WKWebView;
- miniaudio;
- sqlcipher3;
- pyrekordbox;
- certifi.

Do not claim signing or notarization.

---

## Phase 11 — Settings, Secrets, and Persistence

Preserve:

- one SQLite settings source of truth;
- defaults applied at read time;
- no default re-save at boot;
- blank credential preservation;
- `PRAGMA user_version`;
- ordered SQL migrations;
- explicit migration transactions;
- no Alembic;
- all-data export with `VACUUM INTO`;
- safety backup before import;
- path validation;
- OAuth PKCE only;
- fixed callback URI;
- local-first architecture.

For unsigned v1:

- keep the encrypted SQLCipher secret store;
- keep the per-install key file mode 0600;
- do not add keyring;
- do not add Keychain;
- do not export OAuth tokens or ARL in readable files.

If this conflicts with a sentence in `SPEC-UNIFIED`, update the specification to match the safer owner-approved behavior.

---

## Phase 12 — Dependency and Version Reproducibility

Add missing development dependencies, including pytest.

Generate and commit a reproducible Python lock file.

Preserve:

- `pnpm-lock.yaml`;
- `Cargo.lock`;
- one canonical application version.

Align:

- `ui/package.json`;
- `shell/package.json`;
- `shell/src-tauri/Cargo.toml`;
- `sidecar/pyproject.toml`;
- Tauri configuration;
- README release version.

Do not broadly pin dependencies without a reason. Direct runtime and packaging dependencies must nevertheless be reproducible through lock files.

---

## Phase 13 — Documentation and UI Truthfulness

Update documentation to reflect reality:

- v1 is macOS Apple Silicon;
- Windows is v2;
- current app is unsigned;
- no Developer ID yet;
- Keychain deferred;
- B1 state matches its actual POC verdict;
- B2 remains available;
- event deletion migrates retained staging tracks;
- retained files go to `rekordbox/Collection`;
- no universal `protected` concept;
- ownership terminology is used consistently;
- Missing Files is an exceptional recovery path;
- no auto-update.

Remove claims that unsupported platforms or unvalidated features are already complete.

Maintain FR/EN UI parity.

Repository documentation changes must be in English.

---

## Test Contract

Run and report all applicable commands.

### Python

```sh
cd sidecar
uv lock
uv sync --locked
.venv/bin/python -m pytest -q -rs
```

Run the real-Rekordbox integration suite with the local fixture.

No critical write-path test may remain silently skipped in the final local validation report.

### UI

```sh
cd ui
pnpm test
pnpm typecheck
pnpm build
```

### Rust/Tauri

```sh
cd shell/src-tauri
cargo check
```

Build the production macOS app from the shell workspace.

### Source Hygiene

```sh
rg -n "ponytail" sidecar/src ui/src shell/src-tauri/src
```

Expected result: no inline Ponytail marker.

Scan for:

- secrets;
- personal paths;
- ARL;
- generated `config.toml`;
- streamrip in the base artifact;
- unexpected GPL component in the base artifact;
- stale version strings.

### Event Migration Tests

Cover at minimum:

1. staging track with only event MyTag → delete with event;
2. staging track with another MyTag → migrate to Collection;
3. permanent Collection track → keep in place;
4. external track → keep in place unless explicitly owned;
5. collision with different content → deterministic suffix;
6. collision with identical unreferenced content → reuse;
7. collision already referenced by another active content → no silent shared path;
8. copy failure → event deletion aborted;
9. checksum mismatch → event deletion aborted;
10. Rekordbox mutation failure → DB rollback, ANLZ restore, source kept;
11. ANLZ update failure → rollback;
12. post-commit source cleanup failure → committed destination retained and orphan reported;
13. stale preview → no file or database change;
14. retry after partial cleanup → idempotent;
15. cues, beatgrid, MyTags, and playlists survive migration;
16. resulting path opens in Rekordbox;
17. event folder is removed only after all planned actions complete.

### Smart Fixes Tests

Cover:

- dry-run has no write;
- dry-run works while Rekordbox is open;
- execute is blocked while Rekordbox is open;
- stale fingerprint aborts;
- payload forgery is rejected;
- backup precedes mutation;
- exact preview equals exact write;
- deterministic rule composition;
- idempotent rerun;
- clean values are no-ops;
- ownership does not filter metadata fixes.

### Acquisition Tests, Only if B1 Is GO

Cover:

- module absent while OFF;
- no import at boot;
- no config file written;
- ARL never logged;
- job-local settings;
- concurrent jobs do not exchange paths;
- numeric ID resolution;
- real output path;
- valid transitions;
- downloaded file retained when relink is blocked;
- base artifact contains no streamrip code;
- purchase links remain available.

---

## Definition of Done

The task is complete when:

- the macOS Apple Silicon app runs from its unsigned production bundle;
- current sidecar and UI tests pass;
- real Rekordbox mutation tests pass locally;
- all relevant v1 POC have traceable verdicts;
- Windows and signing POC are explicitly deferred;
- no sidecar remains orphaned;
- permanent API/SSE port 8766 is released on shutdown;
- the exact temporary Spotify callback listener on port 8765 is released
  after success, denial, terminal error, timeout, disconnect, and shutdown;
- no secret is stored in cleartext;
- no streamrip configuration contains the ARL;
- event deletion migrates retained staging files to the main Collection;
- migrated contents keep their Rekordbox identity, cues, analysis, MyTags, and playlists;
- a failed migration cannot delete the event or source files;
- temporary event files are removed only after retained files are safe;
- ownership replaces the ambiguous universal `protected` rule;
- keeper selection is not biased solely by file location;
- Smart Fixes are safe, deterministic, and idempotent;
- no inline Ponytail markers remain in executable source;
- B1 is either genuinely GO and delivered, or explicitly deferred;
- B2 is always available;
- documentation matches the actual artifact;
- no v2 feature has been implemented speculatively.

At the end, provide a concise French report containing:

- implemented behavior;
- files changed;
- tests and POC executed;
- measured bundle size and startup;
- remaining skips;
- B1 verdict;
- known limitations;
- deferred v2 work;
- every external blocker stated faithfully.
