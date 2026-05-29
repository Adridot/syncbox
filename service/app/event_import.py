from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .audio import scan_audio_files
from .db import LocalDatabase
from .live_import import build_live_import_package
from .matching import match_spotify_track
from .models import (
    EventReview,
    EventTrackUpdateRequest,
    RekordboxTrack,
    SpotifyEventAnalyzeRequest,
    SpotifyTrack,
)
from .rekordbox import RekordboxAdapter
from .spotify import SpotifyClient, parse_playlist_id, playlist_items_to_tracks


STAGING_AUTO_MATCH_MINIMUM_CONFIDENCE = 85
STAGING_MATCH_METHOD_PREFIX = "staging:"


async def analyze_spotify_event(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    client: SpotifyClient,
    request: SpotifyEventAnalyzeRequest,
) -> EventReview:
    playlist_id = parse_playlist_id(str(request.playlist_url))
    playlist = await client.get_playlist(playlist_id)
    playlist_items = await client.get_playlist_items(playlist_id)
    spotify_tracks = playlist_items_to_tracks(playlist_items)
    library = adapter.read_library_snapshot()
    rekordbox_tracks = [
        RekordboxTrack(**track) for track in library.get("tracks", [])
    ]

    layout = adapter.ensure_storage_layout()
    package = build_live_import_package(Path(layout.events), request.event_name)
    event_id = database.create_event_import(
        {
            "event_name": request.event_name,
            "event_slug": package["eventSlug"],
            "spotify_playlist_id": playlist_id,
            "spotify_playlist_name": str(playlist.get("name") or request.event_name),
            "spotify_snapshot_id": playlist.get("snapshot_id"),
            "default_tag": request.event_name,
            "status": "review",
            "event_dir": package["eventDir"],
            "audio_dir": package["audioDir"],
            "playlist_path": package["playlistPath"],
        }
    )

    rows = build_event_track_rows(event_id, spotify_tracks, rekordbox_tracks, library)
    database.upsert_event_tracks(event_id, rows)
    review = database.get_event_review(event_id)
    if review is None:
        raise RuntimeError("Event review could not be created.")
    return review


