-- 0006: record the actual downloaded quality (streamrip scale: 0 = MP3 128,
-- 1 = MP3 320) so a lower-quality fallback is visible in the UI.

ALTER TABLE acquisition_jobs ADD COLUMN quality INTEGER;
