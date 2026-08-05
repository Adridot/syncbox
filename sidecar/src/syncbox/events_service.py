"""Events service: temporary imports around one gig (SPEC-UNIFIED 5.7 +
11.1/11.2, SPEC-01 1.8).

Legal scope (SPEC-UNIFIED 6.5/11.1): event tracks come from Spotify
METADATA (an injected resolver over the read-only Spotify API), manual
title/artist entry, audio files the user already lawfully owns, or the
separately enabled optional acquisition component. This module contains
no provider credentials or download implementation.

Write-path discipline: every master.db write below goes through
safety.mutate() + rb_write helpers (3.1: no escape hatch); previews and
matching read through rb.SnapshotCache / rb.open_readonly only.
"""

import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from syncbox import event_delete, relink
from syncbox.matching import match
from syncbox.rb_write import (
    add_content,
    create_or_repair_smart_playlist,
    ensure_playlist_folder,
    find_active_content_by_path,
    find_or_create_mytag,
    open_rekordbox,
    tag_content,
)
from syncbox.safety.mutate import mutate
from syncbox.safety.paths import SYNC_DIR_NAME, stored_form
from syncbox.staging import reclassify_stale_ready

EVENT_FOLDER_NAME = "Event Imports"
SITUATION_CATEGORY = "Situation"
XML_NAME = "masterPlaylists6.xml"
# SPEC-UNIFIED 11.2: applied when none of these remain, else partially_applied.
PENDING_STATUSES = frozenset(
    {"matched", "ready", "missing", "ambiguous", "acquisition_failed"}
)
APPLIED_EVENT_STATUSES = frozenset({"applied", "partially_applied"})
# Statuses re-run through the matcher; ready/applied/ignored are never
# re-matched (a staged or already-applied track must not flip back).
REMATCHED_STATUSES = frozenset(
    {"missing", "ambiguous", "matched", "acquisition_failed"}
)
CLAIMABLE_STATUSES = frozenset({"missing", "acquisition_failed"})

