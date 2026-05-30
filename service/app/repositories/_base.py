from __future__ import annotations

import sqlite3
from pathlib import Path

from ._mappers import utc_now


class BaseRepository:
    """Connection + schema migrations shared by all repository mixins."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tag_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_playlist_id TEXT NOT NULL UNIQUE,
                    source_playlist_name TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS spotify_tracks (
                    id TEXT PRIMARY KEY,
                    uri TEXT NOT NULL,
                    isrc TEXT,
                    title TEXT NOT NULL,
                    artists_json TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rekordbox_tracks (
                    content_id TEXT PRIMARY KEY,
                    file_path TEXT,
                    isrc TEXT,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    protected INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS track_links (
                    spotify_track_id TEXT,
                    rekordbox_content_id TEXT,
                    file_path TEXT,
                    match_method TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (spotify_track_id, rekordbox_content_id)
                );

                CREATE TABLE IF NOT EXISTS event_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_name TEXT NOT NULL,
                    spotify_playlist_id TEXT NOT NULL,
                    spotify_snapshot_id TEXT,
                    default_tag TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_name TEXT NOT NULL,
                    event_slug TEXT NOT NULL,
                    spotify_playlist_id TEXT NOT NULL,
                    spotify_playlist_name TEXT NOT NULL,
                    spotify_snapshot_id TEXT,
                    default_tag TEXT NOT NULL,
                    status TEXT NOT NULL,
                    event_dir TEXT NOT NULL,
                    audio_dir TEXT NOT NULL,
                    playlist_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS event_import_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    spotify_track_id TEXT NOT NULL,
                    spotify_uri TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artists_json TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    isrc TEXT,
                    status TEXT NOT NULL,
                    rekordbox_content_id TEXT,
                    match_method TEXT,
                    confidence INTEGER NOT NULL DEFAULT 0,
                    staging_file_path TEXT,
                    permanent INTEGER NOT NULL DEFAULT 0,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES event_imports(id) ON DELETE CASCADE,
                    UNIQUE(event_id, spotify_track_id)
                );

                CREATE TABLE IF NOT EXISTS event_staging_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    duration_ms INTEGER,
                    isrc TEXT,
                    matched_spotify_track_id TEXT,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES event_imports(id) ON DELETE CASCADE,
                    UNIQUE(event_id, file_path)
                );

                CREATE TABLE IF NOT EXISTS event_acquisition_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    spotify_track_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    deezer_track_id TEXT,
                    status TEXT NOT NULL,
                    confidence INTEGER NOT NULL DEFAULT 0,
                    match_method TEXT,
                    download_id TEXT,
                    output_dir TEXT,
                    error TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES event_imports(id) ON DELETE CASCADE,
                    UNIQUE(event_id, spotify_track_id, provider)
                );

                CREATE TABLE IF NOT EXISTS tag_playlist_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_name TEXT NOT NULL UNIQUE,
                    spotify_playlist_id TEXT NOT NULL,
                    spotify_playlist_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    spotify_track_id TEXT,
                    rekordbox_content_id TEXT,
                    file_path TEXT,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS library_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spotify_playlist_id TEXT NOT NULL UNIQUE,
                    spotify_playlist_name TEXT NOT NULL,
                    spotify_snapshot_id TEXT,
                    image_url TEXT,
                    track_count INTEGER NOT NULL DEFAULT 0,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_synced_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS library_source_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    spotify_snapshot_id TEXT,
                    status TEXT NOT NULL,
                    total_tracks INTEGER NOT NULL DEFAULT 0,
                    new_tracks INTEGER NOT NULL DEFAULT 0,
                    removed_tracks INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES library_sources(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS library_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    spotify_track_id TEXT NOT NULL,
                    spotify_uri TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artists_json TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    isrc TEXT,
                    status TEXT NOT NULL,
                    rekordbox_content_id TEXT,
                    match_method TEXT,
                    confidence INTEGER NOT NULL DEFAULT 0,
                    staging_file_path TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES library_sources(id) ON DELETE CASCADE,
                    UNIQUE(source_id, spotify_track_id)
                );

                CREATE TABLE IF NOT EXISTS library_acquisition_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    spotify_track_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    deezer_track_id TEXT,
                    status TEXT NOT NULL,
                    confidence INTEGER NOT NULL DEFAULT 0,
                    match_method TEXT,
                    download_id TEXT,
                    output_dir TEXT,
                    error TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES library_sources(id) ON DELETE CASCADE,
                    UNIQUE(source_id, spotify_track_id, provider)
                );
                """
            )
            now = utc_now()
            connection.execute(
                """
                INSERT INTO schema_migrations (version, applied_at)
                VALUES (1, ?)
                ON CONFLICT(version) DO NOTHING
                """,
                (now,),
            )
            # Incremental migrations: add columns not present in the initial schema
            existing_cols = {
                r[1]
                for r in connection.execute("PRAGMA table_info(library_tracks)").fetchall()
            }
            if "pending_deezer_track_id" not in existing_cols:
                connection.execute(
                    "ALTER TABLE library_tracks ADD COLUMN pending_deezer_track_id TEXT"
                )
            if "pending_deezer_isrc" not in existing_cols:
                connection.execute(
                    "ALTER TABLE library_tracks ADD COLUMN pending_deezer_isrc TEXT"
                )

            connection.execute(
                """
                INSERT INTO library_sources (
                    spotify_playlist_id,
                    spotify_playlist_name,
                    spotify_snapshot_id,
                    image_url,
                    track_count,
                    tags_json,
                    enabled,
                    status,
                    created_at,
                    updated_at
                )
                SELECT source_playlist_id,
                       source_playlist_name,
                       NULL,
                       NULL,
                       0,
                       tags_json,
                       enabled,
                       'pending',
                       created_at,
                       updated_at
                FROM tag_rules
                WHERE true
                ON CONFLICT(spotify_playlist_id) DO UPDATE SET
                    spotify_playlist_name = excluded.spotify_playlist_name,
                    tags_json = excluded.tags_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """
            )
