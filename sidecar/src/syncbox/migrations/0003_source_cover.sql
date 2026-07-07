-- 0003: Spotify cover art on followed sources (owner feedback 2026-07-07:
-- covers everywhere a playlist is displayed). Set at follow time from the
-- picker/preview payload and refreshed on every sync.
ALTER TABLE sources ADD COLUMN cover_url TEXT;
