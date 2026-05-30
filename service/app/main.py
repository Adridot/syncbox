from __future__ import annotations

import asyncio
import json
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from .config import load_config
from .diagnostics import run_diagnostics
from .logging_setup import configure_logging
from .version import app_version
from .acquisition import (
    DeemixClient,
    DeezerResolver,
    DeezerResolveResult,
    acquisition_job_payload,
    get_deemix_status,
    queue_event_manual_deezer,
    refresh_acquisition_jobs,
    retry_acquisition,
    run_auto_acquisition,
)
from .db import LocalDatabase
from .models import (
    AcquisitionJob,
    AppSettings,
    BackupRestoreResponse,
    DeemixStatus,
    DeezerSearchResult,
    DiagnosticsReport,
    EventAcquisitionResponse,
    EventApplyResponse,
    EventDeletePreview,
    EventDeleteResponse,
    EventReview,
    EventSummary,
    EventTrackAddRequest,
    EventTrackReview,
    EventTrackUpdateRequest,
    GlobalAcquisitionJob,
    ManualEventCreateRequest,
    HealthResponse,
    LibraryApplyResponse,
    LibraryReview,
    LibrarySource,
    LibrarySourceIn,
    LibraryTrackDownloadRequest,
    LibraryTrackUpdateRequest,
    LiveImportPackage,
    LiveImportRequest,
    RekordboxBackup,
    RekordboxCollectionStats,
    RekordboxTrack,
    RekordboxPlaylist,
    RekordboxTag,
    SpotifyAuthUrlRequest,
    SpotifyAuthUrlResponse,
    SpotifyEventAnalyzeRequest,
    SpotifyEventPreviewRequest,
    SpotifyPlaylistsResponse,
    StorageLayout,
    SyncProposal,
    SyncProposalResolveRequest,
    TagPlaylistMapping,
    TagPlaylistMappingIn,
    TagRule,
    TagRuleIn,
)
from .event_import import (
    add_spotify_track_to_event,
    analyze_spotify_event,
    apply_event_track_update,
    create_manual_event,
    require_event_review,
    scan_event_staging,
)
from .live_import import build_live_import_package
from .library import (
    deemix_permanent_settings,
    download_library_tracks,
    queue_library_tracks,
    refresh_library_acquisition_jobs,
    require_library_review,
    refresh_library_review_state,
    sync_library_source,
    update_library_tracks,
)
from .rekordbox import RekordboxAdapter
from .spotify import (
    SpotifyAuthError,
    SpotifyClient,
    parse_playlist_id,
    summarize_playlist_page,
)
from .sync import generate_bidirectional_proposals


logger = configure_logging()
config = load_config()
database = LocalDatabase(config.app_database_path)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Syncbox service starting (version %s)", app_version())
    database.migrate()
    defaults = default_settings()
    current = database.get_app_settings(defaults)
    database.save_app_settings(current)
    logger.info("Database ready at %s", database.path)
    yield
    logger.info("Syncbox service shutting down")


app = FastAPI(title="Syncbox API", version=app_version(), lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Local renderer in dev (Vite may pick 5173/5174); packaged app loads from
    # file:// and is not CORS-restricted by Chromium for same-host loopback.
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="syncbox-service",
        version=app.version,
        databasePath=str(database.path),
    )


@app.get("/api/settings", response_model=AppSettings)
def get_settings() -> AppSettings:
    return database.get_app_settings(default_settings())


@app.post("/api/settings", response_model=AppSettings)
def save_settings(settings: AppSettings) -> AppSettings:
    return database.save_app_settings(settings)


@app.get("/api/rekordbox/status")
def rekordbox_status() -> Any:
    return build_rekordbox_adapter().status()


@app.get("/api/rekordbox/collection-stats", response_model=RekordboxCollectionStats)
def rekordbox_collection_stats() -> RekordboxCollectionStats:
    return RekordboxCollectionStats(**build_rekordbox_adapter().collection_stats())


@app.get("/api/diagnostics", response_model=DiagnosticsReport)
async def diagnostics() -> DiagnosticsReport:
    return await run_diagnostics(database, build_rekordbox_adapter())


