-- 0002: domain tables (SPEC-UNIFIED section 4).
-- No tag_rules table (D9), no dead tables (D25). Tags are JSON arrays of
-- MyTag names; Rekordbox-side state stays in master.db, never duplicated
-- here. prior_status backs the D22 restore-unignore rule.

CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    spotify_playlist_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    snapshot_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;

CREATE TABLE library_tracks (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    spotify_track_id TEXT NOT NULL,
    title TEXT,
    artist TEXT,
    duration_ms INTEGER,
    isrc TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    content_id TEXT,
    match_method TEXT,
    confidence INTEGER,
    staging_file_path TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    prior_status TEXT,
    updated_at TEXT,
    UNIQUE (source_id, spotify_track_id)
) STRICT;

CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    snapshot_id TEXT,
    stats TEXT NOT NULL DEFAULT '{}'
) STRICT;

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    default_tag TEXT NOT NULL,
    spotify_playlist_id TEXT,
    staging_dir TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    applied_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;

CREATE TABLE event_tracks (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    spotify_track_id TEXT,
    title TEXT,
    artist TEXT,
    duration_ms INTEGER,
    isrc TEXT,
    status TEXT NOT NULL DEFAULT 'missing',
    content_id TEXT,
    confidence INTEGER,
    staging_file_path TEXT,
    added_after_apply INTEGER NOT NULL DEFAULT 0,
    prior_status TEXT,
    updated_at TEXT
) STRICT;

CREATE TABLE dismissed_duplicate_groups (
    group_key TEXT PRIMARY KEY,
    dismissed_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;

CREATE TABLE untagged_patterns (
    id INTEGER PRIMARY KEY,
    pattern TEXT NOT NULL
) STRICT;
