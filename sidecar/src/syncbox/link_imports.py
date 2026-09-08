"""Durable, bounded event previews and atomic snapshot confirmation."""

import json
import re
import uuid

from syncbox import events_service
from syncbox.music_links import LinkError, parse_link

MAX_ITEMS = 1000
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
INACTIVE = {"removed", "ignored", "removed_upstream"}


def _json(value):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > MAX_MANIFEST_BYTES:
        raise LinkError("manifest_size_limit")
    return encoded


def _event(conn, event_id):
    event = events_service.get_event(conn, event_id)
    if event is None or event.get("delete_phase"):
        raise LinkError("event_unavailable")
    return event


def _decode(row):
    value = dict(row)
    for key in ("manifest", "selection", "result"):
        value[key] = json.loads(value[key]) if value[key] else None
    return value


def get(conn, event_id, import_id):
    _event(conn, event_id)
    row = conn.execute("SELECT * FROM event_link_imports WHERE event_id = ? AND id = ?", (event_id, import_id)).fetchone()
    if row is None:
        raise KeyError("link import not found")
    return _decode(row)


def list_imports(conn, event_id):
    _event(conn, event_id)
    # Full manifests are read individually; reopening never returns 50 large documents.
    return [dict(row) for row in conn.execute(
        "SELECT id, state, source_provider, resource_type, canonical_url, error, created_at, updated_at "
        "FROM event_link_imports WHERE event_id = ? AND state != 'dismissed' "
        "ORDER BY created_at DESC, rowid DESC LIMIT 50", (event_id,),
    )]


def start(conn, event_id, url, request_token, *, choice=None):
    _event(conn, event_id)
    if not isinstance(request_token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_token):
        raise LinkError("invalid_request_token")
    source = parse_link(url, choice=choice)
    prior = conn.execute("SELECT * FROM event_link_imports WHERE event_id = ? AND request_token = ?", (event_id, request_token)).fetchone()
    if prior:
        if prior["request_url"] != source["url"]:
            raise LinkError("request_identity_conflict")
        return _decode(prior)
    # Bound outstanding work only; a ready preview costs nothing until confirmed or dismissed.
    pending = conn.execute("SELECT COUNT(*) FROM event_link_imports WHERE state IN ('queued', 'resolving')").fetchone()[0]
    if pending >= 20:
        raise LinkError("pending_import_limit")
    import_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO event_link_imports (id, event_id, request_token, request_url, source_provider, resource_type, resource_id, canonical_url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (import_id, event_id, request_token, source["url"], source["provider"], source["resource_type"], source["resource_id"], source["url"]),
    )
    return get(conn, event_id, import_id)


def claim(conn, claimant):
    row = conn.execute(
        "UPDATE event_link_imports SET state = 'resolving', claimed_by = ?, error = NULL, updated_at = datetime('now') "
        "WHERE id = (SELECT i.id FROM event_link_imports i JOIN events e ON e.id = i.event_id "
        "WHERE i.state = 'queued' AND e.delete_phase IS NULL ORDER BY i.created_at, i.rowid LIMIT 1) RETURNING *", (claimant,),
    ).fetchone()
    return _decode(row) if row else None


def normalized_manifest(manifest):
    source = parse_link(manifest["url"])
    if source["resource_type"] == "share" or source["provider"] != manifest.get("provider"):
        raise LinkError("invalid_manifest_source")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise LinkError("collection_empty_or_inaccessible")
    if len(entries) > MAX_ITEMS:
        raise LinkError("collection_item_limit")
    clean = []
    for position, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise LinkError("invalid_manifest_entry")
        item = entry.get("item_id")
        available = entry.get("available") is True
        url = None
        if available:
            child = parse_link(entry.get("url"))
            pattern = r"[A-Za-z0-9]{22}" if source["provider"] == "spotify" else r"[A-Za-z0-9_-]{11}" if source["provider"] == "youtube" else r"[1-9][0-9]{0,19}"
            if not isinstance(item, str) or not re.fullmatch(pattern, item) or child["provider"] != source["provider"] or child["resource_type"] != "track" or (child["resource_id"] and child["resource_id"] != item):
                raise LinkError("invalid_manifest_identity")
            url = child["url"]
        else:
            item = str(item)[:150] if item is not None else None
        value = {"entry_key": f"{position}:{item or ''}", "position": position, "provider": source["provider"],
                 "item_id": item, "url": url, "available": available}
        for field in ("title", "artist", "isrc"):
            text = entry.get(field)
            value[field] = text[:1000] if isinstance(text, str) else None
        duration = entry.get("duration_ms")
        if duration is None and isinstance(entry.get("duration_seconds"), (int, float)):
            duration = entry["duration_seconds"] * 1000
        value["duration_ms"] = int(duration) if isinstance(duration, (int, float)) and 0 < duration < 24 * 3600 * 1000 else None
        clean.append(value)
    if source["resource_type"] == "track" and (len(clean) != 1 or (source["resource_id"] and clean[0]["item_id"] != source["resource_id"])):
        raise LinkError("invalid_manifest_identity")
    return {**source, "resource_id": str(manifest.get("resource_id") or source["resource_id"] or "")[:150],
            "title": str(manifest.get("title") or "")[:1000], "entries": clean}


