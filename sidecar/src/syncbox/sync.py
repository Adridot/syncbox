"""Library sync diffing: Spotify playlist -> library track states
(SPEC-UNIFIED 5.6, statuses per section 4).

Three composable steps, all pure (no I/O):
- diff_tracks(): status bookkeeping against the previous sync state;
  fresh rows land as 'new';
- reconcile_links(): preserves eligible persisted links and rematches only
  links whose Rekordbox target is no longer a local candidate;
- apply_matching(): runs the 5.3 matcher on rows still 'new', mapping
  matched -> matched, ambiguous -> conflict (library vocabulary; events
  use 'ambiguous', 5.7), no match -> missing.

Rules carried exactly (5.6): a Spotify duplicate inside one playlist ->
'ignored'; prior 'ignored'/'ready' carried as-is; prior 'imported'/
'matched' carried into reconciliation (valid linkage is preserved without
re-matching); everything else is re-matched fresh; absent from the playlist ->
'removed_from_source'
(Rekordbox tracks and MyTags are never touched by that transition).
Fresh rows inherit the source's default tags.
"""

from syncbox.matching import MatchResult, match

CARRIED_AS_IS = frozenset({"ignored", "ready"})
RECONCILED = frozenset({"imported", "matched"})


def diff_tracks(
    previous: list[dict], spotify_tracks: list[dict], source_tags: list[str]
) -> list[dict]:
    """Return the new library rows for one source.

    previous rows: {spotify_track_id, status, content_id?, confidence?,
    match_method?, tags, ...}; spotify tracks: {spotify_track_id, title,
    artist, duration_ms, isrc}.
    """
    prior = {row["spotify_track_id"]: row for row in previous}
    seen: set[str] = set()
    result: list[dict] = []

    for track in spotify_tracks:
        track_id = track["spotify_track_id"]
        if track_id in seen:
            # Spotify duplicate within the playlist: ignored, never matched.
            result.append(
                {
                    "spotify_track_id": track_id,
                    "status": "ignored",
                    "spotify": track,
                    "tags": list(source_tags),
                }
            )
            continue
        seen.add(track_id)

        old = prior.get(track_id)
        if old is not None and old["status"] in CARRIED_AS_IS | RECONCILED:
            carried = dict(old)
            carried["spotify"] = track
            result.append(carried)
        else:
            fresh = {
                "spotify_track_id": track_id,
                "status": "new",
                "spotify": track,
                "tags": list(old["tags"]) if old else list(source_tags),
            }
            result.append(fresh)

    # Absent from the playlist -> removed_from_source (unconditional, 5.6).
    for track_id, old in prior.items():
        if track_id not in seen:
            gone = dict(old)
            gone["status"] = "removed_from_source"
            result.append(gone)
    return result


def _apply_match_result(row: dict, result: MatchResult) -> dict:
    updated = dict(row)
    updated["confidence"] = result.confidence
    updated["match_method"] = result.method
    updated["content_id"] = result.content_id
    if result.status == "matched":
        updated["status"] = "matched"
    elif result.status == "ambiguous":
        updated["status"] = "conflict"  # library vocabulary (5.6)
    else:
        updated["status"] = "missing"
    return updated


def reconcile_links(
    rows: list[dict], candidates: list[dict], **thresholds
) -> tuple[list[dict], int]:
    """Revalidate persisted Rekordbox links against eligible local content.

    Valid ``matched`` and ``imported`` links are preserved exactly. Only a
    linked row whose target is absent is rematched, using fresh Spotify
    metadata from a playlist diff when present or its stored metadata on the
    unchanged-snapshot path. Spotify streaming references are not eligible
    local targets.
    """
    eligible = [
        candidate for candidate in candidates if not candidate.get("spotify_track_id")
    ]
    active_ids = {candidate["content_id"] for candidate in eligible}
    reconciled: list[dict] = []
    changed = 0

    for row in rows:
        content_id = row.get("content_id")
        if (
            row.get("status") not in RECONCILED
            or content_id is None
            or content_id in active_ids
        ):
            reconciled.append(row)
            continue

        spotify = row.get("spotify") or {
            key: row.get(key) for key in ("title", "artist", "duration_ms", "isrc")
        }
        result = match(spotify, eligible, **thresholds)
        reconciled.append(_apply_match_result(row, result))
        changed += 1

    return reconciled, changed


def apply_matching(rows: list[dict], candidates: list[dict], **thresholds) -> list[dict]:
    """Match every 'new' row against the Rekordbox snapshot candidates."""
    out = []
    for row in rows:
        if row["status"] != "new":
            out.append(row)
            continue
        result = match(row["spotify"], candidates, **thresholds)
        out.append(_apply_match_result(row, result))
    return out


def sync_source(
    previous: list[dict],
    spotify_tracks: list[dict],
    candidates: list[dict],
    source_tags: list[str],
    **thresholds,
) -> list[dict]:
    """Full sync pass for one source: diff, reconcile persisted links, match new."""
    eligible = [
        candidate for candidate in candidates if not candidate.get("spotify_track_id")
    ]
    rows = diff_tracks(previous, spotify_tracks, source_tags)
    rows, _ = reconcile_links(rows, eligible, **thresholds)
    return apply_matching(rows, eligible, **thresholds)
