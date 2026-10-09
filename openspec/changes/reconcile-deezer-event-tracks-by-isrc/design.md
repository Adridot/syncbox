## Context

See proposal.md - Why. The relevant code today:

- `events_service.match_event_tracks` short-circuits exact-source rows into `source_identity.known_file`, which only accepts an `acquisition_jobs` row with the same `provider` + `effective_source_item_id`, the same published path and an unchanged SHA-256. `effective_source_item_id` was added by migration 0011 with no backfill, and the Spotify-to-ISRC path records whatever Deezer ID streamrip picked, so the proof rarely exists.
- `events_service.apply_event` demotes an exact-source `matched` row to `missing` when `source_identity.eligible_file` finds no provenance for the content's file. An ISRC match would be undone here.
- `matching.match` already does ISRC-first with the guarded duration/title collision policy and returns `method == "isrc"`; fuzzy follows only when ISRC fails.
- Deezer link previews carry the public-API ISRC into `event_tracks.isrc`; `rb.py` exposes the collection's ISRC column; `rb_write.add_content` tags ISRC on files it adds.
- `acquisition_migration` is the precedent for a previewed repair of existing data: `build_plan` returns a JSON plan with file states and the Rekordbox fingerprint, `execute` requires the identical plan, runs inside `mutate()` and deletes trash-first via `platform_os.delete_file` with the consent contract. `event_remove` already holds the primitives to untag, soft-delete and classify a content's other usages.
- `event_tracks` has no match-method column; `ready` rows are never re-run through the matcher.

## Goals / Non-Goals

**Goals:** restore recognition of ISRC-identical recordings for exact-source rows without reopening fuzzy matching; repair the duplicates 0.9.0 already produced with the same safety envelope as the other repairs; make the ISRC assumption verifiable on production before anything is executed.

**Non-Goals:** backfilling provenance for old jobs (nothing to compare against), changing library/collection matching, scoring staged files by metadata for exact-source rows, deduplicating contents that Syncbox did not create, a generic "rematch ready rows" feature.

## Decisions

### 1. ISRC equality is an identity proof, second to provenance

In the exact-source branch of `match_event_tracks`: provenance first (unchanged); when it yields neither a collection candidate nor a staged path, run `matching.match` over the same candidate list and accept the result only when `method == "isrc"`; any other result leaves the row `missing`. This keeps the duration/title collision guard and the configured `isrc_collision_policy`, and keeps a provenance `ready` row as `ready` (that row is the reconciliation's job, not the matcher's).

Alternatives: treating Deezer like Spotify (full fuzzy) contradicts the remix/original decision; storing a match method column to distinguish ISRC matches adds schema for something the apply guard can re-verify statelessly (decision 2).

### 2. Apply re-verifies the ISRC instead of demanding provenance

`apply_event` keeps demoting exact-source `matched` rows that fail `eligible_file`, but first accepts the row when the current snapshot row for `content_id` has a normalized ISRC equal to the track's. The comparison is the matcher's own `_isrc` normalization, so match and apply agree. No new column, no new state.

### 3. Reconciliation is a sibling of the acquisition storage migration

New module `event_source_reconcile.py` with `build_plan(conn, storage_root, db_path)` and `execute(conn, db_path, backups_root, cache, storage_root, plan, *, app_db_path, retention, consent_to_permanent_delete)`, exposed as `GET/POST /api/events/source-reconciliation` through the same handler shape as `acquisition_storage_migration`. The plan carries `plan_version`, the Rekordbox fingerprint, each item's row id, status, ISRC, candidate content id, file state (path, size, mtime, SHA-256) and action, plus `skipped` entries with a reason and the `isrc_coverage` block. Execution rebuilds the plan and refuses on any difference (same stale-plan rule as the migration and track removal).

Items are classified per row:

