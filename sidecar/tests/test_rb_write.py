"""Tests for the Rekordbox write helpers (SPEC-01 1.1/1.6/1.7, POC 05).

signed32/smartlist tests are pure; the integration flow needs the real
fixture and runs the FULL mutate unit-of-work on a copy.
"""

import shutil
from pathlib import Path

import pytest

from syncbox import rb
from syncbox.rb_write import (
    _audio_metadata,
    add_content,
    audio_metadata,
    find_or_create_album,
    migrate_content_path,
    signed32,
    smartlist_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "sidecar" / "tests" / "testdata"
FIXTURE = TESTDATA / "master.db"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="real master.db fixture not present"
)


# --- pure: the OWNED conditional signed-32 conversion ---------------------------


def test_signed32_is_conditional_not_unconditional():
    # Spec example (SPEC-01 1.7) verified against real RB data in POC 05
    assert signed32(2662450573) == -1632516723
    # IDs < 2^31 STAY POSITIVE - pyrekordbox's unconditional shift is the
    # #110-family quirk Syncbox must not reproduce
    assert signed32(1248102774) == 1248102774
    assert signed32(2**31) == -(2**31)
    assert signed32(2**31 - 1) == 2**31 - 1


def test_smartlist_payload_shape():
    big_pl, big_tag = 3644759451, 2662450573
    payload = smartlist_payload(str(big_pl), str(big_tag))
    assert f'Id="{signed32(big_pl)}"' in payload  # -650207845
    assert f'ValueLeft="{signed32(big_tag)}"' in payload  # -1632516723
    assert 'Operator="8"' in payload  # contains

    small = smartlist_payload("1248102774", "999")
    assert 'Id="1248102774"' in small  # stays positive (real RB behavior)
    assert 'ValueLeft="999"' in small


def test_add_content_rejects_a_missing_staged_file_before_writing(tmp_path):
    with pytest.raises(FileNotFoundError, match="staged audio file is unavailable"):
        add_content(object(), tmp_path / "gone.mp3", {}, storage_root=tmp_path)


def test_audio_metadata_reads_standard_tags_and_stream_properties(
    monkeypatch, tmp_path
):
    class Info:
        length = 123.456
        bitrate = 320_000
        bits_per_sample = 24
        sample_rate = 48_000

    class Audio:
        info = Info()
        tags = {
            "title": ["Title"],
            "artist": ["Artist"],
            "album": ["Album"],
            "albumartist": ["Album Artist"],
            "genre": ["House"],
            "composer": ["Composer"],
            "date": ["2026-08-03"],
            "tracknumber": ["7/12"],
            "discnumber": ["2/2"],
            "isrc": ["FRABC2600001"],
        }

    monkeypatch.setattr("syncbox.rb_write.MutagenFile", lambda *args, **kwargs: Audio())

    assert _audio_metadata(tmp_path / "track.mp3") == {
        "title": "Title",
        "artist": "Artist",
        "album": "Album",
        "album_artist": "Album Artist",
        "genre": "House",
        "composer": "Composer",
        "comment": None,
        "isrc": "FRABC2600001",
        "track_number": 7,
        "disc_number": 2,
        "release_date": "2026-08-03",
        "release_year": 2026,
        "duration_ms": 123456,
        "bit_rate": 320,
        "bit_depth": 24,
        "sample_rate": 48000,
    }


def test_audio_metadata_tolerates_a_missing_title_and_an_unreadable_file(
    monkeypatch, tmp_path
):
    """The three cases staged-file adoption relies on: complete tags (above),
    no usable title tag, and a file mutagen cannot read at all -> {}."""

    class Untitled:
        info = None
        tags = {"title": ["   "], "artist": ["Artist"]}  # blank = no usable title

    monkeypatch.setattr(
        "syncbox.rb_write.MutagenFile", lambda *args, **kwargs: Untitled()
    )
    untitled = audio_metadata(tmp_path / "track.mp3")
    assert untitled["title"] is None and untitled["artist"] == "Artist"
    assert untitled["duration_ms"] is None

    def boom(*args, **kwargs):
        raise OSError("cloud file unavailable")

    monkeypatch.setattr("syncbox.rb_write.MutagenFile", boom)
    assert audio_metadata(tmp_path / "track.mp3") == {}  # never raises
    monkeypatch.setattr("syncbox.rb_write.MutagenFile", lambda *a, **k: None)
    assert audio_metadata(tmp_path / "track.mp3") == {}


