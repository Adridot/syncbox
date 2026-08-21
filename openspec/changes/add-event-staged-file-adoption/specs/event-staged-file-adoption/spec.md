## Purpose

Audio files the user drops into an event's staging folder become event tracks on their own, so a track that does not exist on Spotify can join an event by being placed next to the acquisition downloads.

## ADDED Requirements

### Requirement: Unreferenced staged files become event tracks

When staged files are claimed for an event, every audio file under the event's staging directory that is referenced by no event track's staged path SHALL be adopted as a new event track of that event. Adoption SHALL run after existing claimable tracks have had their chance to claim files, so a file that satisfies a track already in the event is never adopted as a duplicate track. Adoption SHALL be bounded by the same scan limits as the existing staged-file scan and SHALL tolerate per-entry filesystem errors without aborting the pass.

#### Scenario: A dropped file with no track waiting for it

- **WHEN** an audio file is present in the event staging directory, no event track carries it as its staged path, and staged files are claimed
- **THEN** a new event track is created for that file and the file is no longer unreferenced

#### Scenario: A dropped file that an existing track can claim

- **WHEN** an audio file is present in the event staging directory and an event track in a claimable status matches it
- **THEN** that existing track claims the file and no new track is adopted for it

#### Scenario: Nested folders

- **WHEN** a folder of audio files is placed inside the event staging directory
- **THEN** the audio files it contains are adopted individually, exactly as if they had been placed at the top level

#### Scenario: Non-audio files

- **WHEN** a file that is not a recognised audio file is present in the event staging directory
- **THEN** it is ignored by adoption and no track is created for it

### Requirement: Adopted track metadata comes from the file

An adopted track SHALL take its title, artist, duration and ISRC from the audio file's own embedded tags. When the file carries no usable title tag, the track's title SHALL be the file's complete name including its extension, and the artist SHALL be left unset. An adopted track SHALL carry no Spotify track identifier.

#### Scenario: File with complete tags

- **WHEN** a file carrying title, artist, duration and ISRC tags is adopted
- **THEN** the created track exposes those values and no Spotify track identifier

#### Scenario: File with no title tag

- **WHEN** a file carrying no usable title tag is adopted
- **THEN** the created track's title is the file's complete name including its extension and its artist is unset

#### Scenario: Unreadable or tagless file

- **WHEN** a file whose tags cannot be read is adopted
- **THEN** adoption still succeeds using the file name as the title, and the pass continues with the remaining files

### Requirement: An adopted track resolves through the existing match and claim flow

An adopted track SHALL be created in the `missing` status so that the automatic event matching and the staged-file claim that already run on this operation determine its outcome. A track that matches an existing Rekordbox collection entry SHALL become `matched` and SHALL be reported as duplicating a collection entry, so the user learns the dropped file was unnecessary. A track that matches nothing SHALL claim the file it was created from and become `ready`. Adoption SHALL NOT write to the Rekordbox database.

#### Scenario: Dropped file for a track absent from the collection

- **WHEN** a file is adopted and its metadata matches no entry of the Rekordbox collection
- **THEN** the track claims that file, reaches status `ready`, and is applied by the existing event apply flow

#### Scenario: Dropped file for a track already in the collection

- **WHEN** a file is adopted and its metadata matches an existing Rekordbox collection entry
- **THEN** the track reaches status `matched` against that entry, the existing entry is tagged at apply time rather than a second one being created, and the track is reported as duplicating a collection entry

#### Scenario: Naming the duplicated entry

- **WHEN** a track is reported as duplicating a collection entry and that entry can be read from the collection snapshot
- **THEN** the entry's title and artist are reported alongside, so the user is told which track they already own

#### Scenario: The duplicated entry cannot be read

- **WHEN** a track is reported as duplicating a collection entry and the collection snapshot is unavailable
- **THEN** the duplication is still reported without naming the entry, and reading the event never fails on this account

#### Scenario: Rekordbox is open

- **WHEN** staged files are claimed while Rekordbox is running
- **THEN** adoption completes normally, because it only reads the collection snapshot and writes to the application database

### Requirement: A rejected adopted track stays rejected

Removing an adopted track from an event SHALL retain the track with status `ignored` and SHALL retain its staged path, so the file remains referenced and is not adopted again on a later claim. An `ignored` track SHALL NOT be matched, claimed, applied, or counted among the event's outstanding work. Removing a track that was not adopted SHALL keep its current behaviour.

#### Scenario: The user removes a file they dropped by mistake

- **WHEN** an adopted track that has not been applied is removed from the event
- **THEN** the track is retained with status `ignored`, keeps its staged path, and disappears from the event's outstanding work

#### Scenario: Claiming again after a rejection

- **WHEN** staged files are claimed again after an adopted track was removed
- **THEN** the file behind the ignored track is not adopted a second time

#### Scenario: Removing a track that came from Spotify

- **WHEN** a track that was not adopted from a staged file is removed from the event
- **THEN** it is removed exactly as before this change

### Requirement: A rejection can be undone

Rejected tracks SHALL remain reachable in the event, separately from its outstanding work, and the user SHALL be able to restore one. Restoring a rejected track SHALL return it to the flow that adoption puts a new track through, so that its state is re-derived from the collection and from the file as it stands at that moment rather than from the state it held when it was rejected.

#### Scenario: Consulting rejected tracks

- **WHEN** the user asks to see the tracks they rejected in an event
- **THEN** the rejected tracks are listed, and they remain absent from every other view of the event

#### Scenario: Restoring a rejected track

- **WHEN** the user restores a rejected track
- **THEN** the track re-enters the event's outstanding work with its state re-derived, matching a collection entry or claiming its file exactly as a newly adopted track would

#### Scenario: Restoring a track whose file vanished

- **WHEN** the user restores a rejected track whose staged file is no longer on disk
- **THEN** the track returns as missing rather than as ready, and no operation fails on the absent file

### Requirement: No staged file is deleted without having been shown

Because every audio file under an event's staging directory is adopted as a track, the files an event deletion plans to remove SHALL all correspond to tracks the user has been able to see in that event.

#### Scenario: Deleting an event after files were dropped into it

- **WHEN** files were dropped into an event's staging directory and staged files were claimed at least once
- **THEN** the event deletion preview accounts for those files through tracks that were visible in the event
