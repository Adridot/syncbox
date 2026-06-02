from __future__ import annotations

import json
from typing import Any

from ..models import (
    AcquisitionJob,
    GlobalAcquisitionJob,
)
from ._mappers import (
    acquisition_job_from_row,
    global_acquisition_job_from_row,
    utc_now,
)


class AcquisitionMixin:
    """Acquisition-job persistence (mixed into LocalDatabase).

    Owns the shared CRUD for ``library_acquisition_jobs`` and
    ``event_acquisition_jobs`` (structurally identical bar their foreign-key
    column), plus the cross-cutting global-job queries. The Library/Events
    mixins delegate their public job methods to ``_upsert_job`` et al. here.
    """

    _JOB_UPDATABLE = {
        "deezer_track_id",
        "status",
        "confidence",
        "match_method",
        "download_id",
        "output_dir",
        "error",
        "payload_json",
    }

    def _upsert_job(
        self, table: str, fk_col: str, fk_value: int, job: dict[str, Any]
    ) -> AcquisitionJob:
        now = utc_now()
        payload = job.get("payload", {})
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                INSERT INTO {table} (
                    {fk_col},
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
                ON CONFLICT({fk_col}, spotify_track_id, provider) DO UPDATE SET
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
                    fk_value,
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
        return acquisition_job_from_row(row, source_key=fk_col)

    def _list_jobs(
        self, table: str, fk_col: str, fk_value: int, provider: str | None
    ) -> list[AcquisitionJob]:
        query = f"SELECT * FROM {table} WHERE {fk_col} = ?"
        params: list[Any] = [fk_value]
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        query += " ORDER BY id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [acquisition_job_from_row(row, source_key=fk_col) for row in rows]

    def _get_job(
        self,
        table: str,
        fk_col: str,
        fk_value: int,
        spotify_track_id: str,
        provider: str,
    ) -> AcquisitionJob | None:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM {table}
                WHERE {fk_col} = ? AND spotify_track_id = ? AND provider = ?
                """,
                (fk_value, spotify_track_id, provider),
            ).fetchone()
        return acquisition_job_from_row(row, source_key=fk_col) if row else None

    def _update_job(
        self,
        table: str,
        fk_col: str,
        fk_value: int,
        spotify_track_id: str,
        provider: str,
        values: dict[str, Any],
    ) -> None:
        values = dict(values)
        if "payload" in values:
            payload = values.pop("payload")
            values["payload_json"] = json.dumps(
                payload if isinstance(payload, dict) else {}
            )
        updates = {k: v for k, v in values.items() if k in self._JOB_UPDATABLE}
        if not updates:
            return
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = [*updates.values(), fk_value, spotify_track_id, provider]
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE {table} SET {assignments}
                WHERE {fk_col} = ? AND spotify_track_id = ? AND provider = ?
                """,
                params,
            )

    # --- Collection (missing-file re-download) jobs ----------------------
    # Keyed on Rekordbox content_id rather than an event/library + spotify id,
    # but funnels into the same global job stream + Download & Match view.

    _COLLECTION_UPDATABLE = {
        "deezer_track_id",
        "status",
        "confidence",
        "match_method",
        "download_id",
        "output_dir",
        "error",
        "title",
        "artist",
        "isrc",
        "payload_json",
    }

    def upsert_collection_job(self, content_id: str, job: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        payload = job.get("payload", {})
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO collection_acquisition_jobs (
                    content_id, provider, deezer_track_id, status, confidence,
                    match_method, download_id, output_dir, error, title, artist,
                    isrc, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(content_id, provider) DO UPDATE SET
                    deezer_track_id = excluded.deezer_track_id,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    match_method = excluded.match_method,
                    download_id = excluded.download_id,
                    output_dir = excluded.output_dir,
                    error = excluded.error,
                    title = excluded.title,
                    artist = excluded.artist,
                    isrc = excluded.isrc,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                RETURNING *
                """,
                (
                    str(content_id),
                    job.get("provider", "deemix"),
                    job.get("deezer_track_id"),
                    job["status"],
                    int(job.get("confidence", 0)),
                    job.get("match_method"),
                    job.get("download_id"),
                    job.get("output_dir"),
                    job.get("error"),
                    job.get("title", ""),
                    job.get("artist", ""),
                    job.get("isrc"),
                    json.dumps(payload if isinstance(payload, dict) else {}),
                    now,
                    now,
                ),
            ).fetchone()
        return _collection_job_to_dict(row)

    def list_collection_jobs(self, provider: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM collection_acquisition_jobs"
        params: list[Any] = []
        if provider:
            query += " WHERE provider = ?"
            params.append(provider)
        query += " ORDER BY id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_collection_job_to_dict(row) for row in rows]

    def get_collection_job(
        self, content_id: str, provider: str = "deemix"
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM collection_acquisition_jobs WHERE content_id = ? AND provider = ?",
                (str(content_id), provider),
            ).fetchone()
        return _collection_job_to_dict(row) if row else None

    def update_collection_job(
        self, content_id: str, provider: str = "deemix", **values: Any
    ) -> None:
        if "payload" in values:
            payload = values.pop("payload")
            values["payload_json"] = json.dumps(payload if isinstance(payload, dict) else {})
        updates = {k: v for k, v in values.items() if k in self._COLLECTION_UPDATABLE}
        if not updates:
            return
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = [*updates.values(), str(content_id), provider]
        with self.connect() as connection:
            connection.execute(
                f"UPDATE collection_acquisition_jobs SET {assignments} "
                "WHERE content_id = ? AND provider = ?",
                params,
            )

    # --- Global / cross-cutting acquisition queries ---------------------

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
        if scope in (None, "collection"):
            collection_filters = ""
            collection_params: list[Any] = []
            if status:
                collection_filters += " AND jobs.status = ?"
                collection_params.append(status)
            if source:
                collection_filters += " AND jobs.title LIKE ?"
                collection_params.append(f"%{source}%")
            queries.append(
                f"""
                SELECT jobs.id,
                       'collection' AS scope,
                       NULL AS event_id,
                       NULL AS source_id,
                       'Missing files' AS source_name,
                       jobs.content_id AS spotify_track_id,
                       jobs.title AS track_title,
                       json_array(jobs.artist) AS artists_json,
                       jobs.provider,
                       jobs.deezer_track_id,
                       jobs.status,
                       jobs.confidence,
                       jobs.match_method,
                       jobs.download_id,
                       jobs.output_dir,
                       jobs.error,
                       jobs.updated_at
                FROM collection_acquisition_jobs jobs
                WHERE 1 = 1{collection_filters}
                """
            )
            params.extend(collection_params)
        if not queries:
            return []
        query = " UNION ALL ".join(queries)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM ({query}) ORDER BY updated_at DESC LIMIT 500",
                params,
            ).fetchall()
        return [global_acquisition_job_from_row(row) for row in rows]

    def clear_completed_acquisition_jobs(self, scope: str | None = None) -> int:
        terminal = ("ready", "downloaded", "acquisition_failed", "acquisition_ambiguous")
        placeholders = ", ".join("?" * len(terminal))
        cleared = 0
        with self.connect() as connection:
            if scope in (None, "event"):
                cursor = connection.execute(
                    f"DELETE FROM event_acquisition_jobs WHERE status IN ({placeholders})",
                    terminal,
                )
                cleared += cursor.rowcount
            if scope in (None, "library"):
                cursor = connection.execute(
                    f"DELETE FROM library_acquisition_jobs WHERE status IN ({placeholders})",
                    terminal,
                )
                cleared += cursor.rowcount
            if scope in (None, "collection"):
                cursor = connection.execute(
                    f"DELETE FROM collection_acquisition_jobs WHERE status IN ({placeholders})",
                    terminal,
                )
                cleared += cursor.rowcount
        return cleared


def _collection_job_to_dict(row: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return {
        "id": int(row["id"]),
        "content_id": str(row["content_id"]),
        "provider": str(row["provider"]),
        "deezer_track_id": row["deezer_track_id"],
        "status": str(row["status"]),
        "confidence": int(row["confidence"] or 0),
        "match_method": row["match_method"],
        "download_id": row["download_id"],
        "output_dir": row["output_dir"],
        "error": row["error"],
        "title": str(row["title"] or ""),
        "artist": str(row["artist"] or ""),
        "isrc": row["isrc"],
        "payload": payload if isinstance(payload, dict) else {},
    }
