"""Batch removal of chosen tracks from an event (event-track-removal).

Shape (design.md): ONE ``safety.mutate()`` unit of work in the shape of
``events_service.apply_event`` — deliberately NOT ``event_delete``'s
persisted state machine. The retained case is BLOCKED instead of migrated
(owner decision), so nothing is copied before the commit, there is no torn
window, and nothing has to survive a crash: a failure before the commit
rolls back to the backup with every file still on disk. The plan therefore
lives only in the request/response round trip and never touches the single
``events.delete_plan`` slot a deletion preview owns.

What this module must never do: soft-delete the event MyTag or its smart
playlist, remove the staging directory, or delete the event row. The event
survives a removal intact, and every track outside the batch is untouched.
"""

from __future__ import annotations

from pathlib import Path

from syncbox.event_delete import (
    EventMigrationError,
    _assert_state,
    _expected_file_state,
    _file_state,
    _fingerprint_tuple,
    _inside_staging,
    _serial_fingerprint,
    _TAG_SQL,
    _OTHER_TAGS_SQL,
    _verify_live_plan,
    classify_removal,
    event_staging,
)
from syncbox.events_service import (
    APPLIED_EVENT_STATUSES,
    SITUATION_CATEGORY,
    _now,
    _xml_snapshot,
    get_event,
    list_event_tracks,
    recompute_event_status,
)
from syncbox.platform_os import PermanentDeleteConsentRequired, delete_file
from syncbox.rb import open_readonly
from syncbox.rb_write import open_rekordbox, soft_delete_content, untag_content
from syncbox.safety.mutate import StaleSnapshotError, mutate
from syncbox.safety.paths import canonical_key, classify_ownership, resolve_stored_path

REMOVAL_PLAN_VERSION = 1
# The terminal status of a removed row: it KEEPS its staging_file_path (so a
# file that was NOT deleted stays referenced and is never adopted again) and
# loses its content_id (the Rekordbox entry is no longer this row's).
REMOVED_STATUS = "removed"

_CONTENT_SQL = """
SELECT c.ID, c.Title, a.Name, c.FolderPath
FROM djmdContent c
LEFT JOIN djmdArtist a ON a.ID = c.ArtistID
WHERE c.ID = :content_id AND c.rb_local_deleted = 0
"""
_TAG_LINK_SQL = """
SELECT rb_local_deleted FROM djmdSongMyTag
WHERE ContentID = :content_id AND MyTagID = :tag_id
"""


class EventRemovalError(ValueError):
    """The batch cannot be planned or executed as asked."""


# --- planning ----------------------------------------------------------------------


def _batch(tracks: list[dict], track_ids) -> list[dict]:
    by_id = {int(row["id"]): row for row in tracks}
    batch = []
    for value in dict.fromkeys(int(track_id) for track_id in track_ids):
        row = by_id.get(value)
        if row is None:
            raise KeyError(f"event track {value} is not part of this event")
        if row["status"] == REMOVED_STATUS:
            raise EventRemovalError(f"event track {value} was already removed")
        batch.append(row)
    return batch


def needs_rekordbox(tracks: list[dict], track_ids) -> bool:
    """True unless EVERY batch entry is never-applied.

    Derived from the application database alone, so the caller can decide
    whether master.db has to be configured/closed before it is even opened:
    a batch of never-applied rows has no Rekordbox footprint at all and runs
    with Rekordbox running (spec: "Batch of never-applied tracks only").
    """
    return any(row["content_id"] for row in _batch(tracks, track_ids))


