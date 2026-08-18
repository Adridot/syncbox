## Why

Legacy acquisition storage migration currently removes only the migrated audio file and silently leaves a non-empty `job-N` directory behind. Artwork directories and any other residual files therefore accumulate in Syncbox-managed storage even though the migration reports the job as complete.

## What Changes

- Treat each validated legacy `job-N` directory as the cleanup unit after its audio output has been copied, verified, and reconnected to its semantic owner.
- Send the entire job directory to the operating-system trash, including artwork and unexpected residual content.
- Include safe residual job directories left by previously completed migrations so the existing storage pollution can be removed as well as prevented.
- Preserve the existing explicit-consent requirement before falling back to permanent deletion when trash is unavailable.
- Keep the legacy cleanup reference retryable until the complete job directory has been removed successfully.
- Add focused regression and path-safety coverage for directory-level cleanup.

## Capabilities

### New Capabilities

- `legacy-acquisition-storage-cleanup`: Defines safe, complete, and retryable cleanup of legacy acquisition job directories after verified migration.

### Modified Capabilities

None.

## Impact

- Affects the sidecar's legacy acquisition storage migration, its additive preview/result payload, and filesystem deletion helper behavior.
- Updates the Health backup/migration UI so cleanup-only residual directories can be reviewed and executed even when no audio migration remains.
- Extends acquisition migration tests for residual artwork, unexpected files, trash failure, permanent-delete consent, and symlink/path containment safety.
- Does not change public API routes or add dependencies; it reuses the existing Send2Trash integration and Python standard library.
