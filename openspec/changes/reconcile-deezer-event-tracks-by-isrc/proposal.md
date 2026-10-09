## Why

Since 0.9.0 a track added to an event from a Deezer link is only recognised as already in the Rekordbox collection when Syncbox holds recorded provenance for that exact Deezer item: a published acquisition job with the same Deezer ID, the same path and an unchanged SHA-256. In the owner's and the users' libraries that proof almost never exists (files acquired before 0.9.0, files acquired through the Spotify-to-ISRC path under another Deezer ID, files retagged by Rekordbox, files acquired on another machine), so tracks that are plainly in the collection show as missing, get downloaded again and end up as duplicates in Rekordbox. Spotify additions never regressed because they still use the ISRC-first matcher.

## What Changes

- An exact-source event track (Deezer, YouTube, SoundCloud) that carries an ISRC SHALL be matched to an active local collection content with the same ISRC when no recorded provenance resolves it. The existing ISRC duration guard applies. Fuzzy title/artist/duration matching and staged-file metadata scoring remain forbidden for exact-source tracks: an ISRC identifies a recording, so a remix never matches its original.
- Event apply accepts an exact-source `matched` row either through recorded provenance (unchanged) or by re-verifying that the matched content still carries the same ISRC, instead of demoting ISRC matches to missing.
- A previewed, trash-first reconciliation repairs the data already produced by 0.9.0: a `ready` exact-source row whose download duplicates an ISRC-equal collection content becomes `matched` to that content and its download is trashed; an `applied` exact-source row whose Rekordbox content was created from such a download gets its event tag moved to the ISRC-equal original, the duplicate content soft-deleted and its file trashed. Ambiguous or otherwise-used contents are reported, never touched.
- The reconciliation preview reports ISRC coverage (exact-source rows without ISRC, collection candidates found, managed Deezer downloads in the collection lacking an ISRC tag) so the owner can confirm on the production database that ISRC matching actually covers the affected libraries before executing anything.

## Capabilities

### New Capabilities

- `event-source-reconciliation`: previewed repair of existing exact-source event rows that duplicate ISRC-equal collection contents, including ISRC coverage reporting, trash-first file cleanup and guarded Rekordbox writes.

### Modified Capabilities

- `event-source-acquisition`: the requirement "Direct links retain their exact provider item" changes so that recorded provenance OR ISRC equality with the duration guard may automatically associate an existing collection content; approximate (fuzzy, staged-file scoring) association remains forbidden. This capability was introduced by `add-event-multiplatform-link-import`, which is complete but not yet archived; its spec must be synced to `openspec/specs/` before this delta is archived.

## Impact

- Sidecar: `events_service.match_event_tracks` and `apply_event` (exact-source branch), `source_identity`, one new reconciliation module following `acquisition_migration` (plan/execute, fingerprint freshness, `mutate()`, trash-first consent), two API routes, tests.
- UI: Health > Backups tab gains a reconciliation preview/execute block next to the storage migration, with its localized strings and API types.
- Data: no schema change. Existing acquisition job rows keep their published path; a trashed download simply stops being an eligible provenance file.
- Rekordbox: writes only inside `mutate()` with backups, reusing the existing tag/untag/soft-delete primitives from event track removal.
- Out of scope: library/collection acquisition policy, staged-file claiming by metadata for exact-source rows, YouTube/SoundCloud items without ISRC (they keep today's behaviour), the Duplicates screen.