def plan_removal(
    query, event, tracks, track_ids, storage_root, db_path, db_fingerprint
) -> dict:
    """Build the deterministic payload the confirmation must echo verbatim.

    ``query`` reads master.db (never called when the batch is never-applied
    only); ``tracks`` is the event's complete application-database row set,
    which is what the two group-bys below need.
    """
    batch = _batch(tracks, track_ids)
    batch_ids = {int(row["id"]) for row in batch}
    staging = event_staging(event, storage_root)
    # A 'removed' row is NOT a holder: it kept its staged path only to keep
    # the file referenced, and counting it would make a file that survived a
    # partially covered group unremovable for ever.
    live = [row for row in tracks if row["status"] != REMOVED_STATUS]
    wants_rekordbox = any(row["content_id"] for row in batch)

    tag_rows = (
        query(_TAG_SQL, {"tag": event["default_tag"], "category": SITUATION_CATEGORY})
        if wants_rekordbox
        else []
    )
    tag_id = str(tag_rows[0][0]) if tag_rows else None

    # --- the two group-bys (design.md "Shared audio inside the event") ------
    # Two event tracks can resolve to the SAME Rekordbox entry and the SAME
    # staged file (two Spotify ids sharing one non-empty ISRC share a staged
    # file under the 5.7 claim rule, and apply_event then reuses the content
    # row through find_active_content_by_path). event_delete's
    # _referenced_by_other_content does NOT cover this: it looks at other
    # CONTENT rows, not at other event tracks. An entry or a file is
    # removable only when EVERY live row holding it is in the batch;
    # a partially covered group degrades to NO ACTION, never a partial one.
    contents: dict[str, tuple | None] = {}
    if wants_rekordbox:
        for content_id in dict.fromkeys(
            str(row["content_id"]) for row in live if row["content_id"]
        ):
            found = query(_CONTENT_SQL, {"content_id": content_id})
            contents[content_id] = tuple(found[0]) if found else None
    holders_by_content: dict[str, set[int]] = {}
    holders_by_file: dict[str, set[int]] = {}
    for row in live:
        row_id = int(row["id"])
        keys = set()
        if row["staging_file_path"]:
            keys.add(canonical_key(row["staging_file_path"], storage_root))
        if row["content_id"]:
            content_id = str(row["content_id"])
            holders_by_content.setdefault(content_id, set()).add(row_id)
            # A row that holds an ENTRY also holds the file that entry points
            # at, even when the row itself carries no staged path (an adopted
            # row matched onto the entry a previous apply created).
            found = contents.get(content_id)
            if found is not None and found[3]:
                keys.add(canonical_key(found[3], storage_root))
        for key in keys:
            holders_by_file.setdefault(key, set()).add(row_id)

    # --- per-entry classification, once per content id ----------------------
    decided: dict[str, dict] = {}
    for content_id in dict.fromkeys(
        str(row["content_id"]) for row in batch if row["content_id"]
    ):
        found = contents.get(content_id)
        folder_path = found[3] if found is not None else None
        source = (
            resolve_stored_path(folder_path, storage_root) if folder_path else None
        )
        entry = {
            "content_id": content_id,
            "title": found[1] if found is not None else None,
            "artist": found[2] if found is not None else None,
            "source": source,
            "retaining_ids": [],
            "retaining_names": [],
            # 'tagged' is the invariant that keeps this path narrow: Syncbox
            # only ever touches an entry the EVENT ITSELF tagged. An entry
            # the user already deleted or untagged in Rekordbox gets no
            # Rekordbox write and no file deletion — the row just leaves the
            # event, conservatively (its file may still back a live entry).
            "tagged": False,
            "action": "keep_in_place",
        }
        if found is not None and tag_id is not None:
            link = query(_TAG_LINK_SQL, {"content_id": content_id, "tag_id": tag_id})
            if link and not int(link[0][0] or 0):
                other = query(
                    _OTHER_TAGS_SQL, {"content_id": content_id, "tag_id": tag_id}
                )
                entry["retaining_ids"] = [str(row[0]) for row in other]
                entry["retaining_names"] = [row[1] for row in other]
                entry["tagged"] = True
                entry["action"] = classify_removal(
                    classify_ownership(folder_path, storage_root)
                    if folder_path
                    else "external",
                    _inside_staging(source, staging),
                    entry["retaining_ids"],
                )
        decided[content_id] = entry

    # --- per-row plan -------------------------------------------------------
    plan_tracks: list[dict] = []
    unresolved: list[dict] = []
    entries: dict[str, dict] = {}
    deletions: dict[str, Path] = {}
    for row in batch:
        content_id = str(row["content_id"]) if row["content_id"] else None
        entry = decided.get(content_id) if content_id else None
        if entry is not None and entry["action"] == "migrate_to_collection":
            # Blocked, never migrated here (owner decision): the batch cannot
            # execute at all, so the row is reported ONLY as unresolved.
            if not any(issue["content_id"] == content_id for issue in unresolved):
                unresolved.append(
                    {
                        "id": f"retained_by_other_mytag-{content_id}",
                        "kind": "retained_by_other_mytag",
                        "title": entry["title"] or row["title"],
                        "artist": entry["artist"] or row["artist"],
                        "content_id": content_id,
                        "retaining_mytags": entry["retaining_names"],
                        # Clear the other tag in Rekordbox, or delete the
                        # whole event — the only path that migrates a
                        # retained file into the permanent collection.
                        "resolution_options": ["remove_other_mytag", "delete_event"],
                    }
                )
            continue
        source = entry["source"] if entry is not None else None
        if source is None and row["staging_file_path"]:
            source = Path(row["staging_file_path"]).expanduser()
        file_key = canonical_key(source, storage_root) if source is not None else None
        entry_removable = content_id is not None and holders_by_content.get(
            content_id, set()
        ) <= batch_ids
        file_removable = file_key is not None and holders_by_file.get(
            file_key, set()
        ) <= batch_ids
        action = entry["action"] if entry is not None else "never_applied"
        # The file goes ONLY with the soft-delete that made its entry
        # disappear (never_applied has no entry to begin with), and only
        # when the whole file group is in the batch.
        wants_file = (
            action in ("delete_with_event", "never_applied")
            and file_key is not None
            and _inside_staging(source, staging)
        )
        deletes = wants_file and file_removable
        if entry is not None:
            # Every Rekordbox-side consequence — the untag included — needs
            # the whole entry group in the batch.
            deletes = deletes and entry_removable
            if entry["tagged"] and entry_removable:
                entries.setdefault(
                    content_id,
                    {
                        "content_id": content_id,
                        "source_path": str(source) if source is not None else None,
                        "soft_delete": action == "delete_with_event",
                    },
                )
            elif action == "delete_with_event":
                # Held by a sibling row of the same event (or by an entry the
                # event no longer tags): no untag, no soft-delete, no file
                # deletion. Only the application-database row leaves.
                action = "keep_in_place"
        if deletes:
            deletions.setdefault(file_key, Path(source))
        plan_tracks.append(
            {
                "track_id": int(row["id"]),
                "content_id": content_id,
                "title": row["title"],
                "artist": row["artist"],
                "action": action,
                "source_path": str(source) if source is not None else None,
                # Per-row marker; the file count is len(expected_file_deletions),
                # which holds a shared file exactly once.
                "file_deleted": bool(deletes),
                # Opaque to the UI, kept for auditability: this row asked for
                # a removal one of its two groups refused, so nothing
                # happened outside the application database.
                "shared_with_kept_track": bool(
                    (content_id is not None and not entry_removable)
                    or (wants_file and not deletes)
                ),
            }
        )

    ordered_entries = [entries[key] for key in sorted(entries)]
    ordered_deletions = [str(deletions[key]) for key in sorted(deletions)]
    return {
        "dry_run": True,
        "plan_version": REMOVAL_PLAN_VERSION,
        "event_id": int(event["id"]),
        "event_name": event["name"],
        # False when every batch entry is never-applied: the confirmation
        # dialog must not demand a closed Rekordbox for nothing.
        "needs_rekordbox": wants_rekordbox,
        "fingerprint": db_fingerprint,
        "tag_id": tag_id,
        "tracks": plan_tracks,
        "entries": ordered_entries,
        "expected_file_deletions": ordered_deletions,
        "unresolved": unresolved,
        "validation": {
            "db_fingerprint": db_fingerprint,
            "sources": [
                {
                    "content_id": entry["content_id"],
                    **(
                        _file_state(entry["source_path"])
                        if entry["source_path"]
                        else {"path": None, "exists": False}
                    ),
                }
                for entry in ordered_entries
            ],
            "active_mytags": [
                {
                    "content_id": entry["content_id"],
                    "tag_ids": decided[entry["content_id"]]["retaining_ids"],
                    "tag_names": decided[entry["content_id"]]["retaining_names"],
                }
                for entry in ordered_entries
            ],
            "cleanup_files": [
                _file_state(path, with_hash=True) for path in ordered_deletions
            ],
        },
    }


