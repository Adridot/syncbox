"""Library sync orchestration: Spotify playlist sources -> app DB ->
Rekordbox import (SPEC-UNIFIED 5.6, statuses per section 4).

sync_one_source() drives the pure sync.sync_source diff/match pipeline with
real I/O around it: paginated playlist fetch through the 5.9-retrying
SpotifyClient, snapshot_id short-circuit (a run is recorded either way),
persistence through repos.

apply_to_rekordbox() is the ONLY bridge from library rows into master.db:
- rows must be 'matched'/'ready' (5.6) - anything else is a ConflictError
  (the HTTP layer maps it to 409);
- the library MyTags (source.tags) must PRE-EXIST in master.db (5.6):
  Syncbox never auto-creates library tags - a missing one is a
  ConflictError naming it;
- all tagging happens inside ONE safety.mutate() unit-of-work, as D16 add
  deltas (apply_tag_delta - never a union overwrite); app-DB rows flip to
  'imported' only AFTER the master.db commit is durable (re-applying after
  a mid-flight failure is safe: tag_content is idempotent).
"""

from datetime import datetime

from syncbox import repos
from syncbox.rb import open_readonly
from syncbox.rb_write import (
    add_content,
    apply_tag_delta,
    find_active_content_by_path,
    open_rekordbox,
)
from syncbox.safety.mutate import mutate
from syncbox.safety.paths import stored_form
from syncbox.sync import sync_source

IMPORTABLE_STATUSES = frozenset({"matched", "ready"})