def test_album_identity_includes_album_artist():
    class Artist:
        ID = "artist-wanted"

    class Album:
        ID = "album-wanted"
        AlbumArtistID = "artist-wanted"
        rb_local_deleted = 0

    class SameTitleDifferentArtist:
        ID = "album-other"
        AlbumArtistID = "artist-other"
        rb_local_deleted = 0

    class Query:
        def filter_by(self, **values):
            assert values == {"Name": "Greatest Hits"}
            return self

        def all(self):
            return [SameTitleDifferentArtist(), Album()]

    class Database:
        def query(self, table):
            return Query()

    assert find_or_create_album(Database(), "Greatest Hits", Artist()).ID == "album-wanted"


def test_migrate_content_path_delegates_anlz_without_committing():
    class Row:
        FolderPath = "/old/Track.mp3"
        OrgFolderPath = "/old/Track.mp3"
        FileNameL = "Track.mp3"

    row = Row()

    class Query:
        def filter_by(self, **kwargs):
            assert kwargs == {"ID": "10"}
            return self

        def one(self):
            return row

    class DB:
        def __init__(self):
            self.calls = []

        def query(self, table):
            return Query()

        def get_anlz_paths(self, content):
            return {"DAT": Path("/analysis/ANLZ0000.DAT")}

        def update_content_path(self, content, path, **kwargs):
            self.calls.append((content, path, kwargs))

    db = DB()
    migrate_content_path(
        db,
        "10",
        "/Volume/rekordbox/Collection/Track.mp3",
        update_anlz=True,
        anlz_paths=[Path("/analysis/ANLZ0000.DAT")],
    )
    assert db.calls == [
        (
            row,
            "/Volume/rekordbox/Collection/Track.mp3",
            {"save": True, "check_path": False, "commit": False},
        )
    ]


def test_migrate_content_path_rejects_changed_analysis_file_set():
    class Row:
        FolderPath = "/old/Track.mp3"

    class Query:
        def filter_by(self, **kwargs):
            return self

        def one(self):
            return Row()

    class DB:
        def query(self, table):
            return Query()

        def get_anlz_paths(self, content):
            return {"DAT": Path("/analysis/ANLZ9999.DAT")}

        def update_content_path(self, *args, **kwargs):
            raise AssertionError("changed ANLZ set must abort before writing")

    with pytest.raises(ValueError, match="analysis files changed"):
        migrate_content_path(
            DB(),
            "10",
            "/Volume/rekordbox/Collection/Track.mp3",
            update_anlz=True,
            anlz_paths=[Path("/analysis/ANLZ0000.DAT")],
        )


def test_smartfix_writer_reassigns_shared_artist_references(monkeypatch):
    from syncbox import rb_write

    class Row:
        Title = "Old"
        ArtistID = "artist-old"
        RemixerID = None

    row = Row()

    class Query:
        def filter_by(self, **values):
            assert values == {"ID": "10"}
            return self

        def one(self):
            return row

    class Database:
        flushed = False

        def query(self, _table):
            return Query()

        def flush(self):
            self.flushed = True

    ids = {"New Artist": "artist-new", "Known Remixer": "remixer-known"}
    monkeypatch.setattr(
        rb_write,
        "find_or_create_artist",
        lambda _db, name: type("Artist", (), {"ID": ids[name]})(),
    )
    database = Database()
    rb_write.set_content_fields(
        database,
        "10",
        {"title": "New", "artist": "New Artist", "remixer": "Known Remixer"},
    )

    assert (row.Title, row.ArtistID, row.RemixerID) == (
        "New",
        "artist-new",
        "remixer-known",
    )
    assert database.flushed


# --- integration: full write flow through mutate on the real fixture ------------