| Row | Condition | Action |
| --- | --- | --- |
| `ready`, exact-source, ISRC | staged file inside the event staging dir, regular file; exactly one active local content with equal ISRC (guard passes) | `rematch`: trash the file first, then app DB only - status `matched`, `content_id`, confidence 100, `staging_file_path` NULL |
| `applied`, exact-source, ISRC | its content's file is the row's staged download inside the event staging dir; exactly one other active local content with equal ISRC; the duplicate carries no other tag, no other playlist membership and no other event row | `replace`: inside `mutate()` tag the original with the event tag, untag the duplicate, soft-delete the duplicate; then app DB `content_id` = original; then trash the file |
| any | zero candidates, more than one candidate, guard rejects, file missing/symlink/outside staging, duplicate used elsewhere, no ISRC | `skipped` with reason |
| `applied`, exact-source, ISRC | earlier `replace` repaired the row but its download is still on disk and referenced by no active content | `cleanup`: trash the file, clear `staging_file_path` |

Candidate selection for the reconciliation is stricter than the matcher: more than one ISRC-equal content is `ambiguous` and skipped, because this path deletes files. The matcher keeps its first-candidate rule.

Alternatives: a startup auto-repair was rejected because Rekordbox writes and deletions in this project are always previewed and consented; composing `event_remove.remove_tracks` + re-add was rejected because it leaves a `removed` row per track and runs two mutations per event instead of one.

### 4. Order of effects inside execute

Three actions, each with its own order:

- `rematch` (no Rekordbox write): trash the download first, then set the row `matched`. A refused trash leaves row and file unchanged, so the spec's "row and file left unchanged" scenario holds and nothing can flip the row back through provenance while the file still exists.
- `replace`: one `mutate()` for all `replace` items of all events (a single backup is the pre-reconciliation restore point and a long run never rotates it out of the retention), then the application-DB transaction repointing each row, then trash. The row keeps its `staging_file_path` until the trash succeeds, so a kept file stays referenced and is never re-adopted.
- `cleanup`: an `applied` row repaired by an earlier `replace` whose download is still on disk and referenced by no active content. Trash, then clear `staging_file_path`.

`PermanentDeleteConsentRequired` is raised (HTTP 428) only while nothing has changed in the run, so the client's consent loop replays the identical plan. After a change, a refused trash is reported in `cleanup_pending` with `consent_required`, and the next preview offers the kept file as a `cleanup` item. The acquisition job rows keep their `published_path`; `eligible_file` already ignores a path that no longer exists.

### 5. ISRC coverage is computed in `build_plan`, not a separate script

`isrc_coverage` = counts of exact-source rows with/without ISRC, ISRC rows with a candidate, the list of active contents with an empty ISRC whose file is the published or output path of a Deezer acquisition job (so files the owner dropped into a staging folder never trip the stop check), and the count of ISRCs containing non-alphanumerics. It costs one pass over data the plan already reads. The owner runs the preview against production and records the figures in `verification.md` before executing; a non-empty "without ISRC" list is a stop signal to investigate the tagging, not a reason to loosen matching.

### 6. UI: one block in Health > Backups

Same component pattern as the storage migration block: load the preview, show item count per action and the coverage figures, a button to execute with the plan, consent prompt on `PermanentDeleteConsentRequired`, result toast. No event-screen changes.

## Risks / Trade-offs

- [Deezer downloads lack an ISRC tag in Rekordbox] → coverage report makes it visible before execution; such rows simply stay as today.
- [Collection already holds two originals with one ISRC] → reconciliation skips as ambiguous; the Duplicates screen is the tool for that.
- [ISRC formatting differs (dashes) between Deezer API and Rekordbox tags] → the coverage report also counts ISRCs containing non-alphanumerics; if non-zero, extend `matching._isrc` to strip them in a follow-up.
- [Plan drifts while the user reads it] → fingerprint + file-state equality refuses execution, same as the other repairs.
- [Duplicate content soft-deleted while Rekordbox is open] → `mutate()` already enforces the closed-Rekordbox guard used by every write.

## Migration Plan

1. Ship matcher and apply changes; new imports stop downloading ISRC-known recordings immediately.
2. The owner opens Health > Backups on production, reads the preview and the coverage figures, and executes once satisfied. Backups are taken by `mutate()`; trashed files are recoverable from the OS trash.
3. Rollback: revert the build; reconciled rows remain valid `matched`/`applied` rows for the old code, since neither state depends on the new logic.

## Open Questions

- Whether YouTube/SoundCloud rows should ever carry an ISRC is moot for now: yt-dlp does not supply one, so the rule applies to Deezer in practice without naming the provider.
