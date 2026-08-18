## Context

See `proposal.md` for motivation and `specs/legacy-import-metadata-backfill/spec.md` for the behavior contract. The August 2026 import fix already proves the required tag-to-Rekordbox mapping for new content, and the current audit shows a clean discontinuity: 55 pre-fix rows have the supported fields blank while all six post-fix rows contain them. Every target audio file is readable; all 55 contain album, track/disc number, release date, and release year, and 53 contain genre.

The legacy application database cannot identify created rows by status alone because historical `imported` status also covered already-matched Rekordbox content. Target discovery therefore needs a dedicated, reviewable cohort audit rather than a broad status query. Pyrekordbox supports direct attribute updates followed by `commit()`, but its own documentation requires a Rekordbox backup before changes. The existing Syncbox mutation unit already supplies the stronger process, backup, freshness, rollback, and cache guarantees required here.

References:

- [Syncbox metadata import fix and prior scoped repair](https://github.com/Adridot/syncbox/pull/40)
- [Pyrekordbox database update guidance](https://pyrekordbox.readthedocs.io/en/stable/tutorial/db6.html#updating-the-database)
- [Rekordbox 7 analysis scope](https://cdn.rekordbox.com/files/20260409151936/rekordbox7.214_manual_EN.pdf)

## Goals / Non-Goals

**Goals:**

- Make the exact 55-row cohort independently reviewable before any write.
- Reuse the proven current import mapping while making updates strictly fill-only.
- Apply through the existing guarded mutation unit and produce evidence that identity, DJ preparation data, audio, and ANLZ artifacts were preserved.
- Keep all user-specific track identities, names, paths, and hashes in a local generated manifest/report rather than committed source files.

**Non-Goals:**

- A general-purpose metadata editor, recurring migration, startup migration, or new UI.
- Repairing the other 137 missing-year rows whose files do not provide a recoverable year.
- Adding label/`organization`, barcode, artwork, BPM, key, composer, comment, remixer, or any metadata outside the already validated import-fix scope.
- Re-downloading, re-importing, re-analyzing, moving, renaming, or modifying audio or ANLZ files.
- Overwriting any non-blank Rekordbox metadata value.

## Decisions

### 1. Implement a one-shot preview/apply/verify maintenance command

The change will add a repository maintenance command with three explicit phases: generate a local preview manifest, apply that reviewed manifest, and verify an applied manifest. Preview and verification use read-only database connections. Apply is the only writable phase and delegates to the existing Syncbox mutation unit.

This is preferred over a UI feature or automatic startup migration because the cohort is user-specific and finite. It is preferred over an ad hoc shell or SQL script because the normal mutation guard, backup, transaction, and test seams remain enforceable.

### 2. Discover candidates from the audited legacy signature, then freeze exact identities in a local manifest

Initial preview will select active rows inside the configured permanent collection whose creation/stock dates and blank legacy metadata shape match the audited pre-fix import window. It will resolve each stored path through Syncbox's canonical path rules, require readable regular audio files, derive the supported source tags, deduplicate by content ID and canonical path, and require exactly 55 results.

The preview manifest will freeze the resulting content IDs, canonical paths, current target values, proposed values, database fingerprint, audio-file SHA-256 values, relevant ANLZ SHA-256 values, and preservation digests for cues and memberships. It will also contain aggregate counts and enough track identity for human review. The manifest is local operational data and will not be committed.

This two-stage approach is preferred over committing the 55 IDs, which would publish user-library data, and over reusing legacy `imported` statuses, which include matched tracks that Syncbox did not create. Date/signature discovery alone is never sufficient to write: apply consumes only the reviewed, frozen manifest and revalidates it exactly.

### 3. Re-derive the complete payload immediately before mutation

Apply will load the whole manifest, require exactly 55 unique entries, re-read the database and all source tags, recompute file and preservation identities, and require structural equality with the confirmed preview. Database-fingerprint drift, audio-tag drift, file replacement, changed membership/cue data, missing files, or a different target count aborts before the writable database is opened.

The confirmed payload stores semantic album/album-artist and genre names rather than future database IDs. Inside the transaction, the implementation resolves or creates the required linked rows and verifies them semantically afterward. This avoids predicting generated IDs while retaining exact user-visible intent.

### 4. Share tag parsing and linked-row identity with the fixed import path

The backfill will reuse the current audio-tag extraction and the existing album and genre identity rules. Album identity remains `(album name, album artist)` when an album artist is present; genres use exact names. Matching active linked rows are reused, and the existing safe handling of soft-deleted linked rows remains authoritative.

A dedicated fill-only content update helper will assign only blank `AlbumID`, `GenreID`, `TrackNo`, `DiscNo`, `ReleaseDate`, and `ReleaseYear` fields. It will not call the broader create-content path and will not assign title, track artist, ISRC, technical properties, or unsupported tags.

This is preferred over deleting/re-importing rows, Rekordbox tag reload, or copying every parsed tag because those alternatives either disturb identity/preparation data or broaden the approved scope.

### 5. Use one guarded transaction for all 55 rows

Apply will pass the confirmed database fingerprint into the existing mutation unit, including the Rekordbox process guard, timestamped backup, configured retention, writable Pyrekordbox session, one commit, rollback on exception, app-database backup coverage where required, and post-commit cache invalidation. The operation will use a distinct backup reason so Doctor and logs can identify the repair.

The mutation can create or reactivate shared album, album-artist, or genre rows only when required by a proposed fill. Pyrekordbox-managed USNs and timestamps are expected bookkeeping changes and are excluded from non-target preservation comparisons.

### 6. Verify from a fresh read-only connection after the durable commit

After the mutation unit closes, verification will reopen `master.db` read-only and compare all target values against the confirmed semantic payload. It will also recompute the preserved content/path fields, cue and membership digests, audio hashes, and ANLZ hashes. The success report will include the backup path, 55 verified targets, five universal field fills per target, 53 genre fills, two intentional genre blanks, and zero preservation mismatches.

Post-commit verification cannot roll back an already durable transaction. A mismatch therefore produces a failed report with the exact discrepancy and existing Doctor restoration guidance; it never attempts an unreviewed compensating write.

## Risks / Trade-offs

- **[Legacy signature accidentally includes an unrelated row]** → Require the exact count, freeze the local manifest, expose every identity and before/after value for review, and apply only that confirmed manifest.
- **[The live database or a file changes after preview]** → Recompute the database fingerprint, source payload, hashes, and preservation digests before opening the writable database; abort on any difference.
- **[A shared album name belongs to different artists]** → Preserve the current `(album name, album artist)` identity rule and verify semantic linkage after commit.
- **[A target already gained metadata independently]** → Treat every non-blank target value as protected; the fresh preview will omit it and stale manifests will be rejected.
- **[Pyrekordbox bookkeeping changes appear as collateral edits]** → Explicitly exclude only documented/generated USN and timestamp fields from preservation digests; keep all user and DJ data in scope.
- **[Verification fails after commit]** → Retain the pre-write backup, report exact mismatches, and require explicit restore through the existing guarded Doctor workflow.
- **[Hashing audio and ANLZ files adds runtime]** → Accept the bounded one-time read cost for 55 tracks in exchange for evidence that no media or analysis artifact changed.

## Migration Plan

1. Run the automated unit and disposable-fixture tests for discovery, fill-only mapping, stale rejection, rollback, and preservation verification.
2. Generate the read-only local preview against the live library and confirm that it contains exactly 55 reviewed targets with 55 album/date/year/track/disc proposals and 53 genre proposals.
3. Close Rekordbox and rekordboxAgent completely.
4. Apply the exact manifest through the guarded mutation unit, creating a timestamped backup first.
5. Run automatic post-commit verification and retain the manifest, report, and backup reference as local evidence.
6. Reopen Rekordbox and manually spot-check representative rows without requesting re-analysis.

Rollback is the existing guarded Doctor restore of the reported pre-write backup. Restoration remains an explicit user action and is not triggered automatically by the maintenance command.
