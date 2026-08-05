# reconcile-stale-library-matches Specification

## Purpose

Keep persisted Spotify-to-Rekordbox library associations aligned with the current active local Rekordbox collection without disturbing links that remain valid.

## Requirements

### Requirement: Linked library rows are revalidated during synchronization

The system SHALL validate every `matched` and `imported` library row that references Rekordbox content against the current eligible Rekordbox snapshot whenever its source is synchronized. An eligible target is active Rekordbox content backed by a local-file reference; a Spotify streaming reference SHALL NOT validate a library link.

#### Scenario: Existing target remains eligible

- **WHEN** a source is synchronized and a `matched` or `imported` row still references eligible Rekordbox content
- **THEN** the system preserves its status, content identifier, match metadata, and user-assigned tags without matching it again

#### Scenario: Target is no longer active

- **WHEN** a source is synchronized and the Rekordbox content referenced by a `matched` or `imported` row is absent from the eligible snapshot
- **THEN** the system treats the persisted association as stale and reconciles that row against the current eligible candidates

#### Scenario: Target is only a streaming reference

- **WHEN** a persisted library link resolves only to a Rekordbox Spotify streaming row
- **THEN** the system treats the association as stale because the streaming row does not represent a local library file

### Requirement: Stale links use the existing matching policy

The system SHALL re-run the configured ISRC-first and fuzzy matching policy only for stale linked rows, using their stored Spotify title, artist, duration, and ISRC metadata and the current matching thresholds.

#### Scenario: An alternative local candidate matches

- **WHEN** a stale row has an eligible alternative that satisfies the configured matching policy
- **THEN** the system sets the row to `matched` with the alternative content identifier, method, and confidence

#### Scenario: Alternative candidates are ambiguous

- **WHEN** the best eligible alternatives for a stale row fall within the configured ambiguity margin
- **THEN** the system sets the row to `conflict` using the existing conflict representation

#### Scenario: No alternative candidate matches

- **WHEN** no eligible candidate for a stale row reaches the configured matching threshold
- **THEN** the system sets the row to `missing` and clears its stale Rekordbox content identifier and match method

### Requirement: Spotify snapshot optimization does not suppress Rekordbox reconciliation

The system SHALL continue using Spotify's playlist snapshot identifier to avoid unnecessary playlist item pagination and diffing, but an unchanged Spotify snapshot SHALL NOT skip validation of persisted Rekordbox links.

#### Scenario: Neither external state changed

- **WHEN** the Spotify snapshot is unchanged and every persisted link remains eligible
- **THEN** the system leaves library rows untouched and records the synchronization as skipped

#### Scenario: Rekordbox changed while Spotify did not

- **WHEN** the Spotify snapshot is unchanged but one or more persisted Rekordbox links are stale
- **THEN** the system reconciles and persists the affected rows without fetching additional Spotify playlist item pages
- **AND** the synchronization result and history indicate that row reconciliation occurred rather than reporting the entire run as skipped

#### Scenario: Spotify and Rekordbox both changed

- **WHEN** the Spotify snapshot changed and one or more previously linked rows became stale
- **THEN** the system performs the normal Spotify playlist diff and also reconciles the stale persisted links in the same synchronization

### Requirement: Unrelated lifecycle states are preserved

Link reconciliation SHALL NOT alter rows whose lifecycle does not represent a persisted Rekordbox match, including `ready`, `ignored`, and `removed_from_source` rows.

#### Scenario: Source contains non-linked lifecycle rows

- **WHEN** a source synchronization evaluates rows in `ready`, `ignored`, or `removed_from_source` state
- **THEN** link reconciliation leaves those rows unchanged
