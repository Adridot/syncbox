from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from ..models import (
    AcquisitionJob,
    GlobalAcquisitionJob,
    LibrarySource,
    LibraryTrackReview,
    SyncProposal,
)


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


def count_by_status(items: Iterable[Any], keys: Sequence[str]) -> dict[str, int]:
    """Tally ``item.status`` occurrences into a zero-initialised dict of ``keys``.

    Shared by the review repositories and acquisition job summaries so the same
    status histogram isn't re-implemented per status set.
    """
    counts = {key: 0 for key in keys}
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
    return counts


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
        pendingDeezerTrackId=row["pending_deezer_track_id"] if "pending_deezer_track_id" in row.keys() else None,
        pendingDeezerIsrc=row["pending_deezer_isrc"] if "pending_deezer_isrc" in row.keys() else None,
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