def read_removal_plan(db_path, event, tracks, track_ids, storage_root) -> dict:
    """plan_removal over a stable master.db snapshot (or none at all)."""
    if not needs_rekordbox(tracks, track_ids):
        # No Rekordbox footprint: nothing to read, nothing to keep fresh.
        return plan_removal(
            None, event, tracks, track_ids, storage_root, db_path, None
        )
    db_path = Path(db_path)
    before = _serial_fingerprint(db_path)
    ro = open_readonly(db_path)
    try:

        def query(sql, params):
            return ro.execute(sql, params).fetchall()

        plan = plan_removal(
            query, event, tracks, track_ids, storage_root, db_path, before
        )
    finally:
        ro.close()
    if before != _serial_fingerprint(db_path):
        raise StaleSnapshotError(
            "master.db changed while the track removal preview was being built; "
            "run the preview again"
        )
    return plan


# --- execution ---------------------------------------------------------------------


def _assert_inside_staging(plan: dict, staging) -> None:
    """Plan integrity: a removal only ever trashes files inside THIS event's
    staging directory. Checked before the Rekordbox write AND again before
    any deletion, so it can never be discovered post-commit."""
    for value in plan["expected_file_deletions"]:
        if staging is None or not _inside_staging(Path(value), staging):
            raise EventMigrationError(
                f"planned removal path escapes event staging: {value}"
            )


