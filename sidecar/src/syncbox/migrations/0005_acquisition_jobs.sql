-- 0005: optional Deezer acquisition jobs.

CREATE TABLE acquisition_jobs (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'deezer',
    scope TEXT NOT NULL CHECK (scope IN ('library', 'event', 'collection')),
    ref TEXT NOT NULL,
    title TEXT,
    artist TEXT,
    isrc TEXT,
    status TEXT NOT NULL,
    output_path TEXT,
    stored_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;
