"""Events service: temporary imports around one gig (SPEC-UNIFIED 5.7 +
11.1/11.2, SPEC-01 1.8).

Legal scope (SPEC-UNIFIED 6.5/11.1): event tracks come from Spotify
METADATA (an injected resolver over the read-only Spotify API), manual
title/artist entry, or audio files the user already lawfully owns and
drops into the event staging dir. No download code, no provider
credential, no acquisition job - the staging dir is filled by the USER.

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

from syncbox import relink
from syncbox.matching import match
from syncbox.platform_os import delete_file
from syncbox.rb import open_readonly
from syncbox.rb_write import (
    add_content,
    create_or_repair_smart_playlist,
    ensure_playlist_folder,
    find_active_content_by_path,
    find_or_create_mytag,
    open_rekordbox,
    soft_delete_content,
    soft_delete_mytag,
    soft_delete_playlist,
    tag_content,
    untag_content,
)
from syncbox.safety.mutate import mutate
from syncbox.safety.paths import is_protected_path, stored_form

EVENT_FOLDER_NAME = "Event Imports"
SITUATION_CATEGORY = "Situation"
XML_NAME = "masterPlaylists6.xml"
# SPEC-UNIFIED 11.2: applied when none of these remain, else partially_applied.
PENDING_STATUSES = frozenset({"matched", "ready", "missing", "ambiguous"})
APPLIED_EVENT_STATUSES = frozenset({"applied", "partially_applied"})
# Statuses re-run through the matcher; ready/applied/ignored are never
# re-matched (a staged or already-applied track must not flip back).
REMATCHED_STATUSES = frozenset({"missing", "ambiguous", "matched"})

_SLUG_JUNK = re.compile(r"[^a-z0-9]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _isrc(value) -> str:
    return (value or "").strip().upper()


def slugify(name: str) -> str:
    """ASCII slug: NFKD-folded, lowercase, non-alphanumerics collapsed to '-'."""
    text = (
        unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    )
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
    dir <storage_root>/_rekordbox_sync/events/<slug> is claimed with
    mkdir(exist_ok=False); slug collision walks '-2', '-3', ...
    """
    if manual and spotify_playlist_id:
        raise ValueError("a manual event cannot also carry a spotify_playlist_id")
    events_root = (
        Path(os.path.expanduser(os.fspath(storage_root)))
        / "_rekordbox_sync"
        / "events"
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
        try:
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
            staging.rmdir()
            continue
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
    candidates = cache.get(storage_root)
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
        if track["status"] != "missing":
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
    from the db (poc/05: real-world fixture drift proves it is not
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
    retention: int = 15,
) -> dict:
    """Apply the event inside ONE mutate() unit-of-work (5.7, 11.2).

    matched -> tag the existing content; ready -> create a new content row
    from the staged file (rb_write.add_content) then tag it - unless an
    active row for that staged path already exists (a retry after a
    post-commit crash reuses it, never duplicates); applied tracks reset
    their 11.2 delta flag. ``only_delta`` restricts to added_after_apply
    rows; reapply with no delta is a strict no-op checked BEFORE mutate()
    so no backup is wasted.
    """
    event = get_event(conn, event["id"])
    db_path = Path(db_path)
    tracks = list_event_tracks(conn, event["id"])
    applicable = [
        t
        for t in tracks
        if t["status"] in ("matched", "ready")
        and (not only_delta or t["added_after_apply"])
    ]
    if not applicable and (only_delta or event["status"] in APPLIED_EVENT_STATUSES):
        return {"noop": True, "applied": 0, "event_status": event["status"]}

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
    }


# --- delete (SPEC-01 1.8, D11/D23, T8/T12) -----------------------------------------

# One SQL text per question, shared verbatim by the dry-run executor
# (rb.open_readonly, named params) and the in-mutation executor
# (sqlalchemy text() on the same session) so the two previews can never
# diverge.
_TAG_SQL = """
SELECT t.ID FROM djmdMyTag t JOIN djmdMyTag c ON c.ID = t.ParentID
WHERE t.Name = :tag AND c.Name = :category AND c.ParentID = 'root'
  AND t.rb_local_deleted = 0
"""
_TAGGED_SQL = """
SELECT c.ID, c.Title, c.FolderPath FROM djmdSongMyTag l
JOIN djmdContent c ON c.ID = l.ContentID
WHERE l.MyTagID = :tag_id AND l.rb_local_deleted = 0 AND c.rb_local_deleted = 0
ORDER BY c.ID
"""
_OTHER_TAGS_SQL = """
SELECT COUNT(*) FROM djmdSongMyTag
WHERE ContentID = :content_id AND MyTagID != :tag_id AND rb_local_deleted = 0
"""
_PLAYLISTS_SQL = """
SELECT ID, Name FROM djmdPlaylist
WHERE Name IN (:name, :legacy) AND Attribute != 1 AND rb_local_deleted = 0
ORDER BY ID
"""


def _staging_files(staging_dir, cap: int = 10_000) -> list[Path]:
    files = []
    for count, path in enumerate(Path(staging_dir).rglob("*")):
        if count >= cap:
            break  # ponytail: staging dirs are app-managed and small; the cap
            # only guards a runaway symlinked tree. Raise it if a real event
            # ever legitimately holds more files.
        if path.is_file():
            files.append(path)
    return sorted(files)


