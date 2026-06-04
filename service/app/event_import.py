from __future__ import annotations

import asyncio
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
from .spotify import (
    SpotifyClient,
    parse_playlist_id,
    parse_track_id,
    playlist_items_to_tracks,
    track_payload_to_spotify_track,
)


STAGING_AUTO_MATCH_MINIMUM_CONFIDENCE = 85
STAGING_MATCH_METHOD_PREFIX = "staging:"


def scaffold_event(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    event_name: str,
    *,
    playlist_id: str,
    playlist_name: str,
    snapshot_id: str | None = None,
) -> int:
    """Create the event row and its on-disk staging layout. Returns the event id."""
    layout = adapter.ensure_storage_layout()
    package = build_live_import_package(Path(layout.events), event_name)
    return database.create_event_import(
        {
            "event_name": event_name,
            "event_slug": package["eventSlug"],
            "spotify_playlist_id": playlist_id,
            "spotify_playlist_name": playlist_name,
            "spotify_snapshot_id": snapshot_id,
            "default_tag": event_name,
            "status": "review",
            "event_dir": package["eventDir"],
            "audio_dir": package["audioDir"],
            "playlist_path": package["playlistPath"],
        }
    )


def _load_rekordbox_snapshot(adapter: RekordboxAdapter) -> tuple[list[RekordboxTrack], dict[str, Any]]:
    library = adapter.read_library_snapshot()
    rekordbox_tracks = [RekordboxTrack(**track) for track in library.get("tracks", [])]
    return rekordbox_tracks, library


def _require_review(database: LocalDatabase, event_id: int) -> EventReview:
    review = database.get_event_review(event_id)
    if review is None:
        raise RuntimeError("Event review could not be created.")
    return review


async def analyze_spotify_event(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    client: SpotifyClient,
    request: SpotifyEventAnalyzeRequest,
) -> EventReview:
    playlist_id = parse_playlist_id(str(request.playlist_url))
    playlist, playlist_items = await asyncio.gather(
        client.get_playlist(playlist_id),
        client.get_playlist_items(playlist_id),
    )
    spotify_tracks = playlist_items_to_tracks(playlist_items)
    rekordbox_tracks, library = _load_rekordbox_snapshot(adapter)

    event_id = scaffold_event(
        database,
        adapter,
        request.event_name,
        playlist_id=playlist_id,
        playlist_name=str(playlist.get("name") or request.event_name),
        snapshot_id=playlist.get("snapshot_id"),
    )

    rows = build_event_track_rows(event_id, spotify_tracks, rekordbox_tracks, library)
    database.upsert_event_tracks(event_id, rows)
    return _require_review(database, event_id)


def create_manual_event(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    event_name: str,
) -> EventReview:
    """Create an empty event with no Spotify playlist behind it."""
    name = event_name.strip()
    if not name:
        raise ValueError("Event name is required.")
    layout = adapter.ensure_storage_layout()
    package = build_live_import_package(Path(layout.events), name)
    event_id = database.create_event_import(
        {
            "event_name": name,
            "event_slug": package["eventSlug"],
            # "manual:" prefix keeps it unique and ensures it never matches a
            # permanent library source in event_matches_permanent_source().
            "spotify_playlist_id": f"manual:{package['eventSlug']}",
            "spotify_playlist_name": name,
            "spotify_snapshot_id": None,
            "default_tag": name,
            "status": "review",
            "event_dir": package["eventDir"],
            "audio_dir": package["audioDir"],
            "playlist_path": package["playlistPath"],
        }
    )
    return _require_review(database, event_id)


async def add_spotify_track_to_event(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    client: SpotifyClient,
    event_id: int,
    track_url: str,
) -> EventReview:
    """Fetch a single Spotify track by link/URI/id and add it to an event.

    The track is matched against the Rekordbox collection exactly like playlist
    analysis, then upserted (additively) into the event's track list.
    """
    require_event_review(database, event_id)  # 404 if the event does not exist

    track_id = parse_track_id(track_url)
    # Spotify track ids are 22-char base62 strings; validate before calling the
    # API so a typo gives a clear 400 instead of a misleading auth error.
    if not (len(track_id) == 22 and track_id.isalnum()):
        raise ValueError("That does not look like a Spotify track link.")
    payload = await client.get_track(track_id)
    spotify_track = track_payload_to_spotify_track(payload)
    if spotify_track is None:
        raise ValueError("That Spotify link does not point to a playable track.")

    rekordbox_tracks, library = _load_rekordbox_snapshot(adapter)
    rows = build_event_track_rows(event_id, [spotify_track], rekordbox_tracks, library)
    database.upsert_event_tracks(event_id, rows)
    return _require_review(database, event_id)


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
    # fresh=True: reconciles just-downloaded files against jobs, so it must see
    # files that landed within the cache TTL (cloud FS may not bump dir mtime).
    staging_files = scan_audio_files(Path(review.audio_dir), fresh=True)
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
