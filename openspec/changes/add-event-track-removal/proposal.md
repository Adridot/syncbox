## Why

`add-event-playlist-refresh` signals tracks that have left the Spotify playlist but stops there: acting on the signal still means deleting the whole event, because Rekordbox-side removal exists only at event granularity. `events_track_remove` explicitly refuses an applied track — "an applied track is in Rekordbox; the event delete/reapply flows own that transition" — and there is no such flow short of destroying the event.

The classification the removal needs already exists inside `event_delete.build_plan`: a tagged track is either already permanent, retained by another tag, staged for this event alone, or living outside app-managed storage. What is missing is a way to run that decision over a chosen subset of tracks without invoking the event-deletion state machine.

## What Changes

- New batch removal of chosen tracks from an applied event, in two steps like the event deletion: an exact preview, then an execution that must echo the preview verbatim.
- Per track, the outcome follows where its audio lives:
  - already in the permanent library, or outside app-managed storage → the event tag is removed and the file is untouched;
  - staged for this event and retained by nothing else → the event tag is removed, the Rekordbox entry is soft-deleted, and the staged file goes to the trash;
  - never applied → the row and its staged file go, with no Rekordbox write at all.
- **A track whose staged file is retained by another Rekordbox tag blocks the batch** and is reported as unresolved with the actions that clear it. Migrating such a file to the permanent collection stays the exclusive job of full event deletion.
- The event survives: its MyTag, its smart playlist, its staging directory and every track not in the batch are untouched.
- The per-track classification is extracted from `event_delete.build_plan` and shared, so the rule cannot diverge between full deletion and batch removal.
- Removal requires Rekordbox to be closed and goes through the existing backup and freshness machinery, like every other Rekordbox write.

## Capabilities

### New Capabilities
- `event-track-removal`: chosen tracks can be withdrawn from an applied event — untagged, and deleted from Rekordbox and disk when the event alone brought them in — without deleting the event.

### Modified Capabilities

<!-- None. The event-deletion behaviour is unchanged; only its internal classification is shared. -->

## Impact

- `sidecar/src/syncbox/event_delete.py` — the per-track classification becomes a shared pure function; `build_plan` calls it instead of inlining it. No behaviour change to the deletion path.
- New removal orchestration built on `safety.mutate()` in the shape of `apply_event`, **not** on the event-deletion state machine: without file migration there is no torn window to recover from, and `events.delete_plan` is a single slot that a second in-flight plan would collide with.
- `sidecar/src/syncbox/api.py` — preview and execute routes, guarded on Rekordbox being closed.
- `ui/src/screens/EventsScreen.vue` and a new modal, following `DeleteEventModal`'s preview-and-echo contract.
- Depends on `add-event-playlist-refresh` for the `removed_upstream` signal that selects the batch.
