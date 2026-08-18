## Context

See `proposal.md` for motivation and `specs/legacy-acquisition-storage-cleanup/spec.md` for the behavior contract.

The current storage migration copies and verifies a legacy audio source, updates Rekordbox and Syncbox ownership, sends only that source file to trash, clears `legacy_output_path`, and then attempts `rmdir()` while ignoring failure. A nested artwork directory therefore leaves the workspace behind and also removes the state needed to retry cleanup. Previously completed jobs whose published output is already outside the acquisition root are skipped by the migration preview, so existing residual directories are not surfaced.

Syncbox already has a trash-first deletion policy with explicit consent before permanent fallback. Acquisition paths also have canonical-root and symlink guards that must remain the trust boundary for directory cleanup.

## Goals / Non-Goals

**Goals:**

- Make the validated `job-N` directory the indivisible cleanup target.
- Clean residual directories from both new migrations and previously completed jobs.
- Preserve trash-first behavior, explicit permanent-delete consent, path containment, and retryability.
- Keep the change additive at the existing storage-migration route and reuse the current confirmation flow.

**Non-Goals:**

- Delete unowned `job-*` directories that cannot be tied safely to an acquisition job and verified published output.
- Change acquisition destinations, download behavior, or current-job workspace cleanup.
- Add a background janitor, scheduled cleanup, new database columns, or a new dependency.

## Decisions

### Use the job directory as one trash operation

After migration and ownership updates are committed, cleanup sends the validated direct `job-N` directory to trash as one unit. The target includes the recorded audio source, artwork, and any other content present in that directory. The implementation does not enumerate or classify children before deletion because the user has explicitly selected whole-directory ownership and enumeration would reintroduce partial cleanup states.

Alternative considered: remove only known artwork paths and then call `rmdir()`. This was rejected because any new or unexpected residual file would reproduce the bug.

Alternative considered: trash every child independently. This was rejected because it creates partially cleaned directories and unnecessary per-file state while providing no benefit for a directory whose complete contents are owned by the job.

### Represent residual directories explicitly in a versioned plan

The storage-migration preview will use a new plan version and include an additive `cleanup_directories` collection. Each entry identifies the job and canonical directory plus enough directory identity state to reject a replaced or changed target. New migration items contribute their job directory after publication; cleanup-only entries cover directories left by previously completed jobs.

A cleanup-only directory is eligible only when:

- it is exactly the non-symlinked direct `job-N` child of the canonical acquisition root;
- the matching database job exists and is not queued or running;
- its current published output is outside that job directory and verifies at the semantic owner's destination; and
- no pending legacy source still requires migration.

Directories that fail any check remain untouched and appear in the ignored results. The UI enables execution when either migration items or cleanup-only directories exist and shows cleanup-only directories separately, while reusing the existing confirmation and permanent-delete consent flows.

Alternative considered: scan and delete every `job-*` directory after a migration batch. This was rejected because it could race with active downloads or delete an unowned directory without an exact preview.

### Reuse the trash-first deletion policy for directories

The existing filesystem deletion policy will accept a validated directory target. It will call the installed Send2Trash integration first. If trash fails, it raises the existing consent-required error without changing the directory; after explicit consent, the permanent fallback uses Python's recursive directory removal and propagates any failure.

No cleanup call will use `ignore_errors`, and a symlink passed to the permanent fallback will be refused rather than traversed. Existing file deletion behavior remains unchanged.

Alternative considered: call recursive permanent deletion directly from acquisition migration. This was rejected because it bypasses Syncbox's recoverability and consent contract.

### Commit cleanup state only after the directory is absent

For a newly migrated item, destination copying and semantic-owner updates finish before directory cleanup starts. The legacy source reference remains populated as a cleanup checkpoint until directory removal succeeds. If trash or permanent deletion fails, the next execution revalidates the already-published destination and resumes cleanup without copying or mutating Rekordbox again.

For cleanup-only entries from previously completed jobs, execution revalidates the plan and published output immediately before removing the directory. Missing directories are treated idempotently as already cleaned after all job and destination checks pass.

## Risks / Trade-offs

- [Unexpected user content inside `job-N` is removed] → This is the confirmed product behavior; trash remains the default recovery mechanism, the exact directory is previewed, and permanent fallback requires explicit consent.
- [A directory is replaced between preview and execution] → Revalidate canonical containment, non-symlink status, job activity, published destination, and captured directory identity immediately before cleanup.
- [One directory fails after earlier directories were trashed] → Keep cleanup idempotent and retryable per job; never repeat completed copies or Rekordbox mutations.
- [Old in-memory previews have a different payload] → Increment the plan version so execution rejects them and requires a fresh preview.
- [Cleanup-only UI increases surface area] → Add only a count/details section and reuse the existing action, banner, and consent modal rather than introducing a new workflow.

## Migration Plan

1. Ship the versioned preview/execution behavior and UI support together.
2. Require clients holding an older preview to refresh it before execution.
3. On the next Health-page preview, surface eligible directories left by earlier completed migrations; no database migration or background scan is required.
4. If the release is rolled back, previously trashed directories remain recoverable through the operating-system trash, while verified published audio destinations and owner references remain valid.
