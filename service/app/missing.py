"""Re-download orchestration for missing collection files.

Given a Rekordbox content row whose audio file no longer exists, find the track
on Deezer (ISRC first, then metadata), download it via Deemix into the clean
'permanent' folder, and re-point the existing collection row at the new file —
preserving its cues, tags and playlist memberships.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from .acquisition import DeemixClient, DeezerResolver, deemix_event_settings
from .audio import find_downloaded_file


async def redownload_missing_file(
    adapter: Any,
    content_id: str,
    *,
    deemix_client: DeemixClient | None = None,
    timeout_s: float = 120.0,
    poll_interval_s: float = 2.0,
) -> dict[str, Any]:
    # Fail fast if Rekordbox is open (so we don't download then fail to re-link).
    adapter.assert_mutation_ready()

    meta = adapter.content_meta(content_id)
    isrc = (meta.get("isrc") or "").strip()
    title = meta.get("title") or ""
    artist = meta.get("artist") or ""

    resolver = DeezerResolver()
    candidate = None
    if isrc:
        result = await resolver.resolve_by_isrc(isrc)
        candidate = result.candidate
    if candidate is None:
        query = f"{artist} {title}".strip()
        if query:
            results = await resolver.search(query, limit=5)
            candidate = results[0] if results else None
    if candidate is None:
        raise ValueError(
            "Could not find this track on Deezer (no ISRC/metadata match) to re-download."
        )

    permanent_dir = Path(adapter.storage_layout().permanent)
    permanent_dir.mkdir(parents=True, exist_ok=True)

    client = deemix_client or DeemixClient()
    await client.update_settings(deemix_event_settings(permanent_dir))
    await client.download_batch([candidate.id], "Syncbox Restore")

    downloaded: str | None = None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        downloaded = find_downloaded_file(
            permanent_dir, isrc or None, candidate.title, candidate.artist
        )
        if downloaded:
            break
        await asyncio.sleep(poll_interval_s)

    if not downloaded:
        raise TimeoutError(
            "The download didn't complete in time. Check that the Deemix provider "
            "is running, then try again."
        )

    relink = adapter.relink_content(content_id, downloaded)
    return {
        "contentId": str(content_id),
        "filePath": downloaded,
        "title": candidate.title,
        "artist": candidate.artist,
        "backupPath": relink.get("backupPath"),
        "message": f"Re-downloaded and re-linked “{candidate.artist} – {candidate.title}”.",
    }
