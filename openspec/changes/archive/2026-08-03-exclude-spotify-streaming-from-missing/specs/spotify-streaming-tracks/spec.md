## Purpose

Rekordbox streaming tracks (Spotify references, no local audio file) are recognized as such throughout the sidecar: they never appear as missing files, never enter file-centric flows (acquisition, relink, dedup, match candidates), and their obfuscated Rekordbox metadata is never surfaced raw.

## ADDED Requirements

### Requirement: Streaming rows are identified in the collection snapshot
The Rekordbox snapshot SHALL identify content rows whose stored path is a Spotify streaming reference (`spotify:track:<id>`) and SHALL expose the extracted Spotify track id on the row. Such rows SHALL NOT be reported as having a missing file, and SHALL carry no resolved local path.

#### Scenario: Streaming row in the collection
- **WHEN** the snapshot loads a djmdContent row whose FolderPath is `spotify:track:4uLU6hMCjMI75M1A2tKUQC`
- **THEN** the row carries `spotify_track_id = "4uLU6hMCjMI75M1A2tKUQC"` and is not marked file-missing

#### Scenario: Local file row is unaffected
- **WHEN** the snapshot loads a row whose FolderPath is a regular file path that does not exist on disk
- **THEN** the row is marked file-missing exactly as before, with no Spotify track id

### Requirement: Obfuscated Rekordbox metadata is never surfaced
Title or artist values obfuscated by Rekordbox (values starting with `$A`) SHALL be normalized to null in the snapshot rather than exposed to any consumer or displayed to the user.

#### Scenario: Obfuscated title on a streaming row
- **WHEN** a streaming row's Title is `$A7:v1:abcdef…`
- **THEN** every API response carrying that row reports `title = null`, never the `$A…` string

### Requirement: Streaming tracks never appear as missing
The missing-tracks collection scope SHALL exclude streaming rows: they SHALL NOT appear in the collection missing list, SHALL NOT count toward missing totals, and the collection-scope resolution endpoints (acquisition lookup, missing-remove) SHALL treat a streaming content id as not found among missing entries.

#### Scenario: Missing center collection list
- **WHEN** the collection contains 3 local rows with absent files and 5 streaming rows
- **THEN** `/api/missing/collection` returns exactly the 3 local entries, and the UI missing count reflects 3

#### Scenario: Acquisition attempt on a streaming row
- **WHEN** a collection-scope acquisition or missing-remove request references a streaming row's content id
- **THEN** the request is rejected as not found among missing entries and nothing is mutated

### Requirement: Streaming rows are excluded from file-centric analysis
Duplicate detection and library-sync match candidates SHALL NOT include streaming rows: a streaming reference SHALL never be selected as the local match for a synced Spotify track, and SHALL never be a member of a duplicate group.

#### Scenario: Sync against a collection containing the streaming twin
- **WHEN** a synced Spotify playlist track's only ISRC/title counterpart in the collection is a streaming row
- **THEN** the track is matched as missing (no local file), not as matched to the streaming row

#### Scenario: Duplicate detection over a mixed collection
- **WHEN** duplicate groups are computed over a collection containing streaming rows
- **THEN** no group contains a streaming row
