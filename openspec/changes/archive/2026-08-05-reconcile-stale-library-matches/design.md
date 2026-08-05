## Context

See `proposal.md` for the defect and motivation. Source synchronization currently returns early when Spotify's `snapshot_id` is unchanged, before consulting the Rekordbox snapshot. When Spotify has changed, the pure diff also carries `matched` and `imported` rows forward without checking whether their stored `content_id` is still active.

The existing Rekordbox `SnapshotCache` already fingerprints `master.db` and reloads active content after Rekordbox changes. Its rows contain the eligible content identifiers and matching metadata needed here. Persisted library rows already retain Spotify title, artist, duration, and ISRC, so a stale link can be reconsidered without fetching the playlist items again. The sync path already excludes Rekordbox Spotify streaming rows from match candidates.

## Goals / Non-Goals

**Goals:**

- Make a user-triggered source synchronization reconcile both Spotify playlist state and persisted Rekordbox link state.
- Preserve valid automatic and manual links exactly as they are.
- Reuse the existing matcher and settings only when a linked Rekordbox target has become ineligible.
- Keep the unchanged-Spotify fast path free of playlist pagination and unnecessary app-database writes.
- Keep reconciliation pure enough for direct status-transition tests.

**Non-Goals:**

- Add background monitoring or trigger synchronization automatically when Rekordbox changes.
- Couple event deletion directly to library rows; reconciliation must also cover changes made outside Syncbox.
- Reconsider valid links because their metadata changed, or rematch unrelated lifecycle states.
- Treat an active Rekordbox row whose audio file is missing as a stale library association; the collection Missing workflow owns physical-file availability.
- Change the UI, matching algorithm, thresholds, database schema, or Rekordbox data.

## Decisions

### 1. Reconcile candidate identity before invoking the matcher

Add a pure reconciliation step that receives persisted/diffed library rows plus the already filtered local Rekordbox candidates. It builds an active candidate-id lookup and examines only `matched` and `imported` rows with a stored content identifier.

- If the identifier is present, preserve the row without recalculating confidence or reconsidering a manual choice.
- If it is absent, run the existing matcher with the row's fresh Spotify metadata when available, otherwise its persisted metadata, and map the result through the existing library vocabulary (`matched`, `conflict`, `missing`).
- Return both the reconciled rows and an explicit changed-row count so orchestration can avoid writes and report the run accurately.

This is preferred over rematching every row because a full rematch could silently replace valid manual decisions and adds work proportional to every source track. It is preferred over checking only soft-deletion flags because the snapshot already defines the complete eligible candidate set, including the exclusion of streaming references.

### 2. Run reconciliation on both synchronization paths

For a changed Spotify snapshot, compose the operations as:

1. Diff Spotify items against persisted rows.
2. Reconcile carried `matched` and `imported` links against current candidates.
3. Match fresh `new` rows through the existing path.
4. Persist the complete source result once.

For an unchanged Spotify snapshot, do not paginate playlist items or run the playlist diff. Load the persisted source rows and current cached Rekordbox candidates, run only link reconciliation, and persist only if at least one row changed.

This keeps Spotify's documented `snapshot_id` optimization within its proper boundary: it versions the playlist, while the Rekordbox snapshot independently supplies current local state. Removing the early return entirely was rejected because it would download and diff unchanged playlists unnecessarily and increase Spotify rate-limit pressure.

### 3. Preserve the existing API shape and make skip reporting truthful

No endpoint or database column is added. When Spotify is unchanged and reconciliation changes no rows, keep the existing `skipped: true` behavior. When reconciliation changes rows, return `skipped: false` and add reconciliation/outcome counts to the existing additive `stats` object recorded in `sync_runs`. Changed-Spotify runs retain their existing total/status counts and may add the reconciliation count.

This avoids a versioned API change while ensuring callers and history do not describe a state-changing run as skipped.

### 4. Repair existing stale data lazily and safely

There is no startup migration or bulk mutation. Existing stale rows are repaired the next time their source is synchronized. Reconciliation writes only the Syncbox application database; it never writes to Rekordbox, and a no-change pass performs no library-row replacement.

An event-deletion cascade was rejected as the primary fix because it would miss content deleted directly in Rekordbox or by another process and would couple two otherwise independent workflows.

## Risks / Trade-offs

- **[Extra Rekordbox check on unchanged Spotify sources]** → Use the fingerprinted snapshot cache and O(1) content-id membership checks; invoke the O(candidate count) matcher only for stale links.
- **[A deleted manual target may resolve to a different automatic candidate]** → Preserve manual links while their target exists; once it is gone, use the same visible conflict/missing outcomes and configured policy as every other match.
- **[A stale imported row loses its final-state label]** → Transition it to the truthful current result; an alternative becomes `matched` so it can be reviewed/applied, while no alternative becomes `missing`.
- **[Concurrent Rekordbox changes during snapshot loading]** → Retain the existing fingerprint retry and stale-snapshot safeguards; reconciliation adds no new direct database read path.
- **[Rollback after rows were reconciled]** → No destructive or Rekordbox-side migration exists. Rolling back the application code leaves already corrected Syncbox statuses valid, and a later synchronization can process them under the earlier behavior.

## Migration Plan

1. Ship the pure reconciliation logic and regression tests.
2. Enable it in both changed- and unchanged-Spotify synchronization paths.
3. Verify that an existing stale link is repaired by a normal source synchronization and that an unchanged source with valid links remains a no-write skip.
4. Roll back by reverting the code if necessary; no schema or data rollback step is required.
