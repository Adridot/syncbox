"""Library sync diffing: Spotify playlist -> library track states
(SPEC-UNIFIED 5.6, statuses per section 4).

Two composable steps, both pure (no I/O):
- diff_tracks(): status bookkeeping against the previous sync state;
  fresh rows land as 'new';
- apply_matching(): runs the 5.3 matcher on rows still 'new', mapping
  matched -> matched, ambiguous -> conflict (library vocabulary; events
  use 'ambiguous', 5.7), no match -> missing.

Rules carried exactly (5.6): a Spotify duplicate inside one playlist ->
'ignored'; prior 'ignored'/'ready' carried as-is; prior 'imported'/
'matched' reconciled (linkage preserved, no re-match); everything else is
re-matched fresh; absent from the playlist -> 'removed_from_source'
(Rekordbox tracks and MyTags are never touched by that transition).
Fresh rows inherit the source's default tags.
"""

from syncbox.matching import match

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


def apply_matching(rows: list[dict], candidates: list[dict], **thresholds) -> list[dict]:
    """Match every 'new' row against the Rekordbox snapshot candidates."""
    out = []
    for row in rows:
        if row["status"] != "new":
            out.append(row)
            continue
        result = match(row["spotify"], candidates, **thresholds)
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
        out.append(updated)
    return out


def sync_source(
    previous: list[dict],
    spotify_tracks: list[dict],
    candidates: list[dict],
    source_tags: list[str],
    **thresholds,
) -> list[dict]:
    """Full sync pass for one source: diff then match."""
    return apply_matching(
        diff_tracks(previous, spotify_tracks, source_tags), candidates, **thresholds
    )
