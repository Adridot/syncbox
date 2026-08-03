"""Performance history ("Prestations"): append-only archive of Rekordbox
plays + the deterministic re-clustering that turns them into gigs
(owner-approved 17/07/2026; analysis on a real RB 7.x master.db).

Why Rekordbox's own History view is not enough:
- djmdSongHistory.created_at IS the play timestamp (verified monotonic with
  TrackNo across every session), but one djmdHistory leaf session = one app
  RUN, not one gig: sessions span up to 18 h with 10 h internal gaps, a
  mid-set crash splits a gig in two, and cloud sync merges every machine's
  sessions into every master.db with NO device column (the interleaved
  histories the owner complained about).
- So a "prestation" is rebuilt here: split inside a session on long gaps,
  re-join consecutive sessions across a short gap (crash/restart), and NEVER
  join sessions whose play windows overlap - overlap proves two machines
  played at once (a session is single-machine by construction).

Spotify tracks played inside Rekordbox arrive with obfuscated Title/Artist
($A7:v1:...) but a CLEARTEXT spotify:track:<id> FolderPath - titles are
resolved through the existing read-only Spotify client, never by breaking
the obfuscation. Plays from the Spotify app OUTSIDE Rekordbox are
deliberately out of scope (owner decision 17/07: parallel-room playback
would pollute the gig record).

master.db is only ever opened through rb.open_readonly (mode=ro), so this
whole module is safe while Rekordbox is running - that is what makes the
live "already played" view crash-proof.
"""

import json
from datetime import datetime, timedelta, timezone

from syncbox.rb import open_readonly
from syncbox.safety.mutate import fingerprint

# NotConnectedError stays re-exported: refresh() callers and tests raise it
# through this module when simulating a disconnected Spotify client.
from syncbox.spotify import (
    NotConnectedError,
    resolve_track_meta,
    scrub_obfuscated,
    spotify_id_from_path,
)

# One knob on purpose: intra-session gaps above it split a gig, inter-session
# gaps at or below it re-join one (the 9-minute crash/restart measured on the
# 2026-07-04 gig merges; the 9 h warmup->party gap splits).
GAP_MINUTES = 60

# A gig is "live" while its last play is at most this old.
LIVE_WINDOW_MINUTES = 30

# A whole segment averaging under this per track is not human playback: it is
# a USB/CDJ history IMPORT (observed live: 270 "plays" across 18 sessions in
# 5 minutes on 2026-05-30 - created_at is the import moment there, only the
# track order is real). Such segments stay one-performance-per-session and
# never merge with anything.
BULK_SECONDS_PER_TRACK = 30

# Rekordbox playlist folder holding the exported performance playlists.
# "Historiques" (plural) on purpose: the owner already keeps a root folder
# of that exact name for archived gig playlists - exports join it instead
# of creating a near-twin; ensure_playlist_folder creates it when absent.
EXPORT_FOLDER = "Historiques"

_PLAYS_SQL = """
SELECT s.UUID, s.HistoryID, h.Name, s.ContentID, s.TrackNo, s.created_at,
       c.Title, a.Name AS artist, c.FolderPath
FROM djmdSongHistory s
JOIN djmdHistory h ON h.ID = s.HistoryID
LEFT JOIN djmdContent c ON c.ID = s.ContentID
LEFT JOIN djmdArtist a ON a.ID = c.ArtistID
WHERE s.rb_local_deleted = 0 AND h.rb_local_deleted = 0 AND h.Attribute = 0
"""

# ingested-fingerprint per master.db path: skip the SQLCipher open (~0.2 s of
# key derivation) when the file did not change since the last refresh.
_ingested = {}


