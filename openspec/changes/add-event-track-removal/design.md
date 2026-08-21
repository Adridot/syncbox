## Context

See proposal.md — Why.

`event_delete.py` is 1 299 lines backed by 1 005 lines of tests, and `delete_event` is not a function but a crash-recoverable state machine persisted across four columns added by migration 0004 (`delete_plan`, `delete_backup`, `delete_committed`, `delete_phase`). It moves through `planned → destinations_ready → committed → cleanup → DELETE FROM events`, and can resume mid-flight by re-deriving whether the Rekordbox commit already landed.

That machinery exists for one reason: **file migration**. When a staged file is retained by another tag, deletion copies it into `rekordbox/Collection/`, rewrites its `FolderPath` and its ANLZ paths, then commits Rekordbox, then removes the staging copy. The window between the copy and the commit is torn, and the state machine is what makes it recoverable.

Two other facts constrain the design. `events.delete_plan` is a single column — one plan in flight per event — so a removal plan stored there would collide with a pending deletion preview. And `_execute_rekordbox_plan` is already per-track except for its last two statements, `soft_delete_mytag` and `soft_delete_playlist`, which are the event-scoped tail.

## Goals / Non-Goals

**Goals:**

- Share the classification rule with full deletion so it cannot drift, without importing the deletion orchestration.
- Keep the destructive path auditable: one new small orchestration, not a second mode threaded through the existing one.
- Preserve every safety property the product already guarantees for a Rekordbox write: closed-Rekordbox guard, backup, freshness fingerprint, exact preview echo, files deleted only after a durable commit.

**Non-Goals:**

- Migrating a retained staged file into the permanent collection. Owner decision: blocked and reported instead.
- Any change to the behaviour of full event deletion.
- Per-track removal as a one-click action. Batch only.

## Decisions

### Block the retained case instead of migrating it — and thereby avoid the state machine

Owner decision, and it is what makes the rest of the design small. With migration out of scope, a removal is: open `mutate()`, untag, soft-delete the entries the event alone brought in, commit, then trash the staged files. There is no copy preceding the commit, therefore no torn window, therefore nothing to recover across a crash — a failure before the commit rolls back to the backup with every file still in place, and `delete_file`'s existing contract ("call only AFTER the owning DB transaction committed") covers the rest.

This is the shape of `apply_event`, which is the correct precedent: a single `mutate()` unit of work followed by application-database bookkeeping. Alternative considered: thread `partial=True` through `delete_event`. Rejected — it would add branch points in the preview cache, the resume path, the committed-detection, the cleanup tail and the terminal event deletion, all sharing one persisted plan slot, inside the most safety-critical module of the repository.

The retained case is surfaced through `_unresolved_issues`, which already exists precisely to block a destructive action from the preview onwards with actionable `resolution_options`. A new kind, `retained_by_other_mytag`, joins `missing_retained_source` and `unsafe_retained_source`.

### Extract the classification, share nothing else

The four-way decision currently inlined in `build_plan` is a pure function of `(ownership, in_event_staging, retaining_ids)`. It is extracted as such and called from both `build_plan` and the removal planner. This is the one thing that must never diverge — it is the definition of "the event brought this in" — and it is the one thing that carries no orchestration with it.

`build_plan`'s own behaviour is unchanged by the extraction; the existing deletion tests are the regression net.

### Shared audio inside the event

`build_plan` reasons in Rekordbox entries, and its `_referenced_by_other_content` guard looks at other *content rows*. That is sufficient when the whole event goes away, but not for a batch: two tracks of the same event can resolve to the same entry. Two Spotify ids sharing one non-empty ISRC share a staged file under the claim rule, and `apply_event` then reuses the same content row through `find_active_content_by_path` — the single-versus-album-edit case is the everyday instance.

The removal planner therefore groups the batch by `content_id` and by `staging_file_path`, and treats an entry or a file as removable only when every event track holding it is in the batch. A partially covered group degrades to no action at all, not to a partial one.

### Never-applied tracks bypass Rekordbox entirely

A batch entry with no `content_id` has no Rekordbox footprint: the row goes and its staged file is trashed. If the batch contains only such entries, the operation does not need `mutate()` and does not require Rekordbox to be closed. The preview reports this so the confirmation dialog does not demand a closed Rekordbox for nothing.

### The plan is not persisted

Full deletion persists its plan because it must survive a crash mid-migration. This one does not migrate, so the plan lives only in the request/response round trip, exactly like the freshness fingerprint it carries. That is also what keeps it clear of the `delete_plan` slot.

### The removed track's row

An applied track that is removed keeps a row in `event_tracks` with status `removed` and its `content_id` cleared, rather than being deleted. Two reasons: the event's history stays readable, and — where `add-event-staged-file-adoption` has landed — a row keeping its `staging_file_path` is what prevents a file that was *not* deleted from being adopted again on the next claim. Where the file was trashed, the retained row is inert either way.

## Risks / Trade-offs

- **The blocked case is an annoyance in exactly the situation where the user cared enough to tag the track** → mitigated by naming the retaining tag and offering the two clearing actions; full event deletion still migrates correctly. Migration can be added later without changing anything decided here.
- **A second destructive path to audit** → mitigated by sharing the classification, by not persisting state, and by requiring the same preview-echo and fingerprint contract as deletion. The new code is orchestration only.
- **Grouping by `content_id` and by `staging_file_path` is two group-bys where deletion had none** → each needs its own test with a shared-ISRC fixture; this is the single most likely place for a data-loss bug in the change and should be treated as such in review.
- **A file trashed while its Rekordbox entry survives** (a plan that soft-deletes nothing but deletes a file, or the reverse) → prevented structurally: file deletion is derived from the same per-track action that drove the Rekordbox write, and runs only after the commit is durable.
- **Interaction with a pending event-deletion preview** → the removal plan is not stored, but executing a removal invalidates any deletion preview the user has open. The existing staleness check on the deletion side catches this: the fingerprint will have moved.
