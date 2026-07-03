"""Tests for library sync diffing (SPEC-UNIFIED 5.6)."""

from syncbox.sync import diff_tracks, sync_source

TAGS = ["House", "2026"]


def sp(track_id, title="Strobe", artist="deadmau5", duration_ms=200_000, isrc=None):
    return {
        "spotify_track_id": track_id,
        "title": title,
        "artist": artist,
        "duration_ms": duration_ms,
        "isrc": isrc,
    }


def prior(track_id, status, **kw):
    row = {"spotify_track_id": track_id, "status": status, "tags": ["Old"]}
    row.update(kw)
    return row


def by_id(rows):
    keyed = {}
    for row in rows:
        keyed.setdefault(row["spotify_track_id"], []).append(row)
    return keyed


def test_fresh_track_is_new_and_inherits_source_tags():
    rows = diff_tracks([], [sp("t1")], TAGS)
    assert rows[0]["status"] == "new"
    assert rows[0]["tags"] == TAGS
    assert rows[0]["tags"] is not TAGS  # copy, not shared reference


def test_playlist_internal_duplicate_is_ignored():
    rows = diff_tracks([], [sp("t1"), sp("t1")], TAGS)
    assert [r["status"] for r in rows] == ["new", "ignored"]


def test_ignored_and_ready_carried_as_is():
    previous = [prior("t1", "ignored"), prior("t2", "ready", content_id="c9")]
    rows = diff_tracks(previous, [sp("t1"), sp("t2")], TAGS)
    keyed = by_id(rows)
    assert keyed["t1"][0]["status"] == "ignored"
    assert keyed["t2"][0]["status"] == "ready"
    assert keyed["t2"][0]["content_id"] == "c9"
    assert keyed["t1"][0]["tags"] == ["Old"]  # carried rows keep their tags


def test_imported_and_matched_reconciled_not_rematched():
    previous = [
        prior("t1", "imported", content_id="c1"),
        prior("t2", "matched", content_id="c2", confidence=91),
    ]
    rows = diff_tracks(previous, [sp("t1"), sp("t2")], TAGS)
    keyed = by_id(rows)
    assert keyed["t1"][0]["status"] == "imported"
    assert keyed["t1"][0]["content_id"] == "c1"
    assert keyed["t2"][0]["status"] == "matched"
    assert keyed["t2"][0]["confidence"] == 91


def test_conflict_missing_and_new_are_rematched():
    previous = [
        prior("t1", "conflict"),
        prior("t2", "missing"),
        prior("t3", "new"),
    ]
    rows = diff_tracks(previous, [sp("t1"), sp("t2"), sp("t3")], TAGS)
    assert all(r["status"] == "new" for r in rows)
    # prior tags survive the re-match reset
    assert all(r["tags"] == ["Old"] for r in rows)


def test_absent_from_playlist_becomes_removed_from_source():
    previous = [prior("t1", "imported", content_id="c1"), prior("t2", "missing")]
    rows = diff_tracks(previous, [], TAGS)
    assert {r["spotify_track_id"]: r["status"] for r in rows} == {
        "t1": "removed_from_source",
        "t2": "removed_from_source",
    }
    keyed = by_id(rows)
    assert keyed["t1"][0]["content_id"] == "c1"  # RB linkage kept (5.6)


def test_full_sync_matches_fresh_rows():
    candidates = [
        {
            "content_id": "c1",
            "title": "Strobe",
            "artist": "deadmau5",
            "duration_ms": 200_000,
            "isrc": "X1",
        }
    ]
    rows = sync_source([], [sp("t1", isrc="X1"), sp("t2", title="Nothing Like It")],
                       candidates, TAGS)
    keyed = by_id(rows)
    assert keyed["t1"][0]["status"] == "matched"
    assert keyed["t1"][0]["match_method"] == "isrc"
    assert keyed["t1"][0]["confidence"] == 100
    assert keyed["t2"][0]["status"] == "missing"
    assert keyed["t2"][0]["content_id"] is None


def test_ambiguous_fresh_match_is_conflict_in_library_vocabulary():
    twins = [
        {"content_id": "c1", "title": "Strobe", "artist": "deadmau5",
         "duration_ms": 200_000, "isrc": None},
        {"content_id": "c2", "title": "Strobe", "artist": "deadmau5",
         "duration_ms": 200_050, "isrc": None},
    ]
    rows = sync_source([], [sp("t1")], twins, TAGS)
    assert rows[0]["status"] == "conflict"
    assert rows[0]["content_id"] == "c1"  # best is still linked
