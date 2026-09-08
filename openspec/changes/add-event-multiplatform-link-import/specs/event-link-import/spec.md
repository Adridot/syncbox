## Purpose

Allow users to add linked tracks, albums, and playlists to an existing event while retaining source identity and keeping collection imports reviewable, repeatable, and independent of playlist synchronization.

## ADDED Requirements

### Requirement: Supported music links are recognized consistently

The system SHALL accept Spotify and Deezer track, album, and playlist links; YouTube video and playlist links, including YouTube Music album and playlist representations; and SoundCloud track, album, and playlist/set links. Supported share links SHALL resolve to a canonical provider identity. Unsupported resource types SHALL return an explanatory error. A video link carrying playlist context SHALL offer an explicit choice between the video and the playlist before collection expansion.

#### Scenario: Shared track link
- **WHEN** a user submits a supported short share link or a canonical link with tracking parameters
- **THEN** the system identifies the same provider item and displays its canonical source

#### Scenario: Video within a playlist
- **WHEN** a YouTube link identifies both a video and a playlist
- **THEN** the user chooses whether to import the video or preview the playlist

#### Scenario: Unsupported resource
- **WHEN** a user submits an artist page, channel, unsupported website, malformed link, or unsupported live stream
- **THEN** the system explains that the resource cannot be imported and adds no event tracks

### Requirement: Collection contents are previewed before addition

Album and playlist resolution SHALL run without blocking unrelated application requests. The preview SHALL show the collection identity, entries in source order, available metadata, already-present items, and unavailable entries disclosed by the provider. Users SHALL be able to select all importable entries or a subset before confirming. Preview resolution and dismissal SHALL NOT add event tracks, download audio, or write to Rekordbox. A failed or incomplete enumeration SHALL NOT be presented as a complete collection.

#### Scenario: Multi-page album or playlist
- **WHEN** the provider returns a collection over several pages
- **THEN** the preview includes all returned entries in source order before it is marked complete

#### Scenario: Unavailable entries
- **WHEN** a collection contains accessible tracks and entries identified as private, deleted, or unavailable
- **THEN** accessible tracks remain selectable and the unavailable entries or provider-reported omissions are explained without inventing metadata

#### Scenario: Enumeration fails midway
- **WHEN** fetching a later page fails or an import limit is reached
- **THEN** the preview reports the failure or limit and no apparently complete import is committed

#### Scenario: Dismissed preview
- **WHEN** a user dismisses an album preview
- **THEN** the event and its audio files remain unchanged

### Requirement: Confirmed imports use a stable snapshot

Confirmation SHALL add only the selected entries from the completed preview snapshot. Every newly added row SHALL retain its canonical item identity, collection provenance when applicable, and original position. Confirmation SHALL NOT silently re-enumerate a changed playlist. Added rows SHALL be classified as manual additions and SHALL NOT create or replace the event's synchronized playlist source. Source positions SHALL describe the imported snapshot without changing the event's existing playlist ordering contract.

#### Scenario: Playlist changes after preview
- **WHEN** a playlist changes between preview completion and confirmation
- **THEN** confirmation imports the selected preview entries and does not include newly appearing entries

#### Scenario: Import into a playlist-backed event
- **WHEN** a user manually imports a second playlist and later refreshes the event's original linked playlist
- **THEN** the manually imported rows retain their metadata and status and are not reported as upstream departures

### Requirement: Repeated additions are idempotent by source identity

Replaying the same confirmation SHALL return the original result without duplicate rows or downloads. Repeated occurrences of the same provider item within one import SHALL map to one active event row, retaining the first source position. A separate import of an item already active in the event SHALL report it as already present without changing its status, origin, or file. Identity-based deduplication SHALL NOT collapse different provider items based only on title, artist, or ISRC. Previously removed or ignored rows SHALL be identified separately and SHALL require an explicit restore or re-add choice rather than being silently resurrected.

#### Scenario: Lost confirmation response
- **WHEN** confirmation commits successfully but the client retries because its response was lost
- **THEN** the same committed result is returned and no additional rows or jobs are created

#### Scenario: Repeated track and distinct remix
- **WHEN** a playlist repeats one item and includes a separately identified remix with a similar title
- **THEN** the repeated item is added once and the remix remains a separate item

#### Scenario: Existing playlist-owned row
- **WHEN** a manual Spotify import contains an item already active from the event's linked playlist
- **THEN** the existing row is reported as already present and its playlist ownership is unchanged

### Requirement: Import progress and outcomes remain recoverable

The system SHALL expose resolution progress, the committed result, and per-track download outcomes after the UI is reopened. An interrupted uncommitted resolution SHALL be retryable without adding event rows. Confirmation SHALL add selected rows atomically. Acquisition SHALL use explicit per-track identities, continue after individual failures, and retry failed work without repeating successful publication.

#### Scenario: UI closes during import
- **WHEN** the UI closes after confirmation and then reopens
- **THEN** the committed additions and acquisition progress are recovered from persistent state

#### Scenario: One failed download
- **WHEN** one track in an imported album cannot be downloaded
- **THEN** successful tracks remain ready and the failed track has an individual retryable outcome

### Requirement: Imports preserve existing event lifecycle rules

Adding linked tracks SHALL remain possible on pending, applied, and partially applied events. New rows on an already applied event SHALL count as pending additions and use the existing guarded reapply operation. Import and acquisition SHALL NOT directly write event additions to Rekordbox. Deleted events and removed rows SHALL NOT be recreated by late resolution or download completion.

#### Scenario: Applied event receives an album
- **WHEN** an album is added to an applied event
- **THEN** new rows are pending additions and only become Rekordbox entries through the existing reapply flow

#### Scenario: Event deleted during preview resolution
- **WHEN** an event is deleted while a collection is being resolved
- **THEN** completion cannot create event rows or publish files for that event

### Requirement: Provider access failures are explicit

The system SHALL distinguish invalid links, inaccessible collections, authentication requirements, missing optional components, rate limits, and unavailable tracks. An inaccessible collection SHALL NOT be reported as empty. Spotify collection imports SHALL obey the connected account's API access; anonymous track fallback SHALL NOT be presented as anonymous album or playlist support.

#### Scenario: Spotify playlist content is not accessible
- **WHEN** Spotify returns playlist metadata without accessible items
- **THEN** the user sees an access explanation and no empty successful import

#### Scenario: Optional component is absent
- **WHEN** resolving a supported source requires an optional component that is not installed
- **THEN** the UI identifies the component needed and preserves the entered link