@needs_fixture
def test_full_write_flow_through_mutate(tmp_path, monkeypatch):
    from syncbox.rb_write import (
        apply_tag_delta,
        create_or_repair_smart_playlist,
        ensure_playlist_folder,
        find_or_create_artist,
        find_or_create_mytag,
        open_rekordbox,
        soft_delete_content,
        reactivate_content,
        tag_content,
    )
    from syncbox.safety.mutate import mutate

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    shutil.copy2(TESTDATA / "masterPlaylists6.xml", live / "masterPlaylists6.xml")
    backups = tmp_path / "backups"

    cache = rb.SnapshotCache(db_path)
    rows = cache.get(tmp_path / "storage")
    target = rows[0]["content_id"]
    fingerprint_before = cache.current_fingerprint

    created = {}
    with mutate(
        db_path,
        backups,
        expected_fingerprint=fingerprint_before,
        open_db=open_rekordbox,
        invalidate_cache=cache.invalidate,
    ) as db:
        tag = find_or_create_mytag(db, "IT Event", "Situation")
        tag_content(db, target, tag.ID)
        tag_content(db, target, tag.ID)  # idempotent
        folder = ensure_playlist_folder(db, "Event Imports")
        playlist = create_or_repair_smart_playlist(db, "IT Event", folder.ID, tag.ID)
        created.update(tag_id=tag.ID, folder_id=folder.ID, playlist_id=playlist.ID)
        assert isinstance(playlist.ID, str) and isinstance(tag.ID, str)

    # cache invalidated by the unit-of-work
    assert cache.current_fingerprint is None

    # verify on disk through an independent read-only connection
    conn = rb.open_readonly(db_path)
    pl_row = conn.execute(
        "SELECT SmartList, Attribute, ParentID FROM djmdPlaylist WHERE ID = ?",
        (created["playlist_id"],),
    ).fetchone()
    assert pl_row[1] == 4 and pl_row[2] == created["folder_id"]
    assert f'Id="{signed32(int(created["playlist_id"]))}"' in pl_row[0]
    assert f'ValueLeft="{signed32(int(created["tag_id"]))}"' in pl_row[0]
    links = conn.execute(
        "SELECT COUNT(*) FROM djmdSongMyTag WHERE ContentID=? AND MyTagID=? "
        "AND rb_local_deleted=0",
        (target, created["tag_id"]),
    ).fetchone()[0]
    assert links == 1  # idempotent tagging created exactly one link
    conn.close()

    # --- repair path: same playlist reused, never duplicated (11.2) -----------
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        again = create_or_repair_smart_playlist(
            db, "IT Event", created["folder_id"], created["tag_id"]
        )
        assert again.ID == created["playlist_id"]

    # --- tag delta remove (D16) + soft-delete round trip -----------------------
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        apply_tag_delta(db, target, remove_tag_ids=[created["tag_id"]])
        soft_delete_content(db, target)

    conn = rb.open_readonly(db_path)
    link_deleted = conn.execute(
        "SELECT rb_local_deleted FROM djmdSongMyTag WHERE ContentID=? AND MyTagID=?",
        (target, created["tag_id"]),
    ).fetchone()[0]
    tuple_row = conn.execute(
        "SELECT rb_local_deleted, rb_local_synced, rb_data_status, "
        "rb_local_data_status FROM djmdContent WHERE ID=?",
        (target,),
    ).fetchone()
    conn.close()
    assert int(link_deleted) == 1  # delta remove = reversible soft delete
    assert tuple(int(x) for x in tuple_row) == (1, 0, 258, 0)  # exact 1.1 tuple

    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        reactivate_content(db, target)

    conn = rb.open_readonly(db_path)
    status = conn.execute(
        "SELECT rb_data_status, rb_local_deleted FROM djmdContent WHERE ID=?",
        (target,),
    ).fetchone()
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    assert tuple(int(x) for x in status) == (256, 0)
    assert integrity == "ok"

    # artist self-heal / find-or-create sanity
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        first = find_or_create_artist(db, "Syncbox IT Artist")
        second = find_or_create_artist(db, "Syncbox IT Artist")
        assert first.ID == second.ID

    # every mutation left a timestamped backup behind (5 mutate calls)
    assert len(list(backups.iterdir())) == 5


