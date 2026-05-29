from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .acquisition import (
    DEEMIX_PROVIDER,
    DeezerResolveResult,
    DeezerResolver,
    DeemixClient,
    acquisition_status_counts,
    deezer_candidate_from_payload,
    extract_download_ids,
    extract_queue_items,
    map_deemix_queue_status,
    optional_text,
)
from .audio import scan_audio_files
from .db import LocalDatabase
from .matching import match_spotify_track
from .models import (
    LibraryReview,
    LibrarySource,
    LibrarySourceIn,
    LibraryTrackDownloadRequest,
    LibraryTrackReview,
    LibraryTrackUpdateRequest,
    RekordboxTrack,
    SpotifyTrack,
)
from .rekordbox import RekordboxAdapter
from .spotify import SpotifyClient, playlist_image_url, playlist_items_to_tracks


PERMANENT_DOWNLOAD_QUALITY = "MP3_320"


async def sync_library_source(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    client: SpotifyClient,
    source_id: int,
) -> LibraryReview:
    source = require_library_source(database, source_id)
    playlist = await client.get_playlist(source.spotify_playlist_id)
    playlist_items = await client.get_playlist_items(source.spotify_playlist_id)
    spotify_tracks = playlist_items_to_tracks(playlist_items)
    library = adapter.read_library_snapshot()
    rekordbox_tracks = [
        RekordboxTrack(**track) for track in library.get("tracks", [])
    ]
    existing_review = database.get_library_review(source_id)
    existing_tracks = {
        track.spotify_track_id: track
        for track in (existing_review.tracks if existing_review else [])
    }
    rows = build_library_track_rows(
        source,
        spotify_tracks,
        rekordbox_tracks,
        existing_tracks,
        library,
    )
    active_spotify_ids = {track.id for track in spotify_tracks}
    removed = mark_removed_library_tracks(database, source, existing_tracks, active_spotify_ids)
    new_count = sum(1 for row in rows if row["status"] == "new")
    database.upsert_library_tracks(source_id, rows)
    database.insert_library_source_run(
        source_id,
        spotify_snapshot_id=optional_text(playlist.get("snapshot_id")),
        status="synced",
        total_tracks=len(spotify_tracks),
        new_tracks=new_count,
        removed_tracks=removed,
    )
    database.update_library_source_sync(
        source_id,
        spotify_playlist_name=str(playlist.get("name") or source.spotify_playlist_name),
        spotify_snapshot_id=optional_text(playlist.get("snapshot_id")),
        image_url=playlist_image_url(playlist.get("images") or []),
        track_count=len(spotify_tracks),
        status="synced",
    )
    mark_library_ready_after_scan(database, adapter, source_id)
    review = database.get_library_review(source_id)
    if review is None:
        raise KeyError(f"Library source {source_id} was not found.")
    return review