_SLUG_JUNK = re.compile(r"[^a-z0-9]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _isrc(value) -> str:
    return (value or "").strip().upper()


def slugify(name: str) -> str:
    """ASCII slug: NFKD-folded, lowercase, non-alphanumerics collapsed to '-'."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    text = _SLUG_JUNK.sub("-", text.lower()).strip("-")
    return text or "event"


def get_event(conn, event_id) -> dict | None:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return dict(row) if row is not None else None


def list_events(conn) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY id")]


def list_event_tracks(conn, event_id) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM event_tracks WHERE event_id = ? ORDER BY id", (event_id,)
        )
    ]


# --- creation (5.7: 3 modes - from playlist / empty / link or manual entry) ------


def create_event(conn, storage_root, name, *, spotify_playlist_id=None, manual=False):
    """Create an event with its staging dir claimed ATOMICALLY.

    Modes (5.7/11.1): from a followed playlist or a Spotify link (the API
    layer resolves the link to ``spotify_playlist_id``), or empty/manual
    metadata entry (no playlist -> identity 'manual:<slug>'). The staging
    dir <storage_root>/<SYNC_DIR_NAME>/events/<slug> is claimed with
    mkdir(exist_ok=False); slug collision walks '-2', '-3', ...
    """
    if manual and spotify_playlist_id:
        raise ValueError("a manual event cannot also carry a spotify_playlist_id")
    events_root = (
        Path(os.path.expanduser(os.fspath(storage_root))) / SYNC_DIR_NAME / "events"
    )
    events_root.mkdir(parents=True, exist_ok=True)
    base = slugify(name)
    suffix = 1
    while True:
        slug = base if suffix == 1 else f"{base}-{suffix}"
        suffix += 1
        staging = events_root / slug
        try:
            staging.mkdir(exist_ok=False)  # the atomic slug claim (5.7)
        except FileExistsError:
            continue
        audio_dir = staging / "audio"
        try:
            audio_dir.mkdir()
            cur = conn.execute(
                "INSERT INTO events (name, slug, default_tag,"
                " spotify_playlist_id, staging_dir, status)"
                " VALUES (?, ?, ?, ?, ?, 'pending')",
                (
                    name,
                    slug,
                    name,  # default_tag = event name, category 'Situation' (4/5.7)
                    spotify_playlist_id or f"manual:{slug}",
                    str(staging),
                ),
            )
        except sqlite3.IntegrityError:
            # A DB row holds this slug but its dir was gone (user deleted it
            # by hand): release the freshly claimed dir and walk on.
            audio_dir.rmdir()
            staging.rmdir()
            continue
        except BaseException:
            if audio_dir.is_dir():
                audio_dir.rmdir()
            staging.rmdir()
            raise
        return get_event(conn, cur.lastrowid)


# --- track additions (11.1/11.2) ---------------------------------------------------


def add_track(
    conn, event, *, spotify_track_id=None, resolver=None, title=None, artist=None
) -> dict:
    """Add a track: Spotify metadata via the injected ``resolver`` callable
    (the API layer wires SpotifyClient - 11.1), or manual {title, artist}.

    On an applied/partially_applied event the row is flagged
    ``added_after_apply`` (the 11.2 delta) - additions are NEVER blocked.
    """
    event = get_event(conn, event["id"])
    if spotify_track_id is not None:
        if resolver is None:
            raise ValueError("spotify_track_id requires a resolver callable")
        meta = resolver(spotify_track_id) or {}
    else:
        if not title:
            raise ValueError("manual entry requires at least a title")
        meta = {"title": title, "artist": artist}
    delta = 1 if event["status"] in APPLIED_EVENT_STATUSES else 0
    cur = conn.execute(
        "INSERT INTO event_tracks (event_id, spotify_track_id, title, artist,"
        " duration_ms, isrc, status, added_after_apply, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'missing', ?, ?)",
        (
            event["id"],
            spotify_track_id,
            meta.get("title"),
            meta.get("artist"),
            meta.get("duration_ms"),
            meta.get("isrc"),
            delta,
            _now(),
        ),
    )
    row = conn.execute(
        "SELECT * FROM event_tracks WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


# --- matching (5.7 event flavor) ---------------------------------------------------


def match_event_tracks(conn, event, cache, storage_root, **thresholds) -> list[dict]:
    """Run the 5.3 matcher over the event's pending tracks.

    Event flavor (5.7): 'ambiguous' STAYS 'ambiguous' (never the library
    'conflict'), and NO default tag is attached to tracks - the event tag
    is applied to CONTENT at apply time only. ``thresholds`` are the G4
    matching knobs, forwarded verbatim to matching.match.
    """
    # streaming references can never be the local file a track needs
    candidates = [
        r for r in cache.get(storage_root) if not r.get("spotify_track_id")
    ]
    now = _now()
    out = []
    for track in list_event_tracks(conn, event["id"]):
        if track["status"] not in REMATCHED_STATUSES:
            out.append(track)
            continue
        result = match(
            {
                "title": track["title"],
                "artist": track["artist"],
                "duration_ms": track["duration_ms"],
                "isrc": track["isrc"],
            },
            candidates,
            **thresholds,
        )
        conn.execute(
            "UPDATE event_tracks SET status = ?, content_id = ?, confidence = ?,"
            " updated_at = ? WHERE id = ?",
            (result.status, result.content_id, result.confidence, now, track["id"]),
        )
        out.append(
            {
                **track,
                "status": result.status,
                "content_id": result.content_id,
                "confidence": result.confidence,
            }
        )
    return out


# --- staging claims (5.7 claim rule) -----------------------------------------------


def claim_staged_files(conn, event) -> list[dict]:
    """Scan the staging dir (bounded, relink.iter_audio_files) and claim
    files for 'missing' tracks -> staging_file_path + status 'ready'.

    Claim rule (5.7): one staged file may be shared by two event tracks
    ONLY when both carry the SAME non-empty ISRC; otherwise first claimant
    (by row id, deterministic) wins and the other track stays 'missing'.
    """
    staging = Path(event["staging_dir"]) if event["staging_dir"] else None
    if staging is None or not staging.is_dir():
        return []
    tracks = list_event_tracks(conn, event["id"])
    # path -> ISRC of the claiming track ('' = unshareable claim).
    claims: dict[str, str] = {}
    for track in tracks:
        if track["staging_file_path"]:
            claims.setdefault(track["staging_file_path"], _isrc(track["isrc"]))
    files = sorted(relink.iter_audio_files([staging]))
    now = _now()
    claimed = []
    for track in tracks:
        if track["status"] not in CLAIMABLE_STATUSES:
            continue
        want = {
            "title": track["title"],
            "artist": track["artist"],
            "isrc": track["isrc"],
        }
        scored = sorted(
            ((relink.score_candidate(want, path), str(path)) for path in files),
            key=lambda pair: (-pair[0], pair[1]),
        )
        isrc = _isrc(track["isrc"])
        for score, path in scored:
            if score <= 0:
                break  # sorted desc: nothing scorable remains
            holder = claims.get(path)
            if holder is not None and not (isrc and holder == isrc):
                continue  # held by a different/empty-ISRC track: not shareable
            claims.setdefault(path, isrc)
            conn.execute(
                "UPDATE event_tracks SET staging_file_path = ?, status = 'ready',"
                " confidence = ?, updated_at = ? WHERE id = ?",
                (path, score, now, track["id"]),
            )
            claimed.append(
                {
                    **track,
                    "staging_file_path": path,
                    "status": "ready",
                    "confidence": score,
                }
            )
            break
    return claimed


# --- apply (5.7 + 11.2 delta reapply) ----------------------------------------------


def recompute_event_status(statuses) -> str:
    """11.2: 'applied' when no matched/ready/missing/ambiguous remain."""
    if any(status in PENDING_STATUSES for status in statuses):
        return "partially_applied"
    return "applied"


def _xml_snapshot(db_path: Path, staging_dir):
    """Snapshot masterPlaylists6.xml (next to master.db) BEFORE mutating.

    pyrekordbox rewrites the xml at commit; Rekordbox itself reconciles it
    from the db (POC 05: real-world fixture drift proves it is not
    load-bearing), so the byte-identical restore after commit is safe. The
    on-disk .bak inside the staging dir only covers the crash window
    between commit and restore; event delete cleans it up (T8/T12).
    """
    xml_path = Path(db_path).with_name(XML_NAME)
    if not xml_path.exists():
        return xml_path, None
    data = xml_path.read_bytes()
    staging = Path(staging_dir) if staging_dir else None
    if staging is not None and staging.is_dir():
        (staging / (XML_NAME + ".bak")).write_bytes(data)
    return xml_path, data


def apply_event(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    event,
    *,
    only_delta=False,
    retention: int = 20,
    app_db_path=None,
) -> dict:
    """Apply the event inside ONE mutate() unit-of-work (5.7, 11.2).

    matched -> tag the existing content; ready -> create a new content row
    from the staged file (rb_write.add_content) then tag it - unless an
    active row for that staged path already exists (a retry after a
    post-commit crash reuses it, never duplicates); applied tracks reset
    their 11.2 delta flag.

    The 11.2 delta IS the matched/ready set: an applied row leaves it
    (status 'applied'), so a reapply naturally picks up BOTH rows added
    after the apply and rows that became matched/ready after it (owner bug
    report 2026-07-07: a track matched post-apply must be reappliable).
    ``only_delta`` only tightens the no-op check; reapply with nothing
    applicable is a strict no-op checked BEFORE mutate() so no backup is
    wasted.
    """
    event = get_event(conn, event["id"])
    db_path = Path(db_path)
    tracks = list_event_tracks(conn, event["id"])
    applicable = [t for t in tracks if t["status"] in ("matched", "ready")]
    # staged-file-integrity: a 'ready' track whose staged file vanished is
    # reclassified 'missing' + excluded BEFORE any Rekordbox write; the rest
    # applies normally (no FileNotFoundError, no rollback). Event status is
    # unaffected by the reclassification itself: ready and missing are both
    # pending (11.2).
    reclassified = [t["id"] for t in reclassify_stale_ready(conn, "event_tracks", applicable)]
    applicable = [t for t in applicable if t["status"] in ("matched", "ready")]
    if not applicable and (only_delta or event["status"] in APPLIED_EVENT_STATUSES):
        return {
            "noop": True,
            "applied": 0,
            "event_status": event["status"],
            "reclassified_missing": reclassified,
        }

    xml_path, xml_bytes = _xml_snapshot(db_path, event["staging_dir"])
    applied: list[tuple[int, str]] = []
    with mutate(
        db_path,
        backups_root,
        retention=retention,
        # Freshness guard when the snapshot that produced the matches is
        # known; None (cache never read / invalidated) skips the guard.
        expected_fingerprint=cache.current_fingerprint,
        open_db=open_rekordbox,
        invalidate_cache=cache.invalidate,
        app_db_path=app_db_path,
        backup_reason="event_reapply" if only_delta else "event_apply",
    ) as db:
        tag = find_or_create_mytag(db, event["default_tag"], SITUATION_CATEGORY)
        folder = ensure_playlist_folder(db, EVENT_FOLDER_NAME)
        # REPAIR path on reapply - never a duplicate (5.7/11.2).
        playlist = create_or_repair_smart_playlist(db, event["name"], folder.ID, tag.ID)
        tag_id, playlist_id = str(tag.ID), str(playlist.ID)
        for track in applicable:
            if track["status"] == "ready":
                # Crash-window retry guard: a failure AFTER the durable
                # master.db commit (xml restore, app-DB update, crash) leaves
                # this row 'ready'; the retry must REUSE the content row the
                # first commit created, never add a duplicate.
                stored = stored_form(track["staging_file_path"], storage_root)
                existing = find_active_content_by_path(db, stored)
                if existing is not None:
                    content_id = str(existing.ID)
                else:
                    content = add_content(
                        db,
                        track["staging_file_path"],
                        {
                            "title": track["title"],
                            "artist": track["artist"],
                            "duration_ms": track["duration_ms"],
                            "isrc": track["isrc"],
                        },
                        storage_root=storage_root,
                    )
                    content_id = str(content.ID)
            else:
                content_id = str(track["content_id"])
            tag_content(db, content_id, tag_id)  # the event tag - nothing else (5.7)
            applied.append((track["id"], content_id))
    if xml_bytes is not None:
        xml_path.write_bytes(xml_bytes)  # byte-identical restore (SPEC-01 1.6)

    now = _now()
    conn.execute("BEGIN")
    try:
        for track_id, content_id in applied:
            conn.execute(
                "UPDATE event_tracks SET status = 'applied', content_id = ?,"
                " added_after_apply = 0, updated_at = ? WHERE id = ?",
                (content_id, now, track_id),
            )
        statuses = [
            row["status"]
            for row in conn.execute(
                "SELECT status FROM event_tracks WHERE event_id = ?", (event["id"],)
            )
        ]
        event_status = recompute_event_status(statuses)
        conn.execute(
            "UPDATE events SET status = ?, applied_at = ? WHERE id = ?",
            (event_status, now, event["id"]),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {
        "noop": False,
        "applied": len(applied),
        "event_status": event_status,
        "tag_id": tag_id,
        "playlist_id": playlist_id,
        "reclassified_missing": reclassified,
    }


# --- exact delete planning and retained-track migration ----------------------------


def _staging_files(staging_dir, cap: int = 10_000) -> list[Path]:
    return event_delete._staging_files(staging_dir, cap=cap)


def _delete_preview(query, event, storage_root, db_path, db_fingerprint) -> dict:
    return event_delete.build_plan(query, event, storage_root, db_path, db_fingerprint)


def delete_event(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    event,
    *,
    dry_run: bool = True,
    plan=None,
    consent_to_permanent_delete: bool = False,
    retention: int = 20,
    app_db_path=None,
) -> dict:
    return event_delete.delete_event(
        conn,
        db_path,
        backups_root,
        cache,
        storage_root,
        event,
        dry_run=dry_run,
        plan=plan,
        consent_to_permanent_delete=consent_to_permanent_delete,
        retention=retention,
        app_db_path=app_db_path,
    )
