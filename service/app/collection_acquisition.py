"""Missing-file re-download as first-class acquisition jobs (scope "collection").

Unlike the bespoke synchronous download this replaces, a re-download here is a
real acquisition job: it is created (resolved -> queued), funnels into the same
Deemix download + global job stream + Download & Match view as event/library
acquisitions, and is advanced by the shared SSE refresh loop. When the download
completes, the file is re-linked onto the existing Rekordbox content row
(preserving cues/tags/playlists) and the job is marked "ready".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .acquisition import (
    DEEMIX_PROVIDER,
    DeemixClient,
    DeezerResolver,
    deemix_event_settings,
    extract_download_ids,
    extract_queue_items,
    map_deemix_queue_status,
    nested_value,
    optional_text,
)
from .audio import find_downloaded_file
from .db import LocalDatabase


async def enqueue_collection_redownload(
    database: LocalDatabase,
    adapter: Any,
    content_id: str,
    *,
    deemix_client: DeemixClient | None = None,
    deezer_resolver: DeezerResolver | None = None,
) -> dict[str, Any]:
    """Resolve the track on Deezer and queue a Deemix download, returning at
    once. Completion + re-link happen later via ``sync_collection_jobs``.
    """
    meta = adapter.content_meta(content_id)
    isrc = (meta.get("isrc") or "").strip()
    title = meta.get("title") or ""
    artist = meta.get("artist") or ""

    base_job = {
        "provider": DEEMIX_PROVIDER,
        "title": title,
        "artist": artist,
        "isrc": isrc or None,
        "output_dir": str(adapter.storage_layout().permanent),
    }

    resolver = deezer_resolver or DeezerResolver()
    candidate = None
    if isrc:
        result = await resolver.resolve_by_isrc(isrc)
        candidate = result.candidate
    if candidate is None and (query := f"{artist} {title}".strip()):
        results = await resolver.search(query, limit=5)
        candidate = results[0] if results else None

    if candidate is None:
        database.upsert_collection_job(
            content_id,
            {**base_job, "status": "acquisition_failed",
             "error": "No Deezer match found (ISRC/metadata) to re-download."},
        )
        return {"contentId": str(content_id), "status": "acquisition_failed",
                "message": "Couldn't find this track on Deezer to re-download."}

    client = deemix_client or DeemixClient()
    status = await client.status()
    if not status.available or not status.authenticated:
        database.upsert_collection_job(
            content_id,
            {**base_job, "status": "acquisition_failed", "deezer_track_id": candidate.id,
             "error": status.detail or "Deemix provider is not available."},
        )
        return {"contentId": str(content_id), "status": "acquisition_failed",
                "message": status.detail or "Deemix provider is not available."}

    database.upsert_collection_job(
        content_id,
        {**base_job, "status": "resolved", "deezer_track_id": candidate.id,
         "confidence": 100, "match_method": "missing_redownload"},
    )

    permanent_dir = Path(adapter.storage_layout().permanent)
    permanent_dir.mkdir(parents=True, exist_ok=True)
    try:
        await client.update_settings(deemix_event_settings(permanent_dir))
        response = await client.download_batch([candidate.id], "Syncbox Restore")
    except Exception as exc:
        database.update_collection_job(
            content_id, status="acquisition_failed", error=str(exc)
        )
        return {"contentId": str(content_id), "status": "acquisition_failed",
                "message": str(exc)}

    download_ids = extract_download_ids(response)
    database.update_collection_job(
        content_id,
        status="queued",
        download_id=download_ids[0] if download_ids else None,
        error=None,
    )
    return {
        "contentId": str(content_id),
        "status": "queued",
        "title": candidate.title,
        "artist": candidate.artist,
        "message": f"Queued re-download of “{candidate.artist} – {candidate.title}”. "
        "Follow progress in Download & Match; it re-links automatically when done.",
    }


async def sync_collection_jobs(
    database: LocalDatabase,
    adapter: Any,
    *,
    deemix_client: DeemixClient | None = None,
) -> None:
    """Advance active collection jobs from the live Deemix queue, and re-link the
    Rekordbox row once the file has downloaded. Idempotent: safe to call on every
    refresh. Mirrors ``sync_deemix_queue`` for events/library.
    """
    jobs = [
        job
        for job in database.list_collection_jobs(DEEMIX_PROVIDER)
        if job["status"] in {"resolved", "queued", "downloading", "downloaded"}
    ]
    if not jobs:
        return

    client = deemix_client or DeemixClient()
    queue_payload = await client.queue()
    items = extract_queue_items(queue_payload)
    by_id = {
        optional_text(item.get("id") or item.get("downloadId") or item.get("uuid")): item
        for item in items
    }
    by_track = {
        optional_text(
            item.get("trackId")
            or item.get("deezerTrackId")
            or nested_value(item, ["track", "id"])
        ): item
        for item in items
    }

    permanent_dir = Path(adapter.storage_layout().permanent)
    for job in jobs:
        content_id = job["content_id"]
        item = None
        if job["download_id"]:
            item = by_id.get(job["download_id"])
        if item is None and job["deezer_track_id"]:
            item = by_track.get(job["deezer_track_id"])

        mapped = map_deemix_queue_status(item) if item is not None else job["status"]
        if mapped == "acquisition_failed":
            database.update_collection_job(
                content_id, status="acquisition_failed",
                error=optional_text(item.get("error") or item.get("message")) if item else None,
            )
            continue

        # Try to adopt the file once the download has landed (or as a fallback,
        # whenever it is already on disk under the expected name).
        if mapped in {"downloaded", "ready"} or job["status"] == "downloaded":
            downloaded = find_downloaded_file(
                permanent_dir, job.get("isrc"), job["title"], job["artist"]
            )
            if downloaded:
                try:
                    adapter.relink_content(content_id, downloaded)
                    database.update_collection_job(
                        content_id, status="ready", error=None,
                        output_dir=downloaded,
                    )
                except Exception as exc:
                    # e.g. Rekordbox is open — keep the file, retry next refresh.
                    database.update_collection_job(
                        content_id, status="downloaded", error=str(exc)
                    )
            else:
                database.update_collection_job(content_id, status="downloaded")
        elif mapped != job["status"]:
            database.update_collection_job(content_id, status=mapped)
