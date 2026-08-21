-- 0010: event track provenance (event-playlist-refresh).
--
-- Only 'playlist' rows take part in the refresh diff, so a track added by
-- pasting a link, typed by hand, or adopted from a staged file is never
-- mistaken for a playlist removal. Provenance is UNRECOVERABLE from the
-- other columns (an imported row and a link-added row are byte-identical),
-- which is why this is a column and not an inference.
--
-- Backfill (design decision): a Spotify id means the row came from the
-- playlist; without one, a staged path means it was adopted
-- (event-staged-file-adoption); the rest is manual. This mis-labels a
-- pre-existing link-added row as 'playlist', so the FIRST refresh of an
-- existing event may report one as departed - deliberate, and the 'keep'
-- action is its one-click escape hatch which also fixes the origin for
-- good. The silent alternative (everything 'manual') would make the first
-- refresh of every existing event useless on removals.

ALTER TABLE event_tracks ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual';

UPDATE event_tracks SET origin = CASE
    WHEN spotify_track_id IS NOT NULL AND spotify_track_id != '' THEN 'playlist'
    WHEN staging_file_path IS NOT NULL AND staging_file_path != '' THEN 'adopted'
    ELSE 'manual'
END;
