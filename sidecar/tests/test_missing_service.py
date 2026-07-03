"""Tests for the unified 3-scope missing center (SPEC-UNIFIED 4/5.5, D22)."""

import shutil
from pathlib import Path

import pytest

from syncbox import appdb, missing_service, repos
from syncbox.missing_service import (
    AnlzConsentRequired,
    list_missing,
    relink_collection_file,
    restore_missing,
    set_missing_status,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "poc" / "testdata"
FIXTURE = TESTDATA / "master.db"
PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="real master.db fixture not present"
)


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    yield connection
    connection.close()


def seed_library(conn, statuses):
    source = repos.add_source(conn, PLAYLIST_ID)
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {"spotify_track_id": f"t{i}", "status": status,
             "title": f"Song {i}", "artist": "deadmau5", "isrc": f"ISRC{i}"}
            for i, status in enumerate(statuses)
        ],
    )
    return repos.list_source_tracks(conn, source["id"])


def seed_event_track(conn, status="missing"):
    slug = f"wedding-{status}"
    conn.execute(
        "INSERT INTO events (name, slug, default_tag) VALUES ('Wedding', ?, 'Wedding')",
        (slug,),
    )
    event_id = conn.execute(
        "SELECT id FROM events WHERE slug = ?", (slug,)
    ).fetchone()["id"]
    cursor = conn.execute(
        "INSERT INTO event_tracks (event_id, title, artist, status) "
        "VALUES (?, 'First Dance', 'Artist', ?)",
        (event_id, status),
    )
    return cursor.lastrowid


class FakeCache:
    def __init__(self, rows):
        self.rows = rows
        self.invalidations = 0

    def get(self, storage_root):
        return self.rows

    def invalidate(self):
        self.invalidations += 1


# --- list_missing -------------------------------------------------------------------


def test_library_scope_lists_missing_family_only_with_gated_links(conn):
    seed_library(
        conn,
        ["missing", "purchase_link_unavailable", "manual_relink_needed",
         "matched", "removed_from_source", "ignored"],
    )
    entries = list_missing(conn, "library")
    assert [e["status"] for e in entries] == [
        "missing", "purchase_link_unavailable", "manual_relink_needed"
    ]
    # B2 gate: missing + purchase_link_unavailable get links; the
    # manual_relink_needed failure does not (5.13), and removed_from_source
    # never even reaches the center (excluded above).
    assert len(entries[0]["purchase_links"]) == 2
    assert {l["store"] for l in entries[0]["purchase_links"]} == {"Beatport", "Bandcamp"}
    assert len(entries[1]["purchase_links"]) == 2
    assert entries[2]["purchase_links"] == []


def test_event_scope_lists_missing_event_tracks(conn):
    seed_event_track(conn, "missing")
    seed_event_track(conn, "applied")
    entries = list_missing(conn, "event")
    assert len(entries) == 1
    assert entries[0]["scope"] == "event"
    assert entries[0]["title"] == "First Dance"
    assert len(entries[0]["purchase_links"]) == 2


def test_collection_scope_reads_snapshot_file_missing_rows(conn, tmp_path):
    cache = FakeCache(
        [
            {"content_id": "C1", "title": "Ghost", "artist": "deadmau5",
             "isrc": None, "file_missing": True, "file_path": "/gone.mp3"},
            {"content_id": "C2", "title": "Here", "artist": "x",
             "isrc": None, "file_missing": False, "file_path": "/here.mp3"},
        ]
    )
    entries = list_missing(
        conn, "collection", cache=cache, storage_root=tmp_path / "storage"
    )
    assert [e["content_id"] for e in entries] == ["C1"]
    assert entries[0]["status"] == "missing"
    assert len(entries[0]["purchase_links"]) == 2

    with pytest.raises(ValueError):
        list_missing(conn, "collection")  # requires cache + storage_root
    with pytest.raises(ValueError):
        list_missing(conn, "nope")


def test_relink_candidates_come_from_inbox_and_user_roots(conn, tmp_path):
    tracks = seed_library(conn, ["missing"])
    storage = tmp_path / "storage"
    inbox = storage / "_rekordbox_sync" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "deadmau5 - Song 0.mp3").write_bytes(b"\x00")
    user_dir = tmp_path / "downloads"
    user_dir.mkdir()
    (user_dir / "deadmau5 - Song 0 (extended).mp3").write_bytes(b"\x00")

    entries = list_missing(
        conn, "library", storage_root=storage, user_roots=[user_dir]
    )
    paths = [c["path"] for c in entries[0]["relink_candidates"]]
    assert any("inbox" in p for p in paths)
    assert any("downloads" in p for p in paths)
    assert tracks[0]["status"] == "missing"

    # without roots there is no scan at all
    no_roots = list_missing(conn, "library")
    assert no_roots[0]["relink_candidates"] == []


# --- status transitions (5.5 + D22) ---------------------------------------------------


