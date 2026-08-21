"""Events service tests (SPEC-UNIFIED 5.7 + 11.1/11.2, SPEC-01 1.8).

Unit tests run on the app DB + fakes (no master.db); the lifecycle
integration test needs the real fixture and always works on a copy under
tmp_path (apply -> reapply delta -> delete with preview).
"""

import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from syncbox import appdb, event_delete, events_service, missing_service
from syncbox.events_service import (
    add_track,
    adopt_staged_files,
    apply_event,
    claim_staged_files,
    create_event,
    delete_event,
    get_event,
    list_event_tracks,
    match_event_tracks,
    recompute_event_status,
    slugify,
)
from syncbox.safety.paths import stored_form

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "sidecar" / "tests" / "testdata"
FIXTURE = TESTDATA / "master.db"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="real master.db fixture not present"
)


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    yield connection
    connection.close()


class FakeCache:
    """cache.get() contract only - enough for matching against fakes."""

    def __init__(self, rows):
        self._rows = rows
        self.current_fingerprint = None

    def get(self, storage_root):
        return self._rows

    def invalidate(self):
        self.current_fingerprint = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- slugging / creation ---------------------------------------------------------


def test_slugify_folds_accents_and_junk():
    assert slugify("Wedding Bash!") == "wedding-bash"
    assert slugify("Fête à l'École") == "fete-a-l-ecole"
    assert slugify("  --  ") == "event"  # never an empty slug
    assert slugify("") == "event"


def test_create_event_modes_and_slug_collision(conn, tmp_path):
    storage = tmp_path / "storage"

    e1 = create_event(conn, storage, "Wedding Bash!")
    e2 = create_event(conn, storage, "Wedding Bash")
    e3 = create_event(conn, storage, "Wedding bash", spotify_playlist_id="pl123")

    assert [e["slug"] for e in (e1, e2, e3)] == [
        "wedding-bash",
        "wedding-bash-2",
        "wedding-bash-3",
    ]
    for event in (e1, e2, e3):
        staging = Path(event["staging_dir"])
        assert staging.is_dir()
        assert staging == storage / "_syncbox" / "events" / event["slug"]
        assert event["default_tag"] == event["name"]  # Situation tag = name (5.7)
        assert event["status"] == "pending"
    # empty/manual events get the manual:<slug> identity; playlist mode keeps it
    assert e1["spotify_playlist_id"] == "manual:wedding-bash"
    assert e3["spotify_playlist_id"] == "pl123"

    with pytest.raises(ValueError):
        create_event(conn, storage, "X", spotify_playlist_id="pl1", manual=True)


def test_create_event_skips_orphan_dir_and_orphan_db_slug(conn, tmp_path):
    storage = tmp_path / "storage"
    events_root = storage / "_syncbox" / "events"

    # a stray dir without a DB row blocks the slug (atomic mkdir claim)
    events_root.mkdir(parents=True)
    (events_root / "party").mkdir()
    event = create_event(conn, storage, "Party")
    assert event["slug"] == "party-2"

    # a DB row without a dir also blocks the slug; the claimed dir is released
    conn.execute(
        "INSERT INTO events (name, slug, default_tag) VALUES ('Gala', 'gala', 'Gala')"
    )
    event = create_event(conn, storage, "Gala")
    assert event["slug"] == "gala-2"
    assert not (events_root / "gala").exists()  # released after UNIQUE bounce
    assert (events_root / "gala-2").is_dir()


# --- track additions (11.1/11.2) --------------------------------------------------


