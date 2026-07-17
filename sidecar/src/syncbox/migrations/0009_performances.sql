-- 0009: performance history ("Prestations", owner-approved 17/07/2026).
-- plays is an append-only archive of Rekordbox djmdSongHistory rows keyed by
-- their cloud-stable UUID: once ingested a play survives here even if
-- Rekordbox later soft-deletes or re-merges its history. performances are
-- DERIVED (deterministic re-clustering in performances.py) except the two
-- user fields name/hidden, anchored on the cluster's first play UUID so a
-- rename survives rebuilds.

CREATE TABLE plays (
    uuid TEXT PRIMARY KEY,
    rb_history_id TEXT NOT NULL,
    rb_history_name TEXT NOT NULL DEFAULT '',
    content_id TEXT,
    track_no INTEGER,
    title TEXT,
    artist TEXT,
    spotify_track_id TEXT,
    played_at TEXT NOT NULL,
    performance_id INTEGER,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;

CREATE INDEX plays_played_at ON plays (played_at);
CREATE INDEX plays_performance ON plays (performance_id);

CREATE TABLE performances (
    id INTEGER PRIMARY KEY,
    anchor_uuid TEXT NOT NULL UNIQUE,
    name TEXT,
    hidden INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    track_count INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 1,
    cuts TEXT NOT NULL DEFAULT '[]',
    -- 1 = play timestamps are the import moment, not the gig (USB/CDJ
    -- history import writes whole sessions in seconds); track ORDER is real
    bulk_import INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
) STRICT;
