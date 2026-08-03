"""REST API layer over the M1-M3 services, wired into server.create_app
(SPEC-UNIFIED 6.3 transport, 5.10/F9 doctor, 5.4/5.12 dedup scan, 11.2/11.3).

Concurrency model (deliberately simple and correct for a single-user
loopback app):
- EVERY handler body is a plain sync function executed via
  run_in_threadpool under ONE app-wide lock (Deps.lock): the asyncio loop
  is never blocked, so the canonical /events SSE stream keeps flowing
  while a long job (sync, apply, dedup scan) runs;
- long jobs publish REAL progress on the JobBus from the worker thread via
  anyio.from_thread.run - 'job.progress' with pct derived from actual work
  units (F16: never faked), then 'job.done'.

Error contract (never a 500 for a domain failure):
- MutationBlockedError (Rekordbox running)      -> 423 + message_key;
- StaleSnapshotError (dry-run went stale)        -> 409 + rerun_dry_run;
- ConflictError (5.6 preconditions, state rules) -> 409;
- AnlzConsentRequired / PermanentDeleteConsentRequired -> 428 with the
  consent payload the UI needs to re-ask;
- KeyError/FileNotFoundError -> 404; ValueError/TypeError/re.error -> 400.

Write-path discipline: the two mutations implemented at this layer (dedup
resolve, untagged delete) go through safety.mutate + rb_write helpers like
every other master.db write; reads go through rb.SnapshotCache /
rb.open_readonly. File deletion happens strictly AFTER the durable commit
(5.4 order) via platform_os.delete_file.
"""

import hashlib
import json
import logging
import re
import threading
import uuid as uuidlib
from collections import deque
from datetime import datetime
from pathlib import Path

import anyio.from_thread
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Route

from syncbox import (
    acquisition,
    acquisition_migration,
    appdb,
    dedup,
    events_service,
    library_service,
    matching,
    missing_service,
    performances,
    quality,
    readouts,
    repos,
    smartfixes_run,
    untagged,
)
from syncbox.library_service import ConflictError
from syncbox.missing_service import AnlzConsentRequired
from syncbox.platform_os import PermanentDeleteConsentRequired, delete_file
from syncbox.rb import SnapshotCache, open_readonly
from syncbox.rb_write import (
    add_streaming_content,
    create_plain_playlist,
    ensure_playlist_folder,
    open_rekordbox,
    reactivate_content,
    reassign_memberships,
    soft_delete_content,
)
from syncbox.safety.backup import list_backups, restore_backup
from syncbox.safety.mutate import StaleSnapshotError, fingerprint, mutate
from syncbox.safety.paths import (
    SYNC_DIR_NAME,
    paths_equal,
    resolve_stored_path,
    tcc_exists,
)
from syncbox.safety import process_guard
from syncbox.safety.process_guard import MutationBlockedError
from syncbox.server import JobBus, OAuthCallbackPortInUseError, create_app
from syncbox.settings import DEFAULTS as SETTINGS_DEFAULTS
from syncbox.settings import Settings, validate_directory
from syncbox.spotify import (
    AUTHORIZATION_TIMEOUT_SECONDS,
    SPOTIFY_TRACK_PREFIX,
    NotConnectedError,
    SpotifyApiError,
    resolve_track_meta,
)

# Statuses a single-track re-match refuses to clobber: 'ignored' would
# silently unignore (D22 owns that transition), 'imported' is already in
# Rekordbox, 'ready' carries a claimed staging file, and
# 'removed_from_source' is the 5.6 sync verdict - re-matching would erase
# the marker (and, once 'missing', re-expose purchase links that 5.13
# excludes for removed_from_source); the next sync owns that transition.
_REMATCH_REFUSED = frozenset({"ignored", "imported", "ready", "removed_from_source"})
# 5.6 library vocabulary for matcher outcomes (events keep 'ambiguous').
_LIBRARY_STATUS = {"matched": "matched", "ambiguous": "conflict", "missing": "missing"}

_SOURCE_PATCHABLE = ("name", "tags", "enabled")
log = logging.getLogger(__name__)


# --- wiring bag -------------------------------------------------------------------


class Deps:
    """Dependency bag for the API routes.

    ``conn`` is the manual-transaction app-DB connection from
    appdb.open_app_db. All configuration is read live from Settings, so a
    settings update takes effect on the next request without a restart; the
    snapshot cache is rebuilt when rekordbox_db_path changes.
    """

    def __init__(
        self,
        conn,
        *,
        bus: JobBus | None = None,
        spotify_auth=None,
        spotify_client=None,
        oauth_listener=None,
        cache=None,
        log_path=None,
        app_db_path=None,
        data_dir=None,
        secrets=None,
        acquisition_installer=None,
        acquisition_runner=None,
    ):
        self.conn = conn
        # File behind ``conn`` - needed by the all-data import (5.10), which
        # replaces the file and swaps the live connection. None (tests with
        # a bare conn) disables that route.
        self.app_db_path = app_db_path
        self.settings = Settings(conn)
        self.bus = bus if bus is not None else JobBus()
        self.spotify_auth = spotify_auth
        self.spotify_client = spotify_client
        self.oauth_listener = oauth_listener
        self.log_path = log_path
        self.data_dir = Path(
            data_dir or (Path(app_db_path).parent if app_db_path else ".")
        )
        self.secrets = secrets
        self.acquisition_installer = (
            acquisition_installer or acquisition.install_component
        )
        self.acquisition_runner = acquisition_runner or acquisition.run_deezer_download
        self.acquisition_worker = None
        self.lock = threading.RLock()
        self._injected_cache = cache  # tests inject a fake snapshot cache
        self._cache = None
        self._cache_db = None

    @property
    def db_path(self) -> str:
        return _expanduser(self.settings.get("rekordbox_db_path"))

    @property
    def storage_root(self) -> str:
        return _expanduser(self.settings.get("storage_root"))

    @property
    def backups_root(self) -> Path:
        return Path(self.storage_root) / SYNC_DIR_NAME / "backups"

    @property
    def retention(self) -> int:
        return self.settings.get("backup_retention")

    def cache(self):
        if self._injected_cache is not None:
            return self._injected_cache
        db = self.db_path
        if self._cache is None or self._cache_db != db:
            self._cache = SnapshotCache(db)
            self._cache_db = db
        return self._cache


