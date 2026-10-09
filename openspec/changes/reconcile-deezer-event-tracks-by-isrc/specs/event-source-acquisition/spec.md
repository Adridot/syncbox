## MODIFIED Requirements

### Requirement: Direct links retain their exact provider item

Deezer, YouTube, and SoundCloud link additions SHALL acquire the identified provider item. The system SHALL NOT substitute another item, another provider, or an approximate local/staged match automatically. This constraint SHALL apply to initial matching, later rematching, staged-file claiming, retries, and manual acquisition requests. An unavailable exact item SHALL remain unresolved with an explanation.

An existing file SHALL be associated automatically only through one of two proofs of identity: recorded provenance for the same provider item and a valid file, or an active local collection content whose ISRC equals the linked item's ISRC and passes the existing ISRC duration guard. Recorded provenance takes precedence. Title, artist, or duration similarity, and staged-file metadata scoring, SHALL NOT associate a file with an exact-source track; other local associations SHALL require explicit user selection. When an ISRC association is applied to Rekordbox, the system SHALL re-verify that the matched content still carries the same ISRC and SHALL otherwise return the row to unresolved before writing.

#### Scenario: Remix resembles a local original
- **WHEN** a linked remix resembles a local original by title, artist, or duration and the two carry different ISRCs
- **THEN** the original is not automatically selected and the remix retains its exact-source acquisition target

#### Scenario: Linked item already in the collection under another acquisition
- **WHEN** a linked Deezer item carries an ISRC, no recorded provenance resolves it, and an active local collection content carries the same ISRC within the duration guard
- **THEN** the track is matched to that content with full confidence and no acquisition is offered

#### Scenario: Linked item without ISRC
- **WHEN** a linked item carries no ISRC and no recorded provenance resolves it
- **THEN** the track remains unresolved and no fuzzy or staged-file association is made

#### Scenario: ISRC association no longer valid at apply time
- **WHEN** an ISRC-matched exact-source row is applied and the matched content is no longer active or no longer carries that ISRC
- **THEN** the row is returned to unresolved before any Rekordbox write and the rest of the event applies normally

#### Scenario: Exact Deezer item is unavailable
- **WHEN** a linked Deezer item is unavailable but another item has the same ISRC
- **THEN** acquisition fails for the linked item without automatically downloading the other item

#### Scenario: Subsequent rematch or staged-file scan
- **WHEN** a linked SoundCloud item is still missing and a later matching or staging scan finds an approximate candidate
- **THEN** the scan does not silently associate that file with the linked item
