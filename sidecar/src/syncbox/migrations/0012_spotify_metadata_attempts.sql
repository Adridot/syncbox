-- Retry unavailable history metadata fairly across bounded refreshes and restarts.
ALTER TABLE plays ADD COLUMN spotify_metadata_attempts INTEGER NOT NULL DEFAULT 0;
