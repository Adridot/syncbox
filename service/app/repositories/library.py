from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from ..models import (
    AcquisitionJob,
    LibraryReview,
    LibrarySource,
    LibrarySourceIn,
)
from ._mappers import (
    library_source_from_row,
    library_track_from_row,
    utc_now,
)


class LibraryMixin:
    """Library persistence (mixed into LocalDatabase)."""

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
            "pending_deezer_track_id",
            "pending_deezer_isrc",
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

    # --- Library acquisition jobs (delegate to AcquisitionMixin helpers) ---

    def upsert_library_acquisition_job(
        self, source_id: int, job: dict[str, Any]
    ) -> AcquisitionJob:
        return self._upsert_job("library_acquisition_jobs", "source_id", source_id, job)

    def list_library_acquisition_jobs(
        self,
        source_id: int,
        provider: str | None = None,
    ) -> list[AcquisitionJob]:
        return self._list_jobs("library_acquisition_jobs", "source_id", source_id, provider)

    def get_library_acquisition_job(
        self,
        source_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
    ) -> AcquisitionJob | None:
        return self._get_job(
            "library_acquisition_jobs", "source_id", source_id, spotify_track_id, provider
        )

    def update_library_acquisition_job(
        self,
        source_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
        **values: Any,
    ) -> None:
        self._update_job(
            "library_acquisition_jobs",
            "source_id",
            source_id,
            spotify_track_id,
            provider,
            values,
        )
