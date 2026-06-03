from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from .audio import scan_audio_files
from .db import LocalDatabase, count_by_status, optional_string as optional_text
from .event_import import require_event_review, scan_event_staging
from .matching import duration_score, text_similarity
from .models import (
    AcquisitionJob,
    DeemixStatus,
    EventAcquisitionResponse,
    EventReview,
    EventTrackReview,
)


DEFAULT_DEEMIX_BASE_URL = "http://127.0.0.1:6595"
DEEZER_API_URL = "https://api.deezer.com"
DEEMIX_PROVIDER = "deemix"
AUTO_MATCH_THRESHOLD = 85
REVIEW_MATCH_THRESHOLD = 70

# Deemix's /api/auth/status proxies to Deezer, which rate-limits hard (429) when
# polled often. The status indicator is polled every few seconds, so cache the
# result briefly to keep Deezer load (and the resulting 429s that spill over into
# real downloads) low.
_STATUS_CACHE: dict[str, tuple[float, "DeemixStatus"]] = {}
_STATUS_CACHE_TTL = 25.0

# The ARL last successfully pushed to Deemix in this process — so the download
# flows can guarantee Deemix is configured without re-hitting Deezer every time.
_applied_arl: str | None = None


@dataclass(frozen=True)
class DeezerTrackCandidate:
    id: str
    title: str
    artist: str
    album: str | None
    duration_ms: int | None
    payload: dict[str, Any]
    cover_url: str | None = None
    preview_url: str | None = None


@dataclass(frozen=True)
class DeezerResolveResult:
    status: str
    confidence: int = 0
    match_method: str | None = None
    candidate: DeezerTrackCandidate | None = None
    error: str | None = None
    payload: dict[str, Any] | None = None


class DeemixClient:
    def __init__(
        self,
        base_url: str = DEFAULT_DEEMIX_BASE_URL,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def status(self) -> DeemixStatus:
        now = time.monotonic()
        cached = _STATUS_CACHE.get(self.base_url)
        if cached is not None and now - cached[0] < _STATUS_CACHE_TTL:
            return cached[1]
        result = await self._fetch_status(previous=cached[1] if cached else None)
        _STATUS_CACHE[self.base_url] = (now, result)
        return result

    async def _fetch_status(self, *, previous: DeemixStatus | None) -> DeemixStatus:
        try:
            health = await self.health()
        except Exception as exc:
            return DeemixStatus(
                baseUrl=self.base_url,
                available=False,
                authenticated=False,
                detail=f"Deemix local API is not reachable: {exc}",
                version=None,
            )

        auth_payload = health
        try:
            auth_payload = {**health, **await self.auth_status()}
        except Exception as exc:
            # A 429 from Deezer means the session is live but throttled — keep the
            # last known authenticated state instead of flapping the indicator.
            if previous is not None and (
                "429" in str(exc) or "Too Many Requests" in str(exc)
            ):
                return DeemixStatus(
                    baseUrl=self.base_url,
                    available=True,
                    authenticated=previous.authenticated,
                    detail=previous.detail,
                    version=optional_text(health.get("version")),
                )
            auth_payload = health

        authenticated = bool(
            auth_payload.get("authenticated")
            or auth_payload.get("isAuthenticated")
            or auth_payload.get("loggedIn")
            or auth_payload.get("user")
        )
        detail = (
            "Deemix local API is reachable and authenticated."
            if authenticated
            else "Deemix local API is reachable but is not authenticated."
        )
        return DeemixStatus(
            baseUrl=self.base_url,
            available=True,
            authenticated=authenticated,
            detail=detail,
            version=optional_text(health.get("version")),
        )

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/api/health")

    async def auth_status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/auth/status")

    async def login_arl(self, arl: str) -> dict[str, Any]:
        """Authenticate Deemix's Deezer session with an ARL token. Lets Syncbox
        own the ARL so the user never has to open Deemix's own UI."""
        result = await self._request("POST", "/api/auth/login", json={"arl": arl})
        # Auth state just changed: drop the cached status and remember the ARL so
        # the lazy download-flow check doesn't re-apply it needlessly.
        global _applied_arl
        _STATUS_CACHE.pop(self.base_url, None)
        _applied_arl = arl
        return result

    async def settings(self) -> dict[str, Any]:
        return await self._request("GET", "/api/settings")

    async def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/settings", json=settings)

    async def download_batch(
        self,
        track_ids: list[str],
        playlist_name: str,
        playlist_cover_url: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trackIds": track_ids,
            "playlistName": playlist_name,
        }
        if playlist_cover_url:
            payload["playlistCoverUrl"] = playlist_cover_url
        return await self._request("POST", "/api/download/batch", json=payload)

    async def queue(self) -> dict[str, Any]:
        return await self._request("GET", "/api/queue")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, f"{self.base_url}{path}", json=json)
        if response.status_code >= 400:
            raise RuntimeError(response.text or response.reason_phrase)
        if response.status_code == 204:
            return {}
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return {"items": payload}
        return {"value": payload}


