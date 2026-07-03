"""Tests for the thin app-DB repositories (SPEC-UNIFIED 4/5.6, D22)."""

import re

import pytest

from syncbox import appdb, repos

PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M"  # 22 base62 chars


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    yield connection
    connection.close()


# --- sources -------------------------------------------------------------------


def test_add_source_validates_playlist_id_shape(conn):
    source = repos.add_source(conn, PLAYLIST_ID, name="Weekly", tags=["House"])
    assert source["spotify_playlist_id"] == PLAYLIST_ID
    assert source["status"] == "pending"
    assert source["enabled"] == 1
    assert source["tags"] == ["House"]  # JSON round-trip

    for bad in ("", "short", PLAYLIST_ID + "x", "id with spaces!!,,..22",
                f"https://open.spotify.com/playlist/{PLAYLIST_ID}"):
        with pytest.raises(ValueError):
            repos.add_source(conn, bad)


def test_add_source_duplicate_raises_value_error(conn):
    repos.add_source(conn, PLAYLIST_ID)
    with pytest.raises(ValueError, match="already followed"):
        repos.add_source(conn, PLAYLIST_ID)


def test_update_source_allowlists_columns(conn):
    source = repos.add_source(conn, PLAYLIST_ID)
    updated = repos.update_source(
        conn, source["id"], name="N", snapshot_id="snap", status="synced",
        tags=["A", "B"], enabled=False,
    )
    assert updated["name"] == "N"
    assert updated["snapshot_id"] == "snap"
    assert updated["status"] == "synced"
    assert updated["tags"] == ["A", "B"]
    assert updated["enabled"] == 0
    with pytest.raises(KeyError):
        repos.update_source(conn, source["id"], spotify_playlist_id="nope")


def test_remove_source_cascades_app_rows_only(conn):
    source = repos.add_source(conn, PLAYLIST_ID)
    repos.replace_source_tracks(
        conn, source["id"], [{"spotify_track_id": "t1", "status": "matched"}]
    )
    repos.record_sync_run(conn, source["id"], "s", "f", "snap", {})
    repos.remove_source(conn, source["id"])
    assert repos.get_source(conn, source["id"]) is None
    assert repos.list_source_tracks(conn, source["id"]) == []
    assert repos.list_sync_runs(conn, source["id"]) == []
    # 5.6: stop following only - this module has no master.db access at all.
    from pathlib import Path
    text = Path(repos.__file__).read_text()
    assert "pyrekordbox" not in text and "sqlcipher" not in text
    assert "rb_write" not in text and "safety.mutate" not in text


# --- library tracks --------------------------------------------------------------


def test_replace_source_tracks_upserts_on_stable_ids(conn):
    source = repos.add_source(conn, PLAYLIST_ID)
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {"spotify_track_id": "t1", "status": "new", "title": "A",
             "tags": ["House"]},
            {"spotify_track_id": "t2", "status": "missing", "title": "B"},
        ],
    )
    first = repos.list_source_tracks(conn, source["id"])
    assert [t["spotify_track_id"] for t in first] == ["t1", "t2"]
    assert first[0]["tags"] == ["House"]

    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {"spotify_track_id": "t1", "status": "matched", "content_id": "C1",
             "match_method": "isrc", "confidence": 100, "tags": ["House"]},
            {"spotify_track_id": "t2", "status": "removed_from_source"},
        ],
    )
    second = repos.list_source_tracks(conn, source["id"])
    # same row ids: upsert keyed on (source_id, spotify_track_id)
    assert [t["id"] for t in second] == [t["id"] for t in first]
    assert second[0]["status"] == "matched"
    assert second[0]["content_id"] == "C1"
    assert second[1]["status"] == "removed_from_source"


def test_set_track_status_into_ignored_stores_prior_once_d22(conn):
    source = repos.add_source(conn, PLAYLIST_ID)
    repos.replace_source_tracks(
        conn, source["id"], [{"spotify_track_id": "t1", "status": "matched"}]
    )
    track = repos.list_source_tracks(conn, source["id"])[0]

    ignored = repos.set_track_status(conn, track["id"], "ignored")
    assert ignored["status"] == "ignored"
    assert ignored["prior_status"] == "matched"
    # re-ignoring never overwrites the stored prior status
    again = repos.set_track_status(conn, track["id"], "ignored")
    assert again["prior_status"] == "matched"

    restored = repos.restore_track(conn, track["id"])
    assert restored["status"] == "matched"  # never 'new' (D22)
    assert restored["prior_status"] is None


def test_restore_without_prior_status_raises(conn):
    source = repos.add_source(conn, PLAYLIST_ID)
    repos.replace_source_tracks(
        conn, source["id"], [{"spotify_track_id": "t1", "status": "new"}]
    )
    track = repos.list_source_tracks(conn, source["id"])[0]
    with pytest.raises(ValueError):
        repos.restore_track(conn, track["id"])
    with pytest.raises(KeyError):
        repos.set_track_status(conn, 99999, "ignored")


# --- sync runs -------------------------------------------------------------------


def test_sync_runs_history_newest_first_with_json_stats(conn):
    source = repos.add_source(conn, PLAYLIST_ID)
    repos.record_sync_run(conn, source["id"], "s1", "f1", "snap-1", {"total": 2})
    repos.record_sync_run(conn, source["id"], "s2", "f2", "snap-2", {"skipped": True})
    runs = repos.list_sync_runs(conn, source["id"])
    assert len(runs) == 2
    assert runs[0]["snapshot_id"] == "snap-2"  # newest first
    assert runs[0]["stats"] == {"skipped": True}
    assert runs[1]["stats"] == {"total": 2}
    assert len(repos.list_sync_runs(conn, source["id"], limit=1)) == 1


# --- dismissed duplicate groups ---------------------------------------------------


def test_dismissed_groups_add_is_idempotent(conn):
    repos.add_dismissed_group(conn, "1|2|3")
    repos.add_dismissed_group(conn, "1|2|3")  # idempotent, no error
    repos.add_dismissed_group(conn, "4|5")
    dismissed = repos.list_dismissed_groups(conn)
    assert dismissed == {"1|2|3", "4|5"}
    assert isinstance(dismissed, set)  # dedup.find_duplicate_groups shape


# --- untagged patterns ------------------------------------------------------------


def test_untagged_patterns_crud_rejects_invalid_regex(conn):
    pattern_id = repos.add_untagged_pattern(conn, r"^promo\b")
    assert repos.list_untagged_patterns(conn) == [
        {"id": pattern_id, "pattern": r"^promo\b"}
    ]
    with pytest.raises(re.error):
        repos.add_untagged_pattern(conn, "[unclosed")
    with pytest.raises(ValueError):
        repos.add_untagged_pattern(conn, "   ")
    repos.remove_untagged_pattern(conn, pattern_id)
    assert repos.list_untagged_patterns(conn) == []
