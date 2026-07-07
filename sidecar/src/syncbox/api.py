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

import json
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
    dedup,
    events_service,
    library_service,
    matching,
    missing_service,
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
from syncbox.rb_write import open_rekordbox, reassign_memberships, soft_delete_content
from syncbox.safety.backup import list_backups, restore_backup
from syncbox.safety.mutate import StaleSnapshotError, mutate
from syncbox.safety.paths import (
    SYNC_DIR_NAME,
    is_protected_path,
    paths_equal,
    resolve_stored_path,
    tcc_exists,
)
from syncbox.safety import process_guard
from syncbox.safety.process_guard import MutationBlockedError
from syncbox.server import JobBus, create_app
from syncbox.settings import Settings, validate_directory
from syncbox.spotify import NotConnectedError, SpotifyApiError

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
        cache=None,
        log_path=None,
    ):
        self.conn = conn
        self.settings = Settings(conn)
        self.bus = bus if bus is not None else JobBus()
        self.spotify_auth = spotify_auth
        self.spotify_client = spotify_client
        self.log_path = log_path
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


def build_app(deps: Deps, *, oauth_callback=None):
    """Assemble the full sidecar app: transport routes (server.create_app)
    plus the REST routes below, sharing one JobBus."""
    if oauth_callback is None and deps.spotify_auth is not None:
        oauth_callback = deps.spotify_auth.handle_callback
    app = create_app(bus=deps.bus, oauth_callback=oauth_callback, routes=routes(deps))
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
    if isinstance(exc, KeyError):
        message = str(exc.args[0]) if exc.args else "not found"
        return JSONResponse({"error": "not_found", "message": message}, status_code=404)
    if isinstance(exc, FileNotFoundError):
        return JSONResponse({"error": "not_found", "message": str(exc)}, status_code=404)
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
    from the worker thread back into the running loop via anyio.from_thread
    (the shim the server-side JobBus ponytail note planned for M3).
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
    """Spotify metadata resolver for event track additions (11.1)."""
    client = deps.spotify_client
    if client is None:
        raise NotConnectedError("no Spotify client configured")

    def resolve(spotify_track_id: str):
        payload = client.get(f"/tracks/{spotify_track_id}")
        # Reuse the library mapper so D20 (external_ids.isrc ONLY, never the
        # barcode tag) lives in exactly one place.
        return library_service._spotify_track({"track": payload})

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
        deps.conn, client, deps.cache(), deps.storage_root, source,
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
                deps.conn, client, deps.cache(), deps.storage_root, source,
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
            if query in (t["title"] or "").lower() or query in (t["artist"] or "").lower()
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
        except Exception:  # ponytail: optional enrichment, never load-bearing
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
    return {
        "rb_open": process_guard.is_rekordbox_running(),
        "spotify_connected": connected,
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
        deps.cache().get(deps.storage_root),
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
        deps.cache().get(deps.storage_root),
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
    counts = {
        row["event_id"]: row
        for row in deps.conn.execute(
            "SELECT event_id, COUNT(*) AS n_tracks, "
            "SUM(added_after_apply) AS pending_delta "
            "FROM event_tracks GROUP BY event_id"
        )
    }
    out = []
    for event in events_service.list_events(deps.conn):
        row = counts.get(event["id"])
        out.append(
            {
                **event,
                "n_tracks": row["n_tracks"] if row else 0,
                # 11.2 badge: N additions waiting for a re-apply.
                "pending_delta": (row["pending_delta"] or 0) if row else 0,
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
    return 201, track


def events_track_remove(deps, request, body):
    """Owner-approved 2026-07-07: remove a NOT-YET-IMPORTED track row from an
    event (a mispasted link must not stay 'missing' forever). App-DB only —
    an 'imported' row lives in Rekordbox and belongs to delete/reapply."""
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
    if row["status"] == "imported":
        raise ConflictError(
            "an imported track is in Rekordbox; the event delete/reapply "
            "flows own that transition"
        )
    deps.conn.execute("DELETE FROM event_tracks WHERE id = ?", (track_id,))
    return {"removed": track_id}


def events_match(deps, request, body):
    event = _get_event(deps, request.path_params["event_id"])
    _require_rekordbox(deps)
    tracks = events_service.match_event_tracks(
        deps.conn, event, deps.cache(), deps.storage_root,
        **_matching_thresholds(deps),
    )
    return {"tracks": tracks}


def events_claim(deps, request, body):
    event = _get_event(deps, request.path_params["event_id"])
    return {"claimed": events_service.claim_staged_files(deps.conn, event)}


def _events_apply(deps, request, *, only_delta: bool):
    event = _get_event(deps, request.path_params["event_id"])
    _require_rekordbox(deps)
    progress = _Progress(
        deps.bus, "events.reapply" if only_delta else "events.apply"
    )
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
    """dry_run defaults to TRUE: the destructive call must be explicit and
    its confirmation text reflects the exact executed payload (D11/D23, B10)."""
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
        consent_to_permanent_delete=bool(body.get("consent_to_permanent_delete")),
        retention=deps.retention,
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
    if row["protected"]:
        raise ConflictError(f"protected tracks are never deleted (5.4): {content_id}")
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
    )
    return {"content_id": request.path_params["content_id"], "stored_path": stored}


# --- duplicates (5.4, A3 per 5.12) ---------------------------------------------------


def duplicates_scan(deps, request, body):
    """Dedup scan: groups from the snapshot, quality verdicts computed ON
    DEMAND for group members ONLY and never persisted (5.12), keeper
    suggested with its D6 reason. Progress = members analyzed (real units)."""
    _require_rekordbox(deps)
    cache = deps.cache()
    rows = cache.get(deps.storage_root)
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
    # Owner amendment to 5.4 (2026-07-07): loser files in the protected zone
    # are resolvable like any other — the per-group confirmation is the
    # consent, and the file goes through the same trash-first contract below
    # (permanent delete still requires the 428 consent). The keeper's file
    # remains untouchable either way.

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
                {"content_id": loser, "path": str(resolved), "result": "kept_keeper_file"}
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
    """D15: the protected guard applies with a REAL skip report - protected
    (and stale not-found/now-tagged) rows are skipped and reported, never
    silently dropped. Soft-delete only: reversible via backup + reactivate
    (D21). ponytail: no audio file deletion here - 5.8 asks for collection
    removal; wire the 6.9 trash contract in if a real DJ asks for it."""
    _require_rekordbox(deps)
    content_ids = [str(c) for c in _require_list(body, "content_ids")]
    cache = deps.cache()
    by_id = {row["content_id"]: row for row in cache.get(deps.storage_root)}
    deletable, skipped = [], []
    for content_id in content_ids:
        row = by_id.get(content_id)
        if row is None:
            skipped.append({"content_id": content_id, "reason": "not_found"})
        elif row["protected"]:
            skipped.append({"content_id": content_id, "reason": "protected"})
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
    )


# --- settings (5.10) -----------------------------------------------------------------


def settings_get(deps, request, body):
    return deps.settings.all()


def settings_update(deps, request, body):
    # F15: validate BOTH configured paths before persisting anything; an
    # empty value stays allowed (it means 'not configured yet').
    storage_root = body.get("storage_root")
    if storage_root:
        ok, why = validate_directory(storage_root)
        if not ok:
            raise ValueError(f"storage_root: {why}")
    db_path = body.get("rekordbox_db_path")
    if db_path:
        expanded = Path(db_path).expanduser()
        ok, why = validate_directory(str(expanded.parent))
        if not ok:
            raise ValueError(f"rekordbox_db_path: parent folder {why}")
        if not expanded.is_file():
            raise ValueError("rekordbox_db_path: not found")
    try:
        return deps.settings.update(body)
    except KeyError as exc:
        raise ValueError(str(exc.args[0])) from exc


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


# --- doctor (5.10/F9) ----------------------------------------------------------------


def doctor_backups(deps, request, body):
    _require_storage(deps)
    return {"backups": list_backups(deps.backups_root)}


def doctor_restore(deps, request, body):
    _require_rekordbox(deps)
    name = request.path_params["name"]
    snapshot = restore_backup(name, deps.backups_root, deps.db_path)
    deps.cache().invalidate()  # the restored DB is a different snapshot
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


_PLAYLISTS_MAX_PAGES = 20  # ponytail: 50/page = 1000 playlists; raise if a real DJ overflows


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
            playlists.append(
                {
                    "spotify_playlist_id": item["id"],
                    "name": item.get("name") or "",
                    "owner": (item.get("owner") or {}).get("display_name"),
                    "tracks_total": (item.get("tracks") or {}).get("total") or 0,
                    "image_url": images[0]["url"] if images else None,
                }
            )
        url = payload.get("next")  # absolute URL; SpotifyClient.get accepts it
        if not url:
            break
    return {"playlists": playlists}


def spotify_authorize(deps, request, body):
    if deps.spotify_auth is None:
        return 503, {"error": "oauth not configured"}
    return {"url": deps.spotify_auth.begin_authorization()}


def spotify_playlist_preview(deps, request, body):
    """G5: read-only playlist preview for AddSourceModal, resolved BEFORE
    following. 409 spotify_not_connected / 502 spotify_api_error map
    automatically (404 = private playlist, actionable)."""
    client = _sync_client(deps)
    playlist_id = request.path_params["playlist_id"]
    payload = client.get(
        f"/playlists/{playlist_id}"
        "?fields=name,owner(display_name),tracks(total),images(url)"
    )
    images = payload.get("images") or []
    return {
        "name": payload.get("name"),
        "owner": (payload.get("owner") or {}).get("display_name"),
        "tracks_total": (payload.get("tracks") or {}).get("total") or 0,
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
        r("/api/missing/collection/{content_id}/relink", missing_relink, ["POST"]),
        r("/api/missing/collection/{content_id}/remove", missing_remove, ["POST"]),
        r("/api/missing/{scope}", missing_list, ["GET"]),
        r("/api/missing/{scope}/{row_id:int}/status", missing_status, ["POST"]),
        r("/api/missing/{scope}/{row_id:int}/restore", missing_restore, ["POST"]),
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
        r("/api/readouts", readouts_get, ["GET"]),
        r("/api/doctor/backups", doctor_backups, ["GET"]),
        r("/api/doctor/backups/{name}/restore", doctor_restore, ["POST"]),
        r("/api/doctor/retention", doctor_retention, ["POST"]),
        r("/api/doctor/logs", doctor_logs, ["GET"]),
        r("/api/spotify/authorize", spotify_authorize, ["GET"]),
        r("/api/spotify/playlists", spotify_playlists, ["GET"]),
        r(
            "/api/spotify/playlists/{playlist_id}/preview",
            spotify_playlist_preview,
            ["GET"],
        ),
    ]
