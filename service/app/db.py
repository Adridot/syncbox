from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    AcquisitionJob,
    AppSettings,
    EventReview,
    EventSummary,
    EventTrackReview,
    GlobalAcquisitionJob,
    LibraryReview,
    LibrarySource,
    LibrarySourceIn,
    LibraryTrackReview,
    StagingFile,
    SyncProposal,
    TagPlaylistMapping,
    TagPlaylistMappingIn,
    TagRule,
    TagRuleIn,
)


class LocalDatabase:
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

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else default

    def get_app_settings(self, defaults: AppSettings) -> AppSettings:
        return AppSettings(
            spotifyClientId=self.get_setting(
                "spotify_client_id", defaults.spotify_client_id
            ),
            spotifyRedirectUri=self.get_setting(
                "spotify_redirect_uri", defaults.spotify_redirect_uri
            ),
            rekordboxDatabaseDir=self.get_setting(
                "rekordbox_database_dir", defaults.rekordbox_database_dir
            ),
            storageRoot=self.get_setting("storage_root", defaults.storage_root),
            apiPort=int(self.get_setting("api_port", str(defaults.api_port))),
        )

    def save_app_settings(self, settings: AppSettings) -> AppSettings:
        values = {
            "spotify_client_id": settings.spotify_client_id,
            "spotify_redirect_uri": settings.spotify_redirect_uri,
            "rekordbox_database_dir": settings.rekordbox_database_dir,
            "storage_root": settings.storage_root,
            "api_port": str(settings.api_port),
        }
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                values.items(),
            )
        return settings

    def list_tag_rules(self) -> list[TagRule]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_playlist_id, source_playlist_name, tags_json, enabled
                FROM tag_rules
                ORDER BY source_playlist_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            TagRule(
                id=int(row["id"]),
                sourcePlaylistId=str(row["source_playlist_id"]),
                sourcePlaylistName=str(row["source_playlist_name"]),
                tags=json.loads(str(row["tags_json"])),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def upsert_tag_rule(self, rule: TagRuleIn) -> TagRule:
        now = utc_now()
        tags_json = json.dumps(rule.tags)
        with self.connect() as connection:
            if rule.id:
                connection.execute(
                    """
                    UPDATE tag_rules
                    SET source_playlist_id = ?,
                        source_playlist_name = ?,
                        tags_json = ?,
                        enabled = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        rule.source_playlist_id,
                        rule.source_playlist_name,
                        tags_json,
                        int(rule.enabled),
                        now,
                        rule.id,
                    ),
                )
                next_id = rule.id
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO tag_rules (
                        source_playlist_id,
                        source_playlist_name,
                        tags_json,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_playlist_id) DO UPDATE SET
                        source_playlist_name = excluded.source_playlist_name,
                        tags_json = excluded.tags_json,
                        enabled = excluded.enabled,
                        updated_at = excluded.updated_at
                    RETURNING id
                    """,
                    (
                        rule.source_playlist_id,
                        rule.source_playlist_name,
                        tags_json,
                        int(rule.enabled),
                        now,
                        now,
                    ),
                )
                next_id = int(cursor.fetchone()["id"])

        return TagRule(id=next_id, **rule.model_dump(by_alias=True, exclude={"id"}))

    def list_tag_playlist_mappings(self) -> list[TagPlaylistMapping]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, tag_name, spotify_playlist_id, spotify_playlist_name, enabled
                FROM tag_playlist_mappings
                ORDER BY tag_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            TagPlaylistMapping(
                id=int(row["id"]),
                tagName=str(row["tag_name"]),
                spotifyPlaylistId=str(row["spotify_playlist_id"]),
                spotifyPlaylistName=str(row["spotify_playlist_name"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def upsert_tag_playlist_mapping(
        self, mapping: TagPlaylistMappingIn
    ) -> TagPlaylistMapping:
        now = utc_now()
        with self.connect() as connection:
            if mapping.id:
                connection.execute(
                    """
                    UPDATE tag_playlist_mappings
                    SET tag_name = ?,
                        spotify_playlist_id = ?,
                        spotify_playlist_name = ?,
                        enabled = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        mapping.tag_name.strip(),
                        mapping.spotify_playlist_id.strip(),
                        mapping.spotify_playlist_name.strip(),
                        int(mapping.enabled),
                        now,
                        mapping.id,
                    ),
                )
                next_id = mapping.id
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO tag_playlist_mappings (
                        tag_name,
                        spotify_playlist_id,
                        spotify_playlist_name,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tag_name) DO UPDATE SET
                        spotify_playlist_id = excluded.spotify_playlist_id,
                        spotify_playlist_name = excluded.spotify_playlist_name,
                        enabled = excluded.enabled,
                        updated_at = excluded.updated_at
                    RETURNING id
                    """,
                    (
                        mapping.tag_name.strip(),
                        mapping.spotify_playlist_id.strip(),
                        mapping.spotify_playlist_name.strip(),
                        int(mapping.enabled),
                        now,
                        now,
                    ),
                )
                next_id = int(cursor.fetchone()["id"])
        return TagPlaylistMapping(
            id=next_id, **mapping.model_dump(by_alias=True, exclude={"id"})
        )

    def list_library_sources(self) -> list[LibrarySource]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT library_sources.*,
                       SUM(CASE WHEN library_tracks.status = 'new' THEN 1 ELSE 0 END)
                           AS new_track_count,
                       SUM(CASE WHEN library_tracks.status IN ('new', 'missing', 'conflict')
                           THEN 1 ELSE 0 END) AS pending_track_count,
                       SUM(CASE WHEN library_tracks.status = 'ready' THEN 1 ELSE 0 END)
                           AS ready_track_count,
                       SUM(CASE WHEN library_tracks.status = 'imported' THEN 1 ELSE 0 END)
                           AS imported_track_count,
                       SUM(CASE WHEN library_tracks.status = 'conflict' THEN 1 ELSE 0 END)
                           AS conflict_track_count
                FROM library_sources
                LEFT JOIN library_tracks
                  ON library_tracks.source_id = library_sources.id
                GROUP BY library_sources.id
                ORDER BY library_sources.spotify_playlist_name COLLATE NOCASE
                """
            ).fetchall()
        return [library_source_from_row(row) for row in rows]

    def get_library_source(self, source_id: int) -> LibrarySource | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT library_sources.*,
                       SUM(CASE WHEN library_tracks.status = 'new' THEN 1 ELSE 0 END)
                           AS new_track_count,
                       SUM(CASE WHEN library_tracks.status IN ('new', 'missing', 'conflict')
                           THEN 1 ELSE 0 END) AS pending_track_count,
                       SUM(CASE WHEN library_tracks.status = 'ready' THEN 1 ELSE 0 END)
                           AS ready_track_count,
                       SUM(CASE WHEN library_tracks.status = 'imported' THEN 1 ELSE 0 END)
                           AS imported_track_count,
                       SUM(CASE WHEN library_tracks.status = 'conflict' THEN 1 ELSE 0 END)
                           AS conflict_track_count
                FROM library_sources
                LEFT JOIN library_tracks
                  ON library_tracks.source_id = library_sources.id
                WHERE library_sources.id = ?
                GROUP BY library_sources.id
                """,
                (source_id,),
            ).fetchone()
        return library_source_from_row(row) if row else None


    def upsert_library_source(self, source: LibrarySourceIn) -> LibrarySource:
        now = utc_now()
        tags_json = json.dumps(source.tags)
        with self.connect() as connection:
            if source.id:
                connection.execute(
                    """
                    UPDATE library_sources
                    SET spotify_playlist_id = ?,
                        spotify_playlist_name = ?,
                        spotify_snapshot_id = ?,
                        image_url = ?,
                        track_count = ?,
                        tags_json = ?,
                        enabled = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        source.spotify_playlist_id.strip(),
                        source.spotify_playlist_name.strip(),
                        source.spotify_snapshot_id,
                        source.image_url,
                        int(source.track_count),
                        tags_json,
                        int(source.enabled),
                        now,
                        source.id,
                    ),
                )
                next_id = source.id
            else:
                cursor = connection.execute(
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    ON CONFLICT(spotify_playlist_id) DO UPDATE SET
                        spotify_playlist_name = excluded.spotify_playlist_name,
                        spotify_snapshot_id = excluded.spotify_snapshot_id,
                        image_url = excluded.image_url,
                        track_count = excluded.track_count,
                        tags_json = excluded.tags_json,
                        enabled = excluded.enabled,
                        updated_at = excluded.updated_at
                    RETURNING id
                    """,
                    (
                        source.spotify_playlist_id.strip(),
                        source.spotify_playlist_name.strip(),
                        source.spotify_snapshot_id,
                        source.image_url,
                        int(source.track_count),
                        tags_json,
                        int(source.enabled),
                        now,
                        now,
                    ),
                )
                next_id = int(cursor.fetchone()["id"])
        saved = self.get_library_source(next_id)
        if saved is None:
            raise RuntimeError("Library source could not be saved.")
        return saved

    def update_library_source_sync(
        self,
        source_id: int,
        *,
        spotify_playlist_name: str,
        spotify_snapshot_id: str | None,
        image_url: str | None,
        track_count: int,
        status: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE library_sources
                SET spotify_playlist_name = ?,
                    spotify_snapshot_id = ?,
                    image_url = ?,
                    track_count = ?,
                    status = ?,
                    last_synced_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    spotify_playlist_name,
                    spotify_snapshot_id,
                    image_url,
                    int(track_count),
                    status,
                    utc_now(),
                    utc_now(),
                    source_id,
                ),
            )

    def insert_library_source_run(
        self,
        source_id: int,
        *,
        spotify_snapshot_id: str | None,
        status: str,
        total_tracks: int,
        new_tracks: int,
        removed_tracks: int,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO library_source_runs (
                    source_id,
                    spotify_snapshot_id,
                    status,
                    total_tracks,
                    new_tracks,
                    removed_tracks,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    spotify_snapshot_id,
                    status,
                    int(total_tracks),
                    int(new_tracks),
                    int(removed_tracks),
                    utc_now(),
                ),
            )

    def upsert_library_tracks(
        self,
        source_id: int,
        tracks: Iterable[dict[str, Any]],
    ) -> int:
        rows = []
        now = utc_now()
        for track in tracks:
            rows.append(
                (
                    source_id,
                    track["spotify_track_id"],
                    track["spotify_uri"],
                    track["title"],
                    json.dumps(track["artists"]),
                    track["duration_ms"],
                    track.get("isrc"),
                    track["status"],
                    track.get("rekordbox_content_id"),
                    track.get("match_method"),
                    int(track.get("confidence", 0)),
                    track.get("staging_file_path"),
                    json.dumps(track.get("tags", [])),
                    track["reason"],
                    json.dumps(track.get("payload", {})),
                    now,
                    now,
                )
            )
        if not rows:
            return 0
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO library_tracks (
                    source_id,
                    spotify_track_id,
                    spotify_uri,
                    title,
                    artists_json,
                    duration_ms,
                    isrc,
                    status,
                    rekordbox_content_id,
                    match_method,
                    confidence,
                    staging_file_path,
                    tags_json,
                    reason,
                    payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, spotify_track_id) DO UPDATE SET
                    spotify_uri = excluded.spotify_uri,
                    title = excluded.title,
                    artists_json = excluded.artists_json,
                    duration_ms = excluded.duration_ms,
                    isrc = excluded.isrc,
                    status = excluded.status,
                    rekordbox_content_id = excluded.rekordbox_content_id,
                    match_method = excluded.match_method,
                    confidence = excluded.confidence,
                    staging_file_path = excluded.staging_file_path,
                    tags_json = excluded.tags_json,
                    reason = excluded.reason,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def update_library_track(
        self,
        source_id: int,
        spotify_track_id: str,
        **values: Any,
    ) -> None:
        allowed = {
            "status",
            "rekordbox_content_id",
            "match_method",
            "confidence",
            "staging_file_path",
            "tags_json",
            "reason",
            "payload_json",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = [*updates.values(), source_id, spotify_track_id]
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE library_tracks
                SET {assignments}
                WHERE source_id = ? AND spotify_track_id = ?
                """,
                params,
            )

    def mark_library_tracks_imported(
        self,
        source_id: int,
        spotify_track_ids: list[str],
    ) -> None:
        if not spotify_track_ids:
            return
        placeholders = ",".join("?" for _ in spotify_track_ids)
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE library_tracks
                SET status = 'imported',
                    reason = 'Imported to Rekordbox.',
                    updated_at = ?
                WHERE source_id = ?
                  AND spotify_track_id IN ({placeholders})
                """,
                [utc_now(), source_id, *spotify_track_ids],
            )

    def get_library_review(self, source_id: int) -> LibraryReview | None:
        source = self.get_library_source(source_id)
        if source is None:
            return None
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM library_tracks
                WHERE source_id = ?
                ORDER BY
                    CASE status
                        WHEN 'new' THEN 0
                        WHEN 'conflict' THEN 1
                        WHEN 'missing' THEN 2
                        WHEN 'ready' THEN 3
                        WHEN 'matched' THEN 4
                        ELSE 5
                    END,
                    title COLLATE NOCASE
                """,
                (source_id,),
            ).fetchall()
        tracks = [library_track_from_row(row) for row in rows]
        counts = {
            "new": 0,
            "matched": 0,
            "missing": 0,
            "ready": 0,
            "imported": 0,
            "ignored": 0,
            "conflict": 0,
            "removed_from_source": 0,
        }
        for track in tracks:
            if track.status in counts:
                counts[track.status] += 1
        return LibraryReview(
            source=source,
            totalTracks=len(tracks),
            newTracks=counts["new"],
            matchedTracks=counts["matched"],
            missingTracks=counts["missing"],
            readyTracks=counts["ready"],
            importedTracks=counts["imported"],
            ignoredTracks=counts["ignored"],
            conflictTracks=counts["conflict"],
            removedTracks=counts["removed_from_source"],
            tracks=tracks,
        )

    def upsert_library_acquisition_job(
        self,
        source_id: int,
        job: dict[str, Any],
    ) -> AcquisitionJob:
        now = utc_now()
        payload = job.get("payload", {})
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO library_acquisition_jobs (
                    source_id,
                    spotify_track_id,
                    provider,
                    deezer_track_id,
                    status,
                    confidence,
                    match_method,
                    download_id,
                    output_dir,
                    error,
                    payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, spotify_track_id, provider) DO UPDATE SET
                    deezer_track_id = excluded.deezer_track_id,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    match_method = excluded.match_method,
                    download_id = excluded.download_id,
                    output_dir = excluded.output_dir,
                    error = excluded.error,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                RETURNING *
                """,
                (
                    source_id,
                    job["spotify_track_id"],
                    job.get("provider", "deemix"),
                    job.get("deezer_track_id"),
                    job["status"],
                    int(job.get("confidence", 0)),
                    job.get("match_method"),
                    job.get("download_id"),
                    job.get("output_dir"),
                    job.get("error"),
                    json.dumps(payload if isinstance(payload, dict) else {}),
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
        return acquisition_job_from_row(row, source_key="source_id")

    def list_library_acquisition_jobs(
        self,
        source_id: int,
        provider: str | None = None,
    ) -> list[AcquisitionJob]:
        query = """
            SELECT *
            FROM library_acquisition_jobs
            WHERE source_id = ?
        """
        params: list[Any] = [source_id]
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        query += " ORDER BY id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [acquisition_job_from_row(row, source_key="source_id") for row in rows]

    def get_library_acquisition_job(
        self,
        source_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
    ) -> AcquisitionJob | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM library_acquisition_jobs
                WHERE source_id = ?
                  AND spotify_track_id = ?
                  AND provider = ?
                """,
                (source_id, spotify_track_id, provider),
            ).fetchone()
        return acquisition_job_from_row(row, source_key="source_id") if row else None

    def update_library_acquisition_job(
        self,
        source_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
        **values: Any,
    ) -> None:
        if "payload" in values:
            payload = values.pop("payload")
            values["payload_json"] = json.dumps(payload if isinstance(payload, dict) else {})
        allowed = {
            "deezer_track_id",
            "status",
            "confidence",
            "match_method",
            "download_id",
            "output_dir",
            "error",
            "payload_json",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = [*updates.values(), source_id, spotify_track_id, provider]
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE library_acquisition_jobs
                SET {assignments}
                WHERE source_id = ?
                  AND spotify_track_id = ?
                  AND provider = ?
                """,
                params,
            )

    def list_global_acquisition_jobs(
        self,
        *,
        scope: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> list[GlobalAcquisitionJob]:
        queries: list[str] = []
        params: list[Any] = []
        if scope in (None, "event"):
            event_filters = ""
            event_params: list[Any] = []
            if status:
                event_filters += " AND jobs.status = ?"
                event_params.append(status)
            if source:
                event_filters += " AND event_imports.event_name LIKE ?"
                event_params.append(f"%{source}%")
            queries.append(
                f"""
                SELECT jobs.id,
                       'event' AS scope,
                       jobs.event_id,
                       NULL AS source_id,
                       event_imports.event_name AS source_name,
                       jobs.spotify_track_id,
                       event_import_tracks.title AS track_title,
                       event_import_tracks.artists_json,
                       jobs.provider,
                       jobs.deezer_track_id,
                       jobs.status,
                       jobs.confidence,
                       jobs.match_method,
                       jobs.download_id,
                       jobs.output_dir,
                       jobs.error,
                       jobs.updated_at
                FROM event_acquisition_jobs jobs
                JOIN event_imports ON event_imports.id = jobs.event_id
                LEFT JOIN event_import_tracks
                  ON event_import_tracks.event_id = jobs.event_id
                 AND event_import_tracks.spotify_track_id = jobs.spotify_track_id
                WHERE 1 = 1{event_filters}
                """
            )
            params.extend(event_params)
        if scope in (None, "library"):
            library_filters = ""
            library_params: list[Any] = []
            if status:
                library_filters += " AND jobs.status = ?"
                library_params.append(status)
            if source:
                library_filters += " AND library_sources.spotify_playlist_name LIKE ?"
                library_params.append(f"%{source}%")
            queries.append(
                f"""
                SELECT jobs.id,
                       'library' AS scope,
                       NULL AS event_id,
                       jobs.source_id,
                       library_sources.spotify_playlist_name AS source_name,
                       jobs.spotify_track_id,
                       library_tracks.title AS track_title,
                       library_tracks.artists_json,
                       jobs.provider,
                       jobs.deezer_track_id,
                       jobs.status,
                       jobs.confidence,
                       jobs.match_method,
                       jobs.download_id,
                       jobs.output_dir,
                       jobs.error,
                       jobs.updated_at
                FROM library_acquisition_jobs jobs
                JOIN library_sources ON library_sources.id = jobs.source_id
                LEFT JOIN library_tracks
                  ON library_tracks.source_id = jobs.source_id
                 AND library_tracks.spotify_track_id = jobs.spotify_track_id
                WHERE 1 = 1{library_filters}
                """
            )
            params.extend(library_params)
        if not queries:
            return []
        query = " UNION ALL ".join(queries)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM ({query}) ORDER BY updated_at DESC LIMIT 500",
                params,
            ).fetchall()
        return [global_acquisition_job_from_row(row) for row in rows]

    def resolve_proposal(self, proposal_id: int, status: str) -> SyncProposal | None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE sync_proposals
                SET status = ?
                WHERE id = ?
                """,
                (status, proposal_id),
            )
        return self.get_proposal(proposal_id)

    def get_proposal(self, proposal_id: int) -> SyncProposal | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id,
                       proposal_type,
                       status,
                       spotify_track_id,
                       rekordbox_content_id,
                       file_path,
                       reason,
                       payload_json,
                       created_at
                FROM sync_proposals
                WHERE id = ?
                """,
                (proposal_id,),
            ).fetchone()
        return proposal_from_row(row) if row else None

    def create_event_import(self, event: dict[str, Any]) -> int:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO event_imports (
                    event_name,
                    event_slug,
                    spotify_playlist_id,
                    spotify_playlist_name,
                    spotify_snapshot_id,
                    default_tag,
                    status,
                    event_dir,
                    audio_dir,
                    playlist_path,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_name"],
                    event["event_slug"],
                    event["spotify_playlist_id"],
                    event["spotify_playlist_name"],
                    event.get("spotify_snapshot_id"),
                    event["default_tag"],
                    event.get("status", "review"),
                    event["event_dir"],
                    event["audio_dir"],
                    event["playlist_path"],
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def delete_event_import(self, event_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM event_acquisition_jobs WHERE event_id = ?",
                (event_id,),
            )
            connection.execute(
                "DELETE FROM event_staging_files WHERE event_id = ?",
                (event_id,),
            )
            connection.execute(
                "DELETE FROM event_import_tracks WHERE event_id = ?",
                (event_id,),
            )
            connection.execute(
                "DELETE FROM event_imports WHERE id = ?",
                (event_id,),
            )

    def upsert_event_tracks(self, event_id: int, tracks: Iterable[dict[str, Any]]) -> int:
        rows = []
        for track in tracks:
            rows.append(
                (
                    event_id,
                    track["spotify_track_id"],
                    track["spotify_uri"],
                    track["title"],
                    json.dumps(track["artists"]),
                    track["duration_ms"],
                    track.get("isrc"),
                    track["status"],
                    track.get("rekordbox_content_id"),
                    track.get("match_method"),
                    int(track.get("confidence", 0)),
                    track.get("staging_file_path"),
                    int(track.get("permanent", False)),
                    json.dumps(track.get("tags", [])),
                    track["reason"],
                    json.dumps(track.get("payload", {})),
                    utc_now(),
                )
            )
        if not rows:
            return 0
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO event_import_tracks (
                    event_id,
                    spotify_track_id,
                    spotify_uri,
                    title,
                    artists_json,
                    duration_ms,
                    isrc,
                    status,
                    rekordbox_content_id,
                    match_method,
                    confidence,
                    staging_file_path,
                    permanent,
                    tags_json,
                    reason,
                    payload_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, spotify_track_id) DO UPDATE SET
                    spotify_uri = excluded.spotify_uri,
                    title = excluded.title,
                    artists_json = excluded.artists_json,
                    duration_ms = excluded.duration_ms,
                    isrc = excluded.isrc,
                    status = excluded.status,
                    rekordbox_content_id = excluded.rekordbox_content_id,
                    match_method = excluded.match_method,
                    confidence = excluded.confidence,
                    staging_file_path = excluded.staging_file_path,
                    permanent = excluded.permanent,
                    tags_json = excluded.tags_json,
                    reason = excluded.reason,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def upsert_staging_files(self, event_id: int, files: Iterable[dict[str, Any]]) -> int:
        rows = []
        for file_info in files:
            rows.append(
                (
                    event_id,
                    file_info["file_path"],
                    file_info["title"],
                    file_info["artist"],
                    file_info.get("duration_ms"),
                    file_info.get("isrc"),
                    file_info.get("matched_spotify_track_id"),
                    file_info["status"],
                    utc_now(),
                )
            )
        if not rows:
            return 0
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO event_staging_files (
                    event_id,
                    file_path,
                    title,
                    artist,
                    duration_ms,
                    isrc,
                    matched_spotify_track_id,
                    status,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, file_path) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    duration_ms = excluded.duration_ms,
                    isrc = excluded.isrc,
                    matched_spotify_track_id = excluded.matched_spotify_track_id,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def replace_staging_files(
        self,
        event_id: int,
        files: Iterable[dict[str, Any]],
    ) -> int:
        rows = []
        for file_info in files:
            rows.append(
                (
                    event_id,
                    file_info["file_path"],
                    file_info["title"],
                    file_info["artist"],
                    file_info.get("duration_ms"),
                    file_info.get("isrc"),
                    file_info.get("matched_spotify_track_id"),
                    file_info["status"],
                    utc_now(),
                )
            )

        with self.connect() as connection:
            if rows:
                connection.executemany(
                    """
                    INSERT INTO event_staging_files (
                        event_id,
                        file_path,
                        title,
                        artist,
                        duration_ms,
                        isrc,
                        matched_spotify_track_id,
                        status,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id, file_path) DO UPDATE SET
                        title = excluded.title,
                        artist = excluded.artist,
                        duration_ms = excluded.duration_ms,
                        isrc = excluded.isrc,
                        matched_spotify_track_id = excluded.matched_spotify_track_id,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    rows,
                )
                placeholders = ",".join("?" for _ in rows)
                current_paths = [row[1] for row in rows]
                connection.execute(
                    f"""
                    DELETE FROM event_staging_files
                    WHERE event_id = ?
                      AND file_path NOT IN ({placeholders})
                    """,
                    [event_id, *current_paths],
                )
            else:
                connection.execute(
                    "DELETE FROM event_staging_files WHERE event_id = ?",
                    (event_id,),
                )
        return len(rows)

    def upsert_acquisition_job(
        self,
        event_id: int,
        job: dict[str, Any],
    ) -> AcquisitionJob:
        now = utc_now()
        payload = job.get("payload", {})
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO event_acquisition_jobs (
                    event_id,
                    spotify_track_id,
                    provider,
                    deezer_track_id,
                    status,
                    confidence,
                    match_method,
                    download_id,
                    output_dir,
                    error,
                    payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, spotify_track_id, provider) DO UPDATE SET
                    deezer_track_id = excluded.deezer_track_id,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    match_method = excluded.match_method,
                    download_id = excluded.download_id,
                    output_dir = excluded.output_dir,
                    error = excluded.error,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                RETURNING *
                """,
                (
                    event_id,
                    job["spotify_track_id"],
                    job.get("provider", "deemix"),
                    job.get("deezer_track_id"),
                    job["status"],
                    int(job.get("confidence", 0)),
                    job.get("match_method"),
                    job.get("download_id"),
                    job.get("output_dir"),
                    job.get("error"),
                    json.dumps(payload if isinstance(payload, dict) else {}),
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
        return acquisition_job_from_row(row)

    def list_acquisition_jobs(
        self,
        event_id: int,
        provider: str | None = None,
    ) -> list[AcquisitionJob]:
        query = """
            SELECT *
            FROM event_acquisition_jobs
            WHERE event_id = ?
        """
        params: list[Any] = [event_id]
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        query += " ORDER BY id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [acquisition_job_from_row(row) for row in rows]

    def get_acquisition_job(
        self,
        event_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
    ) -> AcquisitionJob | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM event_acquisition_jobs
                WHERE event_id = ?
                  AND spotify_track_id = ?
                  AND provider = ?
                """,
                (event_id, spotify_track_id, provider),
            ).fetchone()
        return acquisition_job_from_row(row) if row else None

    def update_acquisition_job(
        self,
        event_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
        **values: Any,
    ) -> None:
        if "payload" in values:
            payload = values.pop("payload")
            values["payload_json"] = json.dumps(payload if isinstance(payload, dict) else {})

        allowed = {
            "deezer_track_id",
            "status",
            "confidence",
            "match_method",
            "download_id",
            "output_dir",
            "error",
            "payload_json",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = [*updates.values(), event_id, spotify_track_id, provider]
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE event_acquisition_jobs
                SET {assignments}
                WHERE event_id = ?
                  AND spotify_track_id = ?
                  AND provider = ?
                """,
                params,
            )

    def update_event_track(self, event_id: int, spotify_track_id: str, **values: Any) -> None:
        allowed = {
            "status",
            "rekordbox_content_id",
            "match_method",
            "confidence",
            "staging_file_path",
            "reason",
            "payload_json",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = [*updates.values(), event_id, spotify_track_id]
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE event_import_tracks
                SET {assignments}
                WHERE event_id = ? AND spotify_track_id = ?
                """,
                params,
            )

    def update_event_status(self, event_id: int, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE event_imports
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, utc_now(), event_id),
            )

    def mark_event_tracks_applied(self, event_id: int, spotify_track_ids: list[str]) -> None:
        if not spotify_track_ids:
            return
        placeholders = ",".join("?" for _ in spotify_track_ids)
        params = [event_id, *spotify_track_ids]
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE event_import_tracks
                SET status = 'applied',
                    reason = 'Applied to Rekordbox.',
                    updated_at = ?
                WHERE event_id = ?
                  AND spotify_track_id IN ({placeholders})
                """,
                [utc_now(), *params],
            )

    def list_event_summaries(self) -> list[EventSummary]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT event_imports.id,
                       event_imports.event_name,
                       event_imports.spotify_playlist_name,
                       event_imports.status,
                       event_imports.created_at,
                       COUNT(event_import_tracks.id) AS total_tracks,
                       SUM(CASE WHEN event_import_tracks.status = 'ready' THEN 1 ELSE 0 END)
                           AS ready_tracks
                FROM event_imports
                LEFT JOIN event_import_tracks
                  ON event_import_tracks.event_id = event_imports.id
                GROUP BY event_imports.id
                ORDER BY event_imports.id DESC
                LIMIT 50
                """
            ).fetchall()
        return [
            EventSummary(
                id=int(row["id"]),
                eventName=str(row["event_name"]),
                spotifyPlaylistName=str(row["spotify_playlist_name"]),
                status=str(row["status"]),
                totalTracks=int(row["total_tracks"] or 0),
                readyTracks=int(row["ready_tracks"] or 0),
                createdAt=str(row["created_at"]),
            )
            for row in rows
        ]

    def get_event_review(self, event_id: int) -> EventReview | None:
        with self.connect() as connection:
            event = connection.execute(
                "SELECT * FROM event_imports WHERE id = ?",
                (event_id,),
            ).fetchone()
            if not event:
                return None
            track_rows = connection.execute(
                """
                SELECT *
                FROM event_import_tracks
                WHERE event_id = ?
                ORDER BY id
                """,
                (event_id,),
            ).fetchall()
            file_rows = connection.execute(
                """
                SELECT *
                FROM event_staging_files
                WHERE event_id = ?
                ORDER BY title COLLATE NOCASE, file_path
                """,
                (event_id,),
            ).fetchall()

        tracks = []
        for row in track_rows:
            payload = parse_json_object(row["payload_json"])
            rekordbox_payload = payload.get("rekordbox", {})
            if not isinstance(rekordbox_payload, dict):
                rekordbox_payload = {}
            tracks.append(
                EventTrackReview(
                    id=int(row["id"]),
                    eventId=int(row["event_id"]),
                    spotifyTrackId=str(row["spotify_track_id"]),
                    spotifyUri=str(row["spotify_uri"]),
                    title=str(row["title"]),
                    artists=json.loads(str(row["artists_json"])),
                    durationMs=int(row["duration_ms"]),
                    isrc=row["isrc"],
                    status=str(row["status"]),
                    rekordboxContentId=row["rekordbox_content_id"],
                    rekordboxTitle=optional_string(rekordbox_payload.get("title")),
                    rekordboxArtist=optional_string(rekordbox_payload.get("artist")),
                    rekordboxFilePath=optional_string(rekordbox_payload.get("filePath")),
                    matchMethod=row["match_method"],
                    confidence=int(row["confidence"] or 0),
                    stagingFilePath=row["staging_file_path"],
                    reason=str(row["reason"]),
                )
            )
        staging_files = [
            StagingFile(
                id=int(row["id"]),
                eventId=int(row["event_id"]),
                filePath=str(row["file_path"]),
                title=str(row["title"]),
                artist=str(row["artist"]),
                durationMs=row["duration_ms"],
                isrc=row["isrc"],
                matchedSpotifyTrackId=row["matched_spotify_track_id"],
                status=str(row["status"]),
            )
            for row in file_rows
        ]
        counts = {
            "matched": 0,
            "missing": 0,
            "ambiguous": 0,
            "ready": 0,
            "applied": 0,
            "ignored": 0,
        }
        for track in tracks:
            if track.status in counts:
                counts[track.status] += 1
        return EventReview(
            id=int(event["id"]),
            eventName=str(event["event_name"]),
            eventSlug=str(event["event_slug"]),
            spotifyPlaylistId=str(event["spotify_playlist_id"]),
            spotifyPlaylistName=str(event["spotify_playlist_name"]),
            spotifySnapshotId=event["spotify_snapshot_id"],
            defaultTag=str(event["default_tag"]),
            status=str(event["status"]),
            eventDir=str(event["event_dir"]),
            audioDir=str(event["audio_dir"]),
            playlistPath=str(event["playlist_path"]),
            totalTracks=len(tracks),
            matchedTracks=counts["matched"],
            missingTracks=counts["missing"],
            ambiguousTracks=counts["ambiguous"],
            readyTracks=counts["ready"],
            appliedTracks=counts["applied"],
            ignoredTracks=counts["ignored"],
            tracks=tracks,
            stagingFiles=staging_files,
        )

    def insert_proposals(self, proposals: Iterable[dict[str, Any]]) -> int:
        rows = []
        for proposal in proposals:
            rows.append(
                (
                    proposal["proposal_type"],
                    proposal.get("status", "pending"),
                    proposal.get("spotify_track_id"),
                    proposal.get("rekordbox_content_id"),
                    proposal.get("file_path"),
                    proposal["reason"],
                    json.dumps(proposal.get("payload", {})),
                    utc_now(),
                )
            )
        if not rows:
            return 0

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO sync_proposals (
                    proposal_type,
                    status,
                    spotify_track_id,
                    rekordbox_content_id,
                    file_path,
                    reason,
                    payload_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def list_proposals(self) -> list[SyncProposal]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id,
                       proposal_type,
                       status,
                       spotify_track_id,
                       rekordbox_content_id,
                       file_path,
                       reason,
                       payload_json,
                       created_at
                FROM sync_proposals
                ORDER BY id DESC
                LIMIT 200
                """
            ).fetchall()
        return [
            proposal_from_row(row)
            for row in rows
        ]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def proposal_from_row(row: sqlite3.Row) -> SyncProposal:
    return SyncProposal(
        id=int(row["id"]),
        proposalType=str(row["proposal_type"]),
        status=str(row["status"]),
        spotifyTrackId=row["spotify_track_id"],
        rekordboxContentId=row["rekordbox_content_id"],
        filePath=row["file_path"],
        reason=str(row["reason"]),
        payload=parse_json_object(row["payload_json"]),
        createdAt=str(row["created_at"]),
    )


def library_source_from_row(row: sqlite3.Row) -> LibrarySource:
    return LibrarySource(
        id=int(row["id"]),
        spotifyPlaylistId=str(row["spotify_playlist_id"]),
        spotifyPlaylistName=str(row["spotify_playlist_name"]),
        spotifySnapshotId=row["spotify_snapshot_id"],
        imageUrl=row["image_url"],
        trackCount=int(row["track_count"] or 0),
        tags=json.loads(str(row["tags_json"])),
        enabled=bool(row["enabled"]),
        status=str(row["status"]),
        newTrackCount=int(row["new_track_count"] or 0),
        pendingTrackCount=int(row["pending_track_count"] or 0),
        readyTrackCount=int(row["ready_track_count"] or 0),
        importedTrackCount=int(row["imported_track_count"] or 0),
        conflictTrackCount=int(row["conflict_track_count"] or 0),
        lastSyncedAt=row["last_synced_at"],
        updatedAt=str(row["updated_at"]),
    )


def library_track_from_row(row: sqlite3.Row) -> LibraryTrackReview:
    payload = parse_json_object(row["payload_json"])
    rekordbox_payload = payload.get("rekordbox", {})
    if not isinstance(rekordbox_payload, dict):
        rekordbox_payload = {}
    return LibraryTrackReview(
        id=int(row["id"]),
        sourceId=int(row["source_id"]),
        spotifyTrackId=str(row["spotify_track_id"]),
        spotifyUri=str(row["spotify_uri"]),
        title=str(row["title"]),
        artists=json.loads(str(row["artists_json"])),
        durationMs=int(row["duration_ms"]),
        isrc=row["isrc"],
        status=str(row["status"]),
        rekordboxContentId=row["rekordbox_content_id"],
        rekordboxTitle=optional_string(rekordbox_payload.get("title")),
        rekordboxArtist=optional_string(rekordbox_payload.get("artist")),
        rekordboxFilePath=optional_string(rekordbox_payload.get("filePath")),
        matchMethod=row["match_method"],
        confidence=int(row["confidence"] or 0),
        stagingFilePath=row["staging_file_path"],
        tags=json.loads(str(row["tags_json"])),
        reason=str(row["reason"]),
    )


def global_acquisition_job_from_row(row: sqlite3.Row) -> GlobalAcquisitionJob:
    artists = []
    try:
        artists = json.loads(str(row["artists_json"] or "[]"))
    except json.JSONDecodeError:
        artists = []
    return GlobalAcquisitionJob(
        id=int(row["id"]),
        scope=str(row["scope"]),
        eventId=row["event_id"],
        sourceId=row["source_id"],
        sourceName=str(row["source_name"] or ""),
        spotifyTrackId=str(row["spotify_track_id"]),
        trackTitle=str(row["track_title"] or row["spotify_track_id"]),
        trackArtists=artists if isinstance(artists, list) else [],
        provider=str(row["provider"]),
        deezerTrackId=row["deezer_track_id"],
        status=str(row["status"]),
        confidence=int(row["confidence"] or 0),
        matchMethod=row["match_method"],
        downloadId=row["download_id"],
        outputDir=row["output_dir"],
        error=row["error"],
        updatedAt=str(row["updated_at"]),
    )


def acquisition_job_from_row(
    row: sqlite3.Row,
    *,
    source_key: str = "event_id",
) -> AcquisitionJob:
    return AcquisitionJob(
        id=int(row["id"]),
        eventId=int(row[source_key]),
        spotifyTrackId=str(row["spotify_track_id"]),
        provider=str(row["provider"]),
        deezerTrackId=row["deezer_track_id"],
        status=str(row["status"]),
        confidence=int(row["confidence"] or 0),
        matchMethod=row["match_method"],
        downloadId=row["download_id"],
        outputDir=row["output_dir"],
        error=row["error"],
        payload=parse_json_object(row["payload_json"]),
        createdAt=str(row["created_at"]),
        updatedAt=str(row["updated_at"]),
    )