def _norm_ts(value) -> str | None:
    """'2026-07-05 00:31:54.802 +00:00' -> '2026-07-05 00:31:54' (UTC, sortable)."""
    try:
        return (
            datetime.fromisoformat(str(value).split("+")[0].strip())
            .replace(microsecond=0)
            .isoformat(sep=" ")
        )
    except ValueError:
        return None


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def read_rb_plays(db_path) -> list[dict]:
    """Every active play of every leaf history session, normalized."""
    conn = open_readonly(db_path)
    try:
        rows = []
        for uuid, hid, hname, cid, track_no, created, title, artist, path in (
            conn.execute(_PLAYS_SQL)
        ):
            played_at = _norm_ts(created)
            if not uuid or not played_at:
                continue
            rows.append(
                {
                    "uuid": str(uuid),
                    "rb_history_id": str(hid),
                    "rb_history_name": hname or "",
                    "content_id": str(cid) if cid else None,
                    "track_no": track_no,
                    "title": scrub_obfuscated(title),
                    "artist": scrub_obfuscated(artist),
                    "spotify_track_id": spotify_id_from_path(path),
                    "played_at": played_at,
                }
            )
        return rows
    finally:
        conn.close()


def ingest(conn, rb_rows) -> int:
    """Append-only insert keyed on the play UUID; returns how many were new."""
    before = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
    conn.execute("BEGIN")
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO plays (uuid, rb_history_id, rb_history_name,"
            " content_id, track_no, title, artist, spotify_track_id, played_at)"
            " VALUES (:uuid, :rb_history_id, :rb_history_name, :content_id,"
            " :track_no, :title, :artist, :spotify_track_id, :played_at)",
            rb_rows,
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0] - before


def resolve_spotify_titles(conn, client, transport=None) -> int:
    """Fill title/artist of Spotify-in-Rekordbox plays through the shared
    spotify.resolve_track_meta ladder: an API result carries an artist and
    fills both fields (completing artist-less oEmbed rows later); a
    title-only oEmbed result fills title-less rows and nothing else.
    Best-effort throughout; unresolved rows retry on a later refresh."""
    titleless = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT spotify_track_id FROM plays"
            " WHERE spotify_track_id IS NOT NULL AND title IS NULL"
        )
    ]
    artistless = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT spotify_track_id FROM plays"
            " WHERE spotify_track_id IS NOT NULL"
            " AND title IS NOT NULL AND artist IS NULL"
        )
    ]
    # titleless first: only they can benefit from the capped oEmbed fallback
    pending = titleless + artistless
    if not pending:
        return 0
    resolved = 0
    meta = resolve_track_meta(pending, client, transport=transport)
    conn.execute("BEGIN")
    try:
        for track_id, fields in meta.items():
            if fields.get("artist") is not None:
                conn.execute(
                    "UPDATE plays SET title = ?, artist = ?"
                    " WHERE spotify_track_id = ?",
                    (fields.get("title"), fields["artist"], track_id),
                )
                resolved += 1
            elif conn.execute(
                "UPDATE plays SET title = ?"
                " WHERE spotify_track_id = ? AND title IS NULL",
                (fields.get("title"), track_id),
            ).rowcount:
                resolved += 1
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return resolved


def _cluster(plays: list[dict]) -> list[dict]:
    """plays (any order) -> clusters with plays, session ids and cuts."""
    gap = timedelta(minutes=GAP_MINUTES)
    by_session = {}
    for play in sorted(plays, key=lambda p: (p["played_at"], p["track_no"] or 0)):
        by_session.setdefault(play["rb_history_id"], []).append(play)

    segments = []  # a segment is session-pure: split one session on long gaps
    for rows in by_session.values():
        current = [rows[0]]
        for play in rows[1:]:
            if _parse(play["played_at"]) - _parse(current[-1]["played_at"]) > gap:
                segments.append(current)
                current = [play]
            else:
                current.append(play)
        segments.append(current)
    segments.sort(key=lambda seg: seg[0]["played_at"])

    def _bulk(seg) -> bool:
        if len(seg) < 3:
            return False
        span = _parse(seg[-1]["played_at"]) - _parse(seg[0]["played_at"])
        return span.total_seconds() < BULK_SECONDS_PER_TRACK * (len(seg) - 1)

    clusters = []
    for seg in segments:
        start = _parse(seg[0]["played_at"])
        # merge into the latest-ending compatible cluster: after it (overlap =
        # two machines at once, NEVER merged) and within one gap (crash/restart)
        target = None
        if not _bulk(seg):
            for cluster in clusters:
                if cluster["bulk"]:
                    continue  # import-time timestamps: nothing may attach
                end = _parse(cluster["plays"][-1]["played_at"])
                if end <= start <= end + gap:
                    if target is None or cluster["plays"][-1]["played_at"] > (
                        target["plays"][-1]["played_at"]
                    ):
                        target = cluster
        if target is None:
            clusters.append({"plays": seg, "cuts": [], "bulk": _bulk(seg)})
            continue
        if seg[0]["rb_history_id"] != target["plays"][-1]["rb_history_id"]:
            target["cuts"].append(
                {
                    "ended": target["plays"][-1]["played_at"],
                    "resumed": seg[0]["played_at"],
                }
            )
        target["plays"].extend(seg)
    clusters.sort(key=lambda c: c["plays"][0]["played_at"])
    return clusters


