"""Previewed repair of exact-source event rows whose download duplicates an
ISRC-equal collection content (reconcile-deezer-event-tracks-by-isrc).

Sibling of acquisition_migration: build_plan only reads, execute requires
the identical plan. One action per row:

- rematch: a 'ready' download duplicates one collection content. The
  download is trashed FIRST, then the row is matched to that content; no
  Rekordbox write, and a refused trash leaves row and file unchanged.
- replace: an 'applied' row whose Rekordbox content IS its download. One
  mutate() moves the event tag to the original and soft-deletes the
  duplicate, the row is repointed, then the download is trashed.
- cleanup: a replace whose download is still on disk (trash refused after
  the commit). The row keeps referencing the file until it is gone, so the
  staged-file adoption never picks it up again.

A PermanentDeleteConsentRequired is raised (428) only while nothing has
changed yet, so the client's consent retry with the same plan is exact.
After that, a refused trash is reported as cleanup_pending and the next
preview offers it as a cleanup item.
"""

from __future__ import annotations

import re
from pathlib import Path

from syncbox.event_delete import (
    _OTHER_TAGS_SQL,
    _TAG_SQL,
    EventMigrationError,
    _file_state,
    _fingerprint_tuple,
    _inside_staging,
    _serial_fingerprint,
    event_staging,
)
from syncbox.events_service import SITUATION_CATEGORY, _now, _xml_snapshot
from syncbox.matching import _isrc, _isrc_collision
from syncbox.platform_os import PermanentDeleteConsentRequired, delete_file
from syncbox.rb import open_readonly
from syncbox.rb_write import open_rekordbox, soft_delete_content, tag_content, untag_content
from syncbox.safety.mutate import StaleSnapshotError, mutate
from syncbox.safety.paths import canonical_key
from syncbox.spotify import spotify_id_from_path

PLAN_VERSION = 1
_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_CONTENTS_SQL = (
    "SELECT ID, Title, Length, ISRC, FolderPath FROM djmdContent "
    "WHERE rb_local_deleted = 0 ORDER BY ID"
)
_LINK_SQL = (
    "SELECT 1 FROM djmdSongMyTag WHERE ContentID = :content_id "
    "AND MyTagID = :tag_id AND rb_local_deleted = 0"
)
_PLAYLIST_SQL = (
    "SELECT 1 FROM djmdSongPlaylist WHERE ContentID = :content_id AND rb_local_deleted = 0"
)


