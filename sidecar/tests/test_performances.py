"""Performance history: append-only ingest + deterministic clustering
(the 2026-07-04 crashed-gig shape is the reference scenario)."""

import json
from datetime import datetime

import pytest

from syncbox import appdb, performances
from syncbox.performances import (
    _norm_ts,
    export_plan,
    ingest,
    list_performances,
    live_status,
    rebuild,
    resolve_spotify_titles,
)


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    yield connection
    connection.close()


def play(uuid, session, played_at, **kw):
    return {
        "uuid": uuid,
        "rb_history_id": session,
        "rb_history_name": f"HISTORY {session}",
        "content_id": kw.get("content_id", "42"),
        "track_no": kw.get("track_no", 1),
        "title": kw.get("title", "Titre"),
        "artist": kw.get("artist", "Artiste"),
        "spotify_track_id": kw.get("spotify_track_id"),
        "played_at": played_at,
    }


def test_norm_ts():
    assert _norm_ts("2026-07-05 00:31:54.802 +00:00") == "2026-07-05 00:31:54"
    assert _norm_ts("garbage") is None
    # the '$A' scrub moved to spotify.scrub_obfuscated (tested there)


def test_ingest_is_append_only_and_deduped(conn):
    rows = [play("u1", "s1", "2026-07-04 22:00:00")]
    assert ingest(conn, rows) == 1
    # same UUID again (cloud re-sync), even with changed fields: kept as-is
    assert ingest(conn, [play("u1", "s1", "2026-07-04 23:59:00")]) == 0
    stored = conn.execute("SELECT played_at FROM plays").fetchall()
    assert [row["played_at"] for row in stored] == ["2026-07-04 22:00:00"]


def test_long_gap_splits_one_session_into_two_performances(conn):
    # warmup at 13:00, party from 22:14 - same Rekordbox session
    ingest(
        conn,
        [
            play("u1", "s1", "2026-07-04 13:00:00"),
            play("u2", "s1", "2026-07-04 13:20:00", track_no=2),
            play("u3", "s1", "2026-07-04 22:14:00", track_no=3),
        ],
    )
    rebuild(conn)
    result = list_performances(conn)
    assert len(result) == 2
    assert result[0]["started_at"] == "2026-07-04 22:14:00"  # newest first
    assert result[1]["track_count"] == 2


def test_crash_restart_re_joins_sessions_with_a_cut(conn):
    # the real 04/07 shape: session ends 00:22, new session 00:31 after a crash
    ingest(
        conn,
        [
            play("u1", "s1", "2026-07-05 00:14:00"),
            play("u2", "s1", "2026-07-05 00:22:00", track_no=2),
            play("u3", "s2", "2026-07-05 00:31:54"),
            play("u4", "s2", "2026-07-05 00:35:00", track_no=2),
        ],
    )
    rebuild(conn)
    result = list_performances(conn)
    assert len(result) == 1
    assert result[0]["track_count"] == 4
    assert result[0]["session_count"] == 2
    assert result[0]["cuts"] == [
        {"ended": "2026-07-05 00:22:00", "resumed": "2026-07-05 00:31:54"}
    ]


def test_overlapping_sessions_never_merge_and_are_flagged(conn):
    # two machines on the same account playing at once (29 real pairs found)
    ingest(
        conn,
        [
            play("u1", "s1", "2026-04-07 10:00:00"),
            play("u2", "s1", "2026-04-07 10:30:00", track_no=2),
            play("u3", "s1", "2026-04-07 11:00:00", track_no=3),
            play("u4", "s2", "2026-04-07 10:48:00"),
            play("u5", "s2", "2026-04-07 11:04:00", track_no=2),
        ],
    )
    rebuild(conn)
    result = list_performances(conn)
    assert len(result) == 2
    assert all(row["overlaps"] for row in result)
    assert all(row["cuts"] == [] for row in result)


def test_usb_import_burst_stays_per_session_and_flagged(conn):
    # USB/CDJ history import: whole sessions written in seconds - created_at
    # is the import moment, so these never merge despite tiny gaps
    ingest(
        conn,
        [
            play("u1", "s1", "2026-05-30 07:03:31"),
            play("u2", "s1", "2026-05-30 07:03:32", track_no=2),
            play("u3", "s1", "2026-05-30 07:03:33", track_no=3),
            play("u4", "s2", "2026-05-30 07:03:34"),
            play("u5", "s2", "2026-05-30 07:03:35", track_no=2),
            play("u6", "s2", "2026-05-30 07:03:36", track_no=3),
        ],
    )
    rebuild(conn)
    result = list_performances(conn)
    assert len(result) == 2
    assert all(row["bulk_import"] == 1 for row in result)
    assert all(row["cuts"] == [] for row in result)