def rebuild(conn) -> None:
    """Recompute performances from plays; name/hidden survive through the
    anchor (first play UUID). ponytail: full recluster every time - 6.5k plays
    take ~50 ms; make it incremental only if the archive grows 100x."""
    plays = [
        dict(row)
        for row in conn.execute(
            "SELECT uuid, rb_history_id, played_at, track_no FROM plays"
        )
    ]
    clusters = _cluster(plays) if plays else []
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat(" ")
    conn.execute("BEGIN")
    try:
        anchors = []
        for cluster in clusters:
            rows = cluster["plays"]
            anchor = rows[0]["uuid"]
            anchors.append(anchor)
            conn.execute(
                "INSERT INTO performances (anchor_uuid, started_at, ended_at,"
                " track_count, session_count, cuts, bulk_import, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(anchor_uuid) DO UPDATE SET"
                " started_at = excluded.started_at, ended_at = excluded.ended_at,"
                " track_count = excluded.track_count,"
                " session_count = excluded.session_count,"
                " cuts = excluded.cuts, bulk_import = excluded.bulk_import,"
                " updated_at = excluded.updated_at",
                (
                    anchor,
                    rows[0]["played_at"],
                    rows[-1]["played_at"],
                    len(rows),
                    len({p["rb_history_id"] for p in rows}),
                    json.dumps(cluster["cuts"]),
                    int(cluster["bulk"]),
                    now,
                ),
            )
            performance_id = conn.execute(
                "SELECT id FROM performances WHERE anchor_uuid = ?", (anchor,)
            ).fetchone()[0]
            conn.executemany(
                "UPDATE plays SET performance_id = ? WHERE uuid = ?",
                [(performance_id, p["uuid"]) for p in rows],
            )
        # ponytail: a late-merging session can steal a cluster's anchor; the
        # orphaned row (and its custom name) is dropped rather than re-matched
        placeholders = ",".join("?" for _ in anchors) or "''"
        conn.execute(
            f"DELETE FROM performances WHERE anchor_uuid NOT IN ({placeholders})",
            anchors,
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def refresh(conn, db_path, spotify_client=None, transport=None) -> dict:
    """Ingest+rebuild when master.db changed since the last look (the mutate
    fingerprint gates the expensive SQLCipher open), then always try to
    resolve pending Spotify titles. Reads only - safe while Rekordbox runs."""
    current = fingerprint(db_path)
    ingested = 0
    if _ingested.get(str(db_path)) != current:
        ingested = ingest(conn, read_rb_plays(db_path))
        rebuild(conn)
        _ingested[str(db_path)] = current
    resolved = resolve_spotify_titles(conn, spotify_client, transport)
    return {"ingested": ingested, "resolved_titles": resolved}


def list_performances(conn, include_hidden=False) -> list[dict]:
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT id, anchor_uuid, name, hidden, started_at, ended_at,"
            " track_count, session_count, cuts, bulk_import FROM performances"
            " ORDER BY started_at DESC"
        )
    ]
    for row in rows:
        row["cuts"] = json.loads(row.pop("cuts"))
        # overlap with ANY other performance = another machine played at the
        # same time on the shared account (device attribution is impossible
        # retroactively - flag it instead)
        row["overlaps"] = any(
            other is not row
            and other["started_at"] <= row["ended_at"]
            and row["started_at"] <= other["ended_at"]
            for other in rows
        )
    if not include_hidden:
        rows = [row for row in rows if not row["hidden"]]
    return rows