def build_plan(conn, storage_root, db_path, *, isrc_collision_policy="guarded") -> dict:
    before = _serial_fingerprint(db_path)
    ro = open_readonly(db_path)
    try:
        def query(sql, params=()):
            return ro.execute(sql, params).fetchall()

        contents, by_isrc, by_key = {}, {}, {}
        for content_id, title, length, isrc, folder_path in query(_CONTENTS_SQL):
            local = bool(folder_path) and spotify_id_from_path(folder_path) is None
            content = {
                "content_id": str(content_id),
                "title": title,
                "duration_ms": int(length * 1000) if length else 0,
                "isrc": _isrc(isrc),
                "path": folder_path,
                "key": canonical_key(folder_path, storage_root) if local else None,
            }
            contents[content["content_id"]] = content
            if content["key"]:
                by_key.setdefault(content["key"], set()).add(content["content_id"])
                if content["isrc"]:
                    by_isrc.setdefault(content["isrc"], []).append(content)

        live = [dict(row) for row in conn.execute(
            "SELECT t.*, e.name AS event_name, e.default_tag, e.staging_dir "
            "FROM event_tracks t JOIN events e ON e.id = t.event_id "
            "WHERE t.status != 'removed' AND e.delete_phase IS NULL ORDER BY t.id"
        )]
        file_holders, content_holders = {}, {}
        for row in live:
            for path in (row["staging_file_path"], row["selected_local_path"]):
                if path:
                    file_holders.setdefault(canonical_key(path, storage_root), set()).add(row["id"])
            if row["content_id"]:
                content_holders.setdefault(str(row["content_id"]), set()).add(row["id"])

        tags, stagings = {}, {}

        def event_tag(row):
            if row["event_id"] not in tags:
                found = query(_TAG_SQL, {"tag": row["default_tag"], "category": SITUATION_CATEGORY})
                tags[row["event_id"]] = str(found[0][0]) if found else None
            return tags[row["event_id"]]

        def staging_of(row):
            if row["event_id"] not in stagings:
                try:
                    stagings[row["event_id"]] = event_staging(row, storage_root)
                except EventMigrationError:
                    stagings[row["event_id"]] = None
            return stagings[row["event_id"]]

        def classify(row, isrc, file_key, candidates):
            """An item dict, or the reason the row is left alone."""
            if not isrc:
                return "missing_isrc"
            path = Path(row["staging_file_path"])
            state = _file_state(path, with_hash=True)
            if state.get("kind") != "file" or not _inside_staging(path, staging_of(row)):
                return "unsafe_file"
            if file_holders.get(file_key, set()) - {row["id"]}:
                return "file_in_use"
            on_file = by_key.get(file_key, set())  # active contents playing the download
            item = {
                "track_id": row["id"], "event_id": row["event_id"], "event_name": row["event_name"],
                "title": row["title"], "artist": row["artist"], "isrc": isrc,
                "status": row["status"], "duplicate_content_id": None, "tag_id": None, "file": state,
            }
            if row["status"] == "ready":
                if on_file:
                    return "file_in_use"
                item["action"] = "rematch"
            else:
                own = contents.get(str(row["content_id"])) if row["content_id"] else None
                if own is None:
                    return "not_a_download"
                if not on_file and own["isrc"] == isrc:
                    return {**item, "action": "cleanup", "content_id": own["content_id"]}
                if on_file != {own["content_id"]}:
                    return "not_a_download"
                tag_id = event_tag(row)
                params = {"content_id": own["content_id"], "tag_id": tag_id}
                if tag_id is None or not query(_LINK_SQL, params):
                    return "not_tagged"
                if (content_holders.get(own["content_id"], set()) - {row["id"]}
                        or query(_OTHER_TAGS_SQL, params) or query(_PLAYLIST_SQL, params)):
                    return "duplicate_in_use"
                item.update(action="replace", duplicate_content_id=own["content_id"], tag_id=tag_id)
            if not candidates:
                return "no_candidate"
            if len(candidates) > 1:
                return "ambiguous"
            if _isrc_collision(row, candidates[0], isrc_collision_policy or "guarded"):
                return "guard_rejected"
            return {**item, "content_id": candidates[0]["content_id"]}

        items, skipped = [], []
        coverage = {"rows_with_isrc": 0, "rows_without_isrc": 0, "rows_with_candidate": 0}
        odd_isrcs = sum(bool(_NON_ALNUM.search(c["isrc"])) for c in contents.values() if c["isrc"])
        for row in live:
            if row["source_provider"] not in ("deezer", "youtube", "soundcloud"):
                continue
            isrc = _isrc(row["isrc"])
            path = row["staging_file_path"]
            file_key = canonical_key(path, storage_root) if path else None
            # The row's own download is never its own candidate.
            candidates = [c for c in by_isrc.get(isrc, []) if c["key"] != file_key] if isrc else []
            coverage["rows_with_isrc" if isrc else "rows_without_isrc"] += 1
            coverage["rows_with_candidate"] += bool(candidates)
            odd_isrcs += bool(isrc and _NON_ALNUM.search(isrc))
            if row["status"] not in ("ready", "applied") or not path:
                continue
            outcome = classify(row, isrc, file_key, candidates)
            if isinstance(outcome, dict):
                items.append(outcome)
            else:
                skipped.append({
                    "track_id": row["id"], "event_id": row["event_id"], "event_name": row["event_name"],
                    "title": row["title"], "artist": row["artist"], "isrc": isrc or None,
                    "status": row["status"], "reason": outcome,
                })

        # Managed Deezer downloads Rekordbox knows without an ISRC tag: ISRC
        # matching cannot see them, so the owner inspects them before executing.
        deezer_files = {
            canonical_key(path, storage_root)
            for (path,) in conn.execute(
                "SELECT COALESCE(published_path, output_path) FROM acquisition_jobs "
                "WHERE provider = 'deezer' AND COALESCE(published_path, output_path) IS NOT NULL"
            )
        }
        coverage["downloads_without_isrc"] = [
            {"content_id": c["content_id"], "title": c["title"], "path": c["path"]}
            for c in contents.values()
            if c["key"] in deezer_files and not c["isrc"]
        ]
        coverage["non_alphanumeric_isrcs"] = odd_isrcs
    finally:
        ro.close()
    if before != _serial_fingerprint(db_path):
        raise StaleSnapshotError(
            "master.db changed while the reconciliation preview was built; run it again"
        )
    return {
        "dry_run": True,
        "plan_version": PLAN_VERSION,
        "fingerprint": before,
        "items": items,
        "skipped": skipped,
        "isrc_coverage": coverage,
    }


