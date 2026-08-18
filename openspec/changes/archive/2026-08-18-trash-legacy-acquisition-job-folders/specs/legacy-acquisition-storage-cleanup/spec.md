## Purpose

Ensures legacy acquisition migrations remove their complete managed job directories safely, including existing artwork and other residual files.

## ADDED Requirements

### Requirement: Successful migration cleans the complete job directory
After a legacy acquisition output has been copied, verified, and reconnected to its semantic owner, the system SHALL remove the complete validated `job-N` directory rather than only the recorded audio file. Cleanup SHALL include artwork directories and all other residual content, including unexpected files.

#### Scenario: Job directory contains artwork and unexpected files
- **WHEN** a legacy acquisition output has been migrated successfully and its validated job directory contains the source audio, artwork, and other residual files
- **THEN** the system removes the complete job directory and none of its contents remain in managed acquisition storage

#### Scenario: Migration has not committed its destination
- **WHEN** the migrated output or its semantic-owner reference has not been verified and committed
- **THEN** the system leaves the complete legacy job directory intact

### Requirement: Existing residual job directories are eligible for cleanup
The system SHALL include a residual `job-N` directory left by a previously completed migration in the cleanup plan when the corresponding job is inactive and its published output is verified at the semantic-owner destination.

#### Scenario: Previously completed migration left artwork behind
- **WHEN** a completed acquisition job has a verified owner-published output and its validated legacy job directory still exists
- **THEN** the cleanup plan presents the residual directory for complete removal

#### Scenario: Completed job output cannot be verified
- **WHEN** a residual job directory exists but the corresponding published output or owner cannot be verified
- **THEN** the system leaves the residual directory intact and reports it as ignored

### Requirement: Job directory cleanup is trash-first
The system SHALL send an eligible job directory to the operating-system trash before considering permanent deletion. If trash is unavailable, the system MUST require explicit consent for that operation before permanently deleting the directory tree.

#### Scenario: Operating-system trash accepts the directory
- **WHEN** the operating-system trash accepts an eligible job directory
- **THEN** the system moves the complete directory to trash and does not perform permanent deletion

#### Scenario: Trash is unavailable without consent
- **WHEN** trashing an eligible job directory fails and explicit permanent-delete consent was not provided
- **THEN** the system leaves the directory intact, preserves a retryable cleanup state, and requests explicit consent

#### Scenario: Permanent deletion is explicitly approved
- **WHEN** trashing an eligible job directory fails and explicit permanent-delete consent was provided for the retried operation
- **THEN** the system permanently removes the complete directory tree

### Requirement: Cleanup is confined to the managed job directory
Immediately before cleanup, the system SHALL verify that the target is the canonical, non-symlinked `job-N` directory directly associated with the acquisition job under the managed acquisition root. The system MUST refuse cleanup if containment, job ownership, active-job state, or published-destination verification fails.

#### Scenario: Job directory is a symbolic link or escapes managed storage
- **WHEN** a cleanup target is a symbolic link or does not resolve to the acquisition job's direct managed directory
- **THEN** the system refuses cleanup and does not modify the target or any external path

#### Scenario: Job becomes active or its destination changes
- **WHEN** the job becomes active or its published destination no longer matches the verified cleanup plan before execution
- **THEN** the system refuses cleanup and preserves the job directory for recovery

### Requirement: Cleanup completion is recorded only after directory removal
The system SHALL keep cleanup retryable until the complete job directory is absent. A retry after migration has committed SHALL resume cleanup without copying the audio again or repeating the semantic-owner mutation.

#### Scenario: Directory removal fails after migration commit
- **WHEN** migration state has committed but complete directory removal fails
- **THEN** the system retains the cleanup reference and can retry only the directory cleanup

#### Scenario: Directory removal succeeds
- **WHEN** the complete job directory is removed successfully or is already absent after all safety checks pass
- **THEN** the system clears the legacy cleanup reference and reports cleanup as complete
