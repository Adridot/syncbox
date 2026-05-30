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
        return cleared
