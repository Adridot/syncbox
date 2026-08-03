# spotify-track-resolution

## Purpose

One shared Spotify track-metadata resolver turns Spotify track ids into title/artist for every consumer (Prestations history, event track addition), with a graceful anonymous fallback when no Spotify session exists.

## Requirements

### Requirement: Single resolution ladder shared by all consumers
The sidecar SHALL provide one reusable resolution function mapping Spotify track ids to `{title, artist}`. With a connected Spotify session it SHALL use the Web API tracks endpoint in batches of at most 50 ids (title AND artist); without a session, or when the API fails, it SHALL fall back to the anonymous oEmbed endpoint (title only, bounded batch). Resolution SHALL be best-effort: failures leave ids unresolved for a later retry and never raise to the caller.

#### Scenario: Connected session
- **WHEN** 120 distinct ids need resolution and a Spotify session exists
- **THEN** the resolver issues 3 batched API calls and returns title and artist for the found ids

#### Scenario: No session
- **WHEN** ids need resolution and no Spotify session exists
- **THEN** the resolver returns titles from the anonymous oEmbed endpoint (artist absent) for a bounded batch, leaving the rest for a later refresh

#### Scenario: Offline
- **WHEN** the network is unavailable
- **THEN** the resolver returns what it has (possibly nothing) without raising, and the caller's flow continues

### Requirement: Prestations history keeps its resolution behavior through the shared resolver
Play-history rows with a Spotify track id and incomplete title/artist SHALL be filled by the shared resolver on refresh, preserving today's behavior: API resolution completes artist-less oEmbed rows later, and unresolved rows retry on subsequent refreshes.

#### Scenario: History refresh with pending Spotify plays
- **WHEN** a history refresh runs with plays whose title or artist is null
- **THEN** resolved values are persisted to those plays exactly as before the refactor

### Requirement: Event track addition uses the shared resolver
Adding an event track by Spotify id SHALL obtain its metadata through the shared resolver, gaining the anonymous fallback: without a Spotify session, the track SHALL still be added with its oEmbed title instead of failing.

#### Scenario: Add by id without a session
- **WHEN** a user adds an event track by Spotify link while not connected to Spotify
- **THEN** the track is created with the anonymously resolved title (artist may be empty) instead of an error

### Requirement: One canonical streaming-prefix definition
The `spotify:track:` prefix and id extraction SHALL be defined exactly once in the sidecar and reused by every site that detects or parses streaming references.

#### Scenario: Prefix audit
- **WHEN** searching the sidecar source for the `spotify:track:` literal
- **THEN** it appears only at the single canonical definition site (tests excepted)