class DeezerResolver:
    def __init__(
        self,
        base_url: str = DEEZER_API_URL,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def resolve(self, track: EventTrackReview) -> DeezerResolveResult:
        if track.isrc:
            isrc_result = await self.resolve_by_isrc(track.isrc)
            if isrc_result.status == "resolved":
                return isrc_result

        return await self.resolve_by_metadata(track)

    async def resolve_by_isrc(self, isrc: str) -> DeezerResolveResult:
        payload = await self._get(f"/track/isrc:{isrc.strip()}")
        candidate = deezer_candidate_from_payload(payload)
        if not candidate:
            return DeezerResolveResult(
                status="acquisition_failed",
                error="No Deezer track found for this ISRC.",
                payload=payload,
            )
        return DeezerResolveResult(
            status="resolved",
            confidence=100,
            match_method="isrc",
            candidate=candidate,
            payload=payload,
        )

    async def resolve_by_metadata(self, track: EventTrackReview) -> DeezerResolveResult:
        artist = track.artists[0] if track.artists else ""
        queries = [
            f'artist:"{artist}" track:"{track.title}"'.strip(),
            f"{artist} {track.title}".strip(),
        ]
        best_candidate: DeezerTrackCandidate | None = None
        best_confidence = 0
        best_payload: dict[str, Any] = {}

        for query in queries:
            if not query:
                continue
            payload = await self._get("/search", params={"q": query, "limit": 10})
            data = payload.get("data") if isinstance(payload.get("data"), list) else []
            for item in data:
                if not isinstance(item, dict):
                    continue
                candidate = deezer_candidate_from_payload(item)
                if not candidate:
                    continue
                confidence = score_deezer_candidate(track, candidate)
                if confidence > best_confidence:
                    best_candidate = candidate
                    best_confidence = confidence
                    best_payload = item

        if not best_candidate:
            return DeezerResolveResult(
                status="acquisition_failed",
                error="No Deezer search result found.",
            )
        if best_confidence >= AUTO_MATCH_THRESHOLD:
            return DeezerResolveResult(
                status="resolved",
                confidence=best_confidence,
                match_method="metadata",
                candidate=best_candidate,
                payload=best_payload,
            )
        if best_confidence >= REVIEW_MATCH_THRESHOLD:
            return DeezerResolveResult(
                status="acquisition_ambiguous",
                confidence=best_confidence,
                match_method="metadata",
                candidate=best_candidate,
                error="Deezer metadata match needs manual review.",
                payload=best_payload,
            )
        return DeezerResolveResult(
            status="acquisition_failed",
            confidence=best_confidence,
            match_method="metadata",
            candidate=best_candidate,
            error="No Deezer metadata match reached the automatic threshold.",
            payload=best_payload,
        )

    async def search(self, query: str, *, limit: int = 15) -> list[DeezerTrackCandidate]:
        """Public free-text search returning parsed candidates."""
        payload = await self._get("/search", params={"q": query.strip(), "limit": limit})
        candidates: list[DeezerTrackCandidate] = []
        for item in payload.get("data") or []:
            candidate = deezer_candidate_from_payload(item)
            if candidate:
                candidates.append(candidate)
        return candidates

    async def fetch_track(self, deezer_track_id: str) -> tuple[DeezerTrackCandidate | None, dict[str, Any]]:
        """Public single-track lookup; returns (candidate, raw payload)."""
        payload = await self._get(f"/track/{deezer_track_id}")
        return deezer_candidate_from_payload(payload), payload

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
        if response.status_code >= 400:
            raise RuntimeError(response.text or response.reason_phrase)
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {}


async def get_deemix_status(client: DeemixClient | None = None) -> DeemixStatus:
    return await (client or DeemixClient()).status()


async def ensure_deemix_authenticated(database: LocalDatabase, client: DeemixClient) -> None:
    """Apply the stored Deezer ARL to Deemix once per process (or whenever it
    changes) so downloads work without opening Deemix.

    Deliberately does NOT call ``status()`` first: that proxies to Deezer and,
    polled before every download, gets rate-limited (429) — which then spills
    over into the actual ``download/batch`` call. ``login_arl`` is idempotent, so
    applying the same ARL once is enough. Best-effort: silent on failure (and a
    failure leaves ``_applied_arl`` unset, so it retries next time)."""
    arl = database.get_setting("deemix_arl")
    if not arl or arl == _applied_arl:
        return
    try:
        await client.login_arl(arl)  # records _applied_arl on success
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def run_auto_acquisition(
    database: LocalDatabase,
    event_id: int,
    *,
    deemix_client: DeemixClient | None = None,
    deezer_resolver: DeezerResolver | None = None,
) -> EventAcquisitionResponse:
    review = require_event_review(database, event_id)
    missing_tracks = [track for track in review.tracks if track.status == "missing"]
    client = deemix_client or DeemixClient()
    resolver = deezer_resolver or DeezerResolver()
    await ensure_deemix_authenticated(database, client)
    existing_jobs = {
        job.spotify_track_id: job
        for job in database.list_acquisition_jobs(event_id, DEEMIX_PROVIDER)
    }
    eligible_tracks = [
        track
        for track in missing_tracks
        if should_create_acquisition_job(existing_jobs.get(track.spotify_track_id))
    ]
    created = sum(1 for track in eligible_tracks if track.spotify_track_id not in existing_jobs)

    if not eligible_tracks:
        await refresh_acquisition_jobs(database, event_id, deemix_client=client)
        return build_acquisition_response(database, event_id, created=0)

    status = await client.status()
    if not status.available or not status.authenticated:
        for track in eligible_tracks:
            database.upsert_acquisition_job(
                event_id,
                acquisition_job_payload(
                    track,
                    status="acquisition_failed",
                    output_dir=review.audio_dir,
                    error=status.detail,
                ),
            )
        return build_acquisition_response(database, event_id, created=created)

    resolved_tracks: list[tuple[EventTrackReview, DeezerResolveResult]] = []
    for track in eligible_tracks:
        try:
            result = await resolver.resolve(track)
        except Exception as exc:
            result = DeezerResolveResult(status="acquisition_failed", error=str(exc))
        if result.status == "resolved" and result.candidate:
            resolved_tracks.append((track, result))
        database.upsert_acquisition_job(
            event_id,
            acquisition_job_payload(
                track,
                status=result.status,
                deezer_track_id=result.candidate.id if result.candidate else None,
                confidence=result.confidence,
                match_method=result.match_method,
                output_dir=review.audio_dir,
                error=result.error,
                payload=compact_deezer_payload(result.payload or {}),
            ),
        )

    if resolved_tracks:
        await queue_resolved_tracks(database, review, client, resolved_tracks)
        await refresh_acquisition_jobs(database, event_id, deemix_client=client)

    return build_acquisition_response(database, event_id, created=created)


async def refresh_acquisition_jobs(
    database: LocalDatabase,
    event_id: int,
    *,
    deemix_client: DeemixClient | None = None,
) -> list[AcquisitionJob]:
    client = deemix_client or DeemixClient()
    try:
        await sync_deemix_queue(database, event_id, client)
    except Exception:
        pass
    return database.list_acquisition_jobs(event_id, DEEMIX_PROVIDER)


async def queue_resolved_tracks(
    database: LocalDatabase,
    review: EventReview,
    client: DeemixClient,
    resolved_tracks: list[tuple[EventTrackReview, DeezerResolveResult]],
) -> None:
    track_ids = [
        result.candidate.id
        for _, result in resolved_tracks
        if result.candidate is not None
    ]
    if not track_ids:
        return

    try:
        await client.update_settings(deemix_event_settings(Path(review.audio_dir)))
        response = await client.download_batch(track_ids, review.event_name)
    except Exception as exc:
        for track, result in resolved_tracks:
            database.update_acquisition_job(
                review.id,
                track.spotify_track_id,
                status="acquisition_failed",
                error=str(exc),
                payload=compact_deezer_payload(result.payload or {}),
            )
        return

    download_ids = extract_download_ids(response)
    for index, (track, result) in enumerate(resolved_tracks):
        existing_job = database.get_acquisition_job(review.id, track.spotify_track_id, DEEMIX_PROVIDER)
        existing_payload = existing_job.payload if existing_job and isinstance(existing_job.payload, dict) else {}
        database.update_acquisition_job(
            review.id,
            track.spotify_track_id,
            status="queued",
            download_id=download_ids[index] if index < len(download_ids) else None,
            error=None,
            payload={
                **existing_payload,
                **compact_deezer_payload(result.payload or {}),
                "batchCount": len(download_ids),
            },
        )


def iter_queue_status_changes(
    active_jobs: list[Any],
    queue_payload: dict[str, Any],
) -> "Iterator[tuple[Any, dict[str, Any], str]]":
    """Yield ``(job, queue_item, mapped_status)`` for each active acquisition job
    whose Deemix queue status has changed.

    Shared by the event and library queue-reconciliation loops so the queue
    parsing and job↔item matching lives in exactly one place; each caller keeps
    its own write/post-processing.
    """
    queue_items = extract_queue_items(queue_payload)
    items_by_id = {
        optional_text(item.get("id") or item.get("downloadId") or item.get("uuid")): item
        for item in queue_items
    }
    items_by_track_id = {
        optional_text(
            item.get("trackId")
            or item.get("deezerTrackId")
            or nested_value(item, ["track", "id"])
        ): item
        for item in queue_items
    }
    for job in active_jobs:
        item = items_by_id.get(job.download_id) if job.download_id else None
        if item is None and job.deezer_track_id:
            item = items_by_track_id.get(job.deezer_track_id)
        if item is None:
            continue
        mapped_status = map_deemix_queue_status(item)
        if mapped_status == job.status:
            continue
        yield job, item, mapped_status


async def sync_deemix_queue(
    database: LocalDatabase,
    event_id: int,
    client: DeemixClient,
) -> None:
    jobs = database.list_acquisition_jobs(event_id, DEEMIX_PROVIDER)
    active_jobs = [
        job
        for job in jobs
        if job.status in {"resolved", "queued", "downloading", "downloaded"}
    ]
    if not active_jobs:
        return

    queue_payload = await client.queue()
    changed_to_downloaded = False
    for job, item, mapped_status in iter_queue_status_changes(active_jobs, queue_payload):
        if mapped_status == "acquisition_failed":
            database.update_acquisition_job(
                event_id,
                job.spotify_track_id,
                status=mapped_status,
                error=optional_text(item.get("error") or item.get("message")),
                payload={**job.payload, "queueStatus": mapped_status},
            )
        else:
            database.update_acquisition_job(
                event_id,
                job.spotify_track_id,
                status=mapped_status,
                payload={**job.payload, "queueStatus": mapped_status},
            )
        changed_to_downloaded = changed_to_downloaded or mapped_status == "downloaded"

    if changed_to_downloaded:
        mark_ready_tracks_after_scan(database, event_id)


def match_manual_deezer_jobs(
    tracks: list[Any],
    audio_files: list[dict[str, Any]],
    claimed: set[str],
    *,
    get_job_fn: Callable[[str], AcquisitionJob | None],
    update_track_fn: Callable[..., None],
    update_job_fn: Callable[..., None],
) -> None:
    """Phase 3 (shared): force-assign downloaded files to tracks with manual Deezer jobs.

    Matches by ISRC first (exact), then by Deezer title+artist (fuzzy, 80% threshold).
    This is reliable across concurrent downloads because it uses stored Deezer metadata,
    not Spotify metadata or timing-dependent file scanning.
    """
    for track in tracks:
        if track.status not in {"new", "missing"}:
            continue
        job = get_job_fn(track.spotify_track_id)
        if not job or job.match_method != "manual":
            continue
        if job.status not in {"downloaded", "resolved", "queued", "downloading", "ready"}:
            continue

        payload = job.payload if isinstance(job.payload, dict) else {}
        job_isrc: str | None = payload.get("isrc") or None
        job_title: str = str(payload.get("title") or "")
        job_artist: str = str(payload.get("artist") or "")

        matched_file = None
        unclaimed = [f for f in audio_files if f["file_path"] not in claimed]

        if job_isrc:
            matched_file = next((f for f in unclaimed if f.get("isrc") == job_isrc), None)

        if not matched_file and job_title:
            best_score = 0
            for f in unclaimed:
                title_score = text_similarity(job_title, f.get("title") or "")
                artist_score = text_similarity(job_artist, f.get("artist") or "")
                combined = round(title_score * 0.65 + artist_score * 0.35)
                if combined > best_score:
                    best_score = combined
                    if combined >= 80:
                        matched_file = f

        if matched_file:
            claimed.add(matched_file["file_path"])
            update_track_fn(
                track.spotify_track_id,
                status="ready",
                staging_file_path=matched_file["file_path"],
                match_method="manual_deezer",
                confidence=100,
                reason="Manually selected Deezer track matched by Deezer metadata.",
            )
            if job.status != "ready":
                update_job_fn(track.spotify_track_id, status="ready", error=None)


def mark_ready_tracks_after_scan(database: LocalDatabase, event_id: int) -> None:
    review = scan_event_staging(database, event_id)
    ready_ids = {
        track.spotify_track_id
        for track in review.tracks
        if track.status == "ready" and track.staging_file_path
    }
    for spotify_track_id in ready_ids:
        job = database.get_acquisition_job(event_id, spotify_track_id, DEEMIX_PROVIDER)
        if job and job.status != "ready":
            database.update_acquisition_job(event_id, spotify_track_id, status="ready")
    for job in database.list_acquisition_jobs(event_id, DEEMIX_PROVIDER):
        if job.status == "ready" and job.spotify_track_id not in ready_ids:
            database.update_acquisition_job(
                event_id,
                job.spotify_track_id,
                status="acquisition_failed",
                error="Downloaded file is missing from the event folder.",
            )

    # Phase 3: force-assign for manual Deezer downloads (same logic as library).
    review = require_event_review(database, event_id)
    audio_files = scan_audio_files(Path(review.audio_dir))
    claimed = {
        track.staging_file_path
        for track in review.tracks
        if track.staging_file_path and track.status in {"ready", "applied"}
    }
    match_manual_deezer_jobs(
        review.tracks,
        audio_files,
        claimed,
        get_job_fn=lambda sid: database.get_acquisition_job(event_id, sid, DEEMIX_PROVIDER),
        update_track_fn=lambda sid, **kw: database.update_event_track(event_id, sid, **kw),
        update_job_fn=lambda sid, **kw: database.update_acquisition_job(event_id, sid, **kw),
    )


def build_acquisition_response(
    database: LocalDatabase,
    event_id: int,
    *,
    created: int = 0,
) -> EventAcquisitionResponse:
    review = require_event_review(database, event_id)
    jobs = database.list_acquisition_jobs(event_id, DEEMIX_PROVIDER)
    counts = acquisition_status_counts(jobs)
    return EventAcquisitionResponse(
        eventId=event_id,
        created=created,
        queued=counts["queued"],
        downloading=counts["downloading"],
        downloaded=counts["downloaded"],
        ready=counts["ready"],
        failed=counts["acquisition_failed"],
        ambiguous=counts["acquisition_ambiguous"],
        jobs=jobs,
        review=review,
    )


def acquisition_status_counts(jobs: list[AcquisitionJob]) -> dict[str, int]:
    return count_by_status(
        jobs,
        (
            "queued",
            "downloading",
            "downloaded",
            "ready",
            "acquisition_failed",
            "acquisition_ambiguous",
        ),
    )


def should_create_acquisition_job(job: AcquisitionJob | None) -> bool:
    if job is None:
        return True
    return job.status in {"pending", "acquisition_failed", "acquisition_ambiguous"}


def acquisition_job_payload(
    track: EventTrackReview,
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


def compact_deezer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = deezer_candidate_from_payload(payload)
    if candidate:
        result: dict[str, Any] = {
            "id": candidate.id,
            "title": candidate.title,
            "artist": candidate.artist,
            "album": candidate.album,
            "durationMs": candidate.duration_ms,
        }
        isrc = str(payload.get("isrc") or "").strip()
        if isrc:
            result["isrc"] = isrc
        return result
    compact = {}
    for key in ("id", "title", "title_short", "duration", "isrc", "error"):
        if key in payload:
            compact[key] = payload[key]
    return compact


def deemix_event_settings(audio_dir: Path, quality: str = "MP3_320") -> dict[str, Any]:
    return {
        "downloadPath": str(audio_dir),
        "quality": quality,
        "createArtistFolder": False,
        "createAlbumFolder": False,
        "createPlaylistFolder": False,
        "createCDFolder": False,
        "createPlaylistStructure": False,
        "createSinglesStructure": False,
        "overwriteFiles": "rename",
        "bitrateFallback": True,
        "trackNameTemplate": "%artist% - %title%",
        "albumTrackTemplate": "%artist% - %title%",
        "playlistTrackTemplate": "%artist% - %title%",
    }


def deezer_candidate_from_payload(payload: dict[str, Any]) -> DeezerTrackCandidate | None:
    if payload.get("error") or not payload.get("id"):
        return None
    artist = payload.get("artist") if isinstance(payload.get("artist"), dict) else {}
    album = payload.get("album") if isinstance(payload.get("album"), dict) else {}
    duration = payload.get("duration")
    return DeezerTrackCandidate(
        id=str(payload["id"]),
        title=str(payload.get("title") or payload.get("title_short") or ""),
        artist=str(artist.get("name") or ""),
        album=optional_text(album.get("title")),
        duration_ms=int(duration) * 1000 if duration is not None else None,
        payload=payload,
        cover_url=optional_text(album.get("cover_medium") or album.get("cover")),
        preview_url=optional_text(payload.get("preview")),
    )


def score_deezer_candidate(
    track: EventTrackReview,
    candidate: DeezerTrackCandidate,
) -> int:
    spotify_artist = " ".join(track.artists)
    title = text_similarity(track.title, candidate.title)
    artist = text_similarity(spotify_artist, candidate.artist)
    duration = duration_score(track.duration_ms, candidate.duration_ms)
    return round(title * 0.55 + artist * 0.35 + duration * 0.10)


def extract_download_ids(payload: dict[str, Any]) -> list[str]:
    for key in ("downloadIds", "downloads", "ids", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            ids = []
            for item in value:
                if isinstance(item, dict):
                    item_id = item.get("id") or item.get("downloadId") or item.get("uuid")
                    if item_id is not None:
                        ids.append(str(item_id))
                elif item is not None:
                    ids.append(str(item))
            if ids:
                return ids
    download_id = payload.get("downloadId") or payload.get("id")
    return [str(download_id)] if download_id is not None else []


def extract_queue_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("queue", "items", "downloads", "jobs"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def map_deemix_queue_status(item: dict[str, Any]) -> str:
    if bool(item.get("completed") or item.get("done") or item.get("finished")):
        return "downloaded"
    if bool(item.get("failed")):
        return "acquisition_failed"

    raw_status = str(item.get("status") or item.get("state") or "").lower()
    if any(token in raw_status for token in ("complete", "done", "finish", "success")):
        return "downloaded"
    if any(token in raw_status for token in ("download", "progress", "active", "running")):
        return "downloading"
    if any(token in raw_status for token in ("fail", "error", "cancel")):
        return "acquisition_failed"
    return "queued"


def nested_value(payload: dict[str, Any], path: list[str]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


async def queue_event_manual_deezer(
    database: LocalDatabase,
    event_id: int,
    spotify_track_id: str,
    deezer_track_id: str,
    *,
    deemix_client: DeemixClient | None = None,
) -> dict[str, Any]:
    """Queue a manually selected Deezer track for an event track download.

    Stores {isrc, title, artist} in the job payload so Phase 3 can match the downloaded
    file to this track regardless of timing or Deezer vs Spotify title differences.
    """
    review = require_event_review(database, event_id)
    track = next((t for t in review.tracks if t.spotify_track_id == spotify_track_id), None)
    if track is None:
        raise KeyError(f"Track {spotify_track_id} not found in event {event_id}.")

    resolver = DeezerResolver()
    payload = await resolver._get(f"/track/{deezer_track_id}")
    candidate = deezer_candidate_from_payload(payload)
    if candidate is None:
        raise ValueError(f"Deezer track {deezer_track_id} not found.")

    deezer_isrc = str(payload.get("isrc") or "").strip() or None
    database.upsert_acquisition_job(
        event_id,
        acquisition_job_payload(
            track,
            status="resolved",
            deezer_track_id=candidate.id,
            confidence=100,
            match_method="manual",
            output_dir=review.audio_dir,
            payload={"isrc": deezer_isrc, "title": candidate.title, "artist": candidate.artist},
        ),
    )

    result = DeezerResolveResult(
        status="resolved",
        confidence=100,
        match_method="manual",
        candidate=candidate,
    )
    client = deemix_client or DeemixClient()
    await ensure_deemix_authenticated(database, client)
    await queue_resolved_tracks(database, review, client, [(track, result)])
    await refresh_acquisition_jobs(database, event_id, deemix_client=client)

    return {"queued": 1, "deezerTrackId": candidate.id, "title": candidate.title, "artist": candidate.artist}