def test_rename_and_hidden_survive_rebuild(conn):
    ingest(conn, [play("u1", "s1", "2026-07-04 22:00:00")])
    rebuild(conn)
    row = list_performances(conn)[0]
    conn.execute(
        "UPDATE performances SET name = 'Mariage L&A', hidden = 1 WHERE id = ?",
        (row["id"],),
    )
    # new play arrives, everything reclusters
    ingest(conn, [play("u2", "s1", "2026-07-04 22:05:00", track_no=2)])
    rebuild(conn)
    row = list_performances(conn, include_hidden=True)[0]
    assert row["name"] == "Mariage L&A"
    assert row["hidden"] == 1
    assert row["track_count"] == 2
    assert list_performances(conn) == []  # hidden filtered by default


def test_spotify_titles_resolved_through_client(conn):
    ingest(
        conn,
        [
            play("u1", "s1", "2026-07-05 03:32:00", title=None, artist=None,
                 spotify_track_id="190jyVPHYjAqEaOGmMzdyk"),
            play("u2", "s1", "2026-07-05 03:35:00", track_no=2),
        ],
    )

    class FakeClient:
        def get(self, path):
            assert path == "/tracks?ids=190jyVPHYjAqEaOGmMzdyk"
            return {
                "tracks": [
                    {
                        "id": "190jyVPHYjAqEaOGmMzdyk",
                        "name": "Le titre résolu",
                        "artists": [{"name": "A"}, {"name": "B"}],
                    }
                ]
            }

    assert resolve_spotify_titles(conn, FakeClient()) == 1
    assert resolve_spotify_titles(conn, FakeClient()) == 0  # nothing pending
    row = conn.execute("SELECT title, artist FROM plays WHERE uuid = 'u1'").fetchone()
    assert (row["title"], row["artist"]) == ("Le titre résolu", "A, B")


def test_spotify_title_fallback_via_oembed_without_session(conn):
    ingest(
        conn,
        [
            play("u1", "s1", "2026-07-05 03:32:00", title=None, artist=None,
                 spotify_track_id="190jyVPH"),
        ],
    )
    calls = []

    def transport(url, data=None, headers=None, method="GET"):
        calls.append(url)
        return 200, {}, json.dumps({"title": "Beauty And A Beat"}).encode()

    assert resolve_spotify_titles(conn, None, transport=transport) == 1
    assert calls[0].endswith("/track/190jyVPH")
    row = conn.execute("SELECT title, artist FROM plays WHERE uuid = 'u1'").fetchone()
    assert row["title"] == "Beauty And A Beat"
    assert row["artist"] is None  # oEmbed has no artist field

    # a Spotify session later completes the artist on the same row
    class FakeClient:
        def get(self, path):
            return {
                "tracks": [
                    {
                        "id": "190jyVPH",
                        "name": "Beauty And A Beat",
                        "artists": [{"name": "Justin Bieber"}, {"name": "Nicki Minaj"}],
                    }
                ]
            }

    assert resolve_spotify_titles(conn, FakeClient()) == 1
    row = conn.execute("SELECT artist FROM plays WHERE uuid = 'u1'").fetchone()
    assert row["artist"] == "Justin Bieber, Nicki Minaj"


def test_oembed_fallback_stops_cleanly_when_offline(conn):
    ingest(
        conn,
        [
            play("u1", "s1", "2026-07-05 03:32:00", title=None,
                 spotify_track_id="aaa"),
            play("u2", "s1", "2026-07-05 03:35:00", track_no=2, title=None,
                 spotify_track_id="bbb"),
        ],
    )

    def transport(url, data=None, headers=None, method="GET"):
        raise OSError("network unreachable")

    assert resolve_spotify_titles(conn, None, transport=transport) == 0


def test_refresh_reports_ingest_even_when_spotify_is_down(conn, tmp_path, monkeypatch):
    db = tmp_path / "master.db"
    db.write_text("stand-in for the fingerprint stat")
    monkeypatch.setattr(
        performances,
        "read_rb_plays",
        lambda _p: [
            play("u1", "s1", "2026-07-04 22:00:00", title=None,
                 spotify_track_id="x1")
        ],
    )

    class Disconnected:
        def get(self, path):
            raise performances.NotConnectedError("no session")

    def offline(url, data=None, headers=None, method="GET"):
        raise OSError("network unreachable")

    performances._ingested.clear()
    info = performances.refresh(conn, db, Disconnected(), transport=offline)
    assert info == {"ingested": 1, "resolved_titles": 0}
    # unchanged file: the fingerprint gate skips the re-ingest entirely
    assert performances.refresh(conn, db, None, transport=offline) == {
        "ingested": 0,
        "resolved_titles": 0,
    }


