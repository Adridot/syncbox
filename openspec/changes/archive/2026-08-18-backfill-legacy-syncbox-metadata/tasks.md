## 1. Read-Only Cohort Preview

- [x] 1.1 Add pure legacy-cohort discovery that uses the audited permanent-library/date/blank-field signature, canonicalizes paths, rejects duplicate identities, and requires exactly 55 active rows.
- [x] 1.2 Add read-only collection of current target values, semantic source tags, database fingerprint, audio and ANLZ SHA-256 values, and cue/playlist/MyTag preservation digests without composing or migrating the app database.
- [x] 1.3 Define a deterministic, versioned local manifest format containing all 55 identities, before/after values, hashes, preservation evidence, and aggregate counts while keeping user-specific data outside version control.
- [x] 1.4 Implement the preview command to reject missing/unreadable files or unexpected field counts and atomically write the complete human-reviewable manifest only after every precondition passes.

## 2. Fill-Only Rekordbox Updates

- [x] 2.1 Add a dedicated metadata backfill helper that reuses current audio parsing and album/album-artist/genre identity rules while assigning only blank AlbumID, GenreID, TrackNo, DiscNo, ReleaseDate, and ReleaseYear values.
- [x] 2.2 Cover reuse, creation, and safe reactivation of linked album, album-artist, and genre rows, including same-name albums with different album artists.
- [x] 2.3 Add tests proving that existing target values and all unsupported or non-target content fields remain unchanged apart from required Rekordbox bookkeeping.

## 3. Guarded Apply and Verification

- [x] 3.1 Implement manifest loading and complete pre-mutation revalidation of the exact 55-row target set, database fingerprint, source tags, file hashes, and preservation digests; reject any structural or freshness difference.
- [x] 3.2 Route all 55 updates through one existing guarded mutation unit with process detection, a distinct timestamped-backup reason, one Pyrekordbox transaction, rollback on failure, app-database backup coverage, and post-commit cache invalidation.
- [x] 3.3 Implement fresh read-only post-commit verification of semantic metadata, content identities, non-target fields, cues, playlist/MyTag memberships, audio hashes, and ANLZ hashes.
- [x] 3.4 Emit a deterministic local report containing the backup path, 55 verified tracks, five universal fields per track, 53 genre fills, two intentional genre blanks, preservation results, and explicit Doctor restoration guidance on mismatch.
- [x] 3.5 Make repeat verification of the same manifest report zero remaining supported blanks and zero additional proposed writes.

## 4. Automated Safety Coverage

- [x] 4.1 Add unit tests for exact-count enforcement, ambiguous/duplicate candidates, canonical path handling, unavailable files, absent optional genre, manifest tampering, and audio-tag drift.
- [x] 4.2 Add mutation tests proving that Rekordbox-running refusal occurs before writable open, stale previews create no write, transaction failure rolls back the complete batch, and cache invalidation occurs only after durable commit.
- [x] 4.3 Add disposable-copy integration coverage for all 55 rows, linked-table updates, exact field totals, post-write readback, and unchanged content IDs, relationships, audio, and ANLZ evidence.
- [x] 4.4 Run the targeted metadata/mutation suites and the complete locked sidecar suite, then run formatting and repository diff checks.

## 5. Live Backfill

- [x] 5.1 Generate the read-only live manifest, confirm that it contains exactly the reviewed 55 titles with 55 album/date/year/track/disc proposals and 53 genre proposals, and present the aggregate result for explicit approval.
- [x] 5.2 After approval and after Rekordbox and rekordboxAgent are fully closed, apply the exact manifest once through the guarded mutation path.
- [x] 5.3 Confirm automatic verification succeeded, record the backup/report locations, and check that no audio or ANLZ artifact and no cue, playlist, MyTag, or content identity changed.
- [x] 5.4 Reopen Rekordbox and spot-check representative repaired titles without triggering re-analysis; retain the local manifest and report as repair evidence.
