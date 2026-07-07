"""Unified missing-tracks center: 3 scopes, purchase links + manual relink
ONLY (SPEC-UNIFIED 4/5.5/6.5 - the legal path; no download code exists).

Scopes:
- 'library'    -> library_tracks rows in a missing-family status;
- 'event'      -> event_tracks rows in a missing-family status;
- 'collection' -> Rekordbox snapshot rows whose file is missing on disk
                  (file_missing=True; nothing app-DB-persisted).

Every entry carries purchase links (B2 gate: 'missing' and
'purchase_link_unavailable' only - removed_from_source never reaches this
module because it is not a missing-family status) and LOCAL relink
candidates discovered under <storage_root>/<SYNC_DIR_NAME>/inbox plus any
user-chosen directories. Status cycle (5.5):
missing -> purchase_linked | relinked | ignored, failures
purchase_link_unavailable / manual_relink_needed; 'ignored' stores
prior_status and restore_missing puts it back - never 'new' (D22).

relink_collection_file() is the ONE collection-scope write: FolderPath
re-association inside safety.mutate(), stored in the 3.2 stored form, and
it REQUIRES the named ANLZ consent (cues/beatgrid/waveform may
desynchronize - the ANLZ files are outside the backup guarantee, 3.1/5.5).
"""

import json
from pathlib import Path

from syncbox.purchase_links import links_for_track
from syncbox.rb import open_readonly
from syncbox.rb_write import open_rekordbox, relink_content_path
from syncbox.relink import find_candidates
from syncbox.safety.mutate import mutate
from syncbox.safety.paths import SYNC_DIR_NAME, stored_form, tcc_exists

MISSING_STATUSES = frozenset(
    {"missing", "purchase_link_unavailable", "manual_relink_needed"}
)
RESOLUTION_STATUSES = frozenset(
    {
        "purchase_linked",
        "relinked",
        "ignored",
        "purchase_link_unavailable",
        "manual_relink_needed",
    }
)

_SCOPE_TABLES = {"library": "library_tracks", "event": "event_tracks"}


class AnlzConsentRequired(RuntimeError):
    """Relink consent gate (5.5/3.1): the ANLZ warning was not accepted.

    Replacing a file association can desynchronize cues/beatgrid/waveform
    stored in ANLZ files, which the master.db backup does NOT cover.
    """


def relink_roots(storage_root, user_roots=()) -> list[Path]:
    """Search roots for relink discovery: the storage inbox + user dirs."""
    roots: list[Path] = []
    if storage_root:
        roots.append(Path(storage_root) / SYNC_DIR_NAME / "inbox")
    roots.extend(Path(r) for r in user_roots)
    return roots


def _decorate(entry: dict, roots) -> dict:
    entry["purchase_links"] = links_for_track(
        entry["status"], entry["artist"], entry["title"]
    )
    entry["relink_candidates"] = (
        find_candidates(
            {
                "title": entry["title"],
                "artist": entry["artist"],
                "isrc": entry["isrc"],
            },
            roots,
        )
        if roots
        else []
    )
    return entry


def list_missing(
    conn,
    scope: str,
    *,
    cache=None,
    storage_root=None,
    user_roots=(),
) -> list[dict]:
    """Missing entries for one scope, each with purchase links + local
    relink candidates. Collection scope reads the snapshot cache (requires
    cache and storage_root); the app DB is never a mirror of master.db."""
    if scope == "collection":
        if cache is None or storage_root is None:
            raise ValueError("collection scope requires cache and storage_root")
        entries = [
            {
                "scope": "collection",
                "id": row["content_id"],
                "content_id": row["content_id"],
                "title": row["title"],
                "artist": row["artist"],
                "isrc": row["isrc"],
                "status": "missing",
                "file_path": row["file_path"],
            }
            for row in cache.get(storage_root)
            if row["file_missing"]
        ]
    elif scope in _SCOPE_TABLES:
        placeholders = ", ".join("?" for _ in MISSING_STATUSES)
        rows = conn.execute(
            f"SELECT * FROM {_SCOPE_TABLES[scope]} "  # fixed table map, not input
            f"WHERE status IN ({placeholders}) ORDER BY id",
            tuple(sorted(MISSING_STATUSES)),
        ).fetchall()
        entries = [
            {
                "scope": scope,
                "id": row["id"],
                "content_id": row["content_id"],
                "title": row["title"],
                "artist": row["artist"],
                "isrc": row["isrc"],
                "status": row["status"],
            }
            for row in rows
        ]
    else:
        raise ValueError(f"unknown missing scope {scope!r}")

    roots = relink_roots(storage_root, user_roots)
    return [_decorate(entry, roots) for entry in entries]


