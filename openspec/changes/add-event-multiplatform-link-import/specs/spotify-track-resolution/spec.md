## MODIFIED Requirements

### Requirement: Single resolution ladder shared by all consumers

The sidecar SHALL provide one reusable resolution function mapping Spotify track ids to metadata including title and artist, and duration and ISRC when returned by Spotify. With a connected Spotify session it SHALL use Web API endpoints supported by the account's access mode; it SHALL support individual track requests when batch retrieval is unavailable. Resolution SHALL bound request concurrency and work per operation, honor rate-limit retry guidance without blocking unrelated requests, and preserve already resolved results when later requests fail. Without a session, or when API resolution fails, it SHALL fall back to the anonymous oEmbed endpoint for unresolved ids (title only, bounded batch). Resolution SHALL be best-effort: failures leave ids unresolved for a later retry and never raise to the caller. These changes SHALL NOT alter the existing Spotify-to-Deezer acquisition policy.

#### Scenario: Connected session
- **WHEN** multiple distinct ids need resolution and a Spotify session exists
- **THEN** the resolver uses supported authenticated endpoints with bounded concurrency and returns the metadata available for the found ids

#### Scenario: Batch retrieval unavailable
- **WHEN** Spotify's access mode does not support the multiple-track endpoint
- **THEN** authenticated individual track resolution remains available instead of losing artist and ISRC solely because batch retrieval is unavailable

#### Scenario: No session
- **WHEN** ids need resolution and no Spotify session exists
- **THEN** the resolver returns titles from the anonymous oEmbed endpoint for a bounded batch, leaving other ids unresolved for a later refresh

#### Scenario: Partial authenticated failure
- **WHEN** some authenticated requests succeed and a later request fails or is rate-limited
- **THEN** successful metadata is retained, retries respect the provider's guidance, and fallback work remains bounded

#### Scenario: Offline
- **WHEN** the network is unavailable
- **THEN** the resolver returns what it has, possibly nothing, without raising, and the caller's flow continues