def build_event_track_rows(
    event_id: int,
    spotify_tracks: list[SpotifyTrack],
    rekordbox_tracks: list[RekordboxTrack],
    library: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_spotify_ids: set[str] = set()
    library_warning = ""
    if library and not library.get("available", True):
        library_warning = str(library.get("reason") or "Rekordbox library unavailable.")

    for spotify_track in spotify_tracks:
        if spotify_track.id in seen_spotify_ids:
            rows.append(
                base_track_row(
                    event_id,
                    spotify_track,
                    status="ignored",
                    reason="Duplicate Spotify track in source playlist.",
                )
            )
            continue
        seen_spotify_ids.add(spotify_track.id)

        result = match_spotify_track(spotify_track, rekordbox_tracks)
        rekordbox_payload = rekordbox_track_payload(
            rekordbox_tracks, result.rekordbox_content_id
        )
        if result.status == "matched":
            rows.append(
                base_track_row(
                    event_id,
                    spotify_track,
                    status="matched",
                    reason=result.reason,
                    rekordbox_content_id=result.rekordbox_content_id,
                    rekordbox_payload=rekordbox_payload,
                    match_method=result.method,
                    confidence=result.confidence,
                )
            )
        elif result.status == "ambiguous":
            rows.append(
                base_track_row(
                    event_id,
                    spotify_track,
                    status="ambiguous",
                    reason=result.reason,
                    rekordbox_content_id=result.rekordbox_content_id,
                    rekordbox_payload=rekordbox_payload,
                    match_method=result.method,
                    confidence=result.confidence,
                )
            )
        else:
            reason = result.reason
            if library_warning:
                reason = f"{reason} Library snapshot unavailable: {library_warning}"
            rows.append(
                base_track_row(
                    event_id,
                    spotify_track,
                    status="missing",
                    reason=reason,
                )
            )
    return rows


def base_track_row(
    event_id: int,
    spotify_track: SpotifyTrack,
    *,
    status: str,
    reason: str,
    rekordbox_content_id: str | None = None,
    rekordbox_payload: dict[str, Any] | None = None,
    match_method: str | None = None,
    confidence: int = 0,
    staging_file_path: str | None = None,
) -> dict[str, Any]:
    payload = spotify_track.model_dump(by_alias=True)
    if rekordbox_payload:
        payload["rekordbox"] = rekordbox_payload

    return {
        "event_id": event_id,
        "spotify_track_id": spotify_track.id,
        "spotify_uri": spotify_track.uri,
        "title": spotify_track.title,
        "artists": spotify_track.artists,
        "duration_ms": spotify_track.duration_ms,
        "isrc": spotify_track.isrc,
        "status": status,
        "rekordbox_content_id": rekordbox_content_id,
        "match_method": match_method,
        "confidence": confidence,
        "staging_file_path": staging_file_path,
        "reason": reason,
        "payload": payload,
    }


def rekordbox_track_payload(
    candidates: list[RekordboxTrack],
    content_id: str | None,
) -> dict[str, Any] | None:
    if not content_id:
        return None
    for candidate in candidates:
        if candidate.content_id != content_id:
            continue
        return {
            "contentId": candidate.content_id,
            "title": candidate.title,
            "artist": candidate.artist,
            "filePath": candidate.file_path,
        }
    return None


def scan_event_staging(database: LocalDatabase, event_id: int) -> EventReview:
    review = require_event_review(database, event_id)
    staging_files = scan_audio_files(Path(review.audio_dir))
    current_file_paths = {str(file_info["file_path"]) for file_info in staging_files}
    reconcile_staged_tracks(database, review, current_file_paths)
    review = require_event_review(database, event_id)

    candidates = [
        RekordboxTrack(
            contentId=file_info["file_path"],
            title=file_info["title"],
            artist=file_info["artist"],
            durationMs=file_info["duration_ms"],
            isrc=file_info["isrc"],
            filePath=file_info["file_path"],
        )
        for file_info in staging_files
    ]

    matched_files = staged_files_already_claimed(review, current_file_paths)
    missing_tracks = [track for track in review.tracks if track.status == "missing"]
    for track in missing_tracks:
        available_candidates = [
            candidate
            for candidate in candidates
            if candidate.content_id not in matched_files
        ]
        spotify_track = event_track_to_spotify_track(track)
        result = match_spotify_track(
            spotify_track,
            available_candidates,
            minimum_confidence=STAGING_AUTO_MATCH_MINIMUM_CONFIDENCE,
        )
        if result.status == "matched" and result.rekordbox_content_id:
            matched_files.add(result.rekordbox_content_id)
            database.update_event_track(
                event_id,
                spotify_track.id,
                status="ready",
                staging_file_path=result.rekordbox_content_id,
                match_method=f"staging:{result.method}",
                confidence=result.confidence,
                reason="Staged audio file matched this Spotify track.",
            )

    review = require_event_review(database, event_id)
    tracks_by_file_path = matched_tracks_by_staged_file(review, current_file_paths)
    for file_info in staging_files:
        matched_track = tracks_by_file_path.get(file_info["file_path"])
        file_info["matched_spotify_track_id"] = (
            matched_track.spotify_track_id if matched_track else None
        )
        file_info["status"] = "matched" if matched_track else "unmatched"

    database.replace_staging_files(event_id, staging_files)
    return require_event_review(database, event_id)


def reconcile_staged_tracks(
    database: LocalDatabase,
    review: EventReview,
    current_file_paths: set[str],
) -> None:
    for track in review.tracks:
        if not track.staging_file_path:
            continue
        if track.staging_file_path not in current_file_paths:
            clear_staging_match(
                database,
                review,
                track.spotify_track_id,
                reason="Staged file is missing from the event folder.",
                acquisition_failed=True,
            )
            continue

        if track.status == "ready" and is_automatic_staging_match(track.match_method):
            clear_staging_match(
                database,
                review,
                track.spotify_track_id,
                reason="Staged file metadata no longer validates this track.",
            )


def clear_staging_match(
    database: LocalDatabase,
    review: EventReview,
    spotify_track_id: str,
    *,
    reason: str,
    acquisition_failed: bool = False,
) -> None:
    database.update_event_track(
        review.id,
        spotify_track_id,
        status="missing",
        staging_file_path=None,
        match_method=None,
        confidence=0,
        reason=reason,
    )
    if not acquisition_failed:
        return
    database.update_acquisition_job(
        review.id,
        spotify_track_id,
        status="acquisition_failed",
        error=reason,
        output_dir=review.audio_dir,
    )


def is_automatic_staging_match(match_method: str | None) -> bool:
    return bool(match_method and match_method.startswith(STAGING_MATCH_METHOD_PREFIX))


def staged_files_already_claimed(
    review: EventReview,
    current_file_paths: set[str],
) -> set[str]:
    return {
        track.staging_file_path
        for track in review.tracks
        if track.staging_file_path
        and track.staging_file_path in current_file_paths
        and track.status in {"ready", "applied"}
    }


def matched_tracks_by_staged_file(
    review: EventReview,
    current_file_paths: set[str],
) -> dict[str, Any]:
    matches: dict[str, Any] = {}
    for track in review.tracks:
        if (
            track.staging_file_path
            and track.staging_file_path in current_file_paths
            and track.status in {"ready", "applied"}
            and track.staging_file_path not in matches
        ):
            matches[track.staging_file_path] = track
    return matches


def event_track_to_spotify_track(track: Any) -> SpotifyTrack:
    return SpotifyTrack(
        id=track.spotify_track_id,
        uri=track.spotify_uri,
        title=track.title,
        artists=track.artists,
        durationMs=track.duration_ms,
        isrc=track.isrc,
    )


def apply_event_track_update(
    database: LocalDatabase,
    event_id: int,
    request: EventTrackUpdateRequest,
) -> EventReview:
    values: dict[str, Any] = {}
    if request.status:
        values["status"] = request.status
    if request.rekordbox_content_id:
        values["rekordbox_content_id"] = request.rekordbox_content_id
        values["status"] = request.status or "matched"
        values["match_method"] = "manual"
        values["reason"] = "Manually linked to a Rekordbox track."
    if request.staging_file_path:
        values["staging_file_path"] = request.staging_file_path
        values["status"] = request.status or "ready"
        values["match_method"] = "manual_staging"
        values["reason"] = "Manually linked to a staged audio file."
    database.update_event_track(event_id, request.spotify_track_id, **values)
    return require_event_review(database, event_id)


def require_event_review(database: LocalDatabase, event_id: int) -> EventReview:
    review = database.get_event_review(event_id)
    if review is None:
        raise KeyError(f"Event {event_id} was not found.")
    return review
