## Context

See proposal.md — Why.

`events_create` already does exactly half the work: it calls `library_service._collect_tracks(client, payload)` over `/playlists/{id}` and feeds the result through `events_service.add_track`, then runs `_try_match_event`. The fetch and mapping are therefore settled; what is missing is a second call and a diff.

The library's `sync_one_source` is the reference for the diff, but only partly transferable. It replaces a source's rows wholesale (`replace_source_tracks`) because a library row carries no irreplaceable local state. An event track does: `content_id`, `staging_file_path`, `added_after_apply`, acquisition history. The event diff must therefore be an in-place reconciliation, never a replace.

`pending_delta` is computed in `events_list` by a single aggregate over `event_tracks` and drives the `+n` badge and the re-apply CTA. `recompute_event_status` derives the event's status from `PENDING_STATUSES`. Both are the reason the new status has to be introduced carefully rather than added to the vocabulary and left alone.

## Goals / Non-Goals

**Goals:**

- The addition path terminates in the existing pending-delta and re-apply flow, adding no new way for a track to reach Rekordbox.
- The removal path stops at a signal. Nothing in this change writes to Rekordbox or touches a file.
- One migration, serving both this change and the origin distinction that `add-event-track-removal` depends on.

**Non-Goals:**

- Executing removals. That is `add-event-track-removal`, which depends on the `removed_upstream` signal defined here.
- Automatic or scheduled refresh. Explicit button, owner decision.
- Reordering the event to match the playlist order. The event has no ordering concept.

## Decisions

### No `snapshot_id` on events

`sources` stores Spotify's `snapshot_id` so a scheduled sync can skip pagination when nothing changed. With an explicit, user-initiated button there is nothing to skip: the user clicked because they want to know, and knowing requires the fetch either way. The column would buy only the pagination of an unchanged large playlist. Not added.

### `origin` is a column, not an inference

An event track's provenance is currently unrecoverable: a row imported from the playlist and a row added by pasting a Spotify link are byte-identical. Without a stored origin, the first refresh of an event would report every link-added track as having left the playlist — the exact opposite of the feature's purpose. This is the one unavoidable schema change.

Values are `playlist`, `manual`, `adopted`. Backfill: a row whose `spotify_track_id` is set becomes `playlist`; a row without one that holds a `staging_file_path` becomes `adopted`; the rest become `manual`. This mis-labels pre-existing link-added rows as `playlist`, which means the first refresh of an existing event can report one of them as departed. The spec requires that no existing track be *wrongly* reported; the backfill satisfies it in the common case and the "keep" action is the escape hatch for the rest. Alternative considered — backfilling everything as `manual` so nothing is ever signalled — was rejected because it would make the first refresh of every existing event silently useless on removals, which is worse and harder to explain than one dismissible false positive.

`add-event-staged-file-adoption` has landed, so `adopted` is written from the start. Its API payload currently *infers* the `adopted` flag from the absence of a Spotify id plus the presence of a staged path, which is wrong for a manually typed track that later claimed a file; with the column in place that inference is replaced by a direct read of `origin`, closing the known false positive.

### The diff reconciles in place, keyed on `spotify_track_id`

Three buckets over the playlist-sourced rows only:

- in playlist, in event → update title / artist / duration / ISRC. Never status, `content_id`, `staging_file_path`.
- in playlist, not in event → `add_track` with `origin='playlist'`, `added_after_apply` set by the existing rule in `add_track`.
- in event, not in playlist → `status='removed_upstream'`, previous status saved.

Duplicate occurrences within the playlist are collapsed on `spotify_track_id` before the diff, as `sync_one_source` does — the event is a set of tracks, not a running order.

### `prior_status` already exists

`event_tracks.prior_status` is in the schema and is what the "keep" action reads to restore. No column is added for it. Keeping a track sets its status back and marks it so a later refresh does not re-signal it — the mark is `origin='manual'`: a track the user has explicitly decided to keep despite its absence from the playlist *is* a manual track from that point on. This reuses the existing exclusion rule rather than adding a second flag.

### `removed_upstream` stays out of every existing aggregate

Three call sites must exclude it, and each for a different reason:

- `PENDING_STATUSES` — otherwise a departure alone flips a fully applied event to `partially_applied`, which reads as "you have work to do" when there is nothing to write.
- the `pending_delta` aggregate in `events_list` — otherwise the `+n` badge and the re-apply CTA count a track that re-apply will not write.
- `REMATCHED_STATUSES` and `CLAIMABLE_STATUSES` — a departed track must not be re-matched or claim a file while it is awaiting a decision.

The departure count is surfaced as its own signal next to the pending-delta badge, not folded into it.

### Refresh is one route, "keep" is another

`POST /api/events/{id}/refresh` returns the counts of the three buckets. `POST /api/events/{id}/tracks/{track_id}/keep` clears one signal. Batch keeping is not modelled; the UI can call the route per row. Nothing here needs a preview or an echo contract, because nothing here is destructive.

## Risks / Trade-offs

- **First refresh of an existing event reports a link-added track as departed** → dismissible in one click via "keep", which also fixes its origin permanently. Documented above as a deliberate trade against the silent alternative.
- **A track removed and re-added on Spotify comes back as a new track** → it is a new row with no memory of its prior link, so it will re-match or re-acquire. Acceptable; the alternative is keeping tombstones indefinitely.
- **A refresh imports many tracks at once and the automatic match runs over all of them** → matching already reads only the cached collection snapshot and is already run in bulk by `events_create` on playlist import. Same cost profile, no new exposure.
- **`removed_upstream` is a new status in a vocabulary several call sites enumerate** → the mitigation is the explicit list of exclusion sites above, each with a test; there is no `CHECK` constraint on `event_tracks.status` to catch a missed one at runtime.
- **A departed track that was never applied still holds a staged file** → it keeps it. The file is not touched by this change, and the track remains referenced so the adoption pass (if present) does not re-adopt it.
