# Local Rekordbox Test Fixtures

Everything in this directory except this README is ignored by Git.

## Safety rules

1. Create a Rekordbox library backup through Rekordbox.
2. Fully quit Rekordbox and `rekordboxAgent`.
3. Place regular file copies here. Do not use symlinks and never point the harness at the live Rekordbox directory.
4. Keep fixtures local. Never commit or share a user's database, audio, ANLZ data, credentials, tokens, or personal paths.

The harnesses copy consumed source fixtures into isolated temporary directories
before any write. They hash and stat every consumed source fixture before and
after execution.

## POC #4 fixture

### Required files

- `master.db`
- `masterPlaylists6.xml`

The XML file is required because three of the ten selected tests copy it unconditionally.

### Optional files

- `master.db-wal`
- `master.db-shm`
- `master.db-journal`

The ten POC #4 tests do not consume ANLZ or audio files.

The database must be a representative Rekordbox 7.x collection. Current assertions require more than 1,000 active tracks, varied metadata, at least one unique ISRC, tagged and untagged tracks, playlist membership, and at least one structural Smart Fix. A small or unusually clean fixture may fail honestly.

### Commands

The dedicated runner (`run_real_rekordbox_tests.py`, exit-code contract
included) is archived in git history. The gated tests now run through the
regular suite; each one copies the consumed fixtures into an isolated
temporary directory before any write:

```sh
cd sidecar && uv run --locked pytest -q -rs
```

Without the fixtures present, the gated tests skip and report the reason.

## POC #9 retained-track migration fixture

POC #9 uses the same `master.db`, `masterPlaylists6.xml`, and optional database
sidecars, plus this local-only layout:

```text
sidecar/tests/testdata/
├── event-migration.json
├── master.db
├── masterPlaylists6.xml
├── audio/
│   └── retained-track.mp3
└── share/
    └── .../
        ├── ANLZ....DAT
        ├── ANLZ....EXT
        └── ANLZ....2EX
```

Use a small, user-owned audio file that belongs to the selected Rekordbox
content row. It must be a complete regular-file copy, not a truncated sample.
Copy every relevant `share/**/ANLZ*.DAT`, `ANLZ*.EXT`, and `ANLZ*.2EX` file while
preserving its path relative to the Rekordbox `share` directory. At least one
ANLZ file is required.

The selected `content_id` must identify an active row in this `master.db` with:

- an `AnalysisDataPath` matching the declared ANLZ files;
- at least one active non-event MyTag;
- active playlist membership;
- cue and analysis data that the test can compare before and after migration.

### Manifest contract

`event-migration.json` is UTF-8 JSON with exactly these fields:

```json
{
  "schema_version": 1,
  "content_id": "123456789",
  "staging_audio": "audio/retained-track.mp3",
  "anlz_files": [
    "share/analysis/ANLZ0000.DAT",
    "share/analysis/ANLZ0000.EXT"
  ]
}
```

`content_id` is the existing Rekordbox content ID. `staging_audio` and every
`anlz_files` entry are normalized POSIX-relative paths below this directory;
absolute paths, `..`, backslashes, duplicates, empty files, and symlinks in any
path component are rejected. ANLZ entries must match
`share/**/ANLZ*.{DAT,EXT,2EX}`.

The selected pytest test resolves `master.db`, `masterPlaylists6.xml`, audio,
and ANLZ paths relative to the parent of the manifest named by
`SYNCBOX_EVENT_MIGRATION_FIXTURE`. Never point this environment variable at a
live Rekordbox directory or at this source directory.

### Commands

The dedicated runner (`run_event_migration_tests.py`, exit-code contract
included) is archived in git history. It validated the manifest, copied the
fixed database files and every declared file into an isolated temporary
directory, exported `SYNCBOX_EVENT_MIGRATION_FIXTURE` to the copied manifest,
and re-hashed every source afterwards. To rerun the selected test, reproduce
that isolation manually: copy the complete fixture set to a disposable
directory, then

```sh
cd sidecar && SYNCBOX_EVENT_MIGRATION_FIXTURE=/path/to/copy/event-migration.json \
  uv run --locked pytest -q tests/test_events_service.py
```

Without the environment variable, the selected test skips.

The copied-fixture POC #9 node passed once with zero skips on 2026-07-15 and
left every source unchanged. The required Rekordbox 7.2.16 CommonCrypto manual
checks passed on the disposable mutated copy on 2026-07-15. POC #9 is **GO**.
The final derived database was checkpointed and changed to SQLite DELETE
journal mode through CommonCrypto SQLCipher after an empty persistent WAL was
detected. Its `integrity_check` is `ok`; the final seven-file fixture therefore
contains no inapplicable WAL, SHM, or journal sidecar.

## Disposable directories for manual Rekordbox checks

The manual preparers (`prepare_manual_smartfix_fixture.py`,
`prepare_manual_rekordbox_sandboxes.py`, and the `--retain` mode of the
event-migration runner) are archived in git history. They required a confirmed
complete backup and the same strict Rekordbox/process-agent guard as
production writes, copied regular files only, kept every output below this
ignored directory, and verified every source file before and after copying.

The resulting ignored `rekordbox-sandboxes-final/` directory contains
`smartfix-sandbox/`, `event-sandbox/`, and `sandbox-evidence.json`. It is
published as one atomic directory and is private local evidence. Never commit
or share it. Preparing these directories does not authorize replacing the live
Rekordbox data directory: the documented swap and recovery sequence must be
reviewed and explicitly approved immediately before that separate operation.

## Manual validation result

The owner approved the exact swap and recovery procedure immediately before
the validation sequence. Rekordbox 7.2.16 was opened only against CommonCrypto
disposable copies and passed all required checks on 2026-07-15:

- reopen and playback;
- cues, beatgrid, waveform, and analysis;
- MyTags and playlist membership;
- Smart Fix metadata;
- retained-track volume-relative paths;
- ANLZ PPTH readability.

The live Rekordbox directory was restored after validation. Its complete
12,718-file snapshot matched the pre-operation snapshot with SHA-256
`1b523e27bf96539f0d498a65a57240ff64eba7648c5d3810b107fee07042c074`, and
the strict process guard confirmed that Rekordbox and `rekordboxAgent` were
closed. All databases, XML, audio, ANLZ files, evidence JSON, and personal
paths remain ignored local data.