def test_add_track_resolver_manual_and_validation(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Birthday")

    resolved = add_track(
        conn,
        event,
        spotify_track_id="sp:1",
        resolver=lambda track_id: {
            "title": "Song A",
            "artist": "Artist A",
            "duration_ms": 200_000,
            "isrc": "USABC2400001",
        },
    )
    assert resolved["title"] == "Song A"
    assert resolved["isrc"] == "USABC2400001"
    assert resolved["status"] == "missing"
    assert resolved["added_after_apply"] == 0

    manual = add_track(conn, event, title="Song B", artist="Artist B")
    assert (manual["title"], manual["artist"]) == ("Song B", "Artist B")
    assert manual["spotify_track_id"] is None

    with pytest.raises(ValueError):
        add_track(conn, event, spotify_track_id="sp:2")  # resolver required
    with pytest.raises(ValueError):
        add_track(conn, event, artist="No Title")  # manual needs a title


def test_add_track_after_apply_is_flagged_delta_never_blocked(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Applied Party")
    for status in ("applied", "partially_applied"):
        conn.execute("UPDATE events SET status = ? WHERE id = ?", (status, event["id"]))
        track = add_track(conn, event, title=f"Delta {status}")
        assert track["added_after_apply"] == 1  # 11.2 delta, never blocked


# --- matching (5.7 event flavor) ---------------------------------------------------


def test_match_event_tracks_ambiguous_stays_ambiguous(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Match Night")
    ambiguous = add_track(
        conn,
        event,
        spotify_track_id="sp:amb",
        resolver=lambda _tid: {
            "title": "Midnight City",
            "artist": "M83",
            "duration_ms": 241_000,
            "isrc": None,
        },
    )
    matched = add_track(conn, event, title="Unique Song", artist="Solo Act")
    missing = add_track(conn, event, title="Nowhere To Be Found", artist="Ghost")

    cache = FakeCache(
        [
            {
                "content_id": "c1",
                "title": "Midnight City",
                "artist": "M83",
                "duration_ms": 241_000,
                "isrc": None,
            },
            {
                "content_id": "c2",
                "title": "Midnight City",
                "artist": "M83",
                "duration_ms": 240_500,
                "isrc": None,
            },
            {
                "content_id": "c3",
                "title": "Unique Song",
                "artist": "Solo Act",
                "duration_ms": None,
                "isrc": None,
            },
        ]
    )
    match_event_tracks(conn, event, cache, tmp_path / "storage")
    rows = {t["id"]: t for t in list_event_tracks(conn, event["id"])}

    # event flavor: 'ambiguous' stays 'ambiguous' (never 'conflict', 5.7)
    # and the best content_id is still returned (SPEC-01 2.1)
    assert rows[ambiguous["id"]]["status"] == "ambiguous"
    assert rows[ambiguous["id"]]["content_id"] == "c1"
    assert rows[matched["id"]]["status"] == "matched"
    assert rows[matched["id"]]["content_id"] == "c3"
    assert rows[missing["id"]]["status"] == "missing"
    assert rows[missing["id"]]["content_id"] is None


def test_match_event_tracks_never_touches_ready_or_applied(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Sticky")
    ready = add_track(conn, event, title="Staged Tune")
    conn.execute(
        "UPDATE event_tracks SET status = 'ready', staging_file_path = '/x.mp3'"
        " WHERE id = ?",
        (ready["id"],),
    )
    match_event_tracks(conn, event, FakeCache([]), tmp_path / "storage")
    row = list_event_tracks(conn, event["id"])[0]
    assert row["status"] == "ready"  # a staged track never flips back


def test_match_event_tracks_retries_acquisition_failure(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Retry")
    failed = add_track(conn, event, title="Recovered Song", artist="Artist")
    conn.execute(
        "UPDATE event_tracks SET status = 'acquisition_failed' WHERE id = ?",
        (failed["id"],),
    )
    cache = FakeCache(
        [
            {
                "content_id": "C1",
                "title": "Recovered Song",
                "artist": "Artist",
                "duration_ms": None,
                "isrc": None,
            }
        ]
    )

    match_event_tracks(conn, event, cache, tmp_path / "storage")

    assert list_event_tracks(conn, event["id"])[0]["status"] == "matched"


# --- staging claims (5.7 claim rule) -----------------------------------------------


def test_claim_rule_shares_only_on_same_nonempty_isrc(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Claim Night")
    staging = Path(event["staging_dir"])
    shared = staging / "Shared Song.mp3"
    shared.write_bytes(b"fake")
    other = staging / "Other Tune.mp3"
    other.write_bytes(b"fake")

    def spotify(title, isrc):
        return lambda _tid: {"title": title, "artist": "A", "isrc": isrc}

    same_a = add_track(
        conn,
        event,
        spotify_track_id="sp:1",
        resolver=spotify("Shared Song", "USAAA0000001"),
    )
    same_b = add_track(
        conn,
        event,
        spotify_track_id="sp:2",
        resolver=spotify("Shared Song", "USAAA0000001"),
    )
    diff_isrc = add_track(
        conn,
        event,
        spotify_track_id="sp:3",
        resolver=spotify("Shared Song", "GBZZZ0000009"),
    )
    no_isrc_1 = add_track(conn, event, title="Other Tune")
    no_isrc_2 = add_track(conn, event, title="Other Tune")

    claimed = claim_staged_files(conn, event)
    rows = {t["id"]: t for t in list_event_tracks(conn, event["id"])}

    # same non-empty ISRC: the ONLY legal share of one staged file (5.7)
    assert rows[same_a["id"]]["status"] == "ready"
    assert rows[same_b["id"]]["status"] == "ready"
    assert (
        rows[same_a["id"]]["staging_file_path"]
        == rows[same_b["id"]]["staging_file_path"]
        == str(shared)
    )
    # different ISRC: no share, stays missing
    assert rows[diff_isrc["id"]]["status"] == "missing"
    assert rows[diff_isrc["id"]]["staging_file_path"] is None
    # empty ISRC: first claimant wins, never shared
    assert rows[no_isrc_1["id"]]["status"] == "ready"
    assert rows[no_isrc_1["id"]]["staging_file_path"] == str(other)
    assert rows[no_isrc_2["id"]]["status"] == "missing"
    assert len(claimed) == 3

    # idempotent: nothing left to claim on a second scan
    assert claim_staged_files(conn, event) == []


def test_claim_staged_file_recovers_acquisition_failure(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Recovery")
    track = add_track(conn, event, title="Recovered Song", artist="Artist")
    conn.execute(
        "UPDATE event_tracks SET status = 'acquisition_failed' WHERE id = ?",
        (track["id"],),
    )
    (Path(event["staging_dir"]) / "Artist - Recovered Song.mp3").write_bytes(b"audio")

    claimed = claim_staged_files(conn, event)

    assert len(claimed) == 1
    assert list_event_tracks(conn, event["id"])[0]["status"] == "ready"


# --- staged-file adoption (event-staged-file-adoption) -----------------------------


def _fake_tags(monkeypatch, by_name: dict):
    """rb_write.MutagenFile stand-in: easy-tags per FILE NAME, None elsewhere."""

    class Audio:
        info = None

        def __init__(self, tags):
            self.tags = tags

    def open_file(path, **kwargs):
        tags = by_name.get(Path(path).name)
        return Audio(tags) if tags is not None else None

    monkeypatch.setattr("syncbox.rb_write.MutagenFile", open_file)


def test_adopt_creates_one_missing_track_per_unreferenced_file(
    conn, tmp_path, monkeypatch
):
    event = create_event(conn, tmp_path / "storage", "Drop Night")
    dropped = Path(event["staging_dir"]) / "audio" / "01 dropped.mp3"
    dropped.write_bytes(b"fake")
    _fake_tags(
        monkeypatch,
        {
            "01 dropped.mp3": {
                "title": ["Via Con Me"],
                "artist": ["Paolo Conte"],
                "isrc": ["ITAAA0000001"],
            }
        },
    )

    adopted = adopt_staged_files(conn, event)

    assert len(adopted) == 1
    row = list_event_tracks(conn, event["id"])[0]
    assert (row["title"], row["artist"], row["isrc"]) == (
        "Via Con Me",
        "Paolo Conte",
        "ITAAA0000001",
    )
    assert row["spotify_track_id"] is None
    assert row["status"] == "missing"  # the matcher decides the outcome
    assert row["staging_file_path"] == str(dropped)  # referenced from the start
    assert adopt_staged_files(conn, event) == []  # never twice


def test_adopt_falls_back_to_the_complete_file_name(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Tagless")
    (Path(event["staging_dir"]) / "Paolo Conte - Via Con Me.mp3").write_bytes(b"fake")

    adopt_staged_files(conn, event)

    row = list_event_tracks(conn, event["id"])[0]
    # extension INCLUDED, and no Artist/Title guessed out of the name
    assert row["title"] == "Paolo Conte - Via Con Me.mp3"
    assert row["artist"] is None


def test_adopt_skips_a_file_another_track_already_holds(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Held")
    staged = Path(event["staging_dir"]) / "Recovered Song.mp3"
    staged.write_bytes(b"fake")
    add_track(conn, event, title="Recovered Song", artist="Artist")
    claim_staged_files(conn, event)

    assert adopt_staged_files(conn, event) == []
    assert len(list_event_tracks(conn, event["id"])) == 1

    # an 'ignored' rejection keeps its path, which is what makes it stick
    conn.execute("UPDATE event_tracks SET status = 'ignored'")
    assert adopt_staged_files(conn, event) == []


def test_adopt_walks_subfolders_and_ignores_non_audio(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Nested")
    staging = Path(event["staging_dir"])
    nested = staging / "audio" / "From A Friend"
    nested.mkdir(parents=True)
    (nested / "Deep Cut.mp3").write_bytes(b"fake")
    (staging / "Top Level.flac").write_bytes(b"fake")
    (staging / "cover.jpg").write_bytes(b"not audio")
    (staging / "masterPlaylists6.xml.bak").write_bytes(b"not audio")

    adopted = adopt_staged_files(conn, event)

    assert sorted(track["title"] for track in adopted) == [
        "Deep Cut.mp3",
        "Top Level.flac",
    ]


# --- playlist refresh (event-playlist-refresh) -------------------------------------


def _spotify_item(track_id, name="Song", artist="A", duration_ms=200_000, isrc=None):
    return {
        "item": {
            "id": track_id,
            "name": name,
            "artists": [{"name": artist}],
            "duration_ms": duration_ms,
            "external_ids": {"isrc": isrc},
            "type": "track",
        }
    }


class FakePlaylist:
    """SpotifyClient.get() contract only; ``fail`` raises instead of paging."""

    def __init__(self, *items, fail=None):
        self.payload = {"items": {"items": list(items), "next": None}}
        self.fail = fail
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        if self.fail is not None:
            raise self.fail
        return self.payload


def _playlist_event(conn, tmp_path, *track_ids, name="Refresh Night"):
    event = create_event(
        conn, tmp_path / "storage", name, spotify_playlist_id="PL123"
    )
    for track_id in track_ids:
        add_track(
            conn,
            event,
            spotify_track_id=track_id,
            resolver=lambda tid: {"title": f"Song {tid}", "artist": "A"},
            origin="playlist",
        )
    return event


def test_refresh_buckets_updated_added_and_departed(conn, tmp_path):
    """4.1: one fetch, three buckets keyed on spotify_track_id."""
    event = _playlist_event(conn, tmp_path, "keep", "gone")
    client = FakePlaylist(
        _spotify_item("keep", name="Renamed"),
        _spotify_item("keep", name="Duplicate occurrence"),  # collapsed, first wins
        _spotify_item("fresh"),
    )

    result = events_service.refresh_from_playlist(conn, event, client)

    assert client.calls == ["/playlists/PL123"]
    assert result == {"added": 1, "updated": 1, "removed": 1}
    rows = {t["spotify_track_id"]: t for t in list_event_tracks(conn, event["id"])}
    assert rows["keep"]["title"] == "Renamed"
    assert rows["gone"]["status"] == "removed_upstream"
    assert rows["fresh"]["origin"] == "playlist"
    # an unchanged playlist reports nothing changed (idempotent second run)
    assert events_service.refresh_from_playlist(conn, event, client) == {
        "added": 0,
        "updated": 0,
        "removed": 0,
    }


def test_refresh_updates_metadata_only(conn, tmp_path):
    """4.2: status, content_id and staging_file_path survive the update."""
    event = _playlist_event(conn, tmp_path, "t1")
    staged = Path(event["staging_dir"]) / "t1.mp3"
    staged.write_bytes(b"fake")
    conn.execute(
        "UPDATE event_tracks SET status = 'applied', content_id = '42',"
        " staging_file_path = ? WHERE spotify_track_id = 't1'",
        (str(staged),),
    )
    client = FakePlaylist(
        _spotify_item("t1", name="New Title", artist="New Artist", isrc="USAAA0000001")
    )

    assert events_service.refresh_from_playlist(conn, event, client)["updated"] == 1

    row = list_event_tracks(conn, event["id"])[0]
    assert (row["title"], row["artist"], row["isrc"]) == (
        "New Title",
        "New Artist",
        "USAAA0000001",
    )
    assert row["status"] == "applied"
    assert row["content_id"] == "42"
    assert row["staging_file_path"] == str(staged)


def test_refresh_import_carries_the_11_2_delta_flag(conn, tmp_path):
    """4.3: on an applied event an imported row is a pending addition."""
    event = _playlist_event(conn, tmp_path)
    conn.execute("UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],))

    events_service.refresh_from_playlist(conn, event, FakePlaylist(_spotify_item("new")))

    row = list_event_tracks(conn, event["id"])[0]
    assert row["added_after_apply"] == 1 and row["origin"] == "playlist"


def test_refresh_departure_saves_prior_status(conn, tmp_path):
    """4.4 + 3.1: the signal parks the previous status and costs no work."""
    event = _playlist_event(conn, tmp_path, "gone")
    conn.execute(
        "UPDATE event_tracks SET status = 'applied', content_id = '7'"
        " WHERE spotify_track_id = 'gone'"
    )
    conn.execute("UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],))

    assert events_service.refresh_from_playlist(conn, event, FakePlaylist())["removed"] == 1

    row = list_event_tracks(conn, event["id"])[0]
    assert row["status"] == "removed_upstream"
    assert row["prior_status"] == "applied"
    assert row["content_id"] == "7"  # signalled, never acted on
    # the event stays applied: a departure is not outstanding work (11.2)
    assert recompute_event_status([row["status"]]) == "applied"


def test_refresh_clears_the_signal_when_a_track_comes_back(conn, tmp_path):
    """4.4: put back on the playlist, the departure is contradicted - the row
    returns to its prior status by itself. Leaving it signalled would force
    the user through 'keep', which flips origin to 'manual' and drops the row
    from playlist tracking for good."""
    event = _playlist_event(conn, tmp_path, "gone")
    conn.execute(
        "UPDATE event_tracks SET status = 'applied', content_id = '7'"
        " WHERE spotify_track_id = 'gone'"
    )

    assert events_service.refresh_from_playlist(conn, event, FakePlaylist())["removed"] == 1

    back = FakePlaylist(_spotify_item("gone", name="Song gone"))
    assert events_service.refresh_from_playlist(conn, event, back) == {
        "added": 0,
        "updated": 1,
        "removed": 0,
    }
    row = list_event_tracks(conn, event["id"])[0]
    assert (row["status"], row["prior_status"]) == ("applied", None)
    assert row["content_id"] == "7"
    assert row["origin"] == "playlist"  # still tracked, no 'keep' needed
    # and the return is reported once, not again on the next refresh
    assert events_service.refresh_from_playlist(conn, event, back) == {
        "added": 0,
        "updated": 0,
        "removed": 0,
    }


def test_removed_upstream_is_inert_everywhere(conn, tmp_path):
    """3.1/3.3: never re-matched, never claims a file, never pending."""
    event = _playlist_event(conn, tmp_path, "gone")
    (Path(event["staging_dir"]) / "Song gone.mp3").write_bytes(b"fake")
    events_service.refresh_from_playlist(conn, event, FakePlaylist())

    for statuses in (
        events_service.PENDING_STATUSES,
        events_service.REMATCHED_STATUSES,
        events_service.CLAIMABLE_STATUSES,
    ):
        assert "removed_upstream" not in statuses
    cache = FakeCache([{"content_id": "9", "title": "Song gone", "artist": "A"}])
    match_event_tracks(conn, event, cache, tmp_path / "storage")
    assert claim_staged_files(conn, event) == []
    row = list_event_tracks(conn, event["id"])[0]
    assert row["status"] == "removed_upstream"
    assert row["content_id"] is None and row["staging_file_path"] is None


def test_refresh_ignores_manual_and_adopted_rows(conn, tmp_path):
    """4.5: only origin='playlist' rows are compared to the playlist."""
    event = _playlist_event(conn, tmp_path)
    linked = add_track(
        conn,
        event,
        spotify_track_id="linked",
        resolver=lambda tid: {"title": "Pasted Link", "artist": "A"},
    )
    typed = add_track(conn, event, title="Typed By Hand")
    staged = Path(event["staging_dir"]) / "Dropped.mp3"
    staged.write_bytes(b"fake")
    adopted = adopt_staged_files(conn, event)[0]
    assert adopted["origin"] == "adopted"

    assert events_service.refresh_from_playlist(conn, event, FakePlaylist()) == {
        "added": 0,
        "updated": 0,
        "removed": 0,
    }

    rows = {t["id"]: t for t in list_event_tracks(conn, event["id"])}
    assert [rows[t["id"]]["status"] for t in (linked, typed, adopted)] == [
        "missing",
        "missing",
        "missing",
    ]
    assert rows[linked["id"]]["title"] == "Pasted Link"
    # a link-added track already in the event is not imported a second time
    events_service.refresh_from_playlist(
        conn, event, FakePlaylist(_spotify_item("linked", name="From Playlist"))
    )
    assert len(list_event_tracks(conn, event["id"])) == 3


def test_refresh_leaves_everything_untouched_when_spotify_fails(conn, tmp_path):
    """5.3 at the service level: the fetch precedes every write."""
    event = _playlist_event(conn, tmp_path, "t1", "t2")
    before = list_event_tracks(conn, event["id"])

    with pytest.raises(RuntimeError):
        events_service.refresh_from_playlist(
            conn, event, FakePlaylist(fail=RuntimeError("spotify down"))
        )

    assert list_event_tracks(conn, event["id"]) == before


# --- status recompute + strict no-op (11.2) ----------------------------------------


def test_recompute_event_status():
    assert recompute_event_status([]) == "applied"
    assert recompute_event_status(["applied", "ignored"]) == "applied"
    for pending in ("matched", "ready", "missing", "ambiguous", "acquisition_failed"):
        assert recompute_event_status(["applied", pending]) == "partially_applied"


def test_an_ignored_row_is_inert_everywhere(conn, tmp_path):
    """A rejected adopted track is never matched, claimed, applied nor
    counted: an event holding nothing else computes as 'applied'."""
    event = create_event(conn, tmp_path / "storage", "Rejected")
    track = add_track(conn, event, title="Dropped By Mistake")
    staged = Path(event["staging_dir"]) / "Dropped By Mistake.mp3"
    staged.write_bytes(b"fake")
    conn.execute(
        "UPDATE event_tracks SET status = 'ignored', staging_file_path = ?"
        " WHERE id = ?",
        (str(staged), track["id"]),
    )

    for statuses in (
        events_service.PENDING_STATUSES,
        events_service.REMATCHED_STATUSES,
        events_service.CLAIMABLE_STATUSES,
    ):
        assert "ignored" not in statuses
    assert claim_staged_files(conn, event) == []
    assert recompute_event_status(["applied", "ignored"]) == "applied"
    # not applicable either: a reapply is a strict no-op, no backup wasted
    backups = tmp_path / "backups"
    result = apply_event(
        conn,
        tmp_path / "does-not-exist" / "master.db",
        backups,
        object(),
        tmp_path / "storage",
        event,
        only_delta=True,
    )
    assert result["noop"] is True and not backups.exists()


def test_reapply_without_delta_is_noop_before_mutate(conn, tmp_path):
    event = create_event(conn, tmp_path / "storage", "Noop Night")
    conn.execute("UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],))
    # a delta row that is NOT applicable (still missing) must not trigger a mutation
    add_track(conn, event, title="Still Missing")

    missing_db = tmp_path / "does-not-exist" / "master.db"
    backups = tmp_path / "backups"
    result = apply_event(
        conn,
        missing_db,
        backups,
        object(),  # never touched on the no-op path
        tmp_path / "storage",
        event,
        only_delta=True,
    )
    assert result["noop"] is True and result["applied"] == 0
    assert not backups.exists()  # no backup wasted (11.2)

    # full reapply on an applied event with nothing applicable: same strict no-op
    result = apply_event(
        conn, missing_db, backups, object(), tmp_path / "storage", event
    )
    assert result["noop"] is True
    assert not backups.exists()


def test_reapply_picks_up_rows_matched_after_the_apply(conn, tmp_path, monkeypatch):
    """Owner amendment to 11.2 (2026-07-07): the delta IS the matched/ready
    set — a pre-apply row that became 'matched' only AFTER the first apply
    must be picked up by the reapply (it was reported stuck: shown ready,
    never reappliable)."""
    event = create_event(conn, tmp_path / "storage", "Delta Réel")
    track = add_track(conn, event, title="Matched Later")
    # matched AFTER the apply: not an added_after_apply row
    conn.execute(
        "UPDATE event_tracks SET status = 'matched', content_id = 'C1' WHERE id = ?",
        (track["id"],),
    )
    conn.execute("UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],))

    @contextmanager
    def fake_mutate(
        db_path,
        backups_root,
        *,
        retention=20,
        expected_fingerprint=None,
        open_db,
        invalidate_cache=None,
        **kwargs,
    ):
        yield "db"

    _fake_apply_helpers(monkeypatch, fake_mutate)
    monkeypatch.setattr(events_service, "_xml_snapshot", lambda db, s: (None, None))

    result = apply_event(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        FakeCache([]),
        tmp_path / "storage",
        event,
        only_delta=True,
    )
    assert result["noop"] is False and result["applied"] == 1
    row = list_event_tracks(conn, event["id"])[0]
    assert row["status"] == "applied"


def test_reapply_with_nothing_applicable_is_a_noop_before_mutate(conn, tmp_path):
    """A reapply with no matched/ready row stays a strict no-op checked
    BEFORE mutate() — no backup is wasted."""
    event = create_event(conn, tmp_path / "storage", "Rien à faire")
    add_track(conn, event, title="Toujours manquant")  # stays 'missing'
    conn.execute("UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],))

    backups = tmp_path / "backups"
    result = apply_event(
        conn,
        tmp_path / "does-not-exist" / "master.db",
        backups,
        object(),  # never touched: the no-op fires before mutate
        tmp_path / "storage",
        event,
        only_delta=True,
    )
    assert result["noop"] is True and result["applied"] == 0
    assert not backups.exists()


# --- apply harness fakes (no master.db) --------------------------------------------


def _fake_apply_helpers(monkeypatch, fake_mutate):
    monkeypatch.setattr(events_service, "mutate", fake_mutate)
    monkeypatch.setattr(
        events_service,
        "find_or_create_mytag",
        lambda db, n, c: SimpleNamespace(ID="T1"),
    )
    monkeypatch.setattr(
        events_service, "ensure_playlist_folder", lambda db, n: SimpleNamespace(ID="F1")
    )
    monkeypatch.setattr(
        events_service,
        "create_or_repair_smart_playlist",
        lambda db, n, p, t: SimpleNamespace(ID="P1"),
    )
    monkeypatch.setattr(events_service, "tag_content", lambda db, c, t: None)


def test_apply_retry_after_post_commit_crash_reuses_content_row(
    conn, tmp_path, monkeypatch
):
    """M3 crash-window contract: a failure AFTER the durable master.db
    commit leaves the row 'ready'; the retry must reuse the committed
    content row, never add_content a duplicate for the same staged file."""
    from syncbox.safety.paths import stored_form

    storage = tmp_path / "storage"
    event = create_event(conn, storage, "Crash Party")
    track = add_track(conn, event, title="Staged")
    staged = Path(event["staging_dir"]) / "Staged.mp3"
    staged.write_bytes(b"x")
    conn.execute(
        "UPDATE event_tracks SET status = 'ready', staging_file_path = ? WHERE id = ?",
        (str(staged), track["id"]),
    )

    master = {}  # stored FolderPath -> content row: the fake master.db state
    added = []

    @contextmanager
    def fake_mutate(
        db_path,
        backups_root,
        *,
        retention=20,
        expected_fingerprint=None,
        open_db,
        invalidate_cache=None,
        **kwargs,
    ):
        yield "db"
        if invalidate_cache:
            invalidate_cache()

    def fake_add_content(db, staging_path, metadata, *, storage_root):
        row = SimpleNamespace(ID=f"NEW{len(added) + 1}")
        added.append(str(staging_path))
        master[stored_form(staging_path, storage_root)] = row
        return row

    _fake_apply_helpers(monkeypatch, fake_mutate)
    monkeypatch.setattr(events_service, "add_content", fake_add_content)
    monkeypatch.setattr(
        events_service,
        "find_active_content_by_path",
        lambda db, stored: master.get(stored),
    )

    class CrashAfterCommit:
        """Delegates to the real app-DB conn but dies at the post-commit
        update - the exact crash window (master.db durable, app DB stale)."""

        def __init__(self, real):
            self._real = real

        def execute(self, sql, *args):
            if sql.strip() == "BEGIN":
                raise RuntimeError("simulated crash after the master.db commit")
            return self._real.execute(sql, *args)

    cache = FakeCache([])
    with pytest.raises(RuntimeError, match="simulated crash"):
        apply_event(
            CrashAfterCommit(conn),
            tmp_path / "master.db",
            tmp_path / "b",
            cache,
            storage,
            event,
        )
    assert added == [str(staged)]  # committed once into (fake) master.db
    row = list_event_tracks(conn, event["id"])[0]
    assert row["status"] == "ready"  # the app DB never saw the apply

    # The user's retry: same 'ready' row, same staged file.
    result = apply_event(
        conn, tmp_path / "master.db", tmp_path / "b", cache, storage, event
    )
    assert result["noop"] is False and result["applied"] == 1
    assert added == [str(staged)]  # add_content NOT called again: no duplicate
    row = list_event_tracks(conn, event["id"])[0]
    assert row["status"] == "applied"
    assert row["content_id"] == "NEW1"  # linked to the FIRST commit's row


def test_apply_restores_xml_byte_identical_after_commit(conn, tmp_path, monkeypatch):
    """SPEC-01 1.6 without the fixture: pyrekordbox rewrites the xml at
    commit; apply_event must restore it byte-identical and keep the crash
    -window .bak in the staging dir."""
    storage = tmp_path / "storage"
    event = create_event(conn, storage, "XML Night")
    track = add_track(conn, event, title="Matched")
    conn.execute(
        "UPDATE event_tracks SET status = 'matched', content_id = 'C1' WHERE id = ?",
        (track["id"],),
    )
    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    db_path.write_bytes(b"fake")
    xml_path = live / "masterPlaylists6.xml"
    original = b"<original playlists/>"
    xml_path.write_bytes(original)

    @contextmanager
    def fake_mutate(
        db_path_,
        backups_root,
        *,
        retention=20,
        expected_fingerprint=None,
        open_db,
        invalidate_cache=None,
        **kwargs,
    ):
        yield "db"
        # pyrekordbox rewrites the xml as part of its commit
        xml_path.write_bytes(b"<pyrekordbox rewrote this/>")

    _fake_apply_helpers(monkeypatch, fake_mutate)

    result = apply_event(conn, db_path, tmp_path / "b", FakeCache([]), storage, event)
    assert result["applied"] == 1
    assert xml_path.read_bytes() == original  # byte-identical restore (1.6)
    bak = Path(event["staging_dir"]) / "masterPlaylists6.xml.bak"
    assert bak.read_bytes() == original  # covers the commit->restore window


def test_apply_reclassifies_ready_track_with_vanished_staged_file(
    conn, tmp_path, monkeypatch
):
    """staged-file-integrity: a 'ready' event track whose staged file is gone
    is reclassified 'missing' + excluded BEFORE the Rekordbox write; the rest
    applies normally (no FileNotFoundError, no rollback)."""
    storage = tmp_path / "storage"
    event = create_event(conn, storage, "Ghost File Gig")
    matched = add_track(conn, event, title="Fine")
    conn.execute(
        "UPDATE event_tracks SET status = 'matched', content_id = 'C1' WHERE id = ?",
        (matched["id"],),
    )
    stale = add_track(conn, event, title="Gone")
    conn.execute(
        "UPDATE event_tracks SET status = 'ready', staging_file_path = ? WHERE id = ?",
        (str(Path(event["staging_dir"]) / "gone.mp3"), stale["id"]),
    )

    @contextmanager
    def fake_mutate(
        db_path,
        backups_root,
        *,
        retention=20,
        expected_fingerprint=None,
        open_db,
        invalidate_cache=None,
        **kwargs,
    ):
        yield "db"

    _fake_apply_helpers(monkeypatch, fake_mutate)
    monkeypatch.setattr(
        events_service,
        "add_content",
        lambda *args, **kwargs: pytest.fail(
            "a vanished staged file must never reach add_content"
        ),
    )
    monkeypatch.setattr(
        events_service, "find_active_content_by_path", lambda *args: None
    )

    result = apply_event(
        conn, tmp_path / "master.db", tmp_path / "b", FakeCache([]), storage, event
    )

    assert result["noop"] is False and result["applied"] == 1
    assert result["reclassified_missing"] == [stale["id"]]
    assert result["event_status"] == "partially_applied"
    rows = {t["title"]: t for t in list_event_tracks(conn, event["id"])}
    assert rows["Fine"]["status"] == "applied"
    assert rows["Gone"]["status"] == "missing"
    assert rows["Gone"]["staging_file_path"] is None
    # actionable again in the Missing center
    missing_ids = {e["id"] for e in missing_service.list_missing(conn, "event")}
    assert stale["id"] in missing_ids


def test_delete_event_forwards_exact_plan_and_consent(conn, tmp_path, monkeypatch):
    event = create_event(conn, tmp_path / "storage", "Forward")
    plan = {"plan_version": 1, "event_id": event["id"]}
    seen = {}

    def fake_delete(*args, **kwargs):
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(events_service.event_delete, "delete_event", fake_delete)
    result = delete_event(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        FakeCache([]),
        tmp_path / "storage",
        event,
        dry_run=False,
        plan=plan,
        consent_to_permanent_delete=True,
    )
    assert result == {"ok": True}
    assert seen["plan"] is plan
    assert seen["dry_run"] is False
    assert seen["consent_to_permanent_delete"] is True


# --- delete preview rules (SPEC-01 1.8) --------------------------------------------


def test_delete_preview_ownership_and_retained_track_rules(tmp_path):
    storage = tmp_path / "store"
    staging = storage / "_syncbox" / "events" / "gala"
    staging.mkdir(parents=True)
    solo = staging / "solo.mp3"
    retained = staging / "retained.mp3"
    solo.write_bytes(b"solo")
    retained.write_bytes(b"retained")
    (staging / "masterPlaylists6.xml.bak").write_bytes(b"<xml/>")
    event = {
        "id": 7,
        "name": "Gala Night",
        "default_tag": "Gala Night",
        "staging_dir": str(staging),
    }
    permanent_path = f"/{storage.name}/rekordbox/Collection/track3.flac"
    tagged = {"102": [("88", "Energy")], "105": [("89", "Favorite")]}

    def query(sql, params):
        if sql == event_delete._TAG_SQL:
            assert params == {"tag": "Gala Night", "category": "Situation"}
            return [("42",)]
        if sql == event_delete._ACTIVE_PATHS_SQL:
            return [
                ("101", str(solo)),
                ("102", str(retained)),
                ("103", permanent_path),
                ("104", "/Users/dj/Music/external.mp3"),
                ("105", "/Users/dj/Music/tagged.mp3"),
            ]
        if sql == event_delete._TAGGED_SQL:
            return [
                ("101", "Solo", "Artist", str(solo), None),
                ("102", "Retained", "Artist", str(retained), None),
                ("103", "In Collection", "Artist", permanent_path, None),
                (
                    "104",
                    "External Solo",
                    "Artist",
                    "/Users/dj/Music/external.mp3",
                    None,
                ),
                (
                    "105",
                    "External Tagged",
                    "Artist",
                    "/Users/dj/Music/tagged.mp3",
                    None,
                ),
            ]
        if sql == event_delete._OTHER_TAGS_SQL:
            return tagged.get(params["content_id"], [])
        if sql == event_delete._PLAYLISTS_SQL:
            assert params["legacy"] == "Gala Night - Smart"
            return [("9", "Gala Night"), ("10", "Gala Night - Smart")]
        raise AssertionError(f"unexpected sql: {sql}")

    preview = events_service._delete_preview(
        query, event, storage, tmp_path / "master.db", [["1", "2"]]
    )

    assert preview["tag_id"] == "42"
    by_id = {track["content_id"]: track for track in preview["tracks"]}
    assert by_id["101"]["action"] == "delete_with_event"
    assert by_id["102"]["action"] == "migrate_to_collection"
    assert by_id["102"]["retaining_mytags"] == ["Energy"]
    assert by_id["102"]["destination_path"] == str(
        storage / "rekordbox" / "Collection" / retained.name
    )
    assert by_id["103"]["action"] == "already_permanent"
    assert by_id["103"]["ownership"] == "permanent_library"
    assert by_id["104"]["action"] == "keep_in_place"
    assert by_id["105"]["action"] == "keep_in_place"
    assert by_id["105"]["ownership"] == "external"
    assert {p["name"] for p in preview["playlists"]} == {
        "Gala Night",
        "Gala Night - Smart",
    }
    assert preview["expected_file_deletions"] == preview["staging_artifacts"]
    assert set(preview["staging_artifacts"]) == {
        str(solo),
        str(retained),
        str(staging / "masterPlaylists6.xml.bak"),
    }


def test_delete_preview_without_tag_is_empty(tmp_path):
    event = {
        "id": 8,
        "name": "Ghost",
        "default_tag": "Ghost",
        "staging_dir": None,
    }

    def query(sql, params):
        if sql == event_delete._TAG_SQL:
            return []
        if sql == event_delete._PLAYLISTS_SQL:
            return []
        raise AssertionError("content queries must not run without a tag")

    preview = events_service._delete_preview(
        query, event, tmp_path, tmp_path / "master.db", [["1", "2"]]
    )
    assert preview["tag_id"] is None
    assert preview["tracks"] == []
    assert preview["playlists"] == []
    assert preview["expected_file_deletions"] == []


@pytest.mark.skipif(
    not os.environ.get("SYNCBOX_EVENT_MIGRATION_FIXTURE"),
    reason="POC #9 event-migration fixture is not configured",
)
def test_retained_track_migration_on_real_db(tmp_path, monkeypatch):
    """POC #9: preserve identity and analysis while moving one staged track."""
    from pyrekordbox.anlz import AnlzFile

    from syncbox import rb
    from syncbox.rb_write import (
        find_or_create_mytag,
        migrate_content_path,
        open_rekordbox,
        tag_content,
    )
    from syncbox.safety.mutate import mutate
    from syncbox.safety.paths import stored_form

    manifest_path = Path(os.environ["SYNCBOX_EVENT_MIGRATION_FIXTURE"])
    fixture_root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    db_path = fixture_root / "master.db"
    declared_anlz = [fixture_root / value for value in manifest["anlz_files"]]
    content_id = str(manifest["content_id"])

    def rows(sql, params=()):
        connection = rb.open_readonly(db_path)
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    content_before = rows(
        "SELECT FolderPath, OrgFolderPath, FileNameL, AnalysisDataPath, "
        "rb_local_deleted FROM djmdContent WHERE ID = ?",
        (content_id,),
    )[0]
    assert not int(content_before[4] or 0)
    actual_anlz = event_delete._anlz_paths(db_path, content_before[3])
    assert set(actual_anlz) == set(declared_anlz)
    cue_rows = rows(
        "SELECT * FROM djmdCue WHERE ContentID = ? ORDER BY ID", (content_id,)
    )
    playlist_rows = rows(
        "SELECT PlaylistID, TrackNo FROM djmdSongPlaylist "
        "WHERE ContentID = ? AND rb_local_deleted = 0 ORDER BY PlaylistID",
        (content_id,),
    )
    original_tags = rows(
        "SELECT MyTagID FROM djmdSongMyTag "
        "WHERE ContentID = ? AND rb_local_deleted = 0 ORDER BY MyTagID",
        (content_id,),
    )
    assert cue_rows and playlist_rows and original_tags

    def analysis_payload(path):
        parsed = AnlzFile.parse_file(path)
        return [(tag.type, tag.build()) for tag in parsed.tags if tag.type != "PPTH"]

    analysis_before = {path: analysis_payload(path) for path in declared_anlz}
    audio_source = fixture_root / manifest["staging_audio"]
    audio_digest = _sha256(audio_source)
    storage = Path(
        os.environ.get("SYNCBOX_EVENT_MIGRATION_STORAGE_ROOT", tmp_path / "storage")
    )
    conn = appdb.open_app_db(tmp_path / "app.db")
    event = create_event(conn, storage, "Syncbox POC Retained Migration")
    staged = Path(event["staging_dir"]) / audio_source.name
    shutil.copy2(audio_source, staged)
    backups = tmp_path / "backups"

    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        event_tag = find_or_create_mytag(
            db, event["default_tag"], events_service.SITUATION_CATEGORY
        )
        tag_content(db, content_id, str(event_tag.ID))
        migrate_content_path(db, content_id, str(staged), update_anlz=False)
        db.get_content(ID=content_id).OrgFolderPath = str(staged)
        db.flush()

    cache = rb.SnapshotCache(db_path)
    plan = delete_event(conn, db_path, backups, cache, storage, event, dry_run=True)
    track = next(item for item in plan["tracks"] if item["content_id"] == content_id)
    assert track["action"] == "migrate_to_collection"
    assert track["anlz_update_required"] is True
    assert set(track["retaining_mytags"])

    removed = []

    def unlink(path, *, consent_to_permanent_delete=False):
        Path(path).unlink()
        removed.append(str(path))
        return "trashed"

    monkeypatch.setattr(event_delete, "delete_file", unlink)
    result = delete_event(
        conn,
        db_path,
        backups,
        cache,
        storage,
        event,
        dry_run=False,
        plan=plan,
    )
    destination = Path(track["destination_path"])
    assert result["deleted_event"] is True
    assert str(staged) in removed
    assert not staged.exists()
    assert destination.is_file() and _sha256(destination) == audio_digest

    stored_destination = stored_form(destination, storage)
    assert stored_destination == str(destination.resolve())
    content_after = rows(
        "SELECT FolderPath, OrgFolderPath, FileNameL, AnalysisDataPath, "
        "rb_local_deleted FROM djmdContent WHERE ID = ?",
        (content_id,),
    )[0]
    assert content_after == (
        stored_destination,
        stored_destination,
        destination.name,
        content_before[3],
        0,
    )
    assert (
        rows("SELECT * FROM djmdCue WHERE ContentID = ? ORDER BY ID", (content_id,))
        == cue_rows
    )
    assert (
        rows(
            "SELECT PlaylistID, TrackNo FROM djmdSongPlaylist "
            "WHERE ContentID = ? AND rb_local_deleted = 0 ORDER BY PlaylistID",
            (content_id,),
        )
        == playlist_rows
    )
    assert (
        rows(
            "SELECT MyTagID FROM djmdSongMyTag "
            "WHERE ContentID = ? AND rb_local_deleted = 0 ORDER BY MyTagID",
            (content_id,),
        )
        == original_tags
    )

    for path in declared_anlz:
        parsed = AnlzFile.parse_file(path)
        assert parsed.get("path") == stored_destination
        assert analysis_payload(path) == analysis_before[path]
    assert any(
        all(
            (backup / "extra" / path.relative_to(fixture_root)).is_file()
            for path in declared_anlz
        )
        for backup in backups.glob("rekordbox-db-*")
    )
    assert get_event(conn, event["id"]) is None
    conn.close()


# --- integration: apply -> reapply(delta) -> delete on the real fixture ------------


@needs_fixture
def test_event_lifecycle_on_real_db(tmp_path, monkeypatch):
    from syncbox import rb
    from syncbox.rb_write import (
        create_or_repair_smart_playlist,
        ensure_playlist_folder,
        find_or_create_mytag,
        open_rekordbox,
        tag_content,
    )
    from syncbox.safety.mutate import mutate

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    xml_path = live / "masterPlaylists6.xml"
    shutil.copy2(TESTDATA / "masterPlaylists6.xml", xml_path)
    xml_sha_original = _sha256(xml_path)
    backups = tmp_path / "backups"
    storage_root = tmp_path / "storage"
    conn = appdb.open_app_db(tmp_path / "app.db")
    cache = rb.SnapshotCache(db_path)

    event = create_event(conn, storage_root, "IT Event Lifecycle")
    staging = Path(event["staging_dir"])

    rows = cache.get(storage_root)

    def isrc_unique(row):
        code = (row["isrc"] or "").strip().upper()
        return bool(code) and (
            sum(1 for r in rows if (r["isrc"] or "").strip().upper() == code) == 1
        )

    row_a = next(
        r
        for r in rows
        if r["title"] and r["artist"] and r["tag_count"] == 0 and isrc_unique(r)
    )
    row_x = next(r for r in rows if r["tag_count"] > 0)

    track_a = add_track(
        conn,
        event,
        spotify_track_id="sp:a",
        resolver=lambda _tid: {
            "title": row_a["title"],
            "artist": row_a["artist"],
            "duration_ms": row_a["duration_ms"],
            "isrc": row_a["isrc"],
        },
    )
    track_b = add_track(
        conn, event, title="Syncbox IT Staged Tune QQ", artist="Syncbox IT Artist QQ"
    )

    match_event_tracks(conn, event, cache, storage_root)
    rows_by_id = {t["id"]: t for t in list_event_tracks(conn, event["id"])}
    assert rows_by_id[track_a["id"]]["status"] == "matched"
    assert rows_by_id[track_a["id"]]["content_id"] == row_a["content_id"]
    assert rows_by_id[track_b["id"]]["status"] == "missing"

    staged_b = staging / "Syncbox IT Staged Tune QQ.mp3"
    staged_b.write_bytes(b"fake-audio")
    claimed = claim_staged_files(conn, event)
    assert [c["id"] for c in claimed] == [track_b["id"]]
    assert claimed[0]["staging_file_path"] == str(staged_b)

    # --- apply #1 ---------------------------------------------------------------
    result = apply_event(conn, db_path, backups, cache, storage_root, event)
    assert result["noop"] is False and result["applied"] == 2
    assert result["event_status"] == "applied"
    assert _sha256(xml_path) == xml_sha_original  # byte-identical restore (1.6)
    assert (staging / "masterPlaylists6.xml.bak").is_file()
    tag_id, playlist_id = result["tag_id"], result["playlist_id"]

    event = get_event(conn, event["id"])
    assert event["status"] == "applied" and event["applied_at"]

    ro = rb.open_readonly(db_path)
    new_rows = ro.execute(
        "SELECT ID, MasterSongID, rb_file_id, FolderPath FROM djmdContent"
        " WHERE Title = ? AND rb_local_deleted = 0",
        ("Syncbox IT Staged Tune QQ",),
    ).fetchall()
    assert len(new_rows) == 1
    content_b, master_id, file_id, folder_path = new_rows[0]
    assert content_b == master_id == file_id  # SPEC-01 1.6, string ID
    assert isinstance(content_b, str)
    assert folder_path == str(staged_b)  # staging outside rekordbox/: absolute
    playlists = ro.execute(
        "SELECT ID, Attribute FROM djmdPlaylist WHERE Name = ? AND rb_local_deleted = 0",
        ("IT Event Lifecycle",),
    ).fetchall()
    assert playlists == [(playlist_id, 4)]
    links = ro.execute(
        "SELECT COUNT(*) FROM djmdSongMyTag WHERE MyTagID = ? AND rb_local_deleted = 0",
        (tag_id,),
    ).fetchone()[0]
    assert links == 2
    ro.close()
    assert len(list(backups.iterdir())) == 1

    # --- crash-window retry: master.db committed but the app-DB update was
    # lost -> re-applying must reuse the committed row, never duplicate it.
    conn.execute(
        "UPDATE event_tracks SET status = 'ready', content_id = NULL WHERE id = ?",
        (track_b["id"],),
    )
    retry = apply_event(conn, db_path, backups, cache, storage_root, event)
    assert retry["noop"] is False and retry["applied"] == 1
    ro = rb.open_readonly(db_path)
    assert (
        ro.execute(
            "SELECT COUNT(*) FROM djmdContent WHERE Title = ? AND rb_local_deleted = 0",
            ("Syncbox IT Staged Tune QQ",),
        ).fetchone()[0]
        == 1
    )  # still exactly ONE content row for the staged file
    ro.close()
    row_b = {t["id"]: t for t in list_event_tracks(conn, event["id"])}[track_b["id"]]
    assert row_b["status"] == "applied"
    assert row_b["content_id"] == content_b  # relinked to the FIRST commit's row
    assert len(list(backups.iterdir())) == 2

    # --- reapply with no delta: strict no-op, no backup wasted (11.2) ------------
    noop = apply_event(
        conn, db_path, backups, cache, storage_root, event, only_delta=True
    )
    assert noop["noop"] is True
    assert len(list(backups.iterdir())) == 2

    # --- delta: post-apply addition -> reapply delta only (11.2) -----------------
    track_c = add_track(
        conn, event, title="Syncbox Delta Anthem QQ", artist="Syncbox IT Artist QQ"
    )
    assert track_c["added_after_apply"] == 1
    staged_c = staging / "Syncbox Delta Anthem QQ.mp3"
    staged_c.write_bytes(b"fake-audio-2")
    match_event_tracks(conn, event, cache, storage_root)
    claim_staged_files(conn, event)
    delta = apply_event(
        conn, db_path, backups, cache, storage_root, event, only_delta=True
    )
    assert delta["noop"] is False and delta["applied"] == 1
    # repaired in place, never duplicated (5.7/11.2)
    assert delta["tag_id"] == tag_id and delta["playlist_id"] == playlist_id
    assert _sha256(xml_path) == xml_sha_original

    ro = rb.open_readonly(db_path)
    assert (
        ro.execute(
            "SELECT COUNT(*) FROM djmdPlaylist WHERE Name = ? AND rb_local_deleted = 0",
            ("IT Event Lifecycle",),
        ).fetchone()[0]
        == 1
    )
    ro.close()
    tracks = list_event_tracks(conn, event["id"])
    assert all(t["status"] == "applied" and t["added_after_apply"] == 0 for t in tracks)
    event = get_event(conn, event["id"])
    assert event["status"] == "applied"
    assert len(list(backups.iterdir())) == 3

    # --- delete setup: one retained staged content and a legacy smart playlist --
    with mutate(
        db_path, backups, open_db=open_rekordbox, invalidate_cache=cache.invalidate
    ) as db:
        tag_content(db, row_x["content_id"], tag_id)
        retained_tag = find_or_create_mytag(db, "IT Retained", "Situation")
        tag_content(db, content_b, retained_tag.ID)
        retained_tag_id = str(retained_tag.ID)
        folder = ensure_playlist_folder(db, "Event Imports")
        create_or_repair_smart_playlist(
            db, "IT Event Lifecycle - Smart", folder.ID, tag_id
        )
    assert len(list(backups.iterdir())) == 4
    # the raw setup mutate above deliberately skipped the xml snapshot/restore
    # (it is not the events pipeline), so pyrekordbox rewrote the xml at its
    # commit; the delete below must restore byte-identically to THIS state.
    xml_sha_pre_delete = _sha256(xml_path)

    # --- delete: exact dry-run preview, zero writes -------------------------------
    preview = delete_event(
        conn, db_path, backups, cache, storage_root, event, dry_run=True
    )
    assert preview["dry_run"] is True
    actions = {track["content_id"]: track for track in preview["tracks"]}
    content_c = next(
        track["content_id"]
        for track in preview["tracks"]
        if track["source_path"] == str(staged_c)
    )
    assert actions[row_x["content_id"]]["action"] == "already_permanent"
    assert actions[row_a["content_id"]]["action"] == "keep_in_place"
    assert actions[content_b]["action"] == "migrate_to_collection"
    assert actions[content_b]["retaining_mytags"] == ["IT Retained"]
    assert actions[content_b]["anlz_update_required"] is False
    assert actions[content_b]["destination_path"].endswith(
        "/rekordbox/Collection/Syncbox IT Staged Tune QQ.mp3"
    )
    assert actions[content_c]["action"] == "delete_with_event"
    assert {p["name"] for p in preview["playlists"]} == {
        "IT Event Lifecycle",
        "IT Event Lifecycle - Smart",
    }
    assert str(staged_b) in preview["staging_artifacts"]
    assert str(staged_c) in preview["staging_artifacts"]
    assert len(list(backups.iterdir())) == 4  # dry-run wrote nothing

    # --- real delete ---------------------------------------------------------------
    deletions = []

    def fake_delete(path, *, consent_to_permanent_delete=False):
        Path(path).unlink()
        deletions.append(str(path))
        return "trashed"

    monkeypatch.setattr(event_delete, "delete_file", fake_delete)
    done = delete_event(
        conn,
        db_path,
        backups,
        cache,
        storage_root,
        event,
        dry_run=False,
        plan=preview,
    )
    assert done["dry_run"] is False
    # executed payload == previewed payload (B10/D11 exact preview)
    assert {track["content_id"]: track["action"] for track in done["tracks"]} == {
        track["content_id"]: track["action"] for track in preview["tracks"]
    }

    # artifacts cleaned only after the durable commit; staging fully gone (T8/T12)
    assert not staging.exists()
    assert str(staged_b) in deletions and str(staged_c) in deletions
    assert _sha256(xml_path) == xml_sha_pre_delete  # byte-identical restore (1.6)

    ro = rb.open_readonly(db_path)
    for gone in (row_a["content_id"], content_c):
        tup = ro.execute(
            "SELECT rb_local_deleted, rb_local_synced, rb_data_status,"
            " rb_local_data_status FROM djmdContent WHERE ID = ?",
            (gone,),
        ).fetchone()
        assert tuple(int(x) for x in tup) == (1, 0, 258, 0)  # exact 1.1 tuple
    # Content carrying another tag survives in place; only the event link died.
    assert (
        int(
            ro.execute(
                "SELECT rb_local_deleted FROM djmdContent WHERE ID = ?",
                (row_x["content_id"],),
            ).fetchone()[0]
        )
        == 0
    )
    assert (
        ro.execute(
            "SELECT COUNT(*) FROM djmdSongMyTag WHERE ContentID = ?"
            " AND MyTagID != ? AND rb_local_deleted = 0",
            (row_x["content_id"], tag_id),
        ).fetchone()[0]
        >= 1
    )
    assert (
        int(
            ro.execute(
                "SELECT rb_local_deleted FROM djmdSongMyTag"
                " WHERE ContentID = ? AND MyTagID = ?",
                (row_x["content_id"], tag_id),
            ).fetchone()[0]
        )
        == 1
    )
    migrated = ro.execute(
        "SELECT FolderPath, rb_local_deleted FROM djmdContent WHERE ID = ?",
        (content_b,),
    ).fetchone()
    assert migrated[0] == stored_form(
        actions[content_b]["destination_path"], storage_root
    )
    assert int(migrated[1] or 0) == 0
    assert (
        ro.execute(
            "SELECT COUNT(*) FROM djmdSongMyTag WHERE ContentID = ? "
            "AND MyTagID = ? AND rb_local_deleted = 0",
            (content_b, retained_tag_id),
        ).fetchone()[0]
        == 1
    )
    # smart playlist cleaned by current AND legacy name; event tag gone
    assert (
        ro.execute(
            "SELECT COUNT(*) FROM djmdPlaylist WHERE Name IN (?, ?)"
            " AND rb_local_deleted = 0",
            ("IT Event Lifecycle", "IT Event Lifecycle - Smart"),
        ).fetchone()[0]
        == 0
    )
    assert (
        int(
            ro.execute(
                "SELECT rb_local_deleted FROM djmdMyTag WHERE ID = ?", (tag_id,)
            ).fetchone()[0]
        )
        == 1
    )
    assert ro.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    ro.close()

    # app DB rows gone (cascade), exactly 5 mutations left 5 backups
    assert get_event(conn, event["id"]) is None
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM event_tracks WHERE event_id = ?", (event["id"],)
        ).fetchone()[0]
        == 0
    )
    assert len(list(backups.iterdir())) == 5
    conn.close()