def test_live_status_reflects_freshness(conn):
    ingest(
        conn,
        [
            play("u1", "s1", "2026-07-05 01:00:00"),
            play("u2", "s1", "2026-07-05 01:10:00", track_no=2),
        ],
    )
    rebuild(conn)
    during = live_status(conn, now=datetime(2026, 7, 5, 1, 20))
    assert during["active"] is True
    assert [track["uuid"] for track in during["tracks"]] == ["u1", "u2"]
    after = live_status(conn, now=datetime(2026, 7, 5, 3, 0))
    assert after["active"] is False
    assert after["performance"]["track_count"] == 2


def test_export_plan_orders_dedupes_revives_spotify_and_flags_missing():
    tracks = [
        {"content_id": "1"},
        {"content_id": "2"},
        {"content_id": "1"},  # replayed later in the set: first spin wins
        {"content_id": None},  # play whose content row vanished entirely
        {"content_id": "9"},  # LOCAL file soft-deleted: recoverable slot
        {"content_id": "5"},  # Spotify content RB soft-deleted: revived IN
        {"content_id": "3"},
    ]
    states = {
        "1": {"deleted": False, "spotify": False},
        "2": {"deleted": False, "spotify": False},
        "3": {"deleted": False, "spotify": False},
        "9": {"deleted": True, "spotify": False},
        "5": {"deleted": True, "spotify": True},
    }
    slots, duplicates = export_plan(tracks, states)
    assert [(s["content_id"], s["action"]) for s in slots] == [
        ("1", "keep"),
        ("2", "keep"),
        (None, "missing"),
        ("9", "missing"),
        ("5", "revive"),
        ("3", "keep"),
    ]
    assert duplicates == 1


def test_spotify_links_prefers_event_rows(conn):
    conn.execute(
        "INSERT INTO sources (id, spotify_playlist_id) VALUES (1, 'pl1')"
    )
    conn.execute(
        "INSERT INTO library_tracks (source_id, spotify_track_id, content_id,"
        " duration_ms) VALUES (1, 'lib_id', '42', 100000)"
    )
    conn.execute(
        "INSERT INTO events (id, name, slug, default_tag) VALUES"
        " (1, 'Luis & Diane', 'luis-diane', 'Luis & Diane')"
    )
    conn.execute(
        "INSERT INTO event_tracks (event_id, spotify_track_id, content_id,"
        " duration_ms) VALUES (1, 'event_id', '42', 200000)"
    )
    from syncbox.performances import spotify_links

    assert spotify_links(conn, ["42", "77"]) == {"42": ("event_id", 200000)}
    assert spotify_links(conn, []) == {}


def test_live_status_empty_db(conn):
    assert live_status(conn) == {"active": False, "performance": None, "tracks": []}


def test_read_rb_plays_normalizes_the_rekordbox_shape(tmp_path, monkeypatch):
    import sqlite3

    rb = sqlite3.connect(":memory:")
    rb.executescript(
        """
        CREATE TABLE djmdHistory (ID, Name, Attribute, rb_local_deleted);
        CREATE TABLE djmdSongHistory
            (UUID, HistoryID, ContentID, TrackNo, created_at, rb_local_deleted);
        CREATE TABLE djmdContent (ID, Title, ArtistID, FolderPath);
        CREATE TABLE djmdArtist (ID, Name);
        INSERT INTO djmdHistory VALUES
            ('h1', 'HISTORY 2026-07-05', 0, 0),
            ('folder', '2026', 1, 0),
            ('deleted', 'HISTORY x', 0, 1);
        INSERT INTO djmdContent VALUES
            ('c1', 'Freed From Desire', 'a1', '/music/f.aiff'),
            ('c2', '$A7:v1:xx==:yy==', NULL, 'spotify:track:190jyVPHYjAqEaOGmMzdyk');
        INSERT INTO djmdArtist VALUES ('a1', 'Gala');
        INSERT INTO djmdSongHistory VALUES
            ('u1', 'h1', 'c1', 1, '2026-07-05 01:49:22.000 +00:00', 0),
            ('u2', 'h1', 'c2', 2, '2026-07-05 03:32:36.000 +00:00', 0),
            ('u3', 'h1', 'c1', 3, '2026-07-05 03:40:00.000 +00:00', 1),
            ('u4', 'folder', 'c1', 1, '2026-07-05 03:41:00.000 +00:00', 0),
            ('u5', 'deleted', 'c1', 1, '2026-07-05 03:42:00.000 +00:00', 0);
        """
    )
    monkeypatch.setattr(performances, "open_readonly", lambda _db: rb)
    rows = performances.read_rb_plays(tmp_path / "master.db")
    assert [row["uuid"] for row in rows] == ["u1", "u2"]  # deleted+folder skipped
    assert rows[0]["title"] == "Freed From Desire"
    assert rows[0]["artist"] == "Gala"
    assert rows[0]["spotify_track_id"] is None
    assert rows[1]["title"] is None  # obfuscated -> pending API resolution
    assert rows[1]["spotify_track_id"] == "190jyVPHYjAqEaOGmMzdyk"
    assert rows[1]["played_at"] == "2026-07-05 03:32:36"
