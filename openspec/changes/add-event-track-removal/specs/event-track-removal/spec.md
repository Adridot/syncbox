## Purpose

Chosen tracks can be withdrawn from an event that has already been applied — untagged in Rekordbox, and deleted from Rekordbox and from disk when the event alone brought them in — without deleting the event itself.

## ADDED Requirements

### Requirement: Removal is previewed exactly and executed only on that preview

Removal SHALL be a two-step operation over a batch of chosen tracks. The first step SHALL return an exact plan stating, per track, what will happen in Rekordbox and on disk. The second step SHALL be refused unless it echoes that plan verbatim, and SHALL be refused if the Rekordbox database has changed since the plan was built. A plan targeting a different event, or a plan reporting unresolved cases, SHALL be refused.

#### Scenario: Preview then execute

- **WHEN** the user previews the removal of a batch of tracks and then confirms with that exact plan
- **THEN** the removal is executed as described

#### Scenario: Rekordbox changed after the preview

- **WHEN** the Rekordbox database changes between the preview and the confirmation
- **THEN** the removal is refused and the user is told to reopen the preview

#### Scenario: Altered plan

- **WHEN** a confirmation carries a plan that differs from the one the preview produced
- **THEN** the removal is refused and nothing is modified

#### Scenario: Rekordbox is open

- **WHEN** a removal is requested while Rekordbox is running
- **THEN** the removal is refused, as for every other Rekordbox write

### Requirement: What happens to a track depends on where its audio lives

For each applied track in the batch, the plan SHALL classify the outcome from the location of its audio and from whether any other Rekordbox tag retains it:

- audio in the permanent library, or outside application-managed storage: the event's tag is removed from the entry and the file is left untouched;
- audio staged for this event and retained by no other tag: the event's tag is removed, the Rekordbox entry is soft-deleted, and the staged file is deleted;
- audio staged for this event and retained by another tag: unresolved, see the blocking requirement.

This classification SHALL be the same one the full event deletion applies, so that the two operations cannot diverge.

#### Scenario: Track the user already owned

- **WHEN** a removed track's audio lives outside the event's staging area
- **THEN** the event's tag is removed from the Rekordbox entry, the entry itself is kept, and the file is not touched

#### Scenario: Track the event brought in

- **WHEN** a removed track's audio was staged for this event and no other tag retains it
- **THEN** the event's tag is removed, the Rekordbox entry is soft-deleted, and the staged file is deleted

#### Scenario: File deletion goes to the trash

- **WHEN** a staged file is deleted by a removal
- **THEN** it is sent to the trash rather than destroyed, and a permanent deletion happens only with the user's explicit consent

### Requirement: A track retained by another Rekordbox tag blocks the batch

A track in the batch whose audio was staged for this event but which carries another active Rekordbox tag SHALL be reported as unresolved in the preview, and its presence SHALL prevent the batch from executing. The report SHALL name the retaining tags and SHALL offer the actions that clear the situation. Moving such a file into the permanent collection SHALL remain exclusive to full event deletion.

#### Scenario: A staged track was tagged by the user

- **WHEN** the user previews the removal of a track whose staged file also carries a MyTag they added in Rekordbox
- **THEN** the preview reports it as unresolved, naming that tag, and the batch cannot be executed

#### Scenario: The blocker is cleared

- **WHEN** the user removes the other tag in Rekordbox and previews the removal again
- **THEN** the track is classified as brought in by the event and the batch can proceed

#### Scenario: Partial batch

- **WHEN** a batch contains both resolvable and unresolved tracks
- **THEN** nothing is executed until the unresolved ones are cleared or excluded from the batch

### Requirement: A track that was never applied is removed without touching Rekordbox

A track in the batch that has never been applied SHALL be removed from the event without any Rekordbox write. Its staged file, if it holds one, SHALL be deleted. Such a batch SHALL NOT require Rekordbox to be closed.

#### Scenario: Removing a ready track

- **WHEN** the user removes a track that holds a staged file but was never applied
- **THEN** the track leaves the event, its staged file is deleted, and the Rekordbox database is not modified

#### Scenario: Batch of never-applied tracks only

- **WHEN** every track in the batch was never applied
- **THEN** the removal proceeds while Rekordbox is running

### Requirement: Audio shared by more than one track of the event is never destroyed

When two tracks of the same event resolve to the same Rekordbox entry or the same staged file, removing one of them SHALL NOT soft-delete that entry and SHALL NOT delete that file while the other track still holds it. The event's tag SHALL be removed only once every track holding that entry has been removed.

#### Scenario: Two playlist entries sharing one file

- **WHEN** two tracks of the event share a staged file, and only one of them is removed
- **THEN** the file is kept, the Rekordbox entry is kept, and the event's tag is kept

#### Scenario: Both sharing tracks removed together

- **WHEN** both tracks sharing a staged file are in the same batch
- **THEN** the event's tag is removed once, the entry is soft-deleted once, and the file is deleted once

### Requirement: The event survives a removal intact

A removal SHALL leave the event's MyTag, its smart playlist, its staging directory and every track outside the batch unchanged. The event SHALL remain usable afterwards: further tracks can be added, matched, claimed, applied and re-applied exactly as before.

#### Scenario: The event's Rekordbox footprint after a removal

- **WHEN** a batch of tracks is removed from an event that keeps other applied tracks
- **THEN** the event's MyTag and smart playlist still exist and still carry the remaining tracks

#### Scenario: The staging directory survives

- **WHEN** a removal deletes some staged files
- **THEN** the event's staging directory itself is kept, along with the files of the tracks that remain

#### Scenario: Re-applying after a removal

- **WHEN** a track is added to the event after a removal and the event is re-applied
- **THEN** the re-apply behaves exactly as it would have before the removal

### Requirement: A removal is recoverable and never leaves a half-written state

A removal that writes to Rekordbox SHALL take a backup beforehand, as every other Rekordbox write does. Files SHALL only be deleted after the Rekordbox change has been durably committed, so a failure during the write leaves both the database and the files intact. A failure after the commit SHALL leave the files in place and report the incomplete cleanup rather than losing them.

#### Scenario: Failure during the Rekordbox write

- **WHEN** the Rekordbox write of a removal fails
- **THEN** the database is restored from the backup and no staged file has been deleted

#### Scenario: Failure after the commit

- **WHEN** the Rekordbox change is committed but the file cleanup cannot complete
- **THEN** the remaining files are kept and the incomplete cleanup is reported to the user
