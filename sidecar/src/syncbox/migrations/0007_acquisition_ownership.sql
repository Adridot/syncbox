-- 0007: durable acquisition ownership and resumable queue metadata.

ALTER TABLE acquisition_jobs
ADD COLUMN event_id INTEGER REFERENCES events (id) ON DELETE CASCADE;

ALTER TABLE acquisition_jobs
ADD COLUMN event_track_id INTEGER REFERENCES event_tracks (id) ON DELETE CASCADE;

ALTER TABLE acquisition_jobs
ADD COLUMN library_track_id INTEGER REFERENCES library_tracks (id) ON DELETE CASCADE;

ALTER TABLE acquisition_jobs ADD COLUMN deezer_track_id INTEGER;
ALTER TABLE acquisition_jobs ADD COLUMN relink INTEGER NOT NULL DEFAULT 0;
ALTER TABLE acquisition_jobs ADD COLUMN anlz_consent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE acquisition_jobs ADD COLUMN legacy_output_path TEXT;

UPDATE acquisition_jobs
SET event_track_id = CAST(ref AS INTEGER),
    event_id = (
        SELECT event_id
        FROM event_tracks
        WHERE event_tracks.id = CAST(acquisition_jobs.ref AS INTEGER)
    )
WHERE scope = 'event'
  AND EXISTS (
      SELECT 1
      FROM event_tracks
      WHERE event_tracks.id = CAST(acquisition_jobs.ref AS INTEGER)
  );

UPDATE acquisition_jobs
SET library_track_id = CAST(ref AS INTEGER)
WHERE scope = 'library'
  AND EXISTS (
      SELECT 1
      FROM library_tracks
      WHERE library_tracks.id = CAST(acquisition_jobs.ref AS INTEGER)
  );

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

CREATE UNIQUE INDEX acquisition_jobs_one_active_ref
ON acquisition_jobs (scope, ref)
WHERE status IN ('queued', 'running');