def _delete_preview(query, event, storage_root) -> dict:
    """The exact delete payload (SPEC-01 1.8). ``query(sql, params)`` is the
    executor seam: read-only connection for dry-run, the LIVE mutation
    session for the real delete (reading .Title after commit detaches).

    Protection: a content survives when it carries any OTHER active MyTag
    (superset of the 1.8 'another non-event MyTag' rule - cross-event
    shares survive too, strictly safer) OR its path is under the protected
    zone. Only event-only, unprotected contents are soft-deleted.
    """
    # ponytail: protection counts ANY other tag instead of classifying
    # non-event categories - deletes a strict subset of what 1.8 allows,
    # never more. Ceiling: a content tagged ONLY by two events outlives
    # both deletes (harmless leftover, reversible). Upgrade path: join the
    # tag's ParentID category and exempt 'Situation' if that leftover ever
    # bothers a real user.
    tag_rows = query(
        _TAG_SQL, {"tag": event["default_tag"], "category": SITUATION_CATEGORY}
    )
    tag_id = str(tag_rows[0][0]) if tag_rows else None
    contents = []
    if tag_id is not None:
        for content_id, title, folder_path in query(_TAGGED_SQL, {"tag_id": tag_id}):
            content_id = str(content_id)
            other_tags = query(
                _OTHER_TAGS_SQL, {"content_id": content_id, "tag_id": tag_id}
            )[0][0]
            if other_tags:
                action, reason = "keep", "carries_other_mytag"
            elif folder_path and is_protected_path(folder_path, storage_root):
                action, reason = "keep", "protected_path"
            else:
                action, reason = "soft_delete", "event_only"
            contents.append(
                {
                    "content_id": content_id,
                    "title": title,
                    "action": action,
                    "reason": reason,
                }
            )
    playlists = [
        {"playlist_id": str(playlist_id), "name": name}
        for playlist_id, name in query(
            _PLAYLISTS_SQL,
            # Clean by current name AND legacy '<name> - Smart' (1.8).
            {"name": event["name"], "legacy": f"{event['name']} - Smart"},
        )
    ]
    staging = Path(event["staging_dir"]) if event["staging_dir"] else None
    artifacts = (
        [str(path) for path in _staging_files(staging)]
        if staging is not None and staging.is_dir()
        else []
    )
    return {
        "tag_id": tag_id,
        "contents": contents,
        "playlists": playlists,
        "artifacts": artifacts,
    }


def _cleanup_staging(staging_dir, *, consent: bool) -> list[str]:
    """Remove the event's disk artifacts AFTER a successful commit only
    (T8/T12: no orphans, never a premature deletion). Files go through
    platform_os.delete_file (OS trash first, permanent only with consent);
    directories are removed with rmdir only - a file that appeared
    concurrently survives rather than being silently destroyed.
    """
    staging = Path(staging_dir)
    if not staging.is_dir():
        return []
    removed = []
    for path in _staging_files(staging):
        delete_file(path, consent_to_permanent_delete=consent)
        removed.append(str(path))
    for folder in sorted(
        (p for p in staging.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            folder.rmdir()
        except OSError:
            pass
    try:
        staging.rmdir()
    except OSError:
        pass
    return removed


def delete_event(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    event,
    *,
    dry_run: bool = True,
    consent_to_permanent_delete: bool = False,
    retention: int = 15,
) -> dict:
    """Delete an event. dry_run=True returns the EXACT preview payload with
    zero writes (read-only connection - no backup, no RB-closed guard);
    the real delete recomputes that preview INSIDE the mutation session
    (SPEC-01 1.8) and executes exactly it, then - only after the durable
    commit - removes the disk artifacts and the app-db rows.
    """
    event = get_event(conn, event["id"])
    db_path = Path(db_path)

    ro = open_readonly(db_path)
    try:

        def ro_query(sql, params):
            return ro.execute(sql, params).fetchall()

        preview = _delete_preview(ro_query, event, storage_root)
    finally:
        ro.close()
    if dry_run:
        return {"dry_run": True, **preview}

    if preview["tag_id"] is not None or preview["playlists"]:
        xml_path, xml_bytes = _xml_snapshot(db_path, event["staging_dir"])
        with mutate(
            db_path,
            backups_root,
            retention=retention,
            open_db=open_rekordbox,
            invalidate_cache=cache.invalidate,
        ) as db:
            from sqlalchemy import text

            def live_query(sql, params):
                return db.session.execute(text(sql), params).all()

            # SPEC-01 1.8: the executed payload is the preview computed
            # INSIDE this session, not the read-only one above.
            preview = _delete_preview(live_query, event, storage_root)
            tag_id = preview["tag_id"]
            if tag_id is not None:
                for entry in preview["contents"]:
                    untag_content(db, entry["content_id"], tag_id)
                    if entry["action"] == "soft_delete":
                        soft_delete_content(db, entry["content_id"])
                soft_delete_mytag(db, tag_id)
            for playlist in preview["playlists"]:
                soft_delete_playlist(db, playlist["playlist_id"])
        if xml_bytes is not None:
            xml_path.write_bytes(xml_bytes)  # byte-identical restore (1.6)
    # Disk artifacts strictly AFTER the durable commit (T8/T12); the re-scan
    # is deliberate so the fresh .xml.bak written above is cleaned too.
    removed = (
        _cleanup_staging(event["staging_dir"], consent=consent_to_permanent_delete)
        if event["staging_dir"]
        else []
    )
    conn.execute("DELETE FROM events WHERE id = ?", (event["id"],))
    return {"dry_run": False, "removed_files": removed, **preview}
