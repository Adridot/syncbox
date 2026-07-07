"""Thin data access over the app DB (SPEC-UNIFIED 4/5.6, migration 0002).

Plain SQL over the manual-transaction sqlite3 connection from
appdb.open_app_db - no ORM. Multi-statement writes use explicit
BEGIN/COMMIT (same pattern as settings.update); single statements ride
autocommit. Tags/stats are JSON-encoded TEXT columns, decoded on read.

Load-bearing rules owned here:
- add_source validates the Spotify playlist id SHAPE (22 base62 chars);
- remove_source is STOP FOLLOWING ONLY (5.6): it deletes the app-side
  rows (cascade) and never touches Rekordbox content or MyTags;
- D22: any transition INTO 'ignored' stores prior_status once;
  restore_track puts prior_status back - never 'new'.
"""

import json
import re
import sqlite3

_PLAYLIST_ID = re.compile(r"^[0-9A-Za-z]{22}$")

# Columns update_source may touch; a typo must fail loudly, not create a
# parallel spelling (same rationale as settings' unknown-key rejection).
_SOURCE_COLUMNS = frozenset(
    {"name", "snapshot_id", "tags", "enabled", "status", "cover_url"}
)

_TRACK_COLUMNS = (
    "spotify_track_id",
    "title",
    "artist",
    "duration_ms",
    "isrc",
    "status",
    "content_id",
    "match_method",
    "confidence",
    "staging_file_path",
    "tags",
    "prior_status",
)


def _row_to_dict(row: sqlite3.Row, json_fields=("tags",)) -> dict:
    out = dict(row)
    for field in json_fields:
        if field in out:
            out[field] = json.loads(out[field]) if out[field] else []
    return out


# --- sources -------------------------------------------------------------------


def add_source(
    conn, spotify_playlist_id: str, name: str = "", tags=(), cover_url=None
) -> dict:
    """Follow a playlist. Validates the id shape; duplicate follow -> ValueError."""
    if not _PLAYLIST_ID.match(spotify_playlist_id or ""):
        raise ValueError(
            f"invalid Spotify playlist id {spotify_playlist_id!r}: expected "
            "22 base62 characters (paste the id, not the URL)"
        )
    try:
        cursor = conn.execute(
            "INSERT INTO sources (spotify_playlist_id, name, tags, cover_url) "
            "VALUES (?, ?, ?, ?)",
            (spotify_playlist_id, name, json.dumps(list(tags)), cover_url),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"playlist {spotify_playlist_id} is already followed") from exc
    return get_source(conn, cursor.lastrowid)