def set_missing_status(conn, scope: str, row_id: int, status: str) -> dict:
    """5.5 transition: missing-family -> resolution/failure status.

    D22: entering 'ignored' stores prior_status exactly once. Collection
    scope has no app-DB row - resolving it IS relink_collection_file().
    """
    if scope not in _SCOPE_TABLES:
        raise ValueError(
            f"scope {scope!r} has no app-DB status; collection entries are "
            "resolved by relink_collection_file"
        )
    if status not in RESOLUTION_STATUSES:
        raise ValueError(f"invalid missing resolution status {status!r}")
    table = _SCOPE_TABLES[scope]
    conn.execute("BEGIN")
    try:
        row = conn.execute(
            f"SELECT status FROM {table} WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"{scope} track {row_id} not found")
        if row["status"] not in MISSING_STATUSES:
            raise ValueError(
                f"cannot transition {row['status']!r} -> {status!r}: "
                "not a missing-family status"
            )
        if status == "ignored":
            conn.execute(
                f"UPDATE {table} SET prior_status = ? WHERE id = ?",
                (row["status"], row_id),
            )
        conn.execute(
            f"UPDATE {table} SET status = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (status, row_id),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return _fetch(conn, table, row_id)


def restore_missing(conn, scope: str, row_id: int) -> dict:
    """D22 unignore: put prior_status back - NEVER reset to 'new'."""
    if scope not in _SCOPE_TABLES:
        raise ValueError(f"scope {scope!r} has no app-DB status to restore")
    table = _SCOPE_TABLES[scope]
    conn.execute("BEGIN")
    try:
        row = conn.execute(
            f"SELECT prior_status FROM {table} WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"{scope} track {row_id} not found")
        if not row["prior_status"]:
            raise ValueError(f"{scope} track {row_id} has no prior status to restore")
        conn.execute(
            f"UPDATE {table} SET status = prior_status, prior_status = NULL, "
            "updated_at = datetime('now') WHERE id = ?",
            (row_id,),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return _fetch(conn, table, row_id)


def _fetch(conn, table: str, row_id: int) -> dict:
    row = dict(
        conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    )
    if "tags" in row:
        row["tags"] = json.loads(row["tags"]) if row["tags"] else []
    return row


def relink_collection_file(
    db_path,
    backups_root,
    cache,
    storage_root,
    content_id: str,
    new_path,
    *,
    anlz_consent: bool,
    retention: int = 15,
) -> str:
    """Re-associate DjmdContent.FolderPath to a LOCAL file the user already
    lawfully owns. Returns the stored (3.2) form written to master.db.

    Order is load-bearing: consent gate FIRST (no consent -> nothing is
    touched, not even a backup), then the TCC-safe existence check, then a
    read-only check that the content row still exists (the missing list
    comes from the snapshot cache, so a row deleted in Rekordbox since can
    reach here stale: unknown -> KeyError/404, no backup wasted), then the
    single mutate() unit-of-work. Only FolderPath changes - cues, tags and
    playlist memberships are preserved by construction (rb_write).
    """
    if not anlz_consent:
        raise AnlzConsentRequired(
            "Relinking replaces the file association; cues, beatgrid and "
            "waveform stored in ANLZ files may desynchronize and are NOT "
            "covered by the master.db backup. Explicit consent is required."
        )
    if not tcc_exists(new_path):
        raise FileNotFoundError(f"relink target does not exist locally: {new_path}")
    ro = open_readonly(db_path)
    try:
        row = ro.execute(
            "SELECT rb_local_deleted FROM djmdContent WHERE ID = ?",
            (str(content_id),),
        ).fetchone()
    finally:
        ro.close()
    if row is None or int(row[0] or 0):
        raise KeyError(f"collection content {content_id} not found")
    stored = stored_form(new_path, storage_root)
    with mutate(
        db_path,
        backups_root,
        retention=retention,
        open_db=open_rekordbox,
        invalidate_cache=cache.invalidate,
    ) as db:
        relink_content_path(db, content_id, stored)
    return stored
