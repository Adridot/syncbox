-- 0008: single-writer job claims, durable publication state, and canonical
-- owner references for the acquisition queue.

ALTER TABLE acquisition_jobs ADD COLUMN claimed_by TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN claimed_at TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN phase TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN published_path TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN published_sha256 TEXT;

-- Canonicalize owner references: the API historically accepted spellings
-- such as '01' for track id 1. SQLite resolved both to the same row while
-- the (scope, ref) uniqueness index treated them as distinct keys, allowing
-- two active jobs on one owner. The 0007 index must step aside while the
-- spellings collapse onto their canonical keys.
DROP INDEX acquisition_jobs_one_active_ref;

UPDATE acquisition_jobs
SET ref = CAST(event_track_id AS TEXT)
WHERE scope = 'event'
  AND event_track_id IS NOT NULL
  AND ref <> CAST(event_track_id AS TEXT);

UPDATE acquisition_jobs
SET ref = CAST(library_track_id AS TEXT)
WHERE scope = 'library'
  AND library_track_id IS NOT NULL
  AND ref <> CAST(library_track_id AS TEXT);

-- Re-run duplicate supersession on the canonical keys before tightening
-- the uniqueness guarantees below.
UPDATE acquisition_jobs
SET status = 'failed',
    error = COALESCE(error, 'superseded duplicate active job')
WHERE status IN ('queued', 'running')
  AND id NOT IN (
      SELECT MIN(id)
      FROM acquisition_jobs
      WHERE status IN ('queued', 'running')
      GROUP BY scope, ref
  );

-- One active job per canonical owner row, enforced on the owner ids
-- themselves so no textual ref spelling can ever bypass it. The (scope, ref)
-- guard returns for owner-less scopes (collection refs, orphans).
CREATE UNIQUE INDEX acquisition_jobs_one_active_ref
ON acquisition_jobs (scope, ref)
WHERE status IN ('queued', 'running');

CREATE UNIQUE INDEX acquisition_jobs_one_active_event_track
ON acquisition_jobs (event_track_id)
WHERE event_track_id IS NOT NULL AND status IN ('queued', 'running');

CREATE UNIQUE INDEX acquisition_jobs_one_active_library_track
ON acquisition_jobs (library_track_id)
WHERE library_track_id IS NOT NULL AND status IN ('queued', 'running');