def finish(conn, import_id, claimant, *, manifest=None, error=None):
    clean = normalized_manifest(manifest) if manifest is not None else None
    row = conn.execute("SELECT source_provider, request_url FROM event_link_imports WHERE id = ?", (import_id,)).fetchone()
    if clean and row:
        requested = parse_link(row["request_url"])
        if clean["provider"] != row["source_provider"] or (requested["resource_type"] != "share" and clean["url"] != requested["url"]):
            clean, error = None, "invalid_manifest_source"
    encoded = _json(clean) if clean else None
    # Compare-and-set both claim and event ownership: dismissal/deletion wins over late completion.
    return conn.execute(
        "UPDATE event_link_imports SET state = ?, manifest = ?, error = ?, claimed_by = NULL, "
        "canonical_url = COALESCE(?, canonical_url), resource_type = COALESCE(?, resource_type), resource_id = COALESCE(?, resource_id), "
        "updated_at = datetime('now') WHERE id = ? AND state = 'resolving' AND claimed_by = ? "
        "AND EXISTS (SELECT 1 FROM events WHERE events.id = event_link_imports.event_id AND delete_phase IS NULL)",
        ("ready" if clean else "failed", encoded, error, clean.get("url") if clean else None,
         clean.get("resource_type") if clean else None, clean.get("resource_id") if clean else None, import_id, claimant),
    ).rowcount == 1


def retry(conn, event_id, import_id):
    row = get(conn, event_id, import_id)
    if row["state"] != "failed":
        raise LinkError("import_not_retryable")
    conn.execute("UPDATE event_link_imports SET state = 'queued', error = NULL, claimed_by = NULL, updated_at = datetime('now') WHERE id = ?", (import_id,))
    return get(conn, event_id, import_id)


def dismiss(conn, event_id, import_id):
    row = get(conn, event_id, import_id)
    if row["state"] == "committed":
        raise LinkError("committed_import_immutable")
    conn.execute("UPDATE event_link_imports SET state = 'dismissed', claimed_by = NULL, manifest = NULL, error = NULL, updated_at = datetime('now') WHERE id = ?", (import_id,))
    return get(conn, event_id, import_id)


def commit(conn, event_id, import_id, selected_keys, *, readd_keys=None):
    if not isinstance(selected_keys, list) or not 0 < len(selected_keys) <= MAX_ITEMS or any(not isinstance(k, str) for k in selected_keys):
        raise LinkError("invalid_import_selection")
    readd_keys = readd_keys or []
    if not isinstance(readd_keys, list) or any(not isinstance(k, str) for k in readd_keys) or not set(readd_keys) <= set(selected_keys):
        raise LinkError("invalid_readd_selection")
    selection = {"entries": sorted(set(selected_keys)), "readd": sorted(set(readd_keys))}
    conn.execute("SAVEPOINT link_import_commit")
    try:
        row = get(conn, event_id, import_id)
        if row["state"] == "committed":
            if row["selection"] != selection:
                raise LinkError("committed_selection_conflict")
            return row["result"]
        if row["state"] != "ready":
            raise LinkError("import_not_ready")
        entries = row["manifest"]["entries"]
        if not set(selected_keys) <= {e["entry_key"] for e in entries}:
            raise LinkError("unknown_entry_key")
        event = _event(conn, event_id)
        existing = events_service.list_event_tracks(conn, event_id)
        active, inactive = {}, {}
        for track in existing:
            key = (track["source_provider"] or ("spotify" if track["spotify_track_id"] else None), track["source_item_id"] or track["spotify_track_id"])
            (inactive if track["status"] in INACTIVE else active).setdefault(key, track)
        outcomes = []
        for entry in entries:
            key = entry["entry_key"]
            if key not in selection["entries"]:
                continue
            identity = (entry["provider"], entry["item_id"])
            track = active.get(identity)
            if not entry["available"]:
                outcome = "unavailable"
                track = None
            elif track:
                outcome = "already_present"
            elif identity in inactive and key not in readd_keys:
                outcome, track = "restore_or_readd_required", inactive[identity]
            else:
                track = events_service.add_track(conn, event, resolved_source={**entry, "import_id": import_id})
                active[identity] = track
                outcome = "added"
            outcomes.append({"entry_key": key, "outcome": outcome, "event_track_id": track["id"] if track else None})
        result = {"import_id": import_id, "event_id": event_id, "outcomes": outcomes,
                  "added": sum(o["outcome"] == "added" for o in outcomes)}
        conn.execute("UPDATE event_link_imports SET state = 'committed', selection = ?, result = ?, updated_at = datetime('now') WHERE id = ?",
                     (_json(selection), _json(result), import_id))
        return result
    except BaseException:
        conn.execute("ROLLBACK TO link_import_commit")
        raise
    finally:
        conn.execute("RELEASE link_import_commit")
