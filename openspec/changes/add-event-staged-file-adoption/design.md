## Context

See proposal.md — Why.

Two facts about the current code shape the approach.

`claim_staged_files` (`events_service.py`) iterates over event tracks and, for each claimable one, scores the staging files against it. The file set is only ever read through `relink.iter_audio_files`, which is bounded by `MAX_SCANNED_FILES` and swallows per-entry `OSError` — a hard requirement in cloud folders, where a background process can fail to list a directory it can perfectly well stat (SPEC-01 1.5).

`events_claim` (`api.py`) already chains claim and matching: it calls `claim_staged_files` then `_try_match_event`, whose docstring records the owner decision that matching is fully automatic with no button.

Observed on the live `jo-helo` event: three files were dropped at 16:09 UTC; the one for which a `missing` track existed was claimed at 16:39 with confidence 100, the two others were never seen by anything.

## Goals / Non-Goals

**Goals:**

- Adoption reuses the existing match and claim steps rather than introducing a second path into `event_tracks`.
- No new Rekordbox write path: an adopted track reaches apply through the statuses that already exist.
- Extract nothing from `event_delete.py`; this change does not touch the destructive path.

**Non-Goals:**

- Library-side adoption (`_syncbox/inbox`). Deliberately excluded by the owner; the helpers built here are reusable if that ever changes.
- Parsing `Artist - Title.mp3` file names into fields. The fallback puts the whole file name in the title and stops there.
- Any UI for choosing which dropped files to adopt. Dropping the file is the decision; `ignored` is the undo.

## Decisions

### Adoption creates a `missing` row and lets the existing pipeline converge

An adopted file could be inserted directly as `ready` with its `staging_file_path` already set. It is not. The row is created as `missing` carrying only the metadata read from the file, and the two steps `events_claim` already runs finish the job.

This works because the row's metadata comes from the file itself, so `relink.score_candidate` compares the title against the tags and the stem of that very file and scores it at or near the maximum — the track reliably claims the file it was born from. The gain is the branch in between: `_try_match_event` gets a chance to match the metadata against the Rekordbox collection first. If the user already owns the track, the event tags the existing collection entry instead of importing a second copy of the same music, which is the outcome the deduplication rules elsewhere in the product aim for.

Alternative considered: insert as `ready` directly. Shorter, but it makes every dropped file a new collection entry at apply time, including files the user already has. Rejected.

**Amended during implementation**: the row is inserted `missing` *with its `staging_file_path` already set*, not NULL. Leaving it NULL makes the matched branch unimplementable — a row that `_try_match_event` turns into `matched` leaves `CLAIMABLE_STATUSES`, so nothing ever binds it to its file, the file stays unreferenced and is re-adopted on every subsequent claim (unbounded duplicate rows), and the row is indistinguishable from a manual one so the `adopted` flag could never be true for it. Setting the path at insert makes the file referenced immediately, including across a crash between adoption and matching. A guard at the head of `claim_staged_files`' per-track loop — a claimable row already holding an existing staged file goes straight to `ready` without re-scoring — restores the intended "the trailing claim readies whatever matched nothing" behaviour.

### Ordering inside `claim`

The pass runs as: existing claim → adoption of what is still unreferenced → matching → claim again. The first claim must come first so a file that satisfies a track already in the event is consumed by that track rather than adopted as a near-duplicate. The trailing claim is the one that binds adopted rows to their files; `events_claim` already calls matching after claiming, so the added work is one extra claim call, not a new orchestration.

### Metadata extraction reuses `rb_write._audio_metadata`

`_audio_metadata` already reads title, artist, album, genre, ISRC, duration and stream properties through mutagen, and already returns `{}` rather than raising on an unreadable file. Adoption needs a strict subset. It is promoted to a public name and reused; no second tag reader is introduced. `relink._file_tags` is deliberately not reused — it returns only ISRC and title.

### Rejection is `ignored`, not deletion

Deleting an adopted row would leave its file unreferenced, and the next claim would adopt it again — an unbreakable loop for a file the user has just refused. `event_tracks` already knows the `ignored` status, and `REMATCHED_STATUSES` already excludes it, so an ignored row is inert for matching. Keeping the row with its `staging_file_path` is what makes the file referenced, which is what stops re-adoption; the status is what keeps it out of the counts.

The row is retained only for tracks that were adopted. Removal of a Spotify-sourced track keeps deleting the row, as today.

### Distinguishing adopted rows without a schema change

An adopted row is exactly a row with no `spotify_track_id` and a `staging_file_path`, which no other creation path produces: manual entry sets neither, playlist and link imports set the Spotify id. No column is added. The follow-on change `add-event-playlist-refresh` introduces an `origin` column for its own reasons; this change does not need it and must not wait for it.

## Risks / Trade-offs

- **A dropped file scores higher against another event track than against its own row** → the deterministic first-claimant rule (by row id) already governs this, and the loser stays `missing` and remains actionable. Accepted: the outcome is a wrong-but-visible pairing, not a lost file.
- **A tagless file produces a track titled `Some File.mp3` with no artist** → at apply time `add_content` falls back to `Unknown Artist`. This is the owner-chosen behaviour; the user renames in Rekordbox. The alternative — guessing fields from the file name — is more wrong more often.
- **Adoption makes files visible that were previously silently trashed at event deletion** → this is the intended effect, but it changes what an existing event's deletion preview lists once claim has run at least once. The preview already enumerates the whole staging directory, so the file set does not change, only its description in terms of tracks.
- **Large drop** → the scan is already capped by `MAX_SCANNED_FILES`; adoption inherits the cap and does not widen the walk.
- **TCC listing failure in a cloud folder** → `iter_audio_files` skips unreadable subtrees rather than aborting, so a partial scan adopts what it saw and the next claim picks up the rest. Adoption must not treat "no files found" as "no files exist".