class ConflictError(RuntimeError):
    """Precondition failed (wrong row status, missing MyTag) - HTTP 409."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _spotify_track(item: dict) -> dict | None:
    """Map one playlist item to the matcher's track shape; None for
    unplayable items (removed tracks, episodes, local files without id)."""
    item = item or {}
    track = item.get("item") or item.get("track") or {}
    if not track.get("id") or track.get("type") not in (None, "track"):
        return None
    return {
        "spotify_track_id": track["id"],
        "title": track.get("name"),
        "artist": ", ".join(
            a.get("name") for a in track.get("artists", ()) if a.get("name")
        ),
        "duration_ms": track.get("duration_ms"),
        # D20: only the isrc field - NEVER the barcode tag as an ISRC stand-in.
        "isrc": (track.get("external_ids") or {}).get("isrc"),
    }


def _collect_tracks(spotify_client, first_payload: dict) -> list[dict]:
    """Flatten modern ``items/item`` or legacy ``tracks/track`` pages."""
    tracks: list[dict] = []
    page = first_payload.get("items")
    if not isinstance(page, dict):
        page = first_payload.get("tracks")
    if not isinstance(page, dict):
        raise ConflictError(
            "Spotify did not return playlist items; use a playlist owned by "
            "the connected account or one it collaborates on"
        )
    while True:
        items = page.get("items")
        if not isinstance(items, list):
            raise ConflictError("Spotify returned an invalid playlist items page")
        for item in items:
            mapped = _spotify_track(item)
            if mapped is not None:
                tracks.append(mapped)
        next_url = page.get("next")
        if not next_url:
            return tracks
        page = spotify_client.get(next_url)


def _to_db_row(row: dict) -> dict:
    """One sync.sync_source output row -> library_tracks column dict.

    Rows carrying fresh Spotify metadata refresh title/artist/duration/isrc;
    removed_from_source rows (no 'spotify' key) keep their stored fields.
    """
    spotify = row.get("spotify")
    out = {
        "spotify_track_id": row["spotify_track_id"],
        "status": row["status"],
        "content_id": row.get("content_id"),
        "match_method": row.get("match_method"),
        "confidence": row.get("confidence"),
        "staging_file_path": row.get("staging_file_path"),
        "tags": row.get("tags") or [],
        "prior_status": row.get("prior_status"),
    }
    fields = spotify if spotify is not None else row
    for column in ("title", "artist", "duration_ms", "isrc"):
        out[column] = fields.get(column)
    return out


def sync_one_source(conn, spotify_client, cache, storage_root, source, **thresholds):
    """Sync one followed playlist; returns {skipped, snapshot_id, stats}.

    A sync_run row is recorded EVEN when the snapshot_id is unchanged and
    the diff is skipped (5.6 history contract).
    """
    started = _now()
    payload = spotify_client.get(f"/playlists/{source['spotify_playlist_id']}")
    snapshot_id = payload.get("snapshot_id")

    if snapshot_id and snapshot_id == source.get("snapshot_id"):
        # cover backfill: sources followed before covers existed (0003) would
        # otherwise never get one — the skip path never reaches update_source
        images = payload.get("images") or []
        if images and not source.get("cover_url"):
            repos.update_source(conn, source["id"], cover_url=images[0].get("url"))
        stats = {"skipped": True}
        repos.record_sync_run(conn, source["id"], started, _now(), snapshot_id, stats)
        return {"skipped": True, "snapshot_id": snapshot_id, "stats": stats}

    spotify_tracks = _collect_tracks(spotify_client, payload)
    previous = repos.list_source_tracks(conn, source["id"])
    rows = sync_source(
        previous,
        spotify_tracks,
        # streaming references can never be the local file a track needs
        [r for r in cache.get(storage_root) if not r.get("spotify_track_id")],
        source["tags"],
        **thresholds,
    )
    # One DB row per (source, spotify_track_id) - section 4. diff_tracks
    # emits a trailing 'ignored' marker for a duplicate playlist OCCURRENCE
    # (5.6: the occurrence is ignored, never the track itself), so the FIRST
    # row - the track's real state - wins at persistence.
    db_rows, seen = [], set()
    for row in rows:
        if row["spotify_track_id"] in seen:
            continue
        seen.add(row["spotify_track_id"])
        db_rows.append(_to_db_row(row))
    repos.replace_source_tracks(conn, source["id"], db_rows)
    images = payload.get("images") or []
    repos.update_source(
        conn,
        source["id"],
        name=payload.get("name") or source["name"],
        snapshot_id=snapshot_id,
        status="synced",
        cover_url=(images[0].get("url") if images else None) or source.get("cover_url"),
    )
    stats = {"total": len(rows)}
    for row in rows:
        stats[row["status"]] = stats.get(row["status"], 0) + 1
    repos.record_sync_run(conn, source["id"], started, _now(), snapshot_id, stats)
    return {"skipped": False, "snapshot_id": snapshot_id, "stats": stats}


def _library_tag_ids(db_path, tag_names: list[str]) -> list[str]:
    """Resolve source.tags to ACTIVE MyTag ids; missing -> ConflictError.

    5.6: the library MyTags must pre-exist - Syncbox creates MyTags for
    events only, never silently for library sources. Read-only lookup;
    categories (ParentID='root') are not tags and never match.
    """
    if not tag_names:
        return []
    conn = open_readonly(db_path)
    try:
        found: dict[str, str] = {}
        for tag_id, name in conn.execute(
            "SELECT ID, Name FROM djmdMyTag "
            "WHERE rb_local_deleted = 0 AND ParentID != 'root'"
        ):
            found.setdefault(name, str(tag_id))
    finally:
        conn.close()
    missing = [name for name in tag_names if name not in found]
    if missing:
        raise ConflictError(
            "library MyTags must pre-exist in Rekordbox before applying; "
            f"missing: {missing}"
        )
    return [found[name] for name in tag_names]


def apply_to_rekordbox(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    source_id: int,
    track_ids: list[int],
    *,
    retention: int = 20,
    app_db_path=None,
) -> dict:
    """Import selected library rows: tag their Rekordbox content with the
    source's MyTags inside ONE mutate(), then mark them 'imported'."""
    source = repos.get_source(conn, source_id)
    if source is None:
        raise KeyError(f"source {source_id} not found")

    tracks = []
    for track_id in track_ids:
        track = repos.get_track(conn, track_id)
        if track is None or track["source_id"] != source_id:
            raise KeyError(f"track {track_id} not found in source {source_id}")
        tracks.append(track)

    wrong_status = [t for t in tracks if t["status"] not in IMPORTABLE_STATUSES]
    if wrong_status:
        raise ConflictError(
            "only matched/ready rows can be imported (5.6); refused: "
            + ", ".join(f"{t['id']}={t['status']}" for t in wrong_status)
        )
    unlinked = [
        t
        for t in tracks
        if not t["content_id"]
        and not (t["status"] == "ready" and t["staging_file_path"])
    ]
    if unlinked:
        raise ConflictError(
            "rows without a Rekordbox link or staged file cannot be imported: "
            + ", ".join(str(t["id"]) for t in unlinked)
        )

    tag_ids = _library_tag_ids(db_path, source["tags"])

    # Refresh the snapshot so mutate's freshness guard covers exactly what
    # this apply is based on (the cache invalidates itself on commit).
    cache.get(storage_root)
    imported: list[tuple[int, str]] = []
    with mutate(
        db_path,
        backups_root,
        retention=retention,
        expected_fingerprint=cache.current_fingerprint,
        open_db=open_rekordbox,
        invalidate_cache=cache.invalidate,
        app_db_path=app_db_path,
        backup_reason="library_apply",
    ) as db:
        for track in tracks:
            content_id = track["content_id"]
            if not content_id:
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
            # D16: tag edits are add/remove deltas, never a union overwrite.
            apply_tag_delta(db, content_id, add_tag_ids=tag_ids)
            imported.append((track["id"], str(content_id)))

    # Only after the durable master.db commit; a retry reuses the content row.
    conn.execute("BEGIN")
    try:
        for track_id, content_id in imported:
            conn.execute(
                "UPDATE library_tracks SET status = 'imported', content_id = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (content_id, track_id),
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {"imported": len(tracks), "tags_per_track": len(tag_ids)}
