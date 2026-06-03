from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from ..models import (
    AcquisitionJob,
    EventReview,
    EventSummary,
    EventTrackReview,
    StagingFile,
)
from ._mappers import (
    count_by_status,
    optional_string,
    parse_json_object,
    utc_now,
)


class EventsMixin:
    """Events persistence (mixed into LocalDatabase)."""

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

    # --- Event acquisition jobs -----------------------------------------

    def upsert_acquisition_job(
        self, event_id: int, job: dict[str, Any]
    ) -> AcquisitionJob:
        return self._upsert_job("event_acquisition_jobs", "event_id", event_id, job)

    def list_acquisition_jobs(
        self,
        event_id: int,
        provider: str | None = None,
    ) -> list[AcquisitionJob]:
        return self._list_jobs("event_acquisition_jobs", "event_id", event_id, provider)

    def get_acquisition_job(
        self,
        event_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
    ) -> AcquisitionJob | None:
        return self._get_job(
            "event_acquisition_jobs", "event_id", event_id, spotify_track_id, provider
        )

    def update_acquisition_job(
        self,
        event_id: int,
        spotify_track_id: str,
        provider: str = "deemix",
        **values: Any,
    ) -> None:
        self._update_job(
            "event_acquisition_jobs",
            "event_id",
            event_id,
            spotify_track_id,
            provider,
            values,
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
        counts = count_by_status(
            tracks,
            ("matched", "missing", "ambiguous", "ready", "applied", "ignored"),
        )
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
