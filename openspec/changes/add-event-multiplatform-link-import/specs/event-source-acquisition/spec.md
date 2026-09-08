## Purpose

Acquire the exact linked event item from supported direct sources while preserving Spotify's existing Deezer association and the application's durable staging and guarded import behavior.

## ADDED Requirements

### Requirement: Direct links retain their exact provider item

Deezer, YouTube, and SoundCloud link additions SHALL acquire the identified provider item. The system SHALL NOT substitute another item, another provider, or an approximate local/staged match automatically. This constraint SHALL apply to initial matching, later rematching, staged-file claiming, retries, and manual acquisition requests. An unavailable exact item SHALL remain unresolved with an explanation. Existing files SHALL only be reused automatically with recorded provenance for the same provider item and a valid file; other local associations SHALL require explicit user selection.

#### Scenario: Remix resembles a local original
- **WHEN** a linked remix resembles a local original by title, artist, duration, or ISRC
- **THEN** the original is not automatically selected and the remix retains its exact-source acquisition target

#### Scenario: Exact Deezer item is unavailable
- **WHEN** a linked Deezer item is unavailable but another item has the same ISRC
- **THEN** acquisition fails for the linked item without automatically downloading the other item

#### Scenario: Subsequent rematch or staged-file scan
- **WHEN** a linked SoundCloud item is still missing and a later matching or staging scan finds an approximate candidate
- **THEN** the scan does not silently associate that file with the linked item

### Requirement: Spotify retains its current Deezer association

Spotify additions SHALL retain the current local matching and Deezer acquisition behavior, including automatic ISRC association and explicit manual Deezer selection when needed. This exception SHALL apply to individual tracks and tracks expanded from albums or playlists. No new recording-equivalence approval step SHALL be imposed on existing Spotify acquisition. The original Spotify identity and the actual acquired Deezer identity SHALL remain distinguishable.

#### Scenario: Spotify track with an ISRC
- **WHEN** an imported Spotify track is missing locally and has an ISRC
- **THEN** it uses the existing Deezer association and acquisition path

#### Scenario: Spotify track without an ISRC
- **WHEN** an imported Spotify track has no usable ISRC
- **THEN** the existing manual Deezer selection remains available and automatic acquisition does not invent an association

### Requirement: Acquisition readiness is provider-specific

Each source SHALL report whether its required optional component and credentials are available. YouTube and publicly accessible SoundCloud acquisition SHALL NOT require Deezer enablement or credentials. Disabling or failing one provider SHALL NOT disable unrelated providers. The base application SHALL remain functional without any optional acquisition component, and components SHALL only be installed through explicit enablement.

#### Scenario: YouTube with Deezer disabled
- **WHEN** the web-audio component is enabled and installed but Deezer is disabled
- **THEN** an accessible YouTube item can be acquired without a Deezer credential prompt

#### Scenario: No optional components
- **WHEN** no acquisition component is installed
- **THEN** existing local event workflows still work and unsupported acquisition attempts explain the missing prerequisite

### Requirement: Jobs preserve source identity across recovery

Each queued job SHALL persist the acquisition provider and immutable item selector needed for its intended source. Existing Deezer jobs SHALL remain readable and resumable. Active-job reuse, retries, and published-output recovery SHALL verify the same owner and source intent before reusing work. Batch responses SHALL identify the owning event row explicitly. A source change SHALL NOT cause a job for an earlier item to be reused.

#### Scenario: Restart during publication
- **WHEN** a job has published its exact-source file and the process restarts before finalizing the event row
- **THEN** recovery verifies the recorded output and completes the row without redownloading

#### Scenario: Different selector on the same row
- **WHEN** a request supplies a different source selector for an existing active job
- **THEN** the request cannot silently reuse or mutate that job

### Requirement: Downloaded files are validated and quality is described accurately

An event row SHALL become ready only after a regular audio file is validated inside its job workspace and published through the existing staging path. The result SHALL identify the actual final file after processing. Output SHALL be compatible with the supported Rekordbox import formats. Available source quality and measured output properties SHALL be distinguishable; transcoding SHALL NOT be described as increased source quality. Validation SHALL handle legitimate short web-audio tracks, absent artwork, unavailable metadata, and incomplete downloads without applying Deezer-specific preview assumptions to every provider.

#### Scenario: Valid short track
- **WHEN** a complete 20-second SoundCloud item is acquired
- **THEN** its short duration alone does not make acquisition fail

#### Scenario: Lossy source is converted
- **WHEN** a lossy source is converted into a supported output format
- **THEN** the UI does not claim that a higher output bitrate makes the source higher quality

#### Scenario: Invalid output
- **WHEN** a component reports a missing file, non-audio output, a path outside its workspace, or an incomplete download
- **THEN** the row does not become ready and the failure is reported for that item

### Requirement: External resolution and processing are bounded

Accepted links SHALL be restricted to supported providers and resource types, including validated share redirects. Local paths, private-network targets, unsupported redirects, and arbitrary extractor commands SHALL be rejected. Provider metadata and child entries SHALL remain untrusted inputs. Resolution and media processing SHALL have bounded time, pagination, resource usage, and cancellation behavior. Secrets SHALL NOT appear in URLs, process arguments, durable import manifests, or logs.

#### Scenario: Share link redirects outside permitted destinations
- **WHEN** a submitted share link redirects to an unsupported or private-network destination
- **THEN** resolution is refused without fetching the disallowed destination

#### Scenario: Provider or component stalls
- **WHEN** a resolution or media-processing operation exceeds its configured bound
- **THEN** the operation terminates with an actionable failure and unrelated application requests remain responsive