def execute(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    plan,
    *,
    app_db_path=None,
    retention: int = 20,
    consent_to_permanent_delete: bool = False,
    isrc_collision_policy="guarded",
) -> dict:
    if not isinstance(plan, dict) or plan.get("plan_version") != PLAN_VERSION:
        raise ValueError("a valid source reconciliation preview is required")
    if build_plan(conn, storage_root, db_path, isrc_collision_policy=isrc_collision_policy) != plan:
        raise StaleSnapshotError("the source reconciliation preview is stale; reopen it")
    trashed, pending = [], []

    def trash(item, *, may_raise) -> bool:
        path = Path(item["file"]["path"])
        reason = None
        if _file_state(path, with_hash=True) != item["file"]:
            reason = "changed"
        else:
            try:
                delete_file(path, consent_to_permanent_delete=consent_to_permanent_delete)
            except PermanentDeleteConsentRequired:
                if may_raise:
                    raise  # nothing changed yet: the 428 retry replays this exact plan
                reason = "permanent_delete_consent"
        if reason:
            pending.append({"track_id": item["track_id"], "path": str(path), "reason": reason})
            return False
        trashed.append(str(path))
        return True

    # No Rekordbox write: trash first, so a refused trash changes nothing.
    for item in plan["items"]:
        if item["action"] == "replace" or not trash(item, may_raise=not trashed and not pending):
            continue
        if item["action"] == "rematch":
            conn.execute(
                "UPDATE event_tracks SET status = 'matched', content_id = ?, confidence = 100,"
                " staging_file_path = NULL, updated_at = ? WHERE id = ?",
                (item["content_id"], _now(), item["track_id"]),
            )
        else:
            conn.execute(
                "UPDATE event_tracks SET staging_file_path = NULL, updated_at = ? WHERE id = ?",
                (_now(), item["track_id"]),
            )

    replaces = [item for item in plan["items"] if item["action"] == "replace"]
    if replaces:
        # One mutate() for every event: one backup is THE pre-reconciliation
        # restore point, and a long run never rotates it out of the retention.
        xml_path, xml_bytes = _xml_snapshot(db_path, None)
        with mutate(
            db_path,
            backups_root,
            retention=retention,
            expected_fingerprint=_fingerprint_tuple(plan["fingerprint"]),
            open_db=open_rekordbox,
            invalidate_cache=cache.invalidate,
            app_db_path=app_db_path,
            backup_reason="event_source_reconciliation",
        ) as db:
            for item in replaces:
                tag_content(db, item["content_id"], item["tag_id"])
                untag_content(db, item["duplicate_content_id"], item["tag_id"])
                soft_delete_content(db, item["duplicate_content_id"])
        if xml_bytes is not None:
            xml_path.write_bytes(xml_bytes)  # byte-identical restore (SPEC-01 1.6)
        now = _now()
        conn.execute("BEGIN")
        try:
            for item in replaces:
                conn.execute(
                    "UPDATE event_tracks SET content_id = ?, updated_at = ? WHERE id = ?",
                    (item["content_id"], now, item["track_id"]),
                )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        for item in replaces:
            if trash(item, may_raise=False):
                conn.execute(
                    "UPDATE event_tracks SET staging_file_path = NULL, updated_at = ? WHERE id = ?",
                    (_now(), item["track_id"]),
                )
    return {
        **plan,
        "dry_run": False,
        "trashed_files": trashed,
        "cleanup_pending": pending,
        "consent_required": any(p["reason"] == "permanent_delete_consent" for p in pending),
    }
