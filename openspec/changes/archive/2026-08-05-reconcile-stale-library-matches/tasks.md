## 1. Pure Link Reconciliation

- [x] 1.1 Add a pure library-link reconciliation helper that preserves eligible `matched`/`imported` targets, rematches only stale targets with stored or fresh Spotify metadata, and returns a changed-row count.
- [x] 1.2 Compose reconciliation with the existing Spotify diff and fresh-row matching pipeline while leaving `ready`, `ignored`, and `removed_from_source` states unchanged.
- [x] 1.3 Add focused unit tests for valid automatic/manual links, stale links resolving to matched/conflict/missing outcomes, streaming-only targets, and unrelated lifecycle states.

## 2. Synchronization Orchestration

- [x] 2.1 Update changed-snapshot synchronization to reconcile carried links against the filtered active local Rekordbox candidates before persisting the source result.
- [x] 2.2 Replace the unchanged-snapshot early return with a reconciliation-only fast path that avoids Spotify item pagination and app-database row writes when nothing changed.
- [x] 2.3 Make synchronization responses and `sync_runs` statistics distinguish a true no-change skip from a run that repaired stale links, without changing endpoint or database schemas.
- [x] 2.4 Update library synchronization comments and contracts so Spotify snapshot optimization and Rekordbox reconciliation responsibilities remain explicit.

## 3. Regression Coverage and Verification

- [x] 3.1 Add service tests proving that an unchanged Spotify snapshot repairs a soft-deleted Rekordbox link, preserves a valid link without rewriting it, and records truthful run history without fetching another Spotify page.
- [x] 3.2 Add a changed-Spotify regression test covering a fresh playlist diff and a stale carried link in the same synchronization.
- [x] 3.3 Run the focused matching, sync, library-service, and API test suites, then run the complete sidecar test suite and resolve any regressions.
- [x] 3.4 Validate the OpenSpec change strictly after implementation and confirm no UI, schema, dependency, or Rekordbox-write changes were introduced.
