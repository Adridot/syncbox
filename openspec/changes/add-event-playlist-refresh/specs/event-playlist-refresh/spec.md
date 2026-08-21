## Purpose

An event created from a Spotify playlist can be brought back in line with that playlist on demand, picking up tracks added to it and reporting tracks that have left it, without deleting and recreating the event.

## ADDED Requirements

### Requirement: An event backed by a playlist can be refreshed on demand

The system SHALL provide an explicit refresh operation for an event whose Spotify playlist is known. The operation SHALL re-read the playlist from Spotify and reconcile it against the event's playlist-sourced tracks. The operation SHALL NOT modify the Rekordbox database and SHALL therefore be available whether or not Rekordbox is running. Refreshing an event that has no Spotify playlist SHALL be refused with an explanatory error. A refresh that fails to reach Spotify SHALL leave the event exactly as it was.

#### Scenario: Refreshing a playlist-backed event

- **WHEN** the user refreshes an event whose Spotify playlist is known
- **THEN** the playlist is re-read and the event's playlist-sourced tracks are reconciled against it

#### Scenario: Refreshing while Rekordbox is open

- **WHEN** the user refreshes an event while Rekordbox is running
- **THEN** the refresh completes normally and reports its result

#### Scenario: Refreshing a manual event

- **WHEN** the user refreshes an event that was created without a Spotify playlist
- **THEN** the refresh is refused with an error explaining that the event has no playlist

#### Scenario: Spotify unreachable

- **WHEN** a refresh is requested and the Spotify request fails
- **THEN** the event's tracks are unchanged and the failure is reported to the user

### Requirement: Only playlist-sourced tracks take part in the reconciliation

Every event track SHALL record where it came from: imported from the event's playlist, added by the user, or adopted from a staged file. Only tracks recorded as coming from the playlist SHALL be compared against the playlist's contents. A track the user added by Spotify link, typed by hand, or that was adopted from a staged file SHALL never be reported as having left the playlist and SHALL never be modified by a refresh. Tracks that existed before this capability SHALL be classified so that no existing track is wrongly reported as having left the playlist.

#### Scenario: A track added by link is not in the playlist

- **WHEN** an event contains a track the user added by pasting a Spotify link, and that track is not in the event's playlist, and the event is refreshed
- **THEN** the track is left untouched and is not reported as having left the playlist

#### Scenario: A manually typed track survives a refresh

- **WHEN** an event containing a manually typed track is refreshed
- **THEN** that track is left untouched

#### Scenario: Existing events after the capability is introduced

- **WHEN** an event that predates this capability is refreshed for the first time
- **THEN** its tracks that came from the playlist are reconciled and its other tracks are left untouched

### Requirement: Tracks added to the playlist are imported into the event

A refresh SHALL add to the event every playlist track that the event does not already carry, with the same metadata mapping used when the event was created from that playlist. On an event that has already been applied, an added track SHALL be flagged as a pending addition so that it is counted in the event's outstanding changes and written by the existing re-apply operation. Added tracks SHALL be matched against the Rekordbox collection as part of the refresh, so they land matched rather than missing whenever possible.

#### Scenario: New track in the playlist

- **WHEN** a track has been added to the playlist since the event last saw it and the event is refreshed
- **THEN** the event gains that track, recorded as coming from the playlist

#### Scenario: New track on an already-applied event

- **WHEN** a track is imported by a refresh of an event that has already been applied
- **THEN** the track counts among the event's pending changes and the existing re-apply operation writes it to Rekordbox

#### Scenario: Imported track present in the collection

- **WHEN** an imported track matches an entry of the Rekordbox collection
- **THEN** it is recorded as matched to that entry rather than left missing

#### Scenario: The playlist has not changed

- **WHEN** an event is refreshed and the playlist contains exactly the tracks the event already carries
- **THEN** no track is added, none is reported as having left, and the result reports that nothing changed

### Requirement: Tracks that left the playlist are signalled, not acted on

A refresh SHALL report every playlist-sourced track of the event that is no longer in the playlist by moving it to a distinct `removed_upstream` status that records the status it held before. This status SHALL NOT cause any write to the Rekordbox database, SHALL NOT count among the event's outstanding work, and SHALL NOT change the event's own applied status. A track in this status SHALL remain visible in the event with its previous state intact.

#### Scenario: Track removed from the playlist

- **WHEN** a track that the event carries from the playlist is no longer in that playlist and the event is refreshed
- **THEN** the track moves to `removed_upstream`, keeps a record of its previous status, and stays visible in the event

#### Scenario: Signalling does not touch Rekordbox

- **WHEN** a refresh signals one or more departed tracks
- **THEN** the Rekordbox database is not modified, the event's tag and playlist are untouched, and no file is deleted

#### Scenario: An applied event whose only change is a departure

- **WHEN** an event that was fully applied is refreshed and one of its tracks has left the playlist
- **THEN** the event's applied status is unchanged and its count of pending changes stays at zero

#### Scenario: A departed track put back on the playlist

- **WHEN** a track reported as having left the playlist is added back to it and the event is refreshed
- **THEN** the departure signal is cleared and the track returns to the status it held before the signal, without the user having to act on it

#### Scenario: An already-signalled or rejected track

- **WHEN** a refresh runs over a track that is already reported as departed, or that the user rejected
- **THEN** it is not signalled a second time and the record of its previous status is left intact

### Requirement: A departure signal can be dismissed

The user SHALL be able to keep a track that has left the playlist. Keeping it SHALL restore the status the track held before the signal and SHALL prevent the track from being signalled again by a later refresh, while leaving it otherwise unchanged.

#### Scenario: Keeping a departed track

- **WHEN** the user keeps a track that a refresh reported as having left the playlist
- **THEN** the track returns to the status it held before the signal

#### Scenario: A kept track survives later refreshes

- **WHEN** an event is refreshed again after the user kept a departed track
- **THEN** that track is not reported as having left the playlist a second time

### Requirement: Metadata of surviving tracks is refreshed

For a playlist-sourced track that is still in the playlist, a refresh SHALL update its title, artist, duration and ISRC from the playlist's current metadata. The track's status, its link to a Rekordbox entry, and its staged file SHALL NOT be changed by this update.

#### Scenario: Track metadata changed on Spotify

- **WHEN** a track still present in the playlist has different metadata than the event recorded and the event is refreshed
- **THEN** the event's copy of that metadata is updated

#### Scenario: An applied track keeps its link

- **WHEN** an applied track's metadata is refreshed
- **THEN** the track stays applied and keeps its link to the Rekordbox entry and its staged file
