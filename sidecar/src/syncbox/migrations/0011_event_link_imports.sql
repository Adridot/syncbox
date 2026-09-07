-- Durable previews and exact source intent are additive to legacy event/jobs.
CREATE TABLE event_link_imports (
    id TEXT PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    request_token TEXT NOT NULL,
    request_url TEXT NOT NULL,
    source_provider TEXT NOT NULL CHECK (source_provider IN ('spotify', 'deezer', 'youtube', 'soundcloud')),
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    canonical_url TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'resolving', 'ready', 'failed', 'committed', 'dismissed')),
    manifest TEXT CHECK (manifest IS NULL OR (json_valid(manifest) AND length(CAST(manifest AS BLOB)) <= 4194304)),
    selection TEXT,
    result TEXT,
    error TEXT,
    claimed_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (event_id, request_token)
) STRICT;

CREATE INDEX event_link_imports_queue ON event_link_imports (state, created_at);
ALTER TABLE event_tracks ADD COLUMN source_provider TEXT;
ALTER TABLE event_tracks ADD COLUMN source_item_id TEXT;
ALTER TABLE event_tracks ADD COLUMN source_url TEXT;
ALTER TABLE event_tracks ADD COLUMN source_import_id TEXT REFERENCES event_link_imports (id);
ALTER TABLE event_tracks ADD COLUMN source_position INTEGER;
ALTER TABLE event_tracks ADD COLUMN selected_local_path TEXT;
ALTER TABLE event_tracks ADD COLUMN selected_local_sha256 TEXT;
CREATE INDEX event_tracks_source_identity ON event_tracks (event_id, source_provider, source_item_id);

UPDATE event_tracks SET source_provider = 'spotify', source_item_id = spotify_track_id,
    source_url = 'https://open.spotify.com/track/' || spotify_track_id
WHERE spotify_track_id IS NOT NULL AND spotify_track_id != '';

ALTER TABLE acquisition_jobs ADD COLUMN source_selector TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN effective_source_item_id TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN source_properties TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN output_properties TEXT;
ALTER TABLE acquisition_jobs ADD COLUMN processing TEXT;