def get_performance(conn, performance_id: int) -> dict:
    row = conn.execute(
        "SELECT id, anchor_uuid, name, hidden, started_at, ended_at,"
        " track_count, session_count, cuts, bulk_import FROM performances WHERE id = ?",
        (performance_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"performance {performance_id} not found")
    performance = dict(row)
    performance["cuts"] = json.loads(performance.pop("cuts"))
    performance["tracks"] = performance_tracks(conn, performance_id)
    return performance


def performance_tracks(conn, performance_id: int) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT uuid, content_id, title, artist, spotify_track_id,"
            " played_at, rb_history_name FROM plays WHERE performance_id = ?"
            " ORDER BY played_at, track_no",
            (performance_id,),
        )
    ]


def export_plan(tracks, content_states) -> tuple[list[dict], int]:
    """Ordered export slots, first occurrence wins (Rekordbox refuses the
    same track twice in one playlist). content_states maps content_id ->
    {"deleted": bool, "spotify": bool}. Actions:
    - "keep": content is active, straight into the playlist;
    - "revive": soft-deleted SPOTIFY content - Rekordbox soft-deletes
      streaming rows after playback, reactivating restores the reference;
    - "missing": local file gone (or content row gone entirely) - the
      caller may still recover it as a streaming reference through the
      Syncbox spotify_links mapping (owner request 17/07).
    Returns (slots, duplicates)."""
    slots, seen = [], set()
    duplicates = 0
    for track in tracks:
        content_id = track.get("content_id")
        if content_id in seen:
            duplicates += 1
            continue
        if content_id:
            seen.add(content_id)
        state = content_states.get(content_id) if content_id else None
        if state is None or (state["deleted"] and not state["spotify"]):
            slots.append({"content_id": content_id, "action": "missing"})
        elif state["deleted"]:
            slots.append({"content_id": content_id, "action": "revive"})
        else:
            slots.append({"content_id": content_id, "action": "keep"})
    return slots, duplicates


def spotify_links(conn, content_ids) -> dict:
    """content_id -> (spotify_track_id, duration_ms) from Syncbox's own
    event/library mappings - the deterministic memory of which Spotify track
    a locally-deleted file came from. Event rows win over library rows."""
    if not content_ids:
        return {}
    placeholders = ",".join("?" for _ in content_ids)
    links = {}
    for table in ("library_tracks", "event_tracks"):  # events overwrite
        for content_id, track_id, duration in conn.execute(
            f"SELECT content_id, spotify_track_id, duration_ms FROM {table}"
            f" WHERE content_id IN ({placeholders})"
            f" AND spotify_track_id IS NOT NULL",
            list(content_ids),
        ):
            links[str(content_id)] = (track_id, duration)
    return links


def live_status(conn, now=None) -> dict:
    """Latest performance + its tracks; active while its last play is fresh.
    This is the crash-proof 'already played tonight' view."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    row = conn.execute(
        "SELECT id, name, hidden, started_at, ended_at, track_count,"
        " session_count, cuts, bulk_import FROM performances ORDER BY ended_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return {"active": False, "performance": None, "tracks": []}
    performance = dict(row)
    performance["cuts"] = json.loads(performance.pop("cuts"))
    active = _parse(performance["ended_at"]) >= now - timedelta(
        minutes=LIVE_WINDOW_MINUTES
    )
    return {
        "active": active,
        "performance": performance,
        "tracks": performance_tracks(conn, performance["id"]),
    }