@app.get("/api/rekordbox/backups", response_model=list[RekordboxBackup])
def list_rekordbox_backups() -> list[dict[str, Any]]:
    return build_rekordbox_adapter().list_backups()


@app.post("/api/rekordbox/backups/{name}/restore", response_model=BackupRestoreResponse)
def restore_rekordbox_backup(name: str) -> dict[str, Any]:
    adapter = build_rekordbox_adapter()
    try:
        result = adapter.restore_backup(name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # e.g. RekordboxRunningError — cannot mutate while RB is open.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("Restored Rekordbox backup %s (%s files)", name, result["restoredFiles"])
    return result


@app.post("/api/storage/ensure", response_model=StorageLayout)
def ensure_storage() -> StorageLayout:
    return build_rekordbox_adapter().ensure_storage_layout()


@app.get("/api/storage/layout", response_model=StorageLayout)
def storage_layout() -> StorageLayout:
    # Read-only: resolves the configured paths without creating any folder.
    return build_rekordbox_adapter().storage_layout()


@app.get("/api/storage/validate-path")
def validate_path(path: str = Query(default="")) -> dict[str, Any]:
    """Report whether a configured path exists and is a directory.

    Works on a specific cloud path (Dropbox/Google Drive) even though listing
    the parent is blocked. An empty path means "use the default" — not an error.
    """
    trimmed = path.strip()
    if not trimmed:
        return {"path": path, "configured": False, "exists": False, "isDir": False}
    target = Path(trimmed).expanduser()
    try:
        exists = target.exists()
        is_dir = target.is_dir() if exists else False
    except OSError:
        exists = False
        is_dir = False
    return {"path": path, "configured": True, "exists": exists, "isDir": is_dir}


@app.get("/api/tag-rules", response_model=list[TagRule])
def list_tag_rules() -> list[TagRule]:
    return database.list_tag_rules()


@app.post("/api/tag-rules", response_model=TagRule)
def save_tag_rule(rule: TagRuleIn) -> TagRule:
    if not rule.tags:
        raise HTTPException(status_code=400, detail="At least one tag is required.")
    return database.upsert_tag_rule(rule)


@app.get("/api/library/sources", response_model=list[LibrarySource])
def list_library_sources() -> list[LibrarySource]:
    return database.list_library_sources()


@app.post("/api/library/sources", response_model=LibrarySource)
def save_library_source(source: LibrarySourceIn) -> LibrarySource:
    return database.upsert_library_source(source)


@app.post("/api/library/sources/{source_id}/sync", response_model=LibraryReview)
async def sync_library_source_endpoint(source_id: int) -> LibraryReview:
    try:
        return await sync_library_source(
            database,
            build_rekordbox_adapter(),
            SpotifyClient(database),
            source_id,
        )
    except SpotifyAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/library/sources/sync-all", response_model=list[LibraryReview])
async def sync_all_library_sources() -> list[LibraryReview]:
    sources = database.list_library_sources()
    adapter = build_rekordbox_adapter()
    client = SpotifyClient(database)
    results: list[LibraryReview] = []
    failures: list[str] = []
    for source in sources:
        try:
            review = await sync_library_source(database, adapter, client, source.id)
            results.append(review)
        except Exception as exc:
            failures.append(source.spotify_playlist_name)
            logger.warning(
                "sync-all: source %s (%s) failed: %s",
                source.id, source.spotify_playlist_name, exc,
            )
    if failures and not results:
        raise HTTPException(
            status_code=503,
            detail=f"All sources failed to sync: {', '.join(failures)}",
        )
    return results


@app.get("/api/library/sources/{source_id}/review", response_model=LibraryReview)
async def get_library_source_review(source_id: int) -> LibraryReview:
    try:
        return await refresh_library_review_state(
            database,
            build_rekordbox_adapter(),
            source_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/library/tracks/update", response_model=LibraryReview)
def update_library_track_review(request: LibraryTrackUpdateRequest) -> LibraryReview:
    try:
        return update_library_tracks(database, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/library/tracks/download")
async def download_library_track_files(request: LibraryTrackDownloadRequest) -> dict[str, Any]:
    try:
        return await download_library_tracks(database, build_rekordbox_adapter(), request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/library/search-deezer", response_model=list[DeezerSearchResult])
async def search_deezer(query: str = Query(..., min_length=1)) -> list[dict[str, Any]]:
    return await deezer_search_results(query)


@app.post("/api/library/sources/{source_id}/tracks/{spotify_track_id}/queue-deezer")
async def queue_library_deezer_track(
    source_id: int,
    spotify_track_id: str,
    deezer_track_id: str = Body(..., embed=True, alias="deezerTrackId"),
) -> dict[str, Any]:
    try:
        review = require_library_review(database, source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    track = next((t for t in review.tracks if t.spotify_track_id == spotify_track_id), None)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found in source review.")

    resolver = DeezerResolver()
    try:
        candidate, payload = await resolver.fetch_track(deezer_track_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Deezer lookup failed: {exc}") from exc

    if not candidate:
        raise HTTPException(status_code=404, detail="Deezer track not found.")

    adapter = build_rekordbox_adapter()
    result = DeezerResolveResult(
        status="resolved",
        confidence=100,
        match_method="manual",
        candidate=candidate,
    )
    deezer_isrc = str(payload.get("isrc") or "").strip() or None

    # Store the chosen Deezer track on the library_track itself so matching survives job clearing
    database.update_library_track(
        source_id,
        spotify_track_id,
        pending_deezer_track_id=candidate.id,
        pending_deezer_isrc=deezer_isrc,
    )

    database.upsert_library_acquisition_job(
        source_id,
        acquisition_job_payload(
            track,
            status="resolved",
            deezer_track_id=candidate.id,
            confidence=100,
            match_method="manual",
            output_dir=adapter.storage_layout().permanent,
            payload={
                "isrc": deezer_isrc,
                "title": candidate.title,
                "artist": candidate.artist,
            },
        ),
    )
    client = DeemixClient()
    try:
        await queue_library_tracks(database, adapter, review, client, [(track, result)])
        await refresh_library_acquisition_jobs(database, adapter, source_id, deemix_client=client)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Download queue failed: {exc}") from exc

    return {"queued": 1, "deezerTrackId": candidate.id, "title": candidate.title, "artist": candidate.artist}


@app.post("/api/library/sources/{source_id}/apply", response_model=LibraryApplyResponse)
async def apply_library_source(source_id: int) -> dict[str, Any]:
    try:
        review = require_library_review(database, source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    applicable_tracks = [
        track for track in review.tracks if track.status in {"matched", "ready"}
    ]
    if not applicable_tracks:
        raise HTTPException(
            status_code=409,
            detail="There are no matched or ready library tracks to apply.",
        )
    apply_review = review.model_copy(update={"tracks": applicable_tracks})

    try:
        apply_result = build_rekordbox_adapter().apply_library_import(apply_review)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    warnings: list[str] = []
    try:
        spotify_added = await add_library_tracks_to_spotify(apply_review)
    except Exception as exc:
        spotify_added = 0
        warnings.append(f"Spotify playlist update failed: {exc}")
    database.mark_library_tracks_imported(
        source_id, [track.spotify_track_id for track in applicable_tracks]
    )
    return {
        "sourceId": source_id,
        "backupPath": apply_result["backup_path"],
        "imported": apply_result["imported"],
        "tagged": apply_result["tagged"],
        "spotifyAdded": spotify_added,
        "warnings": warnings,
    }


@app.get("/api/tag-playlist-mappings", response_model=list[TagPlaylistMapping])
def list_tag_playlist_mappings() -> list[TagPlaylistMapping]:
    return database.list_tag_playlist_mappings()


@app.post("/api/tag-playlist-mappings", response_model=TagPlaylistMapping)
def save_tag_playlist_mapping(mapping: TagPlaylistMappingIn) -> TagPlaylistMapping:
    return database.upsert_tag_playlist_mapping(mapping)


@app.get("/api/rekordbox/tags", response_model=list[RekordboxTag])
def list_rekordbox_tags() -> list[RekordboxTag]:
    try:
        return build_rekordbox_adapter().list_tags()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/rekordbox/playlists", response_model=list[RekordboxPlaylist])
def list_rekordbox_playlists() -> list[RekordboxPlaylist]:
    try:
        return build_rekordbox_adapter().list_playlists()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/providers/deemix/status", response_model=DeemixStatus)
async def provider_deemix_status() -> DeemixStatus:
    return await get_deemix_status()


@app.get("/api/acquisition/jobs", response_model=list[GlobalAcquisitionJob])
async def list_global_acquisition_jobs(
    scope: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> list[GlobalAcquisitionJob]:
    await refresh_global_acquisition_state(scope=scope, source=source)
    return database.list_global_acquisition_jobs(scope=scope, status=status, source=source)


@app.delete("/api/acquisition/jobs/clear")
def clear_acquisition_jobs(scope: str | None = Query(default=None)) -> dict[str, int]:
    cleared = database.clear_completed_acquisition_jobs(scope=scope)
    return {"cleared": cleared}


ACQUISITION_STREAM_INTERVAL_S = 4.0


@app.get("/api/acquisition/stream")
async def stream_acquisition_jobs(request: Request) -> StreamingResponse:
    """Server-Sent Events stream of global acquisition jobs.

    The server drives the refresh loop (scan staging + poll Deemix) and pushes
    the job list whenever it changes, so a connected client gets near-real-time
    updates from a single connection instead of polling every few seconds.
    """

    async def event_generator() -> AsyncIterator[str]:
        last_payload: str | None = None
        # Emit immediately on connect, then refresh-and-diff on each tick.
        while True:
            if await request.is_disconnected():
                break
            try:
                await refresh_global_acquisition_state()
                jobs = database.list_global_acquisition_jobs()
                payload = json.dumps(
                    [job.model_dump(by_alias=True, mode="json") for job in jobs]
                )
            except Exception as exc:  # keep the stream alive on transient errors
                logger.warning("acquisition stream refresh failed: %s", exc)
                payload = last_payload or "[]"
            if payload != last_payload:
                last_payload = payload
                yield f"event: jobs\ndata: {payload}\n\n"
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(ACQUISITION_STREAM_INTERVAL_S)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/sync/proposals", response_model=list[SyncProposal])
def list_sync_proposals() -> list[SyncProposal]:
    return database.list_proposals()


@app.post("/api/sync/proposals/{proposal_id}/resolve", response_model=SyncProposal)
def resolve_sync_proposal(
    proposal_id: int,
    request: SyncProposalResolveRequest,
) -> SyncProposal:
    proposal = database.resolve_proposal(proposal_id, request.status)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} was not found.")
    return proposal



@app.post("/api/spotify/auth-url", response_model=SpotifyAuthUrlResponse)
def spotify_auth_url(request: SpotifyAuthUrlRequest) -> dict[str, str]:
    try:
        return SpotifyClient(database).build_authorization_url(
            request.client_id, request.redirect_uri
        )
    except SpotifyAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/spotify/playlists", response_model=SpotifyPlaylistsResponse)
async def list_spotify_playlists(
    limit: int = Query(default=50, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        payload = await SpotifyClient(database).get_current_user_playlists(
            limit=limit, offset=offset
        )
    except SpotifyAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return summarize_playlist_page(payload)


@app.get("/api/spotify/callback", response_class=HTMLResponse)
async def spotify_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> str:
    if error:
        return callback_page("Spotify Authorization Failed", error)
    if not code or not state:
        return callback_page("Spotify Authorization Failed", "Missing code or state.")
    try:
        await SpotifyClient(database).exchange_callback(code, state)
    except SpotifyAuthError as exc:
        return callback_page("Spotify Authorization Failed", str(exc))
    return callback_page("Spotify Connected", "You can return to Syncbox.")




@app.get("/api/events", response_model=list[EventSummary])
def list_events() -> list[EventSummary]:
    return database.list_event_summaries()


@app.post("/api/events/spotify/analyze", response_model=EventReview)
async def analyze_event(request: SpotifyEventAnalyzeRequest) -> EventReview:
    try:
        review = await analyze_spotify_event(
            database,
            build_rekordbox_adapter(),
            SpotifyClient(database),
            request,
        )
        return enrich_review_with_rekordbox_tracks(review)
    except SpotifyAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/events", response_model=EventReview)
def create_event(request: ManualEventCreateRequest) -> EventReview:
    try:
        review = create_manual_event(database, build_rekordbox_adapter(), request.event_name)
        return enrich_review_with_rekordbox_tracks(review)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/events/{event_id}/tracks/spotify", response_model=EventReview)
async def add_event_spotify_track(event_id: int, request: EventTrackAddRequest) -> EventReview:
    try:
        review = await add_spotify_track_to_event(
            database,
            build_rekordbox_adapter(),
            SpotifyClient(database),
            event_id,
            request.track_url,
        )
        return enrich_review_with_rekordbox_tracks(review)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SpotifyAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/events/{event_id}/review", response_model=EventReview)
def get_event_review(event_id: int) -> EventReview:
    try:
        return enrich_review_with_rekordbox_tracks(require_event_review(database, event_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/events/{event_id}/delete-preview", response_model=EventDeletePreview)
def preview_event_delete(event_id: int) -> EventDeletePreview:
    try:
        review = require_event_review(database, event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if event_matches_permanent_source(review):
        return permanent_source_event_delete_preview(review)
    try:
        return build_rekordbox_adapter().preview_event_delete(review)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/events/{event_id}/delete", response_model=EventDeleteResponse)
def delete_event(event_id: int) -> EventDeleteResponse:
    try:
        review = require_event_review(database, event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    adapter = build_rekordbox_adapter()

    if event_matches_permanent_source(review):
        preview = permanent_source_event_delete_preview(review)
        database.delete_event_import(event_id)
        adapter.remove_event_directory(review.event_dir)
        return EventDeleteResponse(
            **preview.model_dump(by_alias=True),
            backupPath=None,
            deletedFromRekordbox=0,
            removedEventTags=0,
            localEventDeleted=True,
        )

    try:
        result = adapter.delete_event_import(review)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    database.delete_event_import(event_id)
    adapter.remove_event_directory(review.event_dir)
    return result.model_copy(update={"local_event_deleted": True})


@app.post("/api/events/{event_id}/staging/scan", response_model=EventReview)
def scan_event_staging_files(event_id: int) -> EventReview:
    try:
        return enrich_review_with_rekordbox_tracks(scan_event_staging(database, event_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/events/{event_id}/acquisition/auto",
    response_model=EventAcquisitionResponse,
)
async def auto_acquire_event_tracks(event_id: int) -> EventAcquisitionResponse:
    try:
        response = await run_auto_acquisition(database, event_id)
        return response.model_copy(
            update={"review": enrich_review_with_rekordbox_tracks(response.review)}
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/events/{event_id}/acquisition/jobs",
    response_model=list[AcquisitionJob],
)
async def list_event_acquisition_jobs(event_id: int) -> list[AcquisitionJob]:
    try:
        require_event_review(database, event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await refresh_acquisition_jobs(database, event_id)


@app.post(
    "/api/events/{event_id}/acquisition/retry",
    response_model=EventAcquisitionResponse,
)
async def retry_event_acquisition(event_id: int) -> EventAcquisitionResponse:
    try:
        response = await retry_acquisition(database, event_id)
        return response.model_copy(
            update={"review": enrich_review_with_rekordbox_tracks(response.review)}
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/events/{event_id}/matches", response_model=EventReview)
def update_event_match(event_id: int, request: EventTrackUpdateRequest) -> EventReview:
    try:
        return enrich_review_with_rekordbox_tracks(
            apply_event_track_update(database, event_id, request)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/events/{event_id}/apply", response_model=EventApplyResponse)
async def apply_event(event_id: int) -> dict[str, Any]:
    try:
        review = require_event_review(database, event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    applicable_tracks = tracks_ready_for_rekordbox_apply(review)
    if not applicable_tracks:
        raise HTTPException(
            status_code=409,
            detail="There are no matched or ready tracks to apply.",
        )
    apply_review = review.model_copy(update={"tracks": applicable_tracks})

    try:
        apply_result = build_rekordbox_adapter().apply_event_import(apply_review)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    database.mark_event_tracks_applied(
        event_id, [track.spotify_track_id for track in applicable_tracks]
    )
    refreshed = require_event_review(database, event_id)
    database.update_event_status(event_id, next_event_status_after_apply(refreshed))
    return {
        "eventId": event_id,
        "backupPath": apply_result["backup_path"],
        "imported": apply_result["imported"],
        "tagged": apply_result["tagged"],
        "spotifyAdded": 0,
        "smartPlaylist": apply_result["smart_playlist"],
        "warnings": [],
    }


@app.post("/api/events/{event_id}/repair-rekordbox-structure")
def repair_event_rekordbox_structure(event_id: int) -> dict[str, Any]:
    try:
        review = require_event_review(database, event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        repair_result = build_rekordbox_adapter().repair_event_import_structure(review)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"eventId": event_id, **repair_result}


@app.get("/api/events/{event_id}/search-deezer", response_model=list[DeezerSearchResult])
async def search_event_deezer(event_id: int, query: str = Query(..., min_length=1)) -> list[dict[str, Any]]:
    return await deezer_search_results(query)


@app.post("/api/events/{event_id}/tracks/{spotify_track_id}/queue-deezer")
async def queue_event_deezer_track(
    event_id: int,
    spotify_track_id: str,
    deezer_track_id: str = Body(..., embed=True, alias="deezerTrackId"),
) -> dict[str, Any]:
    try:
        return await queue_event_manual_deezer(database, event_id, spotify_track_id, deezer_track_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Download queue failed: {exc}") from exc


@app.post("/api/live-imports", response_model=LiveImportPackage)
def create_live_import(request: LiveImportRequest) -> dict[str, object]:
    adapter = build_rekordbox_adapter()
    layout = adapter.ensure_storage_layout()
    return build_live_import_package(Path(layout.events), request.event_name)


async def deezer_search_results(query: str) -> list[dict[str, Any]]:
    """Shared Deezer free-text search used by library and event endpoints."""
    try:
        candidates = await DeezerResolver().search(query)
    except Exception as exc:
        logger.warning("Deezer search failed for %r: %s", query, exc)
        raise HTTPException(status_code=503, detail=f"Deezer search failed: {exc}") from exc
    return [
        {
            "id": candidate.id,
            "title": candidate.title,
            "artist": candidate.artist,
            "album": candidate.album,
            "durationMs": candidate.duration_ms,
            "coverUrl": candidate.cover_url,
            "previewUrl": candidate.preview_url,
        }
        for candidate in candidates
    ]


def default_settings() -> AppSettings:
    return AppSettings(
        spotifyClientId="",
        spotifyRedirectUri=f"http://127.0.0.1:{config.api_port}/api/spotify/callback",
        rekordboxDatabaseDir=str(config.rekordbox_database_dir),
        storageRoot=str(config.storage_root),
        apiPort=config.api_port,
    )


def build_rekordbox_adapter() -> RekordboxAdapter:
    settings = get_settings()
    return RekordboxAdapter(
        database_dir=Path(settings.rekordbox_database_dir),
        storage_root=Path(settings.storage_root),
        permanent_path=settings.permanent_path,
        manual_collection_path=settings.manual_collection_path,
    )


def event_matches_permanent_source(review: EventReview) -> bool:
    event_values = {
        normalized_label(review.event_name),
        normalized_label(review.spotify_playlist_name),
        normalized_label(review.default_tag),
    }
    for source in database.list_library_sources():
        if review.spotify_playlist_id == source.spotify_playlist_id:
            return True
        source_values = {
            normalized_label(source.spotify_playlist_name),
            *[normalized_label(tag_name) for tag_name in source.tags],
        }
        if event_values & source_values:
            return True
    return False


def permanent_source_event_delete_preview(review: EventReview) -> EventDeletePreview:
    return EventDeletePreview(
        eventId=review.id,
        eventName=review.event_name,
        defaultTag=review.default_tag,
        localOnly=True,
        tracksWithEventTag=0,
        willDeleteFromRekordbox=0,
        willRemoveEventTag=0,
        protectedTracks=review.total_tracks,
        deletedSamples=[],
        protectedSamples=[track.title for track in review.tracks[:5]],
        warnings=[
            "This event matches a permanent library source. "
            "Only the temporary event record will be removed from the app."
        ],
    )


def normalized_label(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_accents.casefold().split())


async def refresh_global_acquisition_state(
    *,
    scope: str | None = None,
    source: str | None = None,
) -> None:
    requested_scope = (scope or "").lower()
    source_filter = (source or "").strip().lower()
    adapter = build_rekordbox_adapter()

    if requested_scope in {"", "library"}:
        for library_source in database.list_library_sources():
            if (
                source_filter
                and source_filter not in library_source.spotify_playlist_name.lower()
            ):
                continue
            try:
                await refresh_library_review_state(database, adapter, library_source.id)
            except KeyError:
                continue

    if requested_scope in {"", "event"}:
        for event in database.list_event_summaries():
            if source_filter and source_filter not in event.event_name.lower():
                continue
            try:
                scan_event_staging(database, event.id)
                await refresh_acquisition_jobs(database, event.id)
            except KeyError:
                continue


def enrich_review_with_rekordbox_tracks(review: EventReview) -> EventReview:
    content_ids = {
        str(track.rekordbox_content_id)
        for track in review.tracks
        if track.rekordbox_content_id
    }
    if not content_ids:
        return review

    snapshot = build_rekordbox_adapter().read_library_snapshot()
    if not snapshot.get("available", False):
        return review

    tracks_by_id = {
        str(track.get("contentId")): track
        for track in snapshot.get("tracks", [])
        if track.get("contentId") is not None
    }
    enriched_tracks = []
    changed = False
    for track in review.tracks:
        if not track.rekordbox_content_id:
            enriched_tracks.append(track)
            continue
        details = tracks_by_id.get(str(track.rekordbox_content_id))
        if not details:
            enriched_tracks.append(track)
            continue
        enriched_tracks.append(
            track.model_copy(
                update={
                    "rekordbox_title": optional_snapshot_value(
                        details.get("title"), track.rekordbox_title
                    ),
                    "rekordbox_artist": optional_snapshot_value(
                        details.get("artist"), track.rekordbox_artist
                    ),
                    "rekordbox_file_path": optional_snapshot_value(
                        details.get("filePath"), track.rekordbox_file_path
                    ),
                }
            )
        )
        changed = True

    if not changed:
        return review
    return review.model_copy(update={"tracks": enriched_tracks})


def optional_snapshot_value(value: object, fallback: str | None) -> str | None:
    if value is None:
        return fallback
    text = str(value)
    return text or fallback


def tracks_ready_for_rekordbox_apply(review: EventReview) -> list[EventTrackReview]:
    return [track for track in review.tracks if track.status in {"matched", "ready"}]


def next_event_status_after_apply(review: EventReview) -> str:
    if review.matched_tracks > 0 or review.ready_tracks > 0:
        return "partially_applied"
    if review.missing_tracks > 0 or review.ambiguous_tracks > 0:
        return "partially_applied"
    return "applied"



async def add_library_tracks_to_spotify(review: LibraryReview) -> int:
    mappings = {
        mapping.tag_name: mapping.spotify_playlist_id
        for mapping in database.list_tag_playlist_mappings()
        if mapping.enabled
    }
    playlist_uris: dict[str, set[str]] = {}
    for track in review.tracks:
        for tag_name in track.tags:
            playlist_id = mappings.get(tag_name)
            if playlist_id and playlist_id != review.source.spotify_playlist_id:
                playlist_uris.setdefault(playlist_id, set()).add(track.spotify_uri)

    added = 0
    client = SpotifyClient(database)
    for playlist_id, uris in playlist_uris.items():
        if not uris:
            continue
        await client.add_tracks_to_playlist(playlist_id, sorted(uris))
        added += len(uris)
    return added


def callback_page(title: str, message: str) -> str:
    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <title>{title}</title>
        <style>
          body {{
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: #18202f;
            background: #f7f8fb;
          }}
          main {{
            width: min(520px, calc(100vw - 32px));
            padding: 28px;
            background: #fff;
            border: 1px solid #dfe5ee;
            border-radius: 8px;
          }}
        </style>
      </head>
      <body>
        <main>
          <h1>{title}</h1>
          <p>{message}</p>
        </main>
      </body>
    </html>
    """
