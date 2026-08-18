## Why

Syncbox versions predating the August 2026 metadata-import fix created 55 Rekordbox content rows from richly tagged audio files while leaving album, genre, track/disc number, release date, and release year blank. The forward import path is fixed, but these existing rows require a one-time, guarded, fill-only backfill so their metadata is corrected without re-downloading audio or replacing Rekordbox content identities.

## What Changes

- Add a read-only preview that identifies exactly the 55 audited legacy Syncbox imports and derives only supported missing metadata from their existing audio tags.
- Require the preview to resolve to exactly 55 active Rekordbox rows; refuse an incomplete, expanded, stale, ambiguous, or otherwise changed target set.
- Backfill only blank album, genre, track number, disc number, release date, and release year values. Preserve existing title, artist, ISRC, technical audio properties, user metadata, and every non-target field except Rekordbox's required transaction bookkeeping.
- Apply the confirmed payload through Syncbox's guarded Rekordbox mutation pipeline with the Rekordbox process guard, freshness validation, timestamped backup, one transaction, rollback on failure, cache invalidation, and post-write verification.
- Preserve content IDs, audio files, ANLZ files, cues, beatgrids, playlists, MyTags, and play history; do not download, move, rename, re-import, re-analyze, or replace any track.
- Report that all 55 tracks received the five universally available fields and that genre was filled for the 53 files that contain a genre tag, leaving the other two genre values blank.

## Capabilities

### New Capabilities

- `legacy-import-metadata-backfill`: Preview, validate, apply, and verify the strict fill-only repair of the 55 audited legacy Syncbox imports.

### Modified Capabilities

None.

## Impact

- Affected systems: the Syncbox maintenance surface, the existing read-only Rekordbox snapshot/tag extraction path, the guarded `master.db` mutation unit of work, backup reporting, and metadata write helpers.
- Data impact: exactly 55 existing active Rekordbox content rows plus any shared album, album-artist, or genre rows needed to represent their embedded tags.
- External dependencies: existing pinned `mutagen`, `pyrekordbox`, and SQLCipher runtime only; no network access or new dependency is required.
- Operational constraint: Rekordbox and rekordboxAgent must be fully closed before apply; preview remains read-only and can run while Rekordbox is open.