def get_source(conn, source_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_sources(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def update_source(conn, source_id: int, **fields) -> dict:
    """Partial update over the allowlisted source columns."""
    unknown = set(fields) - _SOURCE_COLUMNS
    if unknown:
        raise KeyError(f"unknown source fields: {sorted(unknown)}")
    if "tags" in fields:
        fields["tags"] = json.dumps(list(fields["tags"]))
    if "enabled" in fields:
        fields["enabled"] = int(bool(fields["enabled"]))
    assignments = ", ".join(f"{column} = ?" for column in fields)
    conn.execute(
        f"UPDATE sources SET {assignments} WHERE id = ?",
        (*fields.values(), source_id),
    )
    return get_source(conn, source_id)


def remove_source(conn, source_id: int) -> None:
    """Stop following ONLY (5.6): deletes the app-side source, its tracks and
    run history via FK cascade. Rekordbox content rows and MyTags are NEVER
    touched by this - there is no master.db access anywhere in this module."""
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


# --- library tracks -------------------------------------------------------------


def replace_source_tracks(conn, source_id: int, rows: list[dict]) -> None:
    """Upsert the full post-sync state for one source, one transaction.

    Row keys follow the library_tracks columns; missing keys default to
    NULL. Keyed on (source_id, spotify_track_id), so existing row ids are
    stable across syncs.
    """
    conn.execute("BEGIN")
    try:
        for row in rows:
            values = {column: row.get(column) for column in _TRACK_COLUMNS}
            values["tags"] = json.dumps(list(values["tags"] or []))
            conn.execute(
                f"""
                INSERT INTO library_tracks (source_id, {", ".join(_TRACK_COLUMNS)},
                                            updated_at)
                VALUES (?, {", ".join("?" for _ in _TRACK_COLUMNS)}, datetime('now'))
                ON CONFLICT (source_id, spotify_track_id) DO UPDATE SET
                    {", ".join(f"{c} = excluded.{c}" for c in _TRACK_COLUMNS)},
                    updated_at = excluded.updated_at
                """,
                (source_id, *values.values()),
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def list_source_tracks(conn, source_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM library_tracks WHERE source_id = ? ORDER BY id", (source_id,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_track(conn, track_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM library_tracks WHERE id = ?", (track_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def set_track_status(conn, track_id: int, status: str) -> dict:
    """Status transition with the D22 bookkeeping: entering 'ignored' stores
    the prior status exactly once (re-ignoring never overwrites it)."""
    conn.execute("BEGIN")
    try:
        current = conn.execute(
            "SELECT status FROM library_tracks WHERE id = ?", (track_id,)
        ).fetchone()
        if current is None:
            raise KeyError(f"library track {track_id} not found")
        if status == "ignored" and current["status"] != "ignored":
            conn.execute(
                "UPDATE library_tracks SET prior_status = ? WHERE id = ?",
                (current["status"], track_id),
            )
        conn.execute(
            "UPDATE library_tracks SET status = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (status, track_id),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return get_track(conn, track_id)


def restore_track(conn, track_id: int) -> dict:
    """D22 unignore: restore the stored prior status - NEVER reset to 'new'."""
    conn.execute("BEGIN")
    try:
        row = conn.execute(
            "SELECT status, prior_status FROM library_tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"library track {track_id} not found")
        if not row["prior_status"]:
            raise ValueError(
                f"library track {track_id} has no prior status to restore"
            )
        conn.execute(
            "UPDATE library_tracks SET status = prior_status, prior_status = NULL, "
            "updated_at = datetime('now') WHERE id = ?",
            (track_id,),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return get_track(conn, track_id)


# --- sync runs -------------------------------------------------------------------


def record_sync_run(
    conn, source_id: int, started_at: str, finished_at: str, snapshot_id, stats: dict
) -> int:
    cursor = conn.execute(
        "INSERT INTO sync_runs (source_id, started_at, finished_at, snapshot_id, "
        "stats) VALUES (?, ?, ?, ?, ?)",
        (source_id, started_at, finished_at, snapshot_id, json.dumps(stats)),
    )
    return cursor.lastrowid


def list_sync_runs(conn, source_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM sync_runs WHERE source_id = ? ORDER BY id DESC LIMIT ?",
        (source_id, limit),
    ).fetchall()
    return [_row_to_dict(r, json_fields=("stats",)) for r in rows]


# --- dismissed duplicate groups ---------------------------------------------------


def add_dismissed_group(conn, group_key: str) -> None:
    """'Not a duplicate', persisted and idempotent (5.4)."""
    conn.execute(
        "INSERT OR IGNORE INTO dismissed_duplicate_groups (group_key) VALUES (?)",
        (group_key,),
    )


def list_dismissed_groups(conn) -> set[str]:
    """As a set - the exact shape dedup.find_duplicate_groups(dismissed=...)
    consumes."""
    rows = conn.execute("SELECT group_key FROM dismissed_duplicate_groups").fetchall()
    return {r["group_key"] for r in rows}


# --- untagged patterns ------------------------------------------------------------


def add_untagged_pattern(conn, pattern: str) -> int:
    """User-configurable junk pattern (D7). Must compile as a regex - a bad
    pattern must fail here, not crash the untagged scan later."""
    if not pattern or not pattern.strip():
        raise ValueError("pattern must not be empty")
    re.compile(pattern)  # raises re.error on an invalid pattern
    cursor = conn.execute(
        "INSERT INTO untagged_patterns (pattern) VALUES (?)", (pattern,)
    )
    return cursor.lastrowid


def list_untagged_patterns(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM untagged_patterns ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def remove_untagged_pattern(conn, pattern_id: int) -> None:
    conn.execute("DELETE FROM untagged_patterns WHERE id = ?", (pattern_id,))