def test_transitions_missing_to_resolutions_and_failures(conn):
    tracks = seed_library(conn, ["missing", "missing", "missing"])
    assert set_missing_status(conn, "library", tracks[0]["id"], "purchase_linked")[
        "status"
    ] == "purchase_linked"
    assert set_missing_status(conn, "library", tracks[1]["id"], "relinked")[
        "status"
    ] == "relinked"
    failed = set_missing_status(
        conn, "library", tracks[2]["id"], "purchase_link_unavailable"
    )
    assert failed["status"] == "purchase_link_unavailable"
    # a failure status is still missing-family: it can be resolved later
    assert set_missing_status(conn, "library", tracks[2]["id"], "relinked")[
        "status"
    ] == "relinked"


def test_ignored_stores_prior_and_restore_returns_it_never_new(conn):
    tracks = seed_library(conn, ["missing"])
    ignored = set_missing_status(conn, "library", tracks[0]["id"], "ignored")
    assert ignored["status"] == "ignored"
    assert ignored["prior_status"] == "missing"
    restored = restore_missing(conn, "library", tracks[0]["id"])
    assert restored["status"] == "missing"  # never 'new' (D22)
    assert restored["prior_status"] is None
    with pytest.raises(ValueError):
        restore_missing(conn, "library", tracks[0]["id"])  # nothing stored


def test_event_scope_transitions_share_the_same_rules(conn):
    row_id = seed_event_track(conn, "missing")
    assert set_missing_status(conn, "event", row_id, "ignored")["prior_status"] == "missing"
    assert restore_missing(conn, "event", row_id)["status"] == "missing"


def test_invalid_transitions_are_rejected(conn):
    tracks = seed_library(conn, ["matched", "missing"])
    with pytest.raises(ValueError, match="not a missing-family"):
        set_missing_status(conn, "library", tracks[0]["id"], "purchase_linked")
    with pytest.raises(ValueError, match="invalid missing resolution"):
        set_missing_status(conn, "library", tracks[1]["id"], "imported")
    with pytest.raises(ValueError):
        set_missing_status(conn, "collection", 1, "relinked")
    with pytest.raises(KeyError):
        set_missing_status(conn, "library", 99999, "relinked")


# --- relink_collection_file -----------------------------------------------------------


def test_relink_requires_anlz_consent_before_touching_anything(tmp_path):
    cache = FakeCache([])
    with pytest.raises(AnlzConsentRequired):
        relink_collection_file(
            tmp_path / "master.db", tmp_path / "backups", cache,
            tmp_path / "storage", "C1", tmp_path / "new.mp3",
            anlz_consent=False,
        )
    assert not (tmp_path / "backups").exists()  # gate fired first: no backup
    assert cache.invalidations == 0


def test_relink_requires_an_existing_local_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        relink_collection_file(
            tmp_path / "master.db", tmp_path / "backups", FakeCache([]),
            tmp_path / "storage", "C1", tmp_path / "not-there.mp3",
            anlz_consent=True,
        )
    assert not (tmp_path / "backups").exists()


@needs_fixture
def test_relink_collection_file_writes_stored_form_and_preserves_links(tmp_path):
    from syncbox import rb

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    backups = tmp_path / "backups"
    storage = tmp_path / "storage"

    cache = rb.SnapshotCache(db_path)
    rows = cache.get(storage)
    # prefer a row that actually has tag/cue/playlist links to protect
    target = max(
        rows,
        key=lambda r: (r["tag_count"] + r["cue_count"] + r["playlist_count"]),
    )
    content_id = target["content_id"]
    links_before = (target["tag_count"], target["cue_count"], target["playlist_count"])
    assert sum(links_before) > 0  # the preservation assertion must bite

    # target file under <storage_root>/rekordbox/ -> MUST be stored
    # volume-relative (3.2)
    new_file = storage / "rekordbox" / "Collection" / "Relinked.mp3"
    new_file.parent.mkdir(parents=True)
    new_file.write_bytes(b"\x00")

    stored = relink_collection_file(
        db_path, backups, cache, storage, content_id, new_file, anlz_consent=True
    )
    assert stored == f"/{storage.name}/rekordbox/Collection/Relinked.mp3"
    # mutate invalidated the snapshot cache on commit
    assert cache.current_fingerprint is None

    # on-disk: FolderPath is the stored form, nothing else moved
    ro = rb.open_readonly(db_path)
    folder_path, title = ro.execute(
        "SELECT FolderPath, Title FROM djmdContent WHERE ID = ?", (content_id,)
    ).fetchone()
    counts = tuple(
        ro.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ContentID = ? AND rb_local_deleted = 0",
            (content_id,),
        ).fetchone()[0]
        for table in ("djmdSongMyTag", "djmdCue", "djmdSongPlaylist")
    )
    integrity = ro.execute("PRAGMA integrity_check").fetchone()[0]
    ro.close()

    assert folder_path == stored
    assert title == target["title"]  # only FolderPath changed
    assert counts == links_before  # cues/tags/playlists preserved (5.5)
    assert integrity == "ok"
    assert len(list(backups.iterdir())) == 1  # mutate left its backup

    # the refreshed snapshot resolves the new path and sees the file present
    fresh = {r["content_id"]: r for r in cache.get(storage)}[content_id]
    assert fresh["file_path"] == stored
    assert fresh["file_missing"] is False
