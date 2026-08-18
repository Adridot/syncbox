# staged-file-integrity Specification

## Purpose

A staged audio file that disappears from disk must never leave a track stuck in a non-actionable state: the track returns to the missing-family flow, and no import ever reaches the Rekordbox write with an unavailable staged file.

## Requirements

### Requirement: A ready track whose staged file vanished becomes actionable again

A library or event track in status `ready` whose `staging_file_path` no longer points to a regular file on disk SHALL be reclassified to status `missing`, with its `staging_file_path` cleared. Prior acquisition jobs SHALL be retained unchanged as history. After reclassification the track SHALL be eligible for the Missing center exactly like any other `missing` track. For library tracks, this validation SHALL run during source synchronization, when prior `ready` rows are carried over.

#### Scenario: Library sync detects a vanished staged file

- **WHEN** a source is synchronized and a prior `ready` row's `staging_file_path` does not resolve to a regular file
- **THEN** the row is carried with status `missing` and an empty `staging_file_path`, its acquisition jobs are left untouched, and it appears in the Missing center

#### Scenario: Staged file still present

- **WHEN** a source is synchronized and a prior `ready` row's `staging_file_path` resolves to a regular file
- **THEN** the row is carried as `ready` unchanged, exactly as before

#### Scenario: Staged path exists but is not a regular file

- **WHEN** a prior `ready` row's `staging_file_path` resolves to a directory or other non-regular file
- **THEN** the row is treated the same as a vanished file and reclassified to `missing`

### Requirement: Imports validate staged files before any Rekordbox write

Library and event imports SHALL verify, before opening the Rekordbox write transaction, that every selected `ready` row's `staging_file_path` resolves to a regular file. Rows failing this check SHALL be reclassified to `missing` (staging path cleared, jobs retained), excluded from the import, and reported to the caller; the remaining selected rows SHALL import normally. The Rekordbox database SHALL NOT be modified on behalf of a row whose staged file is unavailable.

#### Scenario: Library import with one vanished staged file

- **WHEN** a library import is requested for three rows, one of them `ready` with a vanished staged file
- **THEN** the two valid rows are imported, the invalid row is reclassified to `missing` and reported as not imported, and no Rekordbox rollback occurs

#### Scenario: Event import with a vanished staged file

- **WHEN** an event apply includes a `ready` track whose staged file is unavailable
- **THEN** that track is reclassified to `missing` and excluded before the Rekordbox write, the remaining tracks apply normally, and the apply does not fail with a file-not-found error