def build_library_track_rows(
    source: LibrarySource,
    spotify_tracks: list[SpotifyTrack],
    rekordbox_tracks: list[RekordboxTrack],
    existing_tracks: dict[str, LibraryTrackReview],
    library: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    seen: set[str] = set()
    rekordbox_tracks_by_id = {
        str(track.content_id): track for track in rekordbox_tracks if track.content_id
    }
    library_warning = ""
    if library and not library.get("available", True):
        library_warning = str(library.get("reason") or "Rekordbox library unavailable.")

    for spotify_track in spotify_tracks:
        if spotify_track.id in seen:
            rows.append(
                base_library_track_row(
                    source,
                    spotify_track,
                    status="ignored",
                    reason="Duplicate Spotify track in source playlist.",
                )
            )
            continue
        seen.add(spotify_track.id)

        existing = existing_tracks.get(spotify_track.id)
        if existing and existing.status == "ignored":
            rows.append(existing_library_track_row(source, spotify_track, existing))
            continue
        if existing and existing.status == "ready":
            rows.append(existing_library_track_row(source, spotify_track, existing))
            continue
        if existing and existing.status in {"imported", "matched"}:
            rows.append(
                reconcile_existing_rekordbox_track(
                    source,
                    spotify_track,
                    existing,
                    rekordbox_tracks,
                    rekordbox_tracks_by_id,
                    library_warning,
                )
            )
            continue

        result = match_spotify_track(spotify_track, rekordbox_tracks)
        rekordbox_payload = rekordbox_track_payload(
            rekordbox_tracks, result.rekordbox_content_id
        )
        if result.status == "matched":
            rows.append(
                base_library_track_row(
                    source,
                    spotify_track,
                    status="matched",
                    reason=result.reason,
                    rekordbox_content_id=result.rekordbox_content_id,
                    rekordbox_payload=rekordbox_payload,
                    match_method=result.method,
                    confidence=result.confidence,
                    tags=existing.tags if existing else source.tags,
                )
            )
        elif result.status == "ambiguous":
            rows.append(
                base_library_track_row(
                    source,
                    spotify_track,
                    status="conflict",
                    reason=result.reason,
                    rekordbox_content_id=result.rekordbox_content_id,
                    rekordbox_payload=rekordbox_payload,
                    match_method=result.method,
                    confidence=result.confidence,
                    tags=existing.tags if existing else source.tags,
                )
            )
        else:
            reason = "New Spotify track needs download or manual matching."
            if library_warning:
                reason = f"{reason} Library snapshot unavailable: {library_warning}"
            rows.append(
                base_library_track_row(
                    source,
                    spotify_track,
                    status=existing.status if existing and existing.status == "missing" else "new",
                    reason=existing.reason if existing and existing.status == "missing" else reason,
                    tags=existing.tags if existing else source.tags,
                )
            )
    return rows


def reconcile_existing_rekordbox_track(
    source: LibrarySource,
    spotify_track: SpotifyTrack,
    existing: LibraryTrackReview,
    rekordbox_tracks: list[RekordboxTrack],
    rekordbox_tracks_by_id: dict[str, RekordboxTrack],
    library_warning: str = "",
) -> dict[str, Any]:
    if library_warning:
        return existing_library_track_row(source, spotify_track, existing)

    if existing.rekordbox_content_id:
        current = rekordbox_tracks_by_id.get(str(existing.rekordbox_content_id))
        if current:
            return base_library_track_row(
                source,
                spotify_track,
                status=existing.status,
                reason=existing.reason,
                rekordbox_content_id=current.content_id,
                rekordbox_payload=rekordbox_track_payload(
                    rekordbox_tracks, current.content_id
                ),
                match_method=existing.match_method,
                confidence=existing.confidence,
                tags=existing.tags,
            )

    result = match_spotify_track(spotify_track, rekordbox_tracks)
    rekordbox_payload = rekordbox_track_payload(
        rekordbox_tracks, result.rekordbox_content_id
    )
    if result.status == "matched":
        return base_library_track_row(
            source,
            spotify_track,
            status=existing.status,
            reason="Previously imported track was found in the Rekordbox collection.",
            rekordbox_content_id=result.rekordbox_content_id,
            rekordbox_payload=rekordbox_payload,
            match_method=result.method,
            confidence=result.confidence,
            tags=existing.tags,
        )
    if result.status == "ambiguous":
        return base_library_track_row(
            source,
            spotify_track,
            status="conflict",
            reason=(
                "Previously imported track is no longer linked to the Rekordbox "
                "collection and the replacement match is ambiguous."
            ),
            rekordbox_content_id=result.rekordbox_content_id,
            rekordbox_payload=rekordbox_payload,
            match_method=result.method,
            confidence=result.confidence,
            tags=existing.tags,
        )

    return base_library_track_row(
        source,
        spotify_track,
        status="missing",
        reason="Previously imported track is missing from the Rekordbox collection.",
        tags=existing.tags,
    )


def existing_library_track_row(
    source: LibrarySource,
    spotify_track: SpotifyTrack,
    existing: LibraryTrackReview,
) -> dict[str, Any]:
    return base_library_track_row(
        source,
        spotify_track,
        status=existing.status,
        reason=existing.reason,
        rekordbox_content_id=existing.rekordbox_content_id,
        rekordbox_payload=existing_rekordbox_payload(existing),
        match_method=existing.match_method,
        confidence=existing.confidence,
        staging_file_path=existing.staging_file_path,
        tags=existing.tags,
    )


def base_library_track_row(
    source: LibrarySource,
    spotify_track: SpotifyTrack,
    *,
    status: str,
    reason: str,
    rekordbox_content_id: str | None = None,
    rekordbox_payload: dict[str, Any] | None = None,
    match_method: str | None = None,
    confidence: int = 0,
    staging_file_path: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    payload = spotify_track.model_dump(by_alias=True)
    payload["source"] = {
        "id": source.id,
        "spotifyPlaylistId": source.spotify_playlist_id,
        "spotifyPlaylistName": source.spotify_playlist_name,
    }
    if rekordbox_payload:
        payload["rekordbox"] = rekordbox_payload
    return {
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
        "tags": tags or [],
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


def existing_rekordbox_payload(track: LibraryTrackReview) -> dict[str, Any] | None:
    if not track.rekordbox_content_id:
        return None
    return {
        "contentId": track.rekordbox_content_id,
        "title": track.rekordbox_title,
        "artist": track.rekordbox_artist,
        "filePath": track.rekordbox_file_path,
    }


def mark_removed_library_tracks(
    database: LocalDatabase,
    source: LibrarySource,
    existing_tracks: dict[str, LibraryTrackReview],
    active_spotify_ids: set[str],
) -> int:
    removed = 0
    proposals = []
    for track in existing_tracks.values():
        if track.spotify_track_id in active_spotify_ids:
            continue
        if track.status == "removed_from_source":
            continue
        database.update_library_track(
            source.id,
            track.spotify_track_id,
            status="removed_from_source",
            reason="Spotify track is no longer present in the source playlist.",
        )
        removed += 1
        proposals.append(
            {
                "proposal_type": "remove_from_rekordbox",
                "spotify_track_id": track.spotify_track_id,
                "rekordbox_content_id": track.rekordbox_content_id,
                "file_path": track.rekordbox_file_path or track.staging_file_path,
                "reason": (
                    "Permanent source track was removed from Spotify. "
                    "Review before removing tags or files."
                ),
                "payload": {
                    "sourceId": source.id,
                    "sourcePlaylistId": source.spotify_playlist_id,
                    "sourcePlaylistName": source.spotify_playlist_name,
                    "tagNames": source.tags,
                    "trackTitle": track.title,
                    "trackArtists": track.artists,
                },
            }
        )
    database.insert_proposals(proposals)
    return removed


def update_library_tracks(
    database: LocalDatabase,
    request: LibraryTrackUpdateRequest,
) -> LibraryReview:
    for spotify_track_id in request.spotify_track_ids:
        values: dict[str, Any] = {}
        if request.status:
            values["status"] = request.status
            values["reason"] = f"Marked {request.status} from My Library."
        if request.tags is not None:
            values["tags_json"] = json.dumps(request.tags)
        if request.staging_file_path:
            values["staging_file_path"] = request.staging_file_path
            values["status"] = request.status or "ready"
            values["match_method"] = "manual_staging"
            values["reason"] = "Manually linked to a staged audio file."
        if request.rekordbox_content_id:
            values["rekordbox_content_id"] = request.rekordbox_content_id
            values["status"] = request.status or "matched"
            values["match_method"] = "manual"
            values["reason"] = "Manually linked to a Rekordbox track."
        database.update_library_track(request.source_id, spotify_track_id, **values)
    return require_library_review(database, request.source_id)


async def download_library_tracks(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    request: LibraryTrackDownloadRequest,
    *,
    deemix_client: DeemixClient | None = None,
    deezer_resolver: DeezerResolver | None = None,
) -> dict[str, Any]:
    client = deemix_client or DeemixClient()
    resolver = deezer_resolver or DeezerResolver()
    await refresh_library_review_state(
        database,
        adapter,
        request.source_id,
        deemix_client=client,
    )
    review = require_library_review(database, request.source_id)
    selected_ids = set(request.spotify_track_ids or [])
    active_jobs = {
        job.spotify_track_id: job
        for job in database.list_library_acquisition_jobs(request.source_id, DEEMIX_PROVIDER)
        if job.status in {"resolved", "queued", "downloading", "downloaded", "ready"}
    }
    eligible_tracks = [
        track
        for track in review.tracks
        if track.status in {"new", "missing"}
        and (not selected_ids or track.spotify_track_id in selected_ids)
        and track.spotify_track_id not in active_jobs
    ]
    created = 0

    if not eligible_tracks:
        return build_library_download_response(database, request.source_id, created=0)

    status = await client.status()
    if not status.available or not status.authenticated:
        for track in eligible_tracks:
            if database.get_library_acquisition_job(request.source_id, track.spotify_track_id) is None:
                created += 1
            database.upsert_library_acquisition_job(
                request.source_id,
                library_acquisition_job_payload(
                    track,
                    status="acquisition_failed",
                    output_dir=adapter.storage_layout().permanent,
                    error=status.detail,
                ),
            )
        return build_library_download_response(database, request.source_id, created=created)

    resolved_tracks: list[tuple[LibraryTrackReview, DeezerResolveResult]] = []
    for track in eligible_tracks:
        if database.get_library_acquisition_job(request.source_id, track.spotify_track_id) is None:
            created += 1
        try:
            result = await resolver.resolve(track)
        except Exception as exc:
            result = DeezerResolveResult(status="acquisition_failed", error=str(exc))
        if result.status == "resolved" and result.candidate:
            resolved_tracks.append((track, result))
        database.upsert_library_acquisition_job(
            request.source_id,
            library_acquisition_job_payload(
                track,
                status=result.status,
                deezer_track_id=result.candidate.id if result.candidate else None,
                confidence=result.confidence,
                match_method=result.match_method,
                output_dir=adapter.storage_layout().permanent,
                error=result.error,
                payload=compact_deezer_payload(result.payload or {}),
            ),
        )

    if resolved_tracks:
        await queue_library_tracks(database, adapter, review, client, resolved_tracks)
        await refresh_library_acquisition_jobs(database, adapter, request.source_id, deemix_client=client)

    return build_library_download_response(database, request.source_id, created=created)


async def refresh_library_review_state(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    source_id: int,
    *,
    deemix_client: DeemixClient | None = None,
) -> LibraryReview:
    await refresh_library_acquisition_jobs(
        database,
        adapter,
        source_id,
        deemix_client=deemix_client,
    )
    mark_library_ready_after_scan(database, adapter, source_id)
    return require_library_review(database, source_id)


async def queue_library_tracks(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    review: LibraryReview,
    client: DeemixClient,
    resolved_tracks: list[tuple[LibraryTrackReview, DeezerResolveResult]],
) -> None:
    track_ids = [
        result.candidate.id
        for _, result in resolved_tracks
        if result.candidate is not None
    ]
    if not track_ids:
        return

    output_dir = Path(adapter.storage_layout().permanent)
    try:
        await client.update_settings(deemix_permanent_settings(output_dir))
        response = await client.download_batch(track_ids, review.source.spotify_playlist_name)
    except Exception as exc:
        for track, result in resolved_tracks:
            database.update_library_acquisition_job(
                review.source.id,
                track.spotify_track_id,
                status="acquisition_failed",
                error=str(exc),
                payload=compact_deezer_payload(result.payload or {}),
            )
        return

    download_ids = extract_download_ids(response)
    for index, (track, result) in enumerate(resolved_tracks):
        database.update_library_acquisition_job(
            review.source.id,
            track.spotify_track_id,
            status="queued",
            download_id=download_ids[index] if index < len(download_ids) else None,
            error=None,
            payload={
                **compact_deezer_payload(result.payload or {}),
                "batchCount": len(download_ids),
            },
        )


async def refresh_library_acquisition_jobs(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    source_id: int,
    *,
    deemix_client: DeemixClient | None = None,
) -> list[Any]:
    client = deemix_client or DeemixClient()
    try:
        await sync_library_deemix_queue(database, adapter, source_id, client)
    except Exception:
        pass
    return database.list_library_acquisition_jobs(source_id, DEEMIX_PROVIDER)


async def sync_library_deemix_queue(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    source_id: int,
    client: DeemixClient,
) -> None:
    jobs = database.list_library_acquisition_jobs(source_id, DEEMIX_PROVIDER)
    active_jobs = [
        job for job in jobs if job.status in {"resolved", "queued", "downloading", "downloaded"}
    ]
    if not active_jobs:
        return

    queue_payload = await client.queue()
    queue_items = extract_queue_items(queue_payload)
    items_by_id = {
        optional_text(item.get("id") or item.get("downloadId") or item.get("uuid")): item
        for item in queue_items
    }
    items_by_track_id = {
        optional_text(item.get("trackId") or item.get("deezerTrackId")): item
        for item in queue_items
    }
    changed_to_downloaded = False
    for job in active_jobs:
        item = items_by_id.get(job.download_id) if job.download_id else None
        if item is None and job.deezer_track_id:
            item = items_by_track_id.get(job.deezer_track_id)
        if item is None:
            continue

        mapped_status = map_deemix_queue_status(item)
        if mapped_status == job.status:
            continue
        database.update_library_acquisition_job(
            source_id,
            job.spotify_track_id,
            status=mapped_status,
            error=optional_text(item.get("error") or item.get("message"))
            if mapped_status == "acquisition_failed"
            else None,
            payload={**job.payload, "queueStatus": mapped_status},
        )
        changed_to_downloaded = changed_to_downloaded or mapped_status == "downloaded"

    if changed_to_downloaded:
        mark_library_ready_after_scan(database, adapter, source_id)


def mark_library_ready_after_scan(
    database: LocalDatabase,
    adapter: RekordboxAdapter,
    source_id: int,
) -> None:
    review = require_library_review(database, source_id)
    audio_files = scan_audio_files(Path(adapter.storage_layout().permanent))
    candidates = [
        RekordboxTrack(
            contentId=file_info["file_path"],
            title=file_info["title"],
            artist=file_info["artist"],
            durationMs=file_info["duration_ms"],
            isrc=file_info["isrc"],
            filePath=file_info["file_path"],
        )
        for file_info in audio_files
    ]
    available_paths = {candidate.content_id for candidate in candidates}
    claimed = {
        track.staging_file_path
        for track in review.tracks
        if track.staging_file_path and track.status in {"ready", "imported"}
    }
    for track in review.tracks:
        if track.status != "ready":
            continue
        job = database.get_library_acquisition_job(source_id, track.spotify_track_id)
        if track.staging_file_path and track.staging_file_path in available_paths:
            if job and job.status != "ready":
                database.update_library_acquisition_job(
                    source_id,
                    track.spotify_track_id,
                    status="ready",
                    error=None,
                )
            continue
        database.update_library_track(
            source_id,
            track.spotify_track_id,
            status="missing",
            staging_file_path=None,
            match_method=None,
            confidence=0,
            reason="Downloaded file is missing from the permanent folder.",
        )
        if job:
            database.update_library_acquisition_job(
                source_id,
                track.spotify_track_id,
                status="acquisition_failed",
                error="Downloaded file is missing from the permanent folder.",
            )

    review = require_library_review(database, source_id)
    claimed = {
        track.staging_file_path
        for track in review.tracks
        if track.staging_file_path and track.status in {"ready", "imported"}
    }
    for track in review.tracks:
        if track.status not in {"new", "missing"}:
            continue
        available = [candidate for candidate in candidates if candidate.content_id not in claimed]
        result = match_spotify_track(library_track_to_spotify_track(track), available, minimum_confidence=85)
        if result.status == "matched" and result.rekordbox_content_id:
            claimed.add(result.rekordbox_content_id)
            database.update_library_track(
                source_id,
                track.spotify_track_id,
                status="ready",
                staging_file_path=result.rekordbox_content_id,
                match_method=f"staging:{result.method}",
                confidence=result.confidence,
                reason=library_ready_reason(track),
            )
            job = database.get_library_acquisition_job(source_id, track.spotify_track_id)
            if job:
                database.update_library_acquisition_job(
                    source_id,
                    track.spotify_track_id,
                    status="ready",
                    error=None,
                )

    # Phase 3: Force-assign for manual Deezer downloads via pre/post diff.
    # No metadata matching — the user's explicit choice is trusted 100%.
    review = require_library_review(database, source_id)
    claimed = {
        track.staging_file_path
        for track in review.tracks
        if track.staging_file_path and track.status in {"ready", "imported"}
    }
    for track in review.tracks:
        if track.status not in {"new", "missing"}:
            continue
        job = database.get_library_acquisition_job(source_id, track.spotify_track_id)
        if not job or job.match_method != "manual":
            continue
        if job.status not in {"downloaded", "resolved", "queued", "downloading", "ready"}:
            continue

        pre = set(job.payload.get("pre_download_files", []) if isinstance(job.payload, dict) else [])
        job_isrc = job.payload.get("isrc") if isinstance(job.payload, dict) else None

        new_files = [
            f for f in audio_files
            if f["file_path"] not in pre and f["file_path"] not in claimed
        ]

        matched_file = None
        if len(new_files) == 1:
            matched_file = new_files[0]
        elif len(new_files) > 1 and job_isrc:
            matched_file = next((f for f in new_files if f.get("isrc") == job_isrc), None)
        # If 0 new files: download not yet visible → skip, retry on next refresh cycle

        if matched_file:
            claimed.add(matched_file["file_path"])
            database.update_library_track(
                source_id,
                track.spotify_track_id,
                status="ready",
                staging_file_path=matched_file["file_path"],
                match_method="manual_deezer",
                confidence=100,
                reason="Manually selected Deezer track, file assigned by download diff.",
            )
            if job.status != "ready":
                database.update_library_acquisition_job(
                    source_id,
                    track.spotify_track_id,
                    status="ready",
                    error=None,
                )


def library_ready_reason(track: LibraryTrackReview) -> str:
    if "missing from the Rekordbox collection" in track.reason:
        return (
            "Previously imported track is missing from the Rekordbox collection. "
            "A local audio file is ready to re-import."
        )
    return "Downloaded audio file matched this Spotify track."


def library_track_to_spotify_track(track: LibraryTrackReview) -> SpotifyTrack:
    return SpotifyTrack(
        id=track.spotify_track_id,
        uri=track.spotify_uri,
        title=track.title,
        artists=track.artists,
        durationMs=track.duration_ms,
        isrc=track.isrc,
    )


def build_library_download_response(
    database: LocalDatabase,
    source_id: int,
    *,
    created: int,
) -> dict[str, Any]:
    review = require_library_review(database, source_id)
    jobs = database.list_library_acquisition_jobs(source_id, DEEMIX_PROVIDER)
    counts = acquisition_status_counts(jobs)
    return {
        "sourceId": source_id,
        "created": created,
        "queued": counts["queued"],
        "downloading": counts["downloading"],
        "downloaded": counts["downloaded"],
        "ready": counts["ready"],
        "failed": counts["acquisition_failed"],
        "ambiguous": counts["acquisition_ambiguous"],
        "jobs": jobs,
        "review": review,
    }


def library_acquisition_job_payload(
    track: LibraryTrackReview,
    *,
    status: str,
    deezer_track_id: str | None = None,
    confidence: int = 0,
    match_method: str | None = None,
    download_id: str | None = None,
    output_dir: str | None = None,
    error: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "spotify_track_id": track.spotify_track_id,
        "provider": DEEMIX_PROVIDER,
        "deezer_track_id": deezer_track_id,
        "status": status,
        "confidence": confidence,
        "match_method": match_method,
        "download_id": download_id,
        "output_dir": output_dir,
        "error": error,
        "payload": payload or {},
    }


def deemix_permanent_settings(audio_dir: Path) -> dict[str, Any]:
    return {
        "downloadPath": str(audio_dir),
        "quality": PERMANENT_DOWNLOAD_QUALITY,
        "createArtistFolder": False,
        "createAlbumFolder": False,
        "createPlaylistFolder": False,
        "createCDFolder": False,
        "createPlaylistStructure": False,
        "createSinglesStructure": False,
        "overwriteFiles": "rename",
        "bitrateFallback": True,
        "trackNameTemplate": "%artist% - %title%",
    }


def compact_deezer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = deezer_candidate_from_payload(payload)
    if candidate:
        return {
            "id": candidate.id,
            "title": candidate.title,
            "artist": candidate.artist,
            "album": candidate.album,
            "durationMs": candidate.duration_ms,
        }
    compact = {}
    for key in ("id", "title", "title_short", "duration", "isrc", "error"):
        if key in payload:
            compact[key] = payload[key]
    return compact


def require_library_source(database: LocalDatabase, source_id: int) -> LibrarySource:
    source = database.get_library_source(source_id)
    if source is None:
        raise KeyError(f"Library source {source_id} was not found.")
    return source


def require_library_review(database: LocalDatabase, source_id: int) -> LibraryReview:
    review = database.get_library_review(source_id)
    if review is None:
        raise KeyError(f"Library source {source_id} was not found.")
    return review
