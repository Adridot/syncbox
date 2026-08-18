## Purpose

Provide a one-time, auditable repair that fills supported metadata on the 55 known legacy Syncbox imports while preserving their Rekordbox identities and all DJ preparation data.

## ADDED Requirements

### Requirement: Preview the exact audited target set
The system SHALL build a read-only preview for the audited legacy-import cohort and SHALL require that it resolves to exactly 55 distinct, active Rekordbox content rows with readable local audio files. The preview SHALL include each content identity, file identity, current target-field values, proposed target-field values, and an aggregate field-count summary. It SHALL refuse to produce an applicable payload if the cohort is incomplete, expanded, ambiguous, duplicated, or contains an unreadable file.

#### Scenario: Exact cohort is available
- **WHEN** the audit resolves the 55 expected active content rows and every associated audio file is readable
- **THEN** the system produces one complete, read-only preview covering exactly those 55 rows

#### Scenario: Cohort no longer matches the audit
- **WHEN** target discovery resolves any number other than 55, resolves the same content identity more than once, or cannot uniquely identify a row
- **THEN** the system refuses the backfill and writes nothing

#### Scenario: A target audio file is unavailable
- **WHEN** any of the 55 target files is missing, not a regular file, or cannot be read for metadata
- **THEN** the system refuses the entire backfill instead of producing a partial applicable payload

### Requirement: Fill only supported blank metadata
For each of the 55 targets, the system SHALL derive album, album artist, genre, track number, disc number, release date, and release year from the existing audio file. It SHALL fill only blank Rekordbox album, genre, track number, disc number, release date, and release year values. A value is blank when it is null, an empty string, or the field's zero sentinel. The system SHALL use album artist only to preserve album identity and SHALL leave an unavailable optional source value blank.

#### Scenario: All universally available legacy fields are blank
- **WHEN** the 55 audited files provide album, track number, disc number, release date, and release year and the corresponding Rekordbox values are blank
- **THEN** the preview proposes all five values for every target row

#### Scenario: Genre is available for only 53 files
- **WHEN** 53 target files contain a non-blank genre tag and two target files do not
- **THEN** the preview proposes 53 genre fills and leaves the other two genre values blank

#### Scenario: A target value is already populated
- **WHEN** a target Rekordbox field contains a non-blank value
- **THEN** the system preserves that value and does not propose or apply a replacement

#### Scenario: Album names collide across album artists
- **WHEN** two album tags have the same album name but different non-blank album artists
- **THEN** the system treats them as different album identities

### Requirement: Apply only the exact confirmed preview
The system SHALL accept only a complete preview payload that exactly matches a fresh read of both the Rekordbox target fields and the source audio metadata. Apply SHALL require Rekordbox and rekordboxAgent to be closed, create a timestamped safety backup before opening the writable database, perform all changes in one transaction, roll back on failure, and invalidate the cached Rekordbox snapshot only after a durable commit.

#### Scenario: Confirmed preview remains current
- **WHEN** the user confirms the complete preview, the database and source metadata still match it exactly, and Rekordbox is closed
- **THEN** the system creates a backup and applies the complete fill-only payload in one transaction

#### Scenario: Rekordbox is running
- **WHEN** apply is requested while Rekordbox or rekordboxAgent is running
- **THEN** the system refuses before opening the writable database or creating a partial repair

#### Scenario: Database or source metadata changed after preview
- **WHEN** any target row, database fingerprint, file identity, or proposed source value differs from the confirmed preview
- **THEN** the system aborts before mutation and requires a new preview

#### Scenario: A write fails
- **WHEN** any write in the backfill transaction fails
- **THEN** the system rolls back the whole transaction and reports the failure and safety-backup location

### Requirement: Preserve track identity and DJ preparation data
The backfill SHALL update metadata in place and SHALL NOT download, replace, move, rename, re-import, or re-analyze audio. It SHALL preserve every content ID, audio-file byte stream, ANLZ file, cue, beatgrid, playlist membership, MyTag membership, play-history association, and non-target Rekordbox field except bookkeeping values that Rekordbox requires for a committed metadata update.

#### Scenario: Backfill completes successfully
- **WHEN** the confirmed payload is committed
- **THEN** every target retains its original content identity, paths, files, analysis artifacts, relationships, and non-target metadata

#### Scenario: Network is unavailable
- **WHEN** preview or apply runs without network access
- **THEN** the operation can complete using only the local Rekordbox database and existing audio files

### Requirement: Verify and report the strict outcome
After commit, the system SHALL read the repaired rows back through a read-only connection and SHALL verify the complete confirmed payload. Success SHALL report 55 tracks checked, all expected fill-only changes applied, genre present on the 53 source-tagged tracks, two genre values intentionally unchanged, the backup location, and zero preservation violations. A verification mismatch SHALL be reported as a failed operation with restoration guidance.

#### Scenario: Post-write verification succeeds
- **WHEN** all 55 rows match the confirmed target values and every preservation check passes
- **THEN** the system reports the backfill as successful with exact field and track counts

#### Scenario: Post-write verification detects a mismatch
- **WHEN** any repaired value or preservation assertion differs from the confirmed result
- **THEN** the system reports failure, identifies the mismatch, and points to the pre-write backup without attempting an unreviewed corrective write

#### Scenario: Completed repair is inspected again
- **WHEN** the same 55 content identities are checked after a successful backfill
- **THEN** the system reports no remaining supported blank values and proposes no additional writes
