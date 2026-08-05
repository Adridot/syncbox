"""Staged-file integrity (staged-file-integrity spec): a 'ready' row whose
staged file is no longer a regular file on disk is reclassified 'missing'
with its staging path cleared, so the track stays actionable in the Missing
center. Acquisition jobs live in their own table and are never touched.

Shared by library_service and events_service; sync.py stays pure (no I/O),
so callers run this around the pure diff pipeline.
"""

from pathlib import Path

_TABLES = frozenset({"library_tracks", "event_tracks"})


def staged_file_ok(path) -> bool:
    """True when path is non-empty and resolves to a regular file."""
    return bool(path) and Path(path).is_file()


def reclassify_stale_ready(conn, table: str, rows: list[dict]) -> list[dict]:
    """Reclassify 'ready' rows whose staged file vanished: status 'missing',
    staging_file_path cleared, everything else (jobs, content_id) untouched.

    Persists directly and patches the given dicts in place so callers keep
    working on the corrected state. Returns the reclassified rows.
    """
    if table not in _TABLES:
        raise ValueError(f"unknown track table {table!r}")
    stale = [
        row
        for row in rows
        if row.get("status") == "ready" and not staged_file_ok(row.get("staging_file_path"))
    ]
    if not stale:
        return []
    conn.execute("BEGIN")
    try:
        for row in stale:
            conn.execute(
                f"UPDATE {table} SET status = 'missing', staging_file_path = NULL, "
                "updated_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    for row in stale:
        row["status"] = "missing"
        row["staging_file_path"] = None
    return stale
