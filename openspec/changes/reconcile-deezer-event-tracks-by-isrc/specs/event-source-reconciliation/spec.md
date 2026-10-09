## Purpose

Repair exact-source event rows that were downloaded or imported while an ISRC-equal recording already existed in the Rekordbox collection, through a previewed, trash-first, guarded operation.

## ADDED Requirements

### Requirement: Reconciliation is previewed before execution

The system SHALL expose a read-only reconciliation preview covering every exact-source event row that carries an ISRC. The preview SHALL list each row with its proposed action, the ISRC-equal collection content it would be associated with, and the file that would be trashed. Execution SHALL require the exact preview it was built from and SHALL refuse a preview that no longer matches the current Rekordbox snapshot, application rows, or file states.

#### Scenario: Preview lists a redundant download
- **WHEN** a `ready` exact-source row holds a staged download and an active local collection content carries the same ISRC
- **THEN** the preview proposes matching the row to that content and trashing the download

#### Scenario: Preview is stale at execution
- **WHEN** the Rekordbox snapshot, the row, or the download changed after the preview was produced
- **THEN** execution is refused and the user must reopen the preview

### Requirement: Redundant downloads are matched to the existing collection content

For a `ready` exact-source row whose staged download duplicates exactly one active local collection content with the same ISRC, execution SHALL set the row to matched with that content, clear its staged file reference, and send the download to the operating-system trash. No Rekordbox write SHALL occur for this case.

#### Scenario: Ready row becomes matched
- **WHEN** execution processes a `ready` exact-source row with one ISRC-equal collection content
- **THEN** the row is matched to that content with full confidence, its download is trashed, and the next apply tags the existing content

#### Scenario: Trash is unavailable without consent
- **WHEN** trashing the download fails and explicit permanent-delete consent was not provided
- **THEN** the row and the file are left unchanged and the system requests consent for a retry

### Requirement: Duplicate applied contents are replaced by the original

For an `applied` exact-source row whose Rekordbox content was created from its staged download and that duplicates exactly one other active local collection content with the same ISRC, execution SHALL, inside one guarded Rekordbox mutation with a backup: tag the original content with the event tag, remove the event tag from the duplicate, soft-delete the duplicate content, and then repoint the row to the original and trash the download file. The event SHALL keep its status, tag, and smart playlist.

#### Scenario: Applied duplicate is replaced
- **WHEN** execution processes an applied exact-source row whose content duplicates an older ISRC-equal content
- **THEN** the original content carries the event tag, the duplicate content is soft-deleted, the row references the original, and the download is trashed

#### Scenario: Duplicate content is used elsewhere
- **WHEN** the duplicate content carries other tags, belongs to other playlists, or is referenced by another event row
- **THEN** the row is reported as blocked and nothing is changed for it

### Requirement: Ambiguous or unproven candidates are never reconciled

The system SHALL skip and report a row when more than one distinct collection content carries its ISRC, when the ISRC duration guard rejects the candidate, when the row's file is not inside the event's managed staging directory, or when the file is a symbolic link. Fuzzy metadata SHALL NOT be used to choose a candidate.

#### Scenario: Two originals share the ISRC
- **WHEN** two active collection contents other than the row's own carry the same ISRC
- **THEN** the row is reported as ambiguous and left unchanged

### Requirement: ISRC coverage is reported

The preview SHALL report, for the whole application database, how many exact-source event rows carry an ISRC and how many do not, how many ISRC rows found a collection candidate, and which managed Deezer downloads present in the collection carry no ISRC tag. The system SHALL NOT change behaviour based on this report; it exists so the owner can confirm on production that ISRC matching covers the affected libraries before executing.

#### Scenario: Coverage shows a gap
- **WHEN** a managed Deezer download present in the collection has an empty ISRC
- **THEN** the preview lists that content so the owner can inspect it before execution