def _verify_precommit(plan: dict, staging) -> None:
    """Every planned source and every planned deletion is as previewed."""
    _assert_inside_staging(plan, staging)
    for state in plan["validation"]["sources"]:
        _assert_state(state)
    for state in plan["validation"]["cleanup_files"]:
        _assert_state(state, with_hash=True)


def _cleanup_files(plan: dict, staging, *, consent: bool, allow_consent_error: bool):
    """Trash the planned files — ONLY after the Rekordbox commit is durable.

    A file that moved since the preview is KEPT and reported rather than
    deleted. Post-commit nothing raises: the Rekordbox change stands, so an
    incomplete cleanup is reported to the user (spec: "Failure after the
    commit"), never turned into an error that would tear the app state.
    ``allow_consent_error`` is true only when nothing was committed and
    nothing was deleted yet, so the 428 consent round trip can retry exactly.
    """
    _assert_inside_staging(plan, staging)
    states = {state["path"]: state for state in plan["validation"]["cleanup_files"]}
    paths = [Path(value) for value in plan["expected_file_deletions"]]
    removed, kept = [], []
    for path in paths:
        expected = _expected_file_state(states.get(str(path), {}))
        current = _file_state(path, with_hash=True)
        if not current["exists"]:
            continue
        if not expected or {key: current.get(key) for key in expected} != expected:
            kept.append({"path": str(path), "reason": "changed"})
            continue
        try:
            delete_file(path, consent_to_permanent_delete=consent)
        except PermanentDeleteConsentRequired:
            if allow_consent_error and not removed:
                raise
            kept.append({"path": str(path), "reason": "permanent_delete_consent"})
            continue
        removed.append(str(path))
    return removed, kept


