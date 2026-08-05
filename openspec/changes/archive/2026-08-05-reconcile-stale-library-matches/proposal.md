## Why

Library tracks can remain marked as matched or imported after their linked Rekordbox content has been soft-deleted. Spotify's `snapshot_id` only versions the playlist, so treating an unchanged Spotify snapshot as proof that the combined Spotify-to-Rekordbox result is unchanged leaves stale links hidden from the Library review and Missing surfaces.

## What Changes

- Reconcile persisted `matched` and `imported` library links against the current active, local-file Rekordbox snapshot on every source synchronization.
- Preserve valid links and explicit user decisions without running the matcher again.
- Re-run the existing ISRC-first/fuzzy matcher only for links whose Rekordbox content is no longer an eligible candidate, then move the row to `matched`, `conflict`, or `missing` from the new result.
- Perform link reconciliation even when the Spotify playlist snapshot is unchanged, while retaining the snapshot optimization for playlist item fetching and diffing.
- Record synchronization results accurately when reconciliation changes rows, without introducing a new UI workflow or a database migration.

## Capabilities

### New Capabilities

- `reconcile-stale-library-matches`: Keeps persisted Spotify-to-Rekordbox library links consistent with the current active local Rekordbox collection.

### Modified Capabilities

None.

## Impact

- Affects the library synchronization and pure diff/matching orchestration in `sidecar/src/syncbox/library_service.py` and `sidecar/src/syncbox/sync.py`.
- Extends unit and service coverage in `sidecar/tests/test_sync.py` and `sidecar/tests/test_library_service.py`, including unchanged-Spotify-snapshot and soft-deleted-Rekordbox-content cases.
- Reuses the existing Rekordbox snapshot cache and matching thresholds; no API removal, UI change, new dependency, or schema migration is expected.