class AcquisitionWorker:
    """Single persistent FIFO worker for queued acquisition jobs.

    Must be started only AFTER single-instance ownership is established
    (the exclusive API port bind in ``__main__.main``): requeueing every
    'running' job on startup is safe exactly because holding the port
    proves the claimant of those jobs is dead — that transfer is what
    expires its claim. The worker runs on its own app-DB connection so a
    download never holds ``deps.lock``; claims are single atomic
    ``BEGIN IMMEDIATE`` + ``UPDATE ... RETURNING`` transactions, FIFO by
    job id.
    """

    def __init__(self, deps: Deps, *, connect=None):
        self.deps = deps
        self.instance_id = uuidlib.uuid4().hex
        self._connect = connect or (lambda: appdb.connect(deps.app_db_path))
        self._conn = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="syncbox-acquisition",
            daemon=True,
        )

    def start(self) -> None:
        self._conn = self._connect()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "UPDATE acquisition_jobs SET status = 'queued', "
                "claimed_by = NULL, claimed_at = NULL, "
                "error = 'resumed after sidecar restart', "
                "updated_at = datetime('now') WHERE status = 'running'"
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._thread.start()

    def stop(self, timeout: float = 3) -> bool:
        self._stop.set()
        if (
            self._thread.ident is not None
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout)
        stopped = not self._thread.is_alive()
        if stopped and self._conn is not None:
            self._conn.close()
            self._conn = None
        return stopped

    def _claim(self):
        """Atomically claim the oldest queued job; None when the queue is empty."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "UPDATE acquisition_jobs SET status = 'running', error = NULL, "
                "claimed_by = ?, claimed_at = datetime('now'), "
                "updated_at = datetime('now') "
                "WHERE id = (SELECT id FROM acquisition_jobs "
                "            WHERE status = 'queued' ORDER BY id LIMIT 1) "
                "RETURNING id",
                (self.instance_id,),
            ).fetchone()
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return row["id"] if row is not None else None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._claim()
                if job_id is not None:
                    _run_acquisition_job(self.deps, job_id, conn=self._conn)
                    continue
            except Exception:
                log.exception("acquisition worker iteration failed")
            self._stop.wait(0.5)


def build_app(deps: Deps):
    """Assemble the full sidecar app: transport routes (server.create_app)
    plus the REST routes below, sharing one JobBus."""
    app = create_app(
        bus=deps.bus,
        routes=routes(deps),
    )
    app.state.deps = deps
    return app


# --- plumbing ---------------------------------------------------------------------


def _error_response(exc) -> JSONResponse | None:
    """Map domain errors to clean JSON responses; None -> a real bug, re-raise."""
    if isinstance(exc, MutationBlockedError):
        return JSONResponse(
            {
                "error": "mutation_blocked",
                "message_key": exc.message_key,
                "message": str(exc),
            },
            status_code=423,
        )
    if isinstance(exc, StaleSnapshotError):
        return JSONResponse(
            {"error": "stale_snapshot", "action": "rerun_dry_run", "message": str(exc)},
            status_code=409,
        )
    if isinstance(exc, ConflictError):
        return JSONResponse({"error": "conflict", "message": str(exc)}, status_code=409)
    if isinstance(exc, AnlzConsentRequired):
        return JSONResponse(
            {"error": "consent_required", "consent": "anlz", "message": str(exc)},
            status_code=428,
        )
    if isinstance(exc, PermanentDeleteConsentRequired):
        return JSONResponse(
            {
                "error": "consent_required",
                "consent": "permanent_delete",
                "message_key": exc.message_key,
                "path": str(exc.path),
                "message": str(exc),
            },
            status_code=428,
        )
    if isinstance(exc, NotConnectedError):
        return JSONResponse(
            {
                "error": "spotify_not_connected",
                "message": "Connect your Spotify account in Settings first.",
            },
            status_code=409,
        )
    if isinstance(exc, SpotifyApiError):
        return JSONResponse(
            {
                "error": "spotify_api_error",
                "status_code": exc.status_code,
                "message": str(exc),
            },
            status_code=502,
        )
    if isinstance(exc, OAuthCallbackPortInUseError):
        return JSONResponse(
            {
                "error": "oauth_callback_port_in_use",
                "message": str(exc),
            },
            status_code=409,
        )
    if isinstance(exc, KeyError):
        message = str(exc.args[0]) if exc.args else "not found"
        return JSONResponse({"error": "not_found", "message": message}, status_code=404)
    if isinstance(exc, FileNotFoundError):
        return JSONResponse(
            {"error": "not_found", "message": str(exc)}, status_code=404
        )
    if isinstance(exc, (ValueError, TypeError, re.error)):
        return JSONResponse(
            {"error": "invalid_request", "message": str(exc)}, status_code=400
        )
    return None


def _endpoint(deps: Deps, handler):
    """handler(deps, request, body) runs sync, in the threadpool, under the
    app-wide lock. It returns a JSON-serializable payload or (status, payload)."""

    async def route(request):
        body = {}
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            raw = await request.body()
            if raw:
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    return JSONResponse(
                        {"error": "invalid_request", "message": "body must be JSON"},
                        status_code=400,
                    )
                if not isinstance(body, dict):
                    return JSONResponse(
                        {
                            "error": "invalid_request",
                            "message": "body must be a JSON object",
                        },
                        status_code=400,
                    )

        def work():
            with deps.lock:
                return handler(deps, request, body)

        try:
            result = await run_in_threadpool(work)
        except Exception as exc:
            response = _error_response(exc)
            if response is None:
                raise
            return response
        if isinstance(result, tuple):
            status, payload = result
            return JSONResponse(payload, status_code=status)
        return JSONResponse(result)

    return route


class _Progress:
    """Real job progress on the canonical SSE bus (F16).

    pct always derives from done/total actual work units. Publishing happens
    from the worker thread back into the running loop via anyio.from_thread.
    """

    def __init__(self, bus: JobBus, kind: str):
        self._bus = bus
        self.job_id = uuidlib.uuid4().hex
        self.kind = kind

    def _publish(self, event_type: str, payload: dict) -> None:
        payload = {"job": self.job_id, "kind": self.kind, **payload}
        anyio.from_thread.run(self._bus.publish, event_type, payload)

    def publish(self, done: int, total: int) -> None:
        pct = round(100 * done / total) if total else 100
        self._publish("job.progress", {"done": done, "total": total, "pct": pct})

    def done(self, **summary) -> None:
        self._publish("job.done", summary)


def _require(body: dict, key: str):
    value = body.get(key)
    if value is None or value == "":
        raise ValueError(f"missing required field {key!r}")
    return value


def _require_list(body: dict, key: str) -> list:
    value = body.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"field {key!r} must be a non-empty list")
    return value


def _fingerprint_tuple(value):
    """JSON round-trip turns the mutate fingerprint tuples into lists; the
    freshness guard compares tuples, so convert back exactly."""
    if value is None:
        return None
    try:
        return tuple(tuple(part) for part in value)
    except TypeError:
        raise ValueError("fingerprint must be the value returned by the dry-run")


def _expanduser(value):
    # '~' must be expanded before any open() — sqlite/os don't expand it, so an
    # un-expanded '~/Library/.../master.db' fails with ENOENT at scan time even
    # though Settings validation (which DOES expanduser) showed a green tick.
    # Guard falsy so the empty/None "not configured yet" sentinel is preserved.
    return str(Path(value).expanduser()) if value else value


def _require_rekordbox(deps: Deps) -> None:
    if not deps.db_path or not deps.storage_root:
        raise ValueError(
            "configure rekordbox_db_path and storage_root in Settings first"
        )


def _require_storage(deps: Deps) -> None:
    if not deps.storage_root:
        raise ValueError("configure storage_root in Settings first")


def _get_source(deps: Deps, source_id: int) -> dict:
    source = repos.get_source(deps.conn, source_id)
    if source is None:
        raise KeyError(f"source {source_id} not found")
    return source


def _get_track(deps: Deps, track_id: int) -> dict:
    track = repos.get_track(deps.conn, track_id)
    if track is None:
        raise KeyError(f"library track {track_id} not found")
    return track


def _get_event(deps: Deps, event_id: int) -> dict:
    event = events_service.get_event(deps.conn, event_id)
    if event is None:
        raise KeyError(f"event {event_id} not found")
    return event


def _matching_thresholds(deps: Deps) -> dict:
    """G4: the user-tunable matching knobs (SPEC-DESIGN 4), read live from
    settings and forwarded to matching.match / score_candidates. The
    algorithm itself is locked."""
    return {
        "min_confidence": deps.settings.get("match_confidence_threshold"),
        "ambiguity_margin": deps.settings.get("match_ambiguity_margin"),
        "weights": deps.settings.get("match_weights"),
        "isrc_collision_policy": deps.settings.get("isrc_collision_policy"),
    }


def _track_resolver(deps: Deps):
    """Spotify metadata resolver for event track additions (11.1), on the
    shared spotify.resolve_track_meta ladder: without a session the add
    still succeeds with the anonymous oEmbed title instead of a 409."""

    def resolve(spotify_track_id: str):
        meta = resolve_track_meta([spotify_track_id], deps.spotify_client).get(
            spotify_track_id
        )
        if meta is None:
            return None
        # library_service._spotify_track shape; duration/isrc are absent
        # from oEmbed results and stay nullable (add_track tolerates that).
        return {
            "spotify_track_id": spotify_track_id,
            "title": meta.get("title"),
            "artist": meta.get("artist"),
            "duration_ms": meta.get("duration_ms"),
            "isrc": meta.get("isrc"),
        }

    return resolve


# --- sources (5.6) ----------------------------------------------------------------


def sources_list(deps, request, body):
    return {"sources": repos.list_sources(deps.conn)}


def sources_add(deps, request, body):
    source = repos.add_source(
        deps.conn,
        _require(body, "spotify_playlist_id"),
        name=body.get("name", ""),
        tags=body.get("tags") or (),
        cover_url=body.get("cover_url") or None,
    )
    return 201, source


def sources_update(deps, request, body):
    source_id = request.path_params["source_id"]
    _get_source(deps, source_id)
    fields = {k: body[k] for k in _SOURCE_PATCHABLE if k in body}
    if not fields:
        raise ValueError(f"nothing to update; patchable fields: {_SOURCE_PATCHABLE}")
    return repos.update_source(deps.conn, source_id, **fields)


def sources_remove(deps, request, body):
    source_id = request.path_params["source_id"]
    _get_source(deps, source_id)
    # 5.6: stop following ONLY - app-side cascade, Rekordbox rows and MyTags
    # are never touched (repos owns that contract).
    repos.remove_source(deps.conn, source_id)
    return {"removed": source_id}


def _sync_client(deps):
    if deps.spotify_client is None:
        raise NotConnectedError("no Spotify client configured")
    return deps.spotify_client


def sources_sync_one(deps, request, body):
    source = _get_source(deps, request.path_params["source_id"])
    _require_rekordbox(deps)
    client = _sync_client(deps)
    progress = _Progress(deps.bus, "sources.sync")
    progress.publish(0, 1)
    result = library_service.sync_one_source(
        deps.conn,
        client,
        deps.cache(),
        deps.storage_root,
        source,
        **_matching_thresholds(deps),
    )
    progress.publish(1, 1)
    progress.done(source_id=source["id"], **result["stats"])
    return result


def sources_sync_all(deps, request, body):
    _require_rekordbox(deps)
    client = _sync_client(deps)
    sources = [s for s in repos.list_sources(deps.conn) if s["enabled"]]
    progress = _Progress(deps.bus, "sources.sync_all")
    results = []
    thresholds = _matching_thresholds(deps)
    for done, source in enumerate(sources, start=1):
        try:
            result = library_service.sync_one_source(
                deps.conn,
                client,
                deps.cache(),
                deps.storage_root,
                source,
                **thresholds,
            )
            results.append({"source_id": source["id"], **result})
        except SpotifyApiError as exc:
            # One unreachable playlist (404 private, rate-limit exhausted)
            # must not abort the other sources; report it in the results.
            results.append(
                {
                    "source_id": source["id"],
                    "error": str(exc),
                    "status_code": exc.status_code,
                }
            )
        progress.publish(done, len(sources))  # real unit: one source synced
    progress.done(synced=len(sources))
    return {"results": results}


def source_tracks(deps, request, body):
    source = _get_source(deps, request.path_params["source_id"])
    tracks = repos.list_source_tracks(deps.conn, source["id"])
    status = request.query_params.get("status")
    if status:
        tracks = [t for t in tracks if t["status"] == status]
    query = (request.query_params.get("q") or "").lower()
    if query:
        tracks = [
            t
            for t in tracks
            if query in (t["title"] or "").lower()
            or query in (t["artist"] or "").lower()
        ]
    # Bit-rate chip data (SPEC-DESIGN TrackReviewTable): the matched RB row's
    # declared bitrate, joined from the read-only snapshot. Decoration only -
    # a snapshot load failure must never break the review-table fetch.
    bit_rates = {}
    if deps.db_path and deps.storage_root:
        try:
            bit_rates = {
                row["content_id"]: row["bit_rate"]
                for row in deps.cache().get(deps.storage_root)
            }
        except Exception:  # Optional enrichment must never block the track list.
            bit_rates = {}
    for track in tracks:
        track["bit_rate"] = (
            bit_rates.get(track["content_id"]) if track["content_id"] else None
        )
    return {"source_id": source["id"], "tracks": tracks}


def source_apply(deps, request, body):
    source = _get_source(deps, request.path_params["source_id"])
    _require_rekordbox(deps)
    track_ids = [int(t) for t in _require_list(body, "track_ids")]
    progress = _Progress(deps.bus, "sources.apply")
    progress.publish(0, 1)
    # ONE mutate() inside; ConflictError (wrong status / missing MyTag) -> 409.
    result = library_service.apply_to_rekordbox(
        deps.conn,
        deps.db_path,
        deps.backups_root,
        deps.cache(),
        deps.storage_root,
        source["id"],
        track_ids,
        retention=deps.retention,
        app_db_path=deps.app_db_path,
    )
    progress.publish(1, 1)
    progress.done(source_id=source["id"], **result)
    return result


# --- status (G1) --------------------------------------------------------------------


def status_get(deps, request, body):
    """G1: proactive read-only status - feeds the RB banner / dashboard hero /
    HealthPill without waiting for a failing mutation. The UI polls it
    (interval + window focus + after any 423)."""
    connected = deps.spotify_auth is not None and deps.spotify_auth.connected()
    authorization = (
        deps.spotify_auth.authorization_status()
        if deps.spotify_auth is not None
        else {"pending": False, "result": None}
    )
    return {
        "rb_open": process_guard.is_rekordbox_running(),
        "spotify_connected": connected,
        "spotify_authorization_pending": authorization["pending"],
        "spotify_authorization_result": authorization["result"],
    }


# --- library tracks ----------------------------------------------------------------


_CANDIDATE_LIMIT = 10  # ReMatchModal shows a shortlist, not the collection


def track_candidates(deps, request, body):
    """G2 read half: the matcher's scored top-N for ONE track, so
    ReMatchModal shows a candidate list instead of a blind re-run."""
    track = _get_track(deps, request.path_params["track_id"])
    _require_rekordbox(deps)
    thresholds = _matching_thresholds(deps)
    scored = matching.score_candidates(
        {
            "title": track["title"],
            "artist": track["artist"],
            "duration_ms": track["duration_ms"],
            "isrc": track["isrc"],
        },
        # streaming references can never be the local file a track needs
        [
            r
            for r in deps.cache().get(deps.storage_root)
            if not r.get("spotify_track_id")
        ],
        weights=thresholds["weights"],
        isrc_collision_policy=thresholds["isrc_collision_policy"],
    )
    return {
        "track_id": track["id"],
        "candidates": [
            {
                "content_id": row["content_id"],
                "title": row["title"],
                "artist": row["artist"],
                "duration_ms": row["duration_ms"],
                "bit_rate": row["bit_rate"],
                "confidence": confidence,
            }
            for confidence, row in scored[:_CANDIDATE_LIMIT]
        ],
    }


def track_match_manual(deps, request, body):
    """G2 write half: the user confirmed a candidate in ReMatchModal.
    Same status guard as the automatic re-match (D22/5.6 transitions stay
    owned by their flows); confidence=100 - a user confirmation is
    authoritative, and the match method is 'manual' anyway."""
    track = _get_track(deps, request.path_params["track_id"])
    if track["status"] in _REMATCH_REFUSED:
        raise ConflictError(
            f"track {track['id']} is {track['status']!r}; manual match applies "
            "only to unresolved rows (restore/unignore first when applicable)"
        )
    _require_rekordbox(deps)
    content_id = str(_require(body, "content_id"))
    known = {row["content_id"] for row in deps.cache().get(deps.storage_root)}
    if content_id not in known:
        raise KeyError(f"content {content_id} not found in the Rekordbox snapshot")
    deps.conn.execute(
        "UPDATE library_tracks SET status = 'matched', content_id = ?, "
        "match_method = 'manual', confidence = 100, "
        "updated_at = datetime('now') WHERE id = ?",
        (content_id, track["id"]),
    )
    return repos.get_track(deps.conn, track["id"])


def track_rematch(deps, request, body):
    track = _get_track(deps, request.path_params["track_id"])
    if track["status"] in _REMATCH_REFUSED:
        raise ConflictError(
            f"track {track['id']} is {track['status']!r}; re-match applies only "
            "to unresolved rows (restore/unignore first when applicable)"
        )
    _require_rekordbox(deps)
    result = matching.match(
        {
            "title": track["title"],
            "artist": track["artist"],
            "duration_ms": track["duration_ms"],
            "isrc": track["isrc"],
        },
        # streaming references can never be the local file a track needs
        [
            r
            for r in deps.cache().get(deps.storage_root)
            if not r.get("spotify_track_id")
        ],
        **_matching_thresholds(deps),
    )
    deps.conn.execute(
        "UPDATE library_tracks SET status = ?, content_id = ?, match_method = ?, "
        "confidence = ?, updated_at = datetime('now') WHERE id = ?",
        (
            _LIBRARY_STATUS[result.status],
            result.content_id,
            result.method,
            result.confidence,
            track["id"],
        ),
    )
    return repos.get_track(deps.conn, track["id"])


def track_mark_missing(deps, request, body):
    """ReMatchModal escape (M4-PLAN M4.7): none of the candidates matches ->
    the track is not in the collection. Same status guard as re-match; the
    row joins the Missing center (scope=library, 5.5) with purchase links."""
    track = _get_track(deps, request.path_params["track_id"])
    if track["status"] in _REMATCH_REFUSED:
        raise ConflictError(
            f"track {track['id']} is {track['status']!r}; mark-missing applies "
            "only to unresolved rows (restore/unignore first when applicable)"
        )
    deps.conn.execute(
        "UPDATE library_tracks SET status = 'missing', content_id = NULL, "
        "match_method = NULL, confidence = NULL, updated_at = datetime('now') "
        "WHERE id = ?",
        (track["id"],),
    )
    return repos.get_track(deps.conn, track["id"])


def track_ignore(deps, request, body):
    track = _get_track(deps, request.path_params["track_id"])
    # D22 bookkeeping (prior_status stored exactly once) lives in repos.
    return repos.set_track_status(deps.conn, track["id"], "ignored")


def track_restore(deps, request, body):
    track = _get_track(deps, request.path_params["track_id"])
    # D22 unignore: back to the stored prior status, never 'new'.
    return repos.restore_track(deps.conn, track["id"])


def tracks_tag_delta(deps, request, body):
    """D16: bulk tag edits are ADD/REMOVE deltas on the pending app rows -
    never a union overwrite. (Rekordbox-side tagging happens at apply time
    through rb_write.apply_tag_delta with the same delta semantics.)"""
    track_ids = [int(t) for t in _require_list(body, "track_ids")]
    add = [str(t) for t in body.get("add") or []]
    remove = [str(t) for t in body.get("remove") or []]
    if not add and not remove:
        raise ValueError("provide at least one of 'add' or 'remove'")
    tracks = [_get_track(deps, track_id) for track_id in track_ids]
    conn = deps.conn
    conn.execute("BEGIN")
    try:
        for track in tracks:
            tags = [t for t in track["tags"] if t not in remove]
            tags += [t for t in add if t not in tags]
            conn.execute(
                "UPDATE library_tracks SET tags = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (json.dumps(tags), track["id"]),
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {"tracks": [repos.get_track(conn, t["id"]) for t in tracks]}


# --- events (5.7, 11.1/11.2) --------------------------------------------------------


def events_list(deps, request, body):
    # 11.2 delta (owner amendment 2026-07-07): what a reapply would write —
    # every matched/ready row (incl. matched AFTER the apply) plus additions
    # still missing. Only meaningful once the event was applied.
    counts = {
        row["event_id"]: row
        for row in deps.conn.execute(
            "SELECT event_id, COUNT(*) AS n_tracks, "
            "SUM(CASE WHEN status IN ('matched', 'ready') THEN 1 "
            "         WHEN added_after_apply = 1 "
            "              AND status IN ('missing', 'acquisition_failed') THEN 1 "
            "         ELSE 0 END) AS pending_delta "
            "FROM event_tracks GROUP BY event_id"
        )
    }
    out = []
    for event in events_service.list_events(deps.conn):
        row = counts.get(event["id"])
        applied = event["status"] in events_service.APPLIED_EVENT_STATUSES
        out.append(
            {
                **event,
                "n_tracks": row["n_tracks"] if row else 0,
                "pending_delta": (row["pending_delta"] or 0)
                if (row and applied)
                else 0,
            }
        )
    return {"events": out}


def events_create(deps, request, body):
    """5.7 modes: from a Spotify playlist / empty-manual. Playlist mode
    (owner-approved 2026-07-07) imports the playlist's tracks at creation —
    fetched BEFORE the event row is created so a Spotify failure (409/502)
    leaves no dead event behind. Same D20 mapper as the library sync."""
    _require_storage(deps)
    playlist_id = body.get("spotify_playlist_id")
    imported = []
    if playlist_id:
        client = _sync_client(deps)
        payload = client.get(f"/playlists/{playlist_id}")
        imported = library_service._collect_tracks(client, payload)
    event = events_service.create_event(
        deps.conn,
        deps.storage_root,
        _require(body, "name"),
        spotify_playlist_id=playlist_id,
        manual=bool(body.get("manual")),
    )
    for meta in imported:
        events_service.add_track(
            deps.conn,
            event,
            spotify_track_id=meta["spotify_track_id"],
            resolver=lambda tid, meta=meta: meta,
        )
    if imported:
        _try_match_event(deps, event)  # tracks land matched, not 'missing'
    return 201, {**event, "imported_tracks": len(imported)}


def events_get(deps, request, body):
    event = _get_event(deps, request.path_params["event_id"])
    return {**event, "tracks": events_service.list_event_tracks(deps.conn, event["id"])}


def events_rename(deps, request, body):
    event = _get_event(deps, request.path_params["event_id"])
    name = _require(body, "name")
    if event["status"] != "pending":
        raise ConflictError(
            "an applied event cannot be renamed: its Rekordbox MyTag and "
            "smart playlist carry the current name"
        )
    # Pending event: no Rekordbox footprint yet, so name and default_tag
    # (the future 'Situation' MyTag, 5.7) move together.
    deps.conn.execute(
        "UPDATE events SET name = ?, default_tag = ? WHERE id = ?",
        (name, name, event["id"]),
    )
    return events_service.get_event(deps.conn, event["id"])


def events_add_track(deps, request, body):
    event = _get_event(deps, request.path_params["event_id"])
    spotify_track_id = body.get("spotify_track_id")
    track = events_service.add_track(
        deps.conn,
        event,
        spotify_track_id=spotify_track_id,
        resolver=_track_resolver(deps) if spotify_track_id else None,
        title=body.get("title"),
        artist=body.get("artist"),
    )
    matched = _try_match_event(deps, event)
    if matched is not None:
        track = next((t for t in matched if t["id"] == track["id"]), track)
    return 201, track


def events_track_remove(deps, request, body):
    """Owner-approved 2026-07-07: remove a NOT-YET-APPLIED track row from an
    event (a mispasted link must not stay 'missing' forever). App-DB only —
    an 'applied' row lives in Rekordbox and belongs to delete/reapply."""
    event = _get_event(deps, request.path_params["event_id"])
    track_id = request.path_params["track_id"]
    row = next(
        (
            track
            for track in events_service.list_event_tracks(deps.conn, event["id"])
            if track["id"] == track_id
        ),
        None,
    )
    if row is None:
        raise KeyError(f"event track {track_id} not found")
    if row["status"] == "applied":
        # (was 'imported' — a status the events vocabulary never produces,
        # so the guard was dead; found in owner testing 2026-07-07)
        raise ConflictError(
            "an applied track is in Rekordbox; the event delete/reapply "
            "flows own that transition"
        )
    deps.conn.execute("DELETE FROM event_tracks WHERE id = ?", (track_id,))
    return {"removed": track_id}


def events_match(deps, request, body):
    event = _get_event(deps, request.path_params["event_id"])
    _require_rekordbox(deps)
    tracks = events_service.match_event_tracks(
        deps.conn,
        event,
        deps.cache(),
        deps.storage_root,
        **_matching_thresholds(deps),
    )
    return {"tracks": tracks}


def _try_match_event(deps, event):
    """Matching is 100% automatic (owner decision 2026-07-07, no button):
    run on every event mutation that can leave a 'missing'/'ambiguous' row —
    add, playlist import, claim — and (client-side) when the event opens or
    Rekordbox closes. Reads the cached snapshot only, so it runs with
    Rekordbox open too. Best-effort BY DESIGN: the mutation already
    succeeded; a matcher failure (Rekordbox not configured yet, snapshot
    error) leaves rows 'missing', re-attempted on the next trigger."""
    try:
        return events_service.match_event_tracks(
            deps.conn,
            event,
            deps.cache(),
            deps.storage_root,
            **_matching_thresholds(deps),
        )
    except Exception:
        return None


def events_claim(deps, request, body):
    event = _get_event(deps, request.path_params["event_id"])
    claimed = events_service.claim_staged_files(deps.conn, event)
    _try_match_event(deps, event)  # any still-missing row re-matches too
    return {"claimed": claimed}


def _events_apply(deps, request, *, only_delta: bool):
    event = _get_event(deps, request.path_params["event_id"])
    _require_rekordbox(deps)
    progress = _Progress(deps.bus, "events.reapply" if only_delta else "events.apply")
    progress.publish(0, 1)
    result = events_service.apply_event(
        deps.conn,
        deps.db_path,
        deps.backups_root,
        deps.cache(),
        deps.storage_root,
        event,
        only_delta=only_delta,
        retention=deps.retention,
        app_db_path=deps.app_db_path,
    )
    progress.publish(1, 1)
    progress.done(event_id=event["id"], **{k: result[k] for k in ("noop", "applied")})
    return result


def events_apply(deps, request, body):
    return _events_apply(deps, request, only_delta=False)


def events_reapply(deps, request, body):
    # 11.2: the same 5.7 apply pipeline restricted to the delta.
    return _events_apply(deps, request, only_delta=True)


def events_delete(deps, request, body):
    """Preview by default; execution must echo the complete displayed plan."""
    event = _get_event(deps, request.path_params["event_id"])
    _require_rekordbox(deps)
    return events_service.delete_event(
        deps.conn,
        deps.db_path,
        deps.backups_root,
        deps.cache(),
        deps.storage_root,
        event,
        dry_run=bool(body.get("dry_run", True)),
        plan=body.get("plan"),
        consent_to_permanent_delete=bool(body.get("consent_to_permanent_delete")),
        retention=deps.retention,
        app_db_path=deps.app_db_path,
    )


# --- missing center (5.5) -----------------------------------------------------------


def missing_list(deps, request, body):
    scope = request.path_params["scope"]
    if scope == "collection":
        _require_rekordbox(deps)
    user_roots = request.query_params.getlist("root")
    entries = missing_service.list_missing(
        deps.conn,
        scope,
        cache=deps.cache() if deps.db_path else None,
        storage_root=deps.storage_root or None,
        user_roots=user_roots,
    )
    _decorate_acquisition(deps, entries)
    return {"scope": scope, "entries": entries}


def missing_status(deps, request, body):
    return missing_service.set_missing_status(
        deps.conn,
        request.path_params["scope"],
        request.path_params["row_id"],
        _require(body, "status"),
    )


def missing_restore(deps, request, body):
    return missing_service.restore_missing(
        deps.conn, request.path_params["scope"], request.path_params["row_id"]
    )


def missing_remove(deps, request, body):
    """G3: 'remove' a missing collection entry = SOFT-DELETE through mutate
    (423-guarded, backup, reversible). Never touches audio files."""
    _require_rekordbox(deps)
    content_id = str(request.path_params["content_id"])
    cache = deps.cache()
    row = next(
        (r for r in cache.get(deps.storage_root) if r["content_id"] == content_id),
        None,
    )
    if row is None:
        raise KeyError(f"content {content_id} not found in the Rekordbox snapshot")
    if not row["file_missing"]:
        raise ConflictError(
            f"content {content_id} has a present file; remove applies to "
            "missing entries only (5.8)"
        )
    with mutate(
        deps.db_path,
        deps.backups_root,
        retention=deps.retention,
        expected_fingerprint=cache.current_fingerprint,
        open_db=open_rekordbox,
        invalidate_cache=cache.invalidate,
        app_db_path=deps.app_db_path,
        backup_reason="missing_remove",
    ) as db:
        soft_delete_content(db, content_id)
    return {"soft_deleted": content_id}


def missing_relink(deps, request, body):
    _require_rekordbox(deps)
    stored = missing_service.relink_collection_file(
        deps.db_path,
        deps.backups_root,
        deps.cache(),
        deps.storage_root,
        request.path_params["content_id"],
        _require(body, "path"),
        anlz_consent=bool(body.get("anlz_consent")),
        retention=deps.retention,
        app_db_path=deps.app_db_path,
    )
    return {"content_id": request.path_params["content_id"], "stored_path": stored}


# --- optional Deezer acquisition (B1) -----------------------------------------------


def _has_deezer_arl(deps) -> bool:
    return bool(deps.secrets and deps.secrets.get(acquisition.DEEZER_ARL_SECRET))


def _acquisition_ready(deps) -> bool:
    return (
        bool(deps.settings.get("deezer_acquisition_enabled"))
        and _has_deezer_arl(deps)
        and bool(acquisition.component_status(deps.data_dir).get("installed"))
    )


def _decorate_acquisition(deps, entries: list[dict]) -> None:
    enabled = bool(deps.settings.get("deezer_acquisition_enabled"))
    has_arl = _has_deezer_arl(deps)
    component = acquisition.component_status(deps.data_dir)
    ready = enabled and has_arl and bool(component.get("installed"))
    for entry in entries:
        reason = None
        if not enabled:
            reason = "disabled"
        elif not has_arl:
            reason = "missing_arl"
        elif not component.get("installed"):
            reason = "component_not_installed"
        elif not entry.get("isrc"):
            reason = "missing_isrc"
        entry["acquisition"] = {
            "provider": "deezer",
            "available": ready and bool(entry.get("isrc")),
            "reason": reason,
        }


def acquisition_status(deps, request, body):
    return {
        "provider": "deezer",
        "enabled": bool(deps.settings.get("deezer_acquisition_enabled")),
        "has_arl": _has_deezer_arl(deps),
        "component": acquisition.component_status(deps.data_dir),
    }


def acquisition_arl_set(deps, request, body):
    if deps.secrets is None:
        raise ValueError("secrets store is not configured")
    deps.secrets.set(
        acquisition.DEEZER_ARL_SECRET, acquisition.validate_arl(_require(body, "arl"))
    )
    return acquisition_status(deps, request, body)


def acquisition_arl_delete(deps, request, body):
    if deps.secrets is not None:
        deps.secrets.delete(acquisition.DEEZER_ARL_SECRET)
    return acquisition_status(deps, request, body)


def acquisition_deezer_search(deps, request, body):
    """Manual-search panel backend: public Deezer catalogue, no credentials."""
    if not deps.settings.get("deezer_acquisition_enabled"):
        raise ValueError("Deezer acquisition is disabled")
    query = (request.query_params.get("q") or "").strip()
    if not query:
        raise ValueError("missing required query parameter 'q'")
    return {"results": acquisition.deezer_search(query)}


def acquisition_component_install(deps, request, body):
    if not deps.settings.get("deezer_acquisition_enabled"):
        raise ValueError("enable Deezer acquisition before installing the component")
    try:
        component = deps.acquisition_installer(deps.data_dir)
    except Exception as exc:
        raise ValueError("optional Deezer component installation failed") from exc
    return {"component": component}


def _acquisition_entry(
    deps, scope: str, ref: str, *, require_isrc: bool = True, conn=None
) -> dict:
    # require_isrc=False: a manually chosen Deezer track supplies its own
    # ISRC, so the row does not need one
    conn = deps.conn if conn is None else conn

    def isrc_of(value) -> str | None:
        return acquisition.normalize_isrc(value) if require_isrc else None

    if scope in ("library", "event"):
        if scope == "event":
            row = conn.execute(
                "SELECT event_tracks.*, events.staging_dir, events.slug AS event_slug, "
                "events.delete_phase AS event_delete_phase "
                "FROM event_tracks JOIN events ON events.id = event_tracks.event_id "
                "WHERE event_tracks.id = ?",
                (ref,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM library_tracks WHERE id = ?", (ref,)
            ).fetchone()
        if row is None:
            raise KeyError(f"{scope} track {ref} not found")
        if row["status"] not in missing_service.MISSING_STATUSES:
            raise ConflictError(f"{scope} track {ref} is not missing")
        if scope == "event" and row["event_delete_phase"]:
            raise ConflictError(
                "the event is being deleted and cannot accept downloads"
            )
        entry = {
            "scope": scope,
            # Canonical ref: always the id SQLite actually resolved, so
            # spellings such as '01' can never coexist with '1' as two
            # distinct active keys.
            "ref": str(row["id"]),
            "title": row["title"],
            "artist": row["artist"],
            "isrc": isrc_of(row["isrc"]),
            "event_id": row["event_id"] if scope == "event" else None,
            "event_track_id": row["id"] if scope == "event" else None,
            "library_track_id": row["id"] if scope == "library" else None,
        }
        if scope == "event":
            staging_dir = row["staging_dir"] or str(
                Path(deps.storage_root) / SYNC_DIR_NAME / "events" / row["event_slug"]
            )
            destination_dir = acquisition.event_audio_destination(
                deps.storage_root, staging_dir, event_slug=row["event_slug"]
            )
            if not row["staging_dir"]:
                conn.execute(
                    "UPDATE events SET staging_dir = ? WHERE id = ?",
                    (str(destination_dir.parent), row["event_id"]),
                )
            entry["destination_dir"] = str(destination_dir)
        else:
            entry["destination_dir"] = str(
                acquisition.collection_destination(deps.storage_root)
            )
        return entry
    if scope == "collection":
        _require_rekordbox(deps)
        row = next(
            (
                r
                for r in deps.cache().get(deps.storage_root)
                if str(r["content_id"]) == str(ref)
            ),
            None,
        )
        if row is None or not row["file_missing"]:
            raise KeyError(f"missing collection content {ref} not found")
        return {
            "scope": scope,
            "ref": str(row["content_id"]),
            "title": row["title"],
            "artist": row["artist"],
            "isrc": isrc_of(row["isrc"]),
            "event_id": None,
            "event_track_id": None,
            "library_track_id": None,
            "destination_dir": str(
                acquisition.collection_destination(deps.storage_root)
            ),
        }
    raise ValueError(f"unknown acquisition scope {scope!r}")


def _job_row(conn, job_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM acquisition_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"acquisition job {job_id} not found")
    return dict(row)


_JOB_TRANSITIONS = {
    "queued": frozenset({"running", "failed"}),
    "running": frozenset(
        {"downloaded", "relinked", "relink_blocked", "relink_failed", "failed"}
    ),
}


def _update_job(conn, job_id: int, **values) -> dict:
    current = _job_row(conn, job_id)
    next_status = values.get("status")
    if next_status is not None and next_status != current["status"]:
        allowed = _JOB_TRANSITIONS.get(current["status"], frozenset())
        if next_status not in allowed:
            raise ValueError(
                f"invalid acquisition job transition "
                f"{current['status']!r} -> {next_status!r}"
            )
    assignments = ", ".join(f"{key} = ?" for key in values)
    conn.execute(
        f"UPDATE acquisition_jobs SET {assignments}, updated_at = datetime('now') WHERE id = ?",
        (*values.values(), job_id),
    )
    return _job_row(conn, job_id)


def acquisition_job_get(deps, request, body):
    return _job_row(deps.conn, request.path_params["job_id"])


def _acquisition_error_text(exc: Exception) -> str:
    """Persist the actual failure reason, not just the exception class name."""
    return (str(exc).strip() or type(exc).__name__)[:300]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _published_output(job: dict) -> str | None:
    """Validated resume point: this job's durably published output, or None.

    A job that crossed the ``publishing``/``published`` phase persisted its
    deterministic destination and content hash BEFORE moving the file, so a
    restart can finish the owner update or relink from the existing output
    instead of downloading again (and drifting to a `` - 2`` duplicate).
    """
    if job.get("phase") not in ("publishing", "published"):
        return None
    path = job.get("published_path")
    digest = job.get("published_sha256")
    if not path or not digest:
        return None
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        return None
    if _file_sha256(candidate) != digest:
        return None
    return str(candidate)


def _run_acquisition_job(deps, job_id: int, progress=None, *, conn=None) -> dict:
    """Execute one claimed job.

    ``conn`` is the executing thread's own app-DB connection (the persistent
    worker passes its dedicated one; the synchronous HTTP path keeps
    ``deps.conn``). ``deps.lock`` is held only around the validation and
    publish/finalize phases — never across the external download — so the
    API stays responsive while the worker downloads. The lock is an RLock:
    the synchronous path, already inside it, is unaffected.
    """
    conn = deps.conn if conn is None else conn
    job = _job_row(conn, job_id)
    scope = job["scope"]
    ref = job["ref"]
    work_dir = acquisition.acquisition_output_dir(deps.storage_root, job_id)
    try:
        # Resume point: a previous attempt already published this job's
        # output durably (phase + deterministic destination + hash persisted
        # BEFORE the move). Finish the owner update / relink from that file —
        # never download again, never validate 'is missing' against an owner
        # the crashed attempt already flipped to 'ready'.
        resumed_output = _published_output(job)
        if resumed_output is None:
            with deps.lock:
                entry = _acquisition_entry(
                    deps,
                    scope,
                    ref,
                    require_isrc=job["deezer_track_id"] is None,
                    conn=conn,
                )
                if deps.secrets is None:
                    raise ValueError("secrets store is not configured")
                arl = deps.secrets.get(acquisition.DEEZER_ARL_SECRET)
                if not arl:
                    raise ValueError("Deezer ARL is not configured")
                if not acquisition.component_status(deps.data_dir).get("installed"):
                    raise ValueError("optional Deezer component is not installed")

            acquisition.reset_job_workspace(deps.storage_root, job_id)
            if progress is not None:
                progress.publish(1, 3)
            result = (
                deps.acquisition_runner(
                    deps.data_dir,
                    arl,
                    None,
                    work_dir,
                    track_id=int(job["deezer_track_id"]),
                )
                if job["deezer_track_id"] is not None
                else deps.acquisition_runner(
                    deps.data_dir, arl, entry["isrc"], work_dir
                )
            )
        with deps.lock:
            if resumed_output is None:
                downloaded = Path(result["output_path"])
                destination = None
                if job["published_path"]:
                    # A slot reserved by an interrupted attempt whose move
                    # never landed: reuse it as long as it is still free.
                    candidate = Path(job["published_path"])
                    if (
                        candidate.parent
                        == Path(entry["destination_dir"]).resolve(strict=False)
                        and not candidate.exists()
                    ):
                        destination = candidate
                if destination is None:
                    destination = acquisition.plan_publish_destination(
                        downloaded, entry["destination_dir"]
                    )
                job = _update_job(
                    conn,
                    job_id,
                    phase="publishing",
                    published_path=str(destination),
                    published_sha256=_file_sha256(downloaded),
                )
                output_path = str(
                    acquisition.publish_download(
                        downloaded,
                        entry["destination_dir"],
                        destination=destination,
                    )
                )
                quality = (
                    result.get("quality")
                    if isinstance(result.get("quality"), int)
                    else None
                )
            else:
                output_path = resumed_output
                quality = job["quality"]
            if progress is not None:
                progress.publish(2, 3)

            stored_path = None
            status = "downloaded"
            error = None
            # Persist ownership as soon as publication succeeds. If a later
            # DB update fails, the completed file remains discoverable and
            # repairable.
            _update_job(
                conn,
                job_id,
                phase="published",
                output_path=output_path,
                quality=quality,
            )
            if scope in ("library", "event"):
                table = {"library": "library_tracks", "event": "event_tracks"}[scope]
                conn.execute(
                    f"UPDATE {table} SET status = 'ready', staging_file_path = ?, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (output_path, ref),
                )
            elif job["relink"]:
                try:
                    stored_path = missing_service.relink_collection_file(
                        deps.db_path,
                        deps.backups_root,
                        deps.cache(),
                        deps.storage_root,
                        ref,
                        output_path,
                        anlz_consent=bool(job["anlz_consent"]),
                        retention=deps.retention,
                        app_db_path=deps.app_db_path,
                    )
                    status = "relinked"
                except MutationBlockedError:
                    status = "relink_blocked"
                    error = "rekordbox_open"
                except Exception as exc:
                    status = "relink_failed"
                    error = _acquisition_error_text(exc)
            job = _update_job(
                conn,
                job_id,
                status=status,
                output_path=output_path,
                stored_path=stored_path,
                error=error,
                quality=quality,
            )
        if progress is not None:
            progress.publish(3, 3)
            progress.done(id=job_id, status=status, output_path=output_path)
        return job
    except Exception as exc:
        with deps.lock:
            if scope in ("library", "event"):
                table = {"library": "library_tracks", "event": "event_tracks"}[scope]
                conn.execute(
                    f"UPDATE {table} SET status = 'acquisition_failed', "
                    "updated_at = datetime('now') WHERE id = ?",
                    (ref,),
                )
            error = _acquisition_error_text(exc)
            job = _update_job(conn, job_id, status="failed", error=error)
        if progress is not None:
            progress.done(id=job_id, status="failed", error=error)
        return job
    finally:
        acquisition.cleanup_job_workspace(deps.storage_root, job_id)


def _require_acquisition_ready(deps) -> None:
    if not deps.settings.get("deezer_acquisition_enabled"):
        raise ValueError("Deezer acquisition is disabled")
    if deps.secrets is None:
        raise ValueError("secrets store is not configured")
    if not deps.secrets.get(acquisition.DEEZER_ARL_SECRET):
        raise ValueError("Deezer ARL is not configured")
    if not acquisition.component_status(deps.data_dir).get("installed"):
        raise ValueError("optional Deezer component is not installed")
    _require_storage(deps)


def _queue_acquisition_job(deps, body: dict) -> dict:
    """Resolve one owner and make its queued job durable; returns the row.

    Shared by the single-job endpoint and the transactional batch endpoint.
    """
    scope = _require(body, "scope")
    ref = str(body.get("row_id") or body.get("content_id") or body.get("id") or "")
    if not ref:
        raise ValueError("missing required field 'row_id' or 'content_id'")
    # manual pick from the Deezer search panel: download that exact track id
    # (ISRC resolution can land on an unstreamable canonical entry even when
    # the picked re-release is streamable — Martin Solveig "Hello" case)
    deezer_track_id = body.get("deezer_track_id")
    entry = _acquisition_entry(deps, scope, ref, require_isrc=deezer_track_id is None)
    # relink consent is unconditional (missing_service) — gate it BEFORE the
    # download so the client's 428 consent loop re-calls without having
    # wasted a full download on the refused first attempt
    if scope == "collection" and body.get("relink") and not body.get("anlz_consent"):
        raise AnlzConsentRequired(
            "Relinking replaces the file association; cues, beatgrid and "
            "waveform stored in ANLZ files may desynchronize and are NOT "
            "covered by the master.db backup. Explicit consent is required."
        )
    active = deps.conn.execute(
        "SELECT * FROM acquisition_jobs WHERE scope = ? AND ref = ? "
        "AND status IN ('queued', 'running') ORDER BY id LIMIT 1",
        (entry["scope"], entry["ref"]),
    ).fetchone()
    if active is not None:
        return dict(active)
    # Retry with an intact published output (terminal relink_blocked /
    # relink_failed, or a failure after publication): requeue THAT job so it
    # resumes from its file instead of downloading a duplicate.
    previous = deps.conn.execute(
        "SELECT * FROM acquisition_jobs WHERE scope = ? AND ref = ? "
        "AND status IN ('relink_blocked', 'relink_failed', 'failed') "
        "ORDER BY id DESC LIMIT 1",
        (entry["scope"], entry["ref"]),
    ).fetchone()
    if previous is not None and _published_output(dict(previous)) is not None:
        deps.conn.execute(
            "UPDATE acquisition_jobs SET status = 'queued', error = NULL, "
            "claimed_by = NULL, claimed_at = NULL, anlz_consent = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (int(bool(body.get("anlz_consent"))), previous["id"]),
        )
        return _job_row(deps.conn, previous["id"])
    cursor = deps.conn.execute(
        "INSERT INTO acquisition_jobs "
        "(scope, ref, title, artist, isrc, status, event_id, event_track_id, "
        "library_track_id, deezer_track_id, relink, anlz_consent) "
        "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)",
        (
            entry["scope"],
            entry["ref"],
            entry["title"],
            entry["artist"],
            entry["isrc"],
            entry["event_id"],
            entry["event_track_id"],
            entry["library_track_id"],
            int(deezer_track_id) if deezer_track_id is not None else None,
            int(bool(body.get("relink"))),
            int(bool(body.get("anlz_consent"))),
        ),
    )
    return _job_row(deps.conn, cursor.lastrowid)


def acquisition_job_start(deps, request, body):
    _require_acquisition_ready(deps)
    job = _queue_acquisition_job(deps, body)
    if body.get("enqueue"):
        return 202, job
    if job["status"] != "queued":
        return job
    _update_job(deps.conn, job["id"], status="running")
    return _run_acquisition_job(
        deps, job["id"], _Progress(deps.bus, "deezer.acquisition")
    )


def acquisition_jobs_batch(deps, request, body):
    """Persist a whole batch in ONE transaction before any execution.

    The persistent worker claims jobs on its own connection, so without the
    transaction it could start the first item while later items were still
    unpersisted — closing the UI mid-batch then silently truncated the
    intended queue.
    """
    _require_acquisition_ready(deps)
    items = _require_list(body, "items")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("field 'items' must contain JSON objects")
    deps.conn.execute("BEGIN IMMEDIATE")
    try:
        jobs = [_queue_acquisition_job(deps, item) for item in items]
        deps.conn.execute("COMMIT")
    except BaseException:
        deps.conn.execute("ROLLBACK")
        raise
    return 202, {"jobs": jobs}


def acquisition_jobs_list(deps, request, body):
    """Active queue plus recent terminal jobs, for UI rehydration on reopen."""
    try:
        limit = max(1, min(int(request.query_params.get("recent", 50)), 200))
    except ValueError:
        raise ValueError("recent must be an integer")
    active = [
        dict(row)
        for row in deps.conn.execute(
            "SELECT * FROM acquisition_jobs "
            "WHERE status IN ('queued', 'running') ORDER BY id"
        )
    ]
    recent = [
        dict(row)
        for row in deps.conn.execute(
            "SELECT * FROM acquisition_jobs "
            "WHERE status NOT IN ('queued', 'running') ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    ]
    return {"active": active, "recent": recent}


def acquisition_storage_migration(deps, request, body):
    _require_rekordbox(deps)
    _require_storage(deps)
    if request.method == "GET" or bool(body.get("dry_run", True)):
        return acquisition_migration.build_plan(
            deps.conn, deps.storage_root, deps.db_path
        )
    return acquisition_migration.execute(
        deps.conn,
        deps.db_path,
        deps.backups_root,
        deps.cache(),
        deps.storage_root,
        body.get("plan"),
        app_db_path=deps.app_db_path,
        retention=deps.retention,
        consent_to_permanent_delete=bool(body.get("consent_to_permanent_delete")),
    )


# --- duplicates (5.4, A3 per 5.12) ---------------------------------------------------


def duplicates_scan(deps, request, body):
    """Dedup scan: groups from the snapshot, quality verdicts computed ON
    DEMAND for group members ONLY and never persisted (5.12), keeper
    suggested with its D6 reason. Progress = members analyzed (real units)."""
    _require_rekordbox(deps)
    cache = deps.cache()
    # streaming references have no file: never duplicate-group members
    rows = [r for r in cache.get(deps.storage_root) if not r.get("spotify_track_id")]
    groups = dedup.find_duplicate_groups(rows, repos.list_dismissed_groups(deps.conn))
    by_id = {row["content_id"]: row for row in rows}
    progress = _Progress(deps.bus, "duplicates.scan")
    total = sum(len(g.content_ids) for g in groups)
    done = 0
    out = []
    for group in groups:
        members = []
        for content_id in group.content_ids:
            member = dict(by_id[content_id])  # copy: cache rows stay verdict-free
            if member.get("resolved_path"):
                verdict = quality.analyze(member["resolved_path"])
                member["quality_verdict"] = verdict.verdict
                member["quality_reason"] = verdict.reason
            else:
                member["quality_verdict"] = "ok"  # 5.12: neutral by default
                member["quality_reason"] = "no_local_path_neutral"
            members.append(member)
            done += 1
            progress.publish(done, total)
        keeper, reason = dedup.choose_keeper(members)
        out.append(
            {
                "key": group.key,
                "method": group.method,
                "confidence": group.confidence,
                "warning": group.warning,
                "members": members,
                "keeper": {"content_id": keeper["content_id"], "reason": reason},
            }
        )
    progress.done(groups=len(out))
    return {
        "groups": out,
        "scanned": len(rows),
        # Echo of the snapshot fingerprint: pass it back to /resolve so the
        # mutate freshness guard covers exactly what this scan displayed.
        "fingerprint": cache.current_fingerprint,
    }


def duplicates_resolve(deps, request, body):
    """Per-group confirm (D5). Order is load-bearing (5.4): relink
    memberships -> soft-delete losers inside ONE mutate() -> file deletion
    strictly AFTER the durable commit, through the OS-trash-first consent
    contract. A loser whose path denotes the keeper's own file (either 3.2
    spelling) is reported and NEVER deleted. Re-entrant: a 428 consent
    retry skips the already-committed DB work and finishes the file
    cleanup."""
    _require_rekordbox(deps)
    keeper = str(_require(body, "keeper_content_id"))
    losers = [str(c) for c in _require_list(body, "loser_content_ids")]
    if keeper in losers:
        raise ValueError("the keeper cannot be one of the losers (5.4)")
    consent = bool(body.get("consent_to_permanent_delete"))
    expected = _fingerprint_tuple(body.get("fingerprint"))

    # Raw read-only lookup WITHOUT the soft-delete filter: on a consent
    # retry the losers are already soft-deleted (hence absent from the
    # snapshot) but their audio files may still need deleting.
    ro = open_readonly(deps.db_path)
    try:
        ids = [keeper, *losers]
        placeholders = ", ".join("?" for _ in ids)
        states = {
            str(content_id): {"path": folder_path, "deleted": int(deleted or 0)}
            for content_id, folder_path, deleted in ro.execute(
                "SELECT ID, FolderPath, rb_local_deleted FROM djmdContent "
                f"WHERE ID IN ({placeholders})",
                ids,
            )
        }
    finally:
        ro.close()
    if keeper not in states or states[keeper]["deleted"]:
        raise KeyError(f"keeper content {keeper} not found")
    unknown = [c for c in losers if c not in states]
    if unknown:
        raise KeyError(f"unknown content ids: {unknown}")
    # Duplicate resolution is ownership-neutral after exact per-group
    # confirmation. Every loser uses the same trash-first contract; the
    # keeper's physical file remains untouchable.

    active = [c for c in losers if not states[c]["deleted"]]
    cache = deps.cache()
    if active:
        cache.get(deps.storage_root)  # ensure a current fingerprint exists
        with mutate(
            deps.db_path,
            deps.backups_root,
            retention=deps.retention,
            # The scan's fingerprint when provided (StaleSnapshotError ->
            # 409 rerun the scan), else the freshly loaded snapshot's.
            expected_fingerprint=expected or cache.current_fingerprint,
            open_db=open_rekordbox,
            invalidate_cache=cache.invalidate,
            app_db_path=deps.app_db_path,
            backup_reason="duplicate_resolve",
        ) as db:
            for loser in active:
                reassign_memberships(db, loser, keeper)  # playlists + MyTags
                soft_delete_content(db, loser)

    keeper_stored = states[keeper]["path"]
    files = []
    for loser in losers:
        stored = states[loser]["path"]
        if not stored:
            continue
        resolved = resolve_stored_path(stored, deps.storage_root)
        if keeper_stored and paths_equal(stored, keeper_stored, deps.storage_root):
            # 5.4: the keeper's audio file is NEVER deleted. A loser ROW can
            # share the keeper's physical file (double import, manual relink
            # onto the same copy - dedup groups on metadata, never on path),
            # in either the volume-relative or absolute spelling (3.2).
            files.append(
                {
                    "content_id": loser,
                    "path": str(resolved),
                    "result": "kept_keeper_file",
                }
            )
            continue
        if tcc_exists(resolved):
            outcome = delete_file(resolved, consent_to_permanent_delete=consent)
            files.append(
                {"content_id": loser, "path": str(resolved), "result": outcome}
            )
    return {"keeper": keeper, "soft_deleted": active, "files": files}


def duplicates_dismiss(deps, request, body):
    group_key = _require(body, "group_key")
    repos.add_dismissed_group(deps.conn, group_key)  # idempotent (5.4)
    return {"dismissed": group_key}


# --- untagged (5.8) -----------------------------------------------------------------


def untagged_list(deps, request, body):
    _require_rekordbox(deps)
    rows = deps.cache().get(deps.storage_root)
    patterns = [p["pattern"] for p in repos.list_untagged_patterns(deps.conn)]
    tracks = untagged.categorize(
        [r for r in rows if not r["tag_count"]],
        [r for r in rows if r["tag_count"]],
        patterns,
    )
    return {"tracks": tracks}


def untagged_patterns_list(deps, request, body):
    return {"patterns": repos.list_untagged_patterns(deps.conn)}


def untagged_patterns_add(deps, request, body):
    pattern = _require(body, "pattern")
    pattern_id = repos.add_untagged_pattern(deps.conn, pattern)
    return 201, {"id": pattern_id, "pattern": pattern}


def untagged_patterns_remove(deps, request, body):
    repos.remove_untagged_pattern(deps.conn, request.path_params["pattern_id"])
    return {"removed": request.path_params["pattern_id"]}


def untagged_delete(deps, request, body):
    """Soft-delete untagged Rekordbox rows without deleting any audio file.

    Stale not-found or now-tagged rows are skipped and reported. Ownership
    does not affect this reversible database-only operation.
    """
    _require_rekordbox(deps)
    content_ids = [str(c) for c in _require_list(body, "content_ids")]
    cache = deps.cache()
    by_id = {row["content_id"]: row for row in cache.get(deps.storage_root)}
    deletable, skipped = [], []
    for content_id in content_ids:
        row = by_id.get(content_id)
        if row is None:
            skipped.append({"content_id": content_id, "reason": "not_found"})
        elif row["tag_count"]:
            skipped.append({"content_id": content_id, "reason": "tagged"})
        else:
            deletable.append(content_id)
    if deletable:
        with mutate(
            deps.db_path,
            deps.backups_root,
            retention=deps.retention,
            expected_fingerprint=cache.current_fingerprint,
            open_db=open_rekordbox,
            invalidate_cache=cache.invalidate,
            app_db_path=deps.app_db_path,
            backup_reason="untagged_remove",
        ) as db:
            for content_id in deletable:
                soft_delete_content(db, content_id)
    return {"soft_deleted": deletable, "skipped": skipped}


# --- smart fixes (5.11) --------------------------------------------------------------


def smartfixes_dry_run(deps, request, body):
    """Read-only preview: snapshot cache only, master.db never opened, RB
    may be running."""
    _require_rekordbox(deps)
    return smartfixes_run.dry_run(deps.cache(), deps.storage_root)


def smartfixes_execute(deps, request, body):
    """Executes EXACTLY the confirmed dry-run payload (B10); the dry-run
    fingerprint re-asserts freshness (stale -> 409) and the payload is
    re-checked server-side against the freshly derived plan."""
    _require_rekordbox(deps)
    dry = {
        "payload": _require_list(body, "payload"),
        "fingerprint": _fingerprint_tuple(_require(body, "fingerprint")),
    }
    return smartfixes_run.execute(
        deps.db_path,
        deps.backups_root,
        deps.cache(),
        deps.storage_root,
        dry,
        retention=deps.retention,
        app_db_path=deps.app_db_path,
    )


# --- settings (5.10) -----------------------------------------------------------------


def settings_get(deps, request, body):
    return deps.settings.all()


def _path_setting_error(key: str, value: str) -> str | None:
    """F15 path checks, shared by PUT /api/settings and the settings import."""
    if key == "storage_root":
        ok, why = validate_directory(value)
        return None if ok else why
    if key == "rekordbox_db_path":
        expanded = Path(value).expanduser()
        ok, why = validate_directory(str(expanded.parent))
        if not ok:
            return f"parent folder {why}"
        if not expanded.is_file():
            return "not found"
    return None


def settings_update(deps, request, body):
    # F15: validate BOTH configured paths before persisting anything; an
    # empty value stays allowed (it means 'not configured yet').
    for key in ("storage_root", "rekordbox_db_path"):
        value = body.get(key)
        if value:
            why = _path_setting_error(key, value)
            if why:
                raise ValueError(f"{key}: {why}")
    try:
        return deps.settings.update(body)
    except KeyError as exc:
        raise ValueError(str(exc.args[0])) from exc


# --- export/import (5.10 transfer) ----------------------------------------------------


SETTINGS_EXPORT_KIND = "syncbox-settings"


def _body_path(body, *, must_exist=False) -> Path:
    path = Path(_require(body, "path")).expanduser()
    if not path.is_absolute():
        raise ValueError("path must be absolute")
    if must_exist:
        if not path.is_file():
            raise FileNotFoundError(str(path))
    elif not path.parent.is_dir():
        raise ValueError("path: parent folder not found")
    return path


def settings_export(deps, request, body):
    """5.10 settings export: ONE JSON file, written by the sidecar (the
    webview has no fs access). OAuth tokens are not settings - they live in
    the encrypted SecretsStore and are never in this file (3.6)."""
    dest = _body_path(body)
    payload = {
        "kind": SETTINGS_EXPORT_KIND,
        "version": 1,
        "settings": deps.settings.all(),
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"path": str(dest)}


def settings_import(deps, request, body):
    """Apply a settings export. Path values that do not exist on THIS machine
    are skipped and reported, never a wholesale failure (the file may come
    from another machine); unknown keys are skipped the same way."""
    source = _body_path(body, must_exist=True)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"not a Syncbox settings export: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("kind") != SETTINGS_EXPORT_KIND:
        raise ValueError("not a Syncbox settings export")
    values = payload.get("settings")
    if not isinstance(values, dict):
        raise ValueError("settings export carries no settings object")
    skipped = {key: "unknown setting" for key in values if key not in SETTINGS_DEFAULTS}
    incoming = {key: value for key, value in values.items() if key in SETTINGS_DEFAULTS}
    for key in ("storage_root", "rekordbox_db_path"):
        value = incoming.get(key)
        if value:
            why = _path_setting_error(key, value)
            if why:
                skipped[key] = why
                del incoming[key]
    settings = deps.settings.update(incoming)
    return {"applied": sorted(incoming), "skipped": skipped, "settings": settings}


def data_export(deps, request, body):
    """All-data export (5.10): VACUUM INTO writes one coherent snapshot. An
    existing destination needs the explicit overwrite flag - the UI's native
    save dialog already asked; the sidecar never clobbers silently."""
    dest = _body_path(body)
    if dest.exists():
        if not body.get("overwrite"):
            raise ValueError(f"file already exists: {dest}")
        dest.unlink()
    appdb.export_data(deps.conn, dest)
    return {"path": str(dest)}


def data_import(deps, request, body):
    """All-data import (5.10): the incoming file is checked (Syncbox schema +
    integrity_check in appdb.import_data), the current DB is safety-backed-up,
    then the live connection swaps to the new file - open_app_db migrates it,
    so an export from an older version imports fine."""
    if deps.app_db_path is None:
        raise ValueError("all-data import needs a file-backed app DB")
    source = _body_path(body, must_exist=True)
    deps.conn.close()
    try:
        backup = appdb.import_data(deps.app_db_path, source)
    finally:
        # always come back up on a live connection - on the imported DB, or
        # on the untouched original if import_data refused the file
        deps.conn = appdb.open_app_db(deps.app_db_path)
        deps.settings = Settings(deps.conn)
        deps._cache = None  # imported settings may point at another master.db
        deps._cache_db = None
    return {"backup": str(backup) if backup else None}


# --- readouts (11.3) -----------------------------------------------------------------


def readouts_get(deps, request, body):
    _require_rekordbox(deps)
    rows = deps.cache().get(deps.storage_root)
    return {
        "total_tracks": len(rows),
        "keys_analyzed": readouts.keys_analyzed(rows),
        "never_played": readouts.never_played(rows),
        **readouts.added_this_month(rows, datetime.now()),
        "genres": readouts.genre_distribution(rows),
        # QualityBadge vocabulary; verdicts are on-demand only, so absent
        # verdicts read as neutral 'ok' (11.3 rejected the binary red counter).
        "quality": readouts.quality_readout(rows),
    }


# --- performances (historique des prestations; owner-approved 17/07/2026) -----------


def _performances_refresh(deps) -> dict:
    """Read-only ingest from master.db - deliberately NOT process-guarded:
    running while Rekordbox plays is the point (crash-proof live view)."""
    if not deps.db_path:
        raise ValueError("configure rekordbox_db_path in Settings first")
    return performances.refresh(deps.conn, deps.db_path, deps.spotify_client)


def performances_list(deps, request, body):
    refresh_info = _performances_refresh(deps)
    include_hidden = request.query_params.get("hidden") == "1"
    return {
        "performances": performances.list_performances(deps.conn, include_hidden),
        **refresh_info,
    }


def performances_live(deps, request, body):
    _performances_refresh(deps)
    return performances.live_status(deps.conn)


def performances_get(deps, request, body):
    return performances.get_performance(
        deps.conn, request.path_params["performance_id"]
    )


def performances_update(deps, request, body):
    performance_id = request.path_params["performance_id"]
    updates = {}
    if "name" in body:
        name = body["name"]
        if name is not None and not isinstance(name, str):
            raise ValueError("name must be a string or null")
        updates["name"] = (name or "").strip() or None
    if "hidden" in body:
        if not isinstance(body["hidden"], bool):
            raise ValueError("hidden must be a boolean")
        updates["hidden"] = int(body["hidden"])
    if not updates:
        raise ValueError("nothing to update: send name and/or hidden")
    assignments = ", ".join(f"{column} = ?" for column in updates)
    cursor = deps.conn.execute(
        f"UPDATE performances SET {assignments} WHERE id = ?",
        (*updates.values(), performance_id),
    )
    if cursor.rowcount == 0:
        raise KeyError(f"performance {performance_id} not found")
    return performances.get_performance(deps.conn, performance_id)


def performances_export_playlist(deps, request, body):
    """Export a prestation as an ordered PLAIN playlist under the
    'Historique' folder (owner request 17/07/2026) - the keep-this-set
    archive. Standard write path: mutate guard, so Rekordbox must be
    closed; the fingerprint comes from the live snapshot cache."""
    _require_rekordbox(deps)
    performance = performances.get_performance(
        deps.conn, request.path_params["performance_id"]
    )
    # "YYYY-MM-DD - Name": the owner's existing convention inside the
    # Historiques folder (e.g. "2024-01-13 - Rallye Fontainebleau #1"),
    # which also keeps the folder chronologically sorted.
    custom = (body.get("name") or "").strip() or performance["name"]
    name = f"{performance['started_at'][:10]} - {custom or 'Prestation'}"
    # Content states read directly (fingerprint taken FIRST, re-asserted by
    # mutate): soft-deleted Spotify contents are revived into the playlist,
    # soft-deleted local files stay out.
    expected = fingerprint(deps.db_path)
    content_ids = [t["content_id"] for t in performance["tracks"] if t["content_id"]]
    states = {}
    ro = open_readonly(deps.db_path)
    try:
        for chunk_start in range(0, len(content_ids), 500):
            chunk = content_ids[chunk_start : chunk_start + 500]
            placeholders = ",".join("?" for _ in chunk)
            for row_id, deleted, path in ro.execute(
                f"SELECT ID, rb_local_deleted, FolderPath FROM djmdContent"
                f" WHERE ID IN ({placeholders})",
                chunk,
            ):
                states[str(row_id)] = {
                    "deleted": bool(deleted),
                    "spotify": str(path or "").startswith(SPOTIFY_TRACK_PREFIX),
                }
    finally:
        ro.close()
    slots, duplicates = performances.export_plan(performance["tracks"], states)
    # A missing local play may still be recoverable as a STREAMING reference
    # (owner request 17/07: no audio, just the Spotify link) when Syncbox's
    # own event/library mappings remember which Spotify track the deleted
    # file came from.
    links = performances.spotify_links(
        deps.conn,
        [s["content_id"] for s in slots if s["action"] == "missing" and s["content_id"]],
    )
    if not any(
        s["action"] in ("keep", "revive")
        or (s["action"] == "missing" and s["content_id"] in links)
        for s in slots
    ):
        raise ConflictError(
            "none of this performance's tracks are still in the collection"
        )
    cache = deps.cache()
    revived = recovered = missing = 0
    with mutate(
        deps.db_path,
        deps.backups_root,
        retention=deps.retention,
        expected_fingerprint=expected,
        open_db=open_rekordbox,
        invalidate_cache=cache.invalidate,
        app_db_path=deps.app_db_path,
        backup_reason="performance_export",
    ) as db:
        ordered = []
        for slot in slots:
            content_id = slot["content_id"]
            if slot["action"] == "revive":
                reactivate_content(db, content_id)
                revived += 1
            elif slot["action"] == "missing":
                link = links.get(content_id)
                if link is None:
                    missing += 1
                    continue
                track_id, duration_ms = link
                row = add_streaming_content(
                    db, track_id, (duration_ms or 0) / 1000 or None
                )
                content_id = str(row.ID)
                recovered += 1
            if content_id in ordered:
                duplicates += 1  # two deleted files mapping to one track
                continue
            ordered.append(content_id)
        folder = ensure_playlist_folder(db, performances.EXPORT_FOLDER)
        playlist = create_plain_playlist(db, name, folder.ID, ordered)
        playlist_name = playlist.Name
    return {
        "playlist": playlist_name,
        "folder": performances.EXPORT_FOLDER,
        "tracks": len(ordered),
        "spotify_revived": revived,
        "spotify_recovered": recovered,
        "skipped_duplicates": duplicates,
        "skipped_missing": missing,
    }


# --- doctor (5.10/F9) ----------------------------------------------------------------


def doctor_backups(deps, request, body):
    _require_storage(deps)
    return {"backups": list_backups(deps.backups_root)}


def doctor_restore(deps, request, body):
    _require_rekordbox(deps)
    name = request.path_params["name"]
    backups_root = deps.backups_root
    db_path = deps.db_path
    cache = deps.cache()
    if deps.app_db_path is None:
        snapshot = restore_backup(
            name, backups_root, db_path, journal_dir=deps.data_dir
        )
    else:
        deps.conn.close()
        try:
            snapshot = restore_backup(
                name,
                backups_root,
                db_path,
                app_db_path=deps.app_db_path,
                journal_dir=deps.data_dir,
            )
        finally:
            deps.conn = appdb.open_app_db(deps.app_db_path)
            deps.settings = Settings(deps.conn)
    cache.invalidate()
    deps._cache = None
    deps._cache_db = None
    return {
        "restored": name,
        # SPEC-01 1.3: restore snapshots the current DB first, so it is
        # itself reversible; None only in the no-live-DB disaster case.
        "pre_restore_snapshot": snapshot.name if snapshot else None,
    }


def doctor_retention(deps, request, body):
    value = body.get("backup_retention")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("backup_retention must be an integer >= 0 (0 = unlimited)")
    deps.settings.update({"backup_retention": value})
    return {"backup_retention": value}


def doctor_logs(deps, request, body):
    try:
        lines = max(1, min(int(request.query_params.get("lines", 200)), 2000))
    except ValueError:
        raise ValueError("lines must be an integer")
    path = Path(deps.log_path) if deps.log_path else None
    if path is None or not path.is_file():
        return {"configured": False, "lines": []}
    tail: deque[str] = deque(maxlen=lines)
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            tail.append(line.rstrip("\n"))
    return {"configured": True, "path": str(path), "lines": list(tail)}


# --- mytags ----------------------------------------------------------------------


def mytags_get(deps, request, body):
    """MyTag catalog for the TagPicker (SPEC-DESIGN 6; owner-approved route,
    2026-07-07): read-only djmdMyTag names with their parent category
    (categories are the ParentID='root' rows). The write side is unchanged -
    apply still requires library MyTags to pre-exist (5.6)."""
    _require_rekordbox(deps)
    ro = open_readonly(deps.db_path)
    try:
        rows = ro.execute(
            "SELECT ID, Name, ParentID FROM djmdMyTag WHERE rb_local_deleted = 0"
        ).fetchall()
    finally:
        ro.close()
    categories = {
        str(row_id): name for row_id, name, parent in rows if str(parent) == "root"
    }
    tags = sorted(
        (
            {"name": name, "category": categories.get(str(parent))}
            for row_id, name, parent in rows
            if str(parent) != "root" and name
        ),
        key=lambda tag: (tag["category"] or "", tag["name"]),
    )
    return {"tags": tags}


# --- spotify ----------------------------------------------------------------------


_PLAYLISTS_MAX_PAGES = 20  # 50/page bounds one request to 1,000 playlists.


def spotify_playlists(deps, request, body):
    """R5 (owner-approved 2026-07-07): the connected account's playlists for
    the AddSourceModal picker - read-only /me/playlists walk (the existing
    read scopes cover it, 5.9 D3). Link-paste stays the other add path.
    409 spotify_not_connected / 502 spotify_api_error map automatically."""
    client = _sync_client(deps)
    playlists = []
    url = "/me/playlists?limit=50"
    for _ in range(_PLAYLISTS_MAX_PAGES):
        payload = client.get(url)
        for item in payload.get("items") or []:
            if not item or not item.get("id"):
                continue  # Spotify pads deleted playlists with nulls
            images = item.get("images") or []
            page = item.get("items")
            if not isinstance(page, dict):
                page = item.get("tracks") or {}
            playlists.append(
                {
                    "spotify_playlist_id": item["id"],
                    "name": item.get("name") or "",
                    "owner": (item.get("owner") or {}).get("display_name"),
                    "tracks_total": page.get("total") or 0,
                    "image_url": images[0]["url"] if images else None,
                }
            )
        url = payload.get("next")  # absolute URL; SpotifyClient.get accepts it
        if not url:
            break
    return {"playlists": playlists}


def spotify_authorize(deps, request, body):
    if deps.spotify_auth is None or deps.oauth_listener is None:
        return 503, {"error": "oauth not configured"}
    created = deps.oauth_listener.start(
        deps.spotify_auth.handle_callback,
        oauth_lock=deps.lock,
        timeout=AUTHORIZATION_TIMEOUT_SECONDS,
    )
    try:
        return {"url": deps.spotify_auth.begin_authorization()}
    except Exception:
        if created:
            deps.oauth_listener.stop()
        raise


def spotify_disconnect(deps, request, body):
    """Disconnect Spotify and delete local playlist relationships.

    The token deletion happens first so a later SQLite failure cannot leave
    Syncbox able to make new Spotify requests. Followed sources and their
    tracks/runs are deleted by cascade. Events remain usable as local
    lifecycle records, with Spotify identifiers detached. Rekordbox and local
    audio files are never opened by this endpoint.
    """
    if deps.spotify_auth is None:
        return 503, {"error": "oauth not configured"}
    if deps.oauth_listener is not None:
        deps.oauth_listener.stop()
    deps.spotify_auth.disconnect()

    counts = {
        "sources": deps.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "library_tracks": deps.conn.execute(
            "SELECT COUNT(*) FROM library_tracks"
        ).fetchone()[0],
        "sync_runs": deps.conn.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0],
        "events_detached": deps.conn.execute(
            "SELECT COUNT(*) FROM events "
            "WHERE spotify_playlist_id IS NOT NULL "
            "AND spotify_playlist_id NOT LIKE 'manual:%'"
        ).fetchone()[0],
        "event_tracks_detached": deps.conn.execute(
            "SELECT COUNT(*) FROM event_tracks WHERE spotify_track_id IS NOT NULL"
        ).fetchone()[0],
        "acquisition_jobs_deleted": deps.conn.execute(
            "SELECT COUNT(*) FROM acquisition_jobs WHERE scope IN ('library', 'event')"
        ).fetchone()[0],
    }
    deps.conn.execute("BEGIN")
    try:
        deps.conn.execute("DELETE FROM sources")
        deps.conn.execute(
            "UPDATE events SET spotify_playlist_id = 'manual:' || slug "
            "WHERE spotify_playlist_id IS NOT NULL "
            "AND spotify_playlist_id NOT LIKE 'manual:%'"
        )
        deps.conn.execute(
            "UPDATE event_tracks SET spotify_track_id = NULL "
            "WHERE spotify_track_id IS NOT NULL"
        )
        deps.conn.execute(
            "DELETE FROM acquisition_jobs WHERE scope IN ('library', 'event')"
        )
        deps.conn.execute("COMMIT")
    except BaseException:
        deps.conn.execute("ROLLBACK")
        raise
    return {"disconnected": True, "rekordbox_changed": False, **counts}


def spotify_playlist_preview(deps, request, body):
    """G5: read-only playlist preview for AddSourceModal, resolved BEFORE
    following. 409 spotify_not_connected / 502 spotify_api_error map
    automatically (404 = private playlist, actionable)."""
    client = _sync_client(deps)
    playlist_id = request.path_params["playlist_id"]
    payload = client.get(f"/playlists/{playlist_id}")
    images = payload.get("images") or []
    page = payload.get("items")
    if not isinstance(page, dict):
        page = payload.get("tracks") or {}
    return {
        "name": payload.get("name"),
        "owner": (payload.get("owner") or {}).get("display_name"),
        "tracks_total": page.get("total") or 0,
        "image_url": images[0]["url"] if images else None,
    }


# --- route table -------------------------------------------------------------------


def routes(deps: Deps) -> list[Route]:
    def r(path: str, handler, methods: list[str]) -> Route:
        return Route(path, _endpoint(deps, handler), methods=methods)

    return [
        r("/api/status", status_get, ["GET"]),
        r("/api/sources", sources_list, ["GET"]),
        r("/api/sources", sources_add, ["POST"]),
        r("/api/sources/sync", sources_sync_all, ["POST"]),
        r("/api/sources/{source_id:int}", sources_update, ["PATCH"]),
        r("/api/sources/{source_id:int}", sources_remove, ["DELETE"]),
        r("/api/sources/{source_id:int}/sync", sources_sync_one, ["POST"]),
        r("/api/sources/{source_id:int}/tracks", source_tracks, ["GET"]),
        r("/api/sources/{source_id:int}/apply", source_apply, ["POST"]),
        r("/api/library/tracks/tags", tracks_tag_delta, ["POST"]),
        r("/api/library/tracks/{track_id:int}/candidates", track_candidates, ["GET"]),
        r("/api/library/tracks/{track_id:int}/match", track_match_manual, ["POST"]),
        r("/api/library/tracks/{track_id:int}/rematch", track_rematch, ["POST"]),
        r("/api/library/tracks/{track_id:int}/missing", track_mark_missing, ["POST"]),
        r("/api/library/tracks/{track_id:int}/ignore", track_ignore, ["POST"]),
        r("/api/library/tracks/{track_id:int}/restore", track_restore, ["POST"]),
        r("/api/events", events_list, ["GET"]),
        r("/api/events", events_create, ["POST"]),
        r("/api/events/{event_id:int}", events_get, ["GET"]),
        r("/api/events/{event_id:int}", events_rename, ["PATCH"]),
        r("/api/events/{event_id:int}/tracks", events_add_track, ["POST"]),
        r(
            "/api/events/{event_id:int}/tracks/{track_id:int}",
            events_track_remove,
            ["DELETE"],
        ),
        r("/api/events/{event_id:int}/match", events_match, ["POST"]),
        r("/api/events/{event_id:int}/claim", events_claim, ["POST"]),
        r("/api/events/{event_id:int}/apply", events_apply, ["POST"]),
        r("/api/events/{event_id:int}/reapply", events_reapply, ["POST"]),
        r("/api/events/{event_id:int}/delete", events_delete, ["POST"]),
        r("/api/performances", performances_list, ["GET"]),
        r("/api/performances/live", performances_live, ["GET"]),
        r("/api/performances/{performance_id:int}", performances_get, ["GET"]),
        r("/api/performances/{performance_id:int}", performances_update, ["PATCH"]),
        r(
            "/api/performances/{performance_id:int}/export-playlist",
            performances_export_playlist,
            ["POST"],
        ),
        r("/api/missing/collection/{content_id}/relink", missing_relink, ["POST"]),
        r("/api/missing/collection/{content_id}/remove", missing_remove, ["POST"]),
        r("/api/missing/{scope}", missing_list, ["GET"]),
        r("/api/missing/{scope}/{row_id:int}/status", missing_status, ["POST"]),
        r("/api/missing/{scope}/{row_id:int}/restore", missing_restore, ["POST"]),
        r("/api/acquisition/deezer", acquisition_status, ["GET"]),
        r("/api/acquisition/deezer/search", acquisition_deezer_search, ["GET"]),
        r("/api/acquisition/deezer/arl", acquisition_arl_set, ["PUT"]),
        r("/api/acquisition/deezer/arl", acquisition_arl_delete, ["DELETE"]),
        r(
            "/api/acquisition/component/install",
            acquisition_component_install,
            ["POST"],
        ),
        r("/api/acquisition/jobs", acquisition_job_start, ["POST"]),
        r("/api/acquisition/jobs", acquisition_jobs_list, ["GET"]),
        r("/api/acquisition/jobs/batch", acquisition_jobs_batch, ["POST"]),
        r("/api/acquisition/jobs/{job_id:int}", acquisition_job_get, ["GET"]),
        r(
            "/api/acquisition/storage-migration",
            acquisition_storage_migration,
            ["GET", "POST"],
        ),
        r("/api/duplicates/scan", duplicates_scan, ["POST"]),
        r("/api/duplicates/resolve", duplicates_resolve, ["POST"]),
        r("/api/duplicates/dismiss", duplicates_dismiss, ["POST"]),
        r("/api/untagged", untagged_list, ["GET"]),
        r("/api/untagged/patterns", untagged_patterns_list, ["GET"]),
        r("/api/untagged/patterns", untagged_patterns_add, ["POST"]),
        r(
            "/api/untagged/patterns/{pattern_id:int}",
            untagged_patterns_remove,
            ["DELETE"],
        ),
        r("/api/untagged/delete", untagged_delete, ["POST"]),
        r("/api/smartfixes/dry-run", smartfixes_dry_run, ["POST"]),
        r("/api/smartfixes/execute", smartfixes_execute, ["POST"]),
        r("/api/mytags", mytags_get, ["GET"]),
        r("/api/settings", settings_get, ["GET"]),
        r("/api/settings", settings_update, ["PUT"]),
        r("/api/settings/export", settings_export, ["POST"]),
        r("/api/settings/import", settings_import, ["POST"]),
        r("/api/data/export", data_export, ["POST"]),
        r("/api/data/import", data_import, ["POST"]),
        r("/api/readouts", readouts_get, ["GET"]),
        r("/api/doctor/backups", doctor_backups, ["GET"]),
        r("/api/doctor/backups/{name}/restore", doctor_restore, ["POST"]),
        r("/api/doctor/retention", doctor_retention, ["POST"]),
        r("/api/doctor/logs", doctor_logs, ["GET"]),
        r("/api/spotify/authorize", spotify_authorize, ["GET"]),
        r("/api/spotify/session", spotify_disconnect, ["DELETE"]),
        r("/api/spotify/playlists", spotify_playlists, ["GET"]),
        r(
            "/api/spotify/playlists/{playlist_id}/preview",
            spotify_playlist_preview,
            ["GET"],
        ),
    ]