def remove_tracks(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    event,
    *,
    track_ids,
    dry_run: bool = True,
    plan=None,
    consent_to_permanent_delete: bool = False,
    retention: int = 20,
    app_db_path=None,
) -> dict:
    """Preview, or execute, one exact batch removal."""
    event = get_event(conn, event["id"])
    if event is None:
        raise KeyError("event no longer exists")
    tracks = list_event_tracks(conn, event["id"])

    if dry_run:
        return read_removal_plan(db_path, event, tracks, track_ids, storage_root)

    if not isinstance(plan, dict):
        raise EventRemovalError("track removal requires the exact preview plan")
    if plan.get("plan_version") != REMOVAL_PLAN_VERSION:
        raise EventRemovalError("unsupported track removal plan version")
    if int(plan.get("event_id", -1)) != int(event["id"]):
        raise EventRemovalError("track removal plan targets a different event")
    if plan.get("unresolved"):
        raise EventRemovalError("track removal has unresolved cases")
    fresh = read_removal_plan(db_path, event, tracks, track_ids, storage_root)
    if fresh != plan:
        raise StaleSnapshotError(
            "the track removal preview is stale; reopen it before removing"
        )

    staging = event_staging(event, storage_root)
    _verify_precommit(plan, staging)
    entries = plan["entries"]
    if entries:
        xml_path, xml_bytes = _xml_snapshot(db_path, event["staging_dir"])
        with mutate(
            db_path,
            backups_root,
            retention=retention,
            expected_fingerprint=_fingerprint_tuple(plan["fingerprint"]),
            open_db=open_rekordbox,
            invalidate_cache=cache.invalidate,
            app_db_path=app_db_path,
            backup_reason="event_track_remove",
        ) as db:
            # The SAME live re-verification the deletion path runs, over the
            # removal's entries: content still active, path unchanged, event
            # tag link still there, retaining tags unmoved.
            _verify_live_plan(
                db,
                {
                    "tag_id": plan["tag_id"],
                    "tracks": entries,
                    "validation": {
                        "active_mytags": plan["validation"]["active_mytags"]
                    },
                },
                storage_root,
            )
            for entry in entries:
                untag_content(db, entry["content_id"], plan["tag_id"])
                if entry["soft_delete"]:
                    soft_delete_content(db, entry["content_id"])
        if xml_bytes is not None:
            xml_path.write_bytes(xml_bytes)  # byte-identical restore (SPEC-01 1.6)

    removed_files, kept_files = _cleanup_files(
        plan,
        staging,
        consent=consent_to_permanent_delete,
        allow_consent_error=not entries,
    )

    now = _now()
    removed_tracks = [track["track_id"] for track in plan["tracks"]]
    conn.execute("BEGIN")
    try:
        for track_id in removed_tracks:
            # staging_file_path is RETAINED (design.md): a file that was not
            # deleted stays referenced and is never adopted back.
            conn.execute(
                "UPDATE event_tracks SET status = ?, content_id = NULL,"
                " prior_status = NULL, updated_at = ? WHERE id = ?",
                (REMOVED_STATUS, now, track_id),
            )
        event_status = event["status"]
        if event_status in APPLIED_EVENT_STATUSES:
            # Only for an applied event: recompute_event_status returns
            # 'applied' as soon as nothing pending remains, which would be a
            # lie on an event that was never applied at all.
            event_status = recompute_event_status(
                row["status"]
                for row in conn.execute(
                    "SELECT status FROM event_tracks WHERE event_id = ?",
                    (event["id"],),
                )
            )
            conn.execute(
                "UPDATE events SET status = ? WHERE id = ?",
                (event_status, event["id"]),
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {
        **plan,
        "dry_run": False,
        "removed_files": removed_files,
        "kept_files": kept_files,
        "removed_tracks": removed_tracks,
        "event_status": event_status,
    }