@needs_fixture
def test_reassign_memberships_moves_active_links_to_keeper(tmp_path):
    """SPEC-UNIFIED 5.4: dedup resolve relinks the loser's ACTIVE playlist
    and MyTag memberships onto the keeper before the loser is soft-deleted
    - REAL coverage on the fixture, not a monkeypatched stand-in."""
    from syncbox.rb_write import (
        find_or_create_mytag,
        open_rekordbox,
        reassign_memberships,
        soft_delete_content,
        tag_content,
    )
    from syncbox.safety.mutate import mutate

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    backups = tmp_path / "backups"

    cache = rb.SnapshotCache(db_path)
    rows = cache.get(tmp_path / "storage")
    loser = next(r for r in rows if r["playlist_count"] > 0)
    keeper = next(r for r in rows if r["content_id"] != loser["content_id"])

    # guarantee the loser also carries a MyTag link that must move
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        tag = find_or_create_mytag(db, "IT Dedup Tag", "Situation")
        tag_content(db, loser["content_id"], tag.ID)
        tag_id = str(tag.ID)

    conn = rb.open_readonly(db_path)
    loser_playlists = [
        str(pid)
        for (pid,) in conn.execute(
            "SELECT PlaylistID FROM djmdSongPlaylist"
            " WHERE ContentID = ? AND rb_local_deleted = 0",
            (loser["content_id"],),
        )
    ]
    loser_tags = [
        str(tid)
        for (tid,) in conn.execute(
            "SELECT MyTagID FROM djmdSongMyTag"
            " WHERE ContentID = ? AND rb_local_deleted = 0",
            (loser["content_id"],),
        )
    ]
    conn.close()
    assert loser_playlists and tag_id in loser_tags

    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        reassign_memberships(db, loser["content_id"], keeper["content_id"])
        soft_delete_content(db, loser["content_id"])

    conn = rb.open_readonly(db_path)
    # loser: NO active membership survives
    for table in ("djmdSongPlaylist", "djmdSongMyTag"):
        left = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
            " WHERE ContentID = ? AND rb_local_deleted = 0",
            (loser["content_id"],),
        ).fetchone()[0]
        assert left == 0
    # keeper: exactly ONE active link per playlist/tag the loser had (5.4)
    for pid in loser_playlists:
        active = conn.execute(
            "SELECT TrackNo FROM djmdSongPlaylist"
            " WHERE ContentID = ? AND PlaylistID = ? AND rb_local_deleted = 0",
            (keeper["content_id"], pid),
        ).fetchall()
        assert len(active) == 1
        assert int(active[0][0] or 0) >= 1  # a real TrackNo, never 0
    for tid in loser_tags:
        active = conn.execute(
            "SELECT COUNT(*) FROM djmdSongMyTag"
            " WHERE ContentID = ? AND MyTagID = ? AND rb_local_deleted = 0",
            (keeper["content_id"], tid),
        ).fetchone()[0]
        assert active == 1
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()

    # idempotent: the consent-retry re-run (loser already soft-deleted with
    # no active links) changes nothing
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        reassign_memberships(db, loser["content_id"], keeper["content_id"])

    conn = rb.open_readonly(db_path)
    for pid in loser_playlists:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM djmdSongPlaylist"
                " WHERE ContentID = ? AND PlaylistID = ? AND rb_local_deleted = 0",
                (keeper["content_id"], pid),
            ).fetchone()[0]
            == 1
        )
    conn.close()


@needs_fixture
def test_smartfixes_runner_end_to_end(tmp_path):
    from syncbox import smartfixes_run
    from syncbox.safety.mutate import StaleSnapshotError

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    backups = tmp_path / "backups"
    cache = rb.SnapshotCache(db_path)

    dry = smartfixes_run.dry_run(cache, tmp_path / "storage")
    assert dry["fingerprint"] is not None
    # The representative fixture must contain at least one supported fix.
    assert len(dry["payload"]) > 0
    assert all(c["before"] != c["after"] for c in dry["payload"])
    assert smartfixes_run.dry_run(cache, tmp_path / "storage") == dry

    result = smartfixes_run.execute(db_path, backups, cache, tmp_path / "storage", dry)
    assert result["fields_applied"] == len(dry["payload"])

    written = {
        row["content_id"]: row
        for row in cache.get(tmp_path / "storage")
    }
    for change in dry["payload"]:
        assert written[change["content_id"]][change["field"]] == change["after"]
    assert len(list(backups.iterdir())) == 1

    # idempotence: a fresh dry-run after mutate is empty (5.11)
    dry2 = smartfixes_run.dry_run(cache, tmp_path / "storage")
    assert dry2["payload"] == []

    # freshness guard: stale dry-run against a changed DB aborts pre-backup
    with open(db_path, "ab") as f:
        f.write(b"x")
    with pytest.raises(StaleSnapshotError):
        smartfixes_run.execute(db_path, backups, cache, tmp_path / "storage", dry)
