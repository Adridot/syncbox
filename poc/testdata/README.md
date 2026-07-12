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

From the repository root:

```sh
sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py --check
sidecar/.venv/bin/python poc/run_real_rekordbox_tests.py
```

Exit codes:

- `0`: all ten tests passed, none skipped, fixtures unchanged;
- `2`: fixture or environment preflight failed;
- `3`: a source fixture changed;
- `4`: pytest did not report exactly ten passes or at least one selected test was skipped;
- any other non-zero code: pytest's failure code.

## POC #9 retained-track migration fixture

POC #9 uses the same `master.db`, `masterPlaylists6.xml`, and optional database
sidecars, plus this local-only layout:

```text
poc/testdata/
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

The runner copies only the fixed database files and files declared by this
manifest. It then sets `SYNCBOX_EVENT_MIGRATION_FIXTURE` to the copied manifest
path. The selected pytest test resolves `master.db`, `masterPlaylists6.xml`,
audio, and ANLZ paths relative to that manifest's parent. Never point this
environment variable at a live Rekordbox directory or run the test directly
against the source manifest.

### Commands

From the repository root:

```sh
sidecar/.venv/bin/python poc/run_event_migration_tests.py --list
sidecar/.venv/bin/python poc/run_event_migration_tests.py --check
sidecar/.venv/bin/python poc/run_event_migration_tests.py
```

Exit codes:

- `0`: fixture preflight passed, or the selected test passed once with zero skips and sources unchanged;
- `2`: fixture, manifest, or environment preflight failed;
- `3`: a source fixture changed;
- `4`: pytest did not report exactly one pass or the selected test was skipped;
- any other non-zero code: pytest's failure code.

POC #9 remains **BLOCKED** until the real test passes and the required
macOS/Rekordbox evidence is recorded. This fixture contract and runner do not
claim a successful POC execution.
