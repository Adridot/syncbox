"""Batch track removal (event-track-removal): the shared classification, the
two group-bys that keep shared audio alive, and the destructive execution.

The riskiest path in the repository after full event deletion: it writes to
the user's real Rekordbox database and trashes audio. Every test below is
written from the failure it must make impossible.
"""

import inspect
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from syncbox import appdb, event_delete, event_remove
from syncbox.events_service import add_track, create_event, list_event_tracks
from syncbox.platform_os import PermanentDeleteConsentRequired
from syncbox.safety.mutate import StaleSnapshotError


class FakeCache:
    def __init__(self):
        self.invalidated = 0

    def invalidate(self):
        self.invalidated += 1


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    yield connection
    connection.close()


def rb_query(contents=(), tag=None, links=()):
    """A `query` callable over the REAL SQL of the removal planner.

    contents: (content_id, title, artist, folder_path)
    tag:      (tag_id, name) for the event MyTag under 'Situation'
    links:    (content_id, tag_id, tag_name) active MyTag links
    """
    db = sqlite3.connect(":memory:")
    db.executescript(
        "CREATE TABLE djmdContent (ID TEXT, Title TEXT, ArtistID TEXT,"
        " FolderPath TEXT, rb_local_deleted INTEGER);"
        "CREATE TABLE djmdArtist (ID TEXT, Name TEXT);"
        "CREATE TABLE djmdMyTag (ID TEXT, Name TEXT, ParentID TEXT,"
        " rb_local_deleted INTEGER);"
        "CREATE TABLE djmdSongMyTag (ContentID TEXT, MyTagID TEXT,"
        " rb_local_deleted INTEGER);"
    )
    for content_id, title, artist, folder_path in contents:
        db.execute(
            "INSERT INTO djmdContent VALUES (?, ?, ?, ?, 0)",
            (content_id, title, f"A{content_id}", folder_path),
        )
        db.execute("INSERT INTO djmdArtist VALUES (?, ?)", (f"A{content_id}", artist))
    db.execute("INSERT INTO djmdMyTag VALUES ('cat', 'Situation', 'root', 0)")
    if tag is not None:
        db.execute("INSERT INTO djmdMyTag VALUES (?, ?, 'cat', 0)", tag)
    for content_id, tag_id, tag_name in links:
        if tag_id != (tag[0] if tag else None):
            db.execute(
                "INSERT OR IGNORE INTO djmdMyTag VALUES (?, ?, 'cat', 0)",
                (tag_id, tag_name),
            )
        db.execute(
            "INSERT INTO djmdSongMyTag VALUES (?, ?, 0)", (content_id, tag_id)
        )

    def query(sql, params):
        return db.execute(sql, params).fetchall()

    return query


def seeded_event(conn, storage, name="Gig", tracks=()):
    """An event plus rows: (title, status, content_id, staged filename, isrc)."""
    event = create_event(conn, storage, name)
    out = []
    for title, status, content_id, filename, isrc in tracks:
        row = add_track(conn, event, title=title)
        path = None
        if filename is not None:
            path = Path(event["staging_dir"]) / "audio" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(b"audio-" + filename.encode())
        conn.execute(
            "UPDATE event_tracks SET status = ?, content_id = ?,"
            " staging_file_path = ?, isrc = ? WHERE id = ?",
            (status, content_id, str(path) if path else None, isrc, row["id"]),
        )
        out.append(conn.execute(
            "SELECT * FROM event_tracks WHERE id = ?", (row["id"],)
        ).fetchone()["id"])
    return event, out


# --- 1.2 the shared classification --------------------------------------------------


def test_classify_removal_covers_the_four_outcomes():
    """The one rule that must never diverge between the two destructive
    paths. Tested directly here, not only through the deletion plan."""
    assert event_delete.classify_removal("permanent_library", True, ["t"]) == (
        "already_permanent"
    )
    assert event_delete.classify_removal("app_managed", True, ["t"]) == (
        "migrate_to_collection"
    )
    assert event_delete.classify_removal("app_managed", True, []) == (
        "delete_with_event"
    )
    assert event_delete.classify_removal("external", False, []) == "keep_in_place"
    # ownership wins over everything: a permanent-library file is never
    # deleted, whatever else claims it.
    assert event_delete.classify_removal("permanent_library", False, []) == (
        "already_permanent"
    )


# --- 2. the removal plan ------------------------------------------------------------


def test_plan_covers_untag_only_and_delete_with_event(conn, tmp_path):
    storage = tmp_path / "storage"
    owned = storage / "Music" / "Owned.mp3"
    owned.parent.mkdir(parents=True)
    owned.write_bytes(b"owned")
    event, ids = seeded_event(
        conn,
        storage,
        tracks=[
            ("Owned", "applied", "C1", None, None),
            ("Brought in", "applied", "C2", "brought.mp3", None),
        ],
    )
    tracks = list_event_tracks(conn, event["id"])
    staged = Path(tracks[1]["staging_file_path"])
    query = rb_query(
        contents=[("C1", "Owned", "Artist", str(owned)),
                  ("C2", "Brought in", "Artist", str(staged))],
        tag=("T1", event["default_tag"]),
        links=[("C1", "T1", event["default_tag"]), ("C2", "T1", event["default_tag"])],
    )

    plan = event_remove.plan_removal(
        query, event, tracks, ids, storage, tmp_path / "master.db", [["1", "2"]]
    )

    assert plan["plan_version"] == 1 and plan["needs_rekordbox"] is True
    assert plan["tag_id"] == "T1" and plan["unresolved"] == []
    assert [(t["track_id"], t["action"], t["file_deleted"]) for t in plan["tracks"]] == [
        (ids[0], "keep_in_place", False),
        (ids[1], "delete_with_event", True),
    ]
    assert plan["entries"] == [
        {"content_id": "C1", "source_path": str(owned), "soft_delete": False},
        {"content_id": "C2", "source_path": str(staged), "soft_delete": True},
    ]
    assert plan["expected_file_deletions"] == [str(staged)]
    # The file's expected state is recorded so execution can prove it did
    # not move between the preview and the deletion.
    assert plan["validation"]["cleanup_files"][0]["sha256"]


def test_shared_isrc_group_degrades_to_no_action_when_partially_covered(
    conn, tmp_path
):
    """The everyday single-vs-album-edit case: two Spotify ids sharing one
    non-empty ISRC share ONE staged file (5.7 claim rule) and ONE content row
    (apply_event reuses it via find_active_content_by_path). Removing one of
    them must touch NOTHING."""
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn,
        storage,
        tracks=[
            ("Single", "applied", "C9", "shared.mp3", "GB1234567890"),
            ("Album edit", "applied", "C9", "shared.mp3", "GB1234567890"),
        ],
    )
    tracks = list_event_tracks(conn, event["id"])
    staged = Path(tracks[0]["staging_file_path"])
    assert tracks[0]["staging_file_path"] == tracks[1]["staging_file_path"]
    query = rb_query(
        contents=[("C9", "Single", "Artist", str(staged))],
        tag=("T1", event["default_tag"]),
        links=[("C9", "T1", event["default_tag"])],
    )

    partial = event_remove.plan_removal(
        query, event, tracks, [ids[0]], storage, tmp_path / "master.db", None
    )
    assert partial["entries"] == []  # no untag, no soft-delete
    assert partial["expected_file_deletions"] == []
    assert partial["tracks"][0]["action"] == "keep_in_place"
    assert partial["tracks"][0]["file_deleted"] is False
    assert partial["tracks"][0]["shared_with_kept_track"] is True

    whole = event_remove.plan_removal(
        query, event, tracks, ids, storage, tmp_path / "master.db", None
    )
    # Both rows lose their audio, but the entry and the file go exactly ONCE.
    assert [t["file_deleted"] for t in whole["tracks"]] == [True, True]
    assert whole["entries"] == [
        {"content_id": "C9", "source_path": str(staged), "soft_delete": True}
    ]
    assert whole["expected_file_deletions"] == [str(staged)]


def test_file_shared_with_a_row_outside_the_batch_is_kept(conn, tmp_path):
    """Second group-by, on its own: the entry is fully covered but another
    live row (a rejected adoption keeping its file referenced) still holds
    the staged file. The entry goes, the file stays."""
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn,
        storage,
        tracks=[
            ("Applied", "applied", "C3", "shared.mp3", None),
            ("Rejected", "ignored", None, "shared.mp3", None),
        ],
    )
    tracks = list_event_tracks(conn, event["id"])
    staged = Path(tracks[0]["staging_file_path"])
    query = rb_query(
        contents=[("C3", "Applied", "Artist", str(staged))],
        tag=("T1", event["default_tag"]),
        links=[("C3", "T1", event["default_tag"])],
    )

    plan = event_remove.plan_removal(
        query, event, tracks, [ids[0]], storage, tmp_path / "master.db", None
    )
    assert plan["entries"][0]["soft_delete"] is True
    assert plan["expected_file_deletions"] == []
    assert plan["tracks"][0]["file_deleted"] is False


def test_retained_by_another_mytag_blocks_the_batch(conn, tmp_path):
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn, storage, tracks=[("Tagged", "applied", "C4", "kept.mp3", None)]
    )
    tracks = list_event_tracks(conn, event["id"])
    staged = Path(tracks[0]["staging_file_path"])
    query = rb_query(
        contents=[("C4", "Tagged", "Artist", str(staged))],
        tag=("T1", event["default_tag"]),
        links=[("C4", "T1", event["default_tag"]), ("C4", "T9", "Energy")],
    )

    plan = event_remove.plan_removal(
        query, event, tracks, ids, storage, tmp_path / "master.db", None
    )
    assert plan["unresolved"] == [
        {
            "id": "retained_by_other_mytag-C4",
            "kind": "retained_by_other_mytag",
            "title": "Tagged",
            "artist": "Artist",
            "content_id": "C4",
            "retaining_mytags": ["Energy"],
            "resolution_options": ["remove_other_mytag", "delete_event"],
        }
    ]
    # Nothing at all is planned for a blocked row: no entry, no deletion,
    # and no per-track outcome that could be mistaken for one.
    assert plan["tracks"] == [] and plan["entries"] == []
    assert plan["expected_file_deletions"] == []


def test_never_applied_batch_needs_no_rekordbox_at_all(conn, tmp_path):
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn,
        storage,
        tracks=[
            ("Ready", "ready", None, "ready.mp3", None),
            ("Missing", "missing", None, None, None),
        ],
    )
    tracks = list_event_tracks(conn, event["id"])
    staged = Path(tracks[0]["staging_file_path"])

    assert event_remove.needs_rekordbox(tracks, ids) is False
    # No query callable is ever used: a never-applied batch must not need
    # master.db to be readable, let alone closed.
    plan = event_remove.plan_removal(
        None, event, tracks, ids, storage, tmp_path / "master.db", None
    )
    assert plan["needs_rekordbox"] is False and plan["tag_id"] is None
    assert [t["action"] for t in plan["tracks"]] == ["never_applied"] * 2
    assert plan["entries"] == []
    assert plan["expected_file_deletions"] == [str(staged)]


def test_plan_refuses_a_foreign_or_already_removed_track(conn, tmp_path):
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn, storage, tracks=[("Gone", "removed", None, "x.mp3", None)]
    )
    tracks = list_event_tracks(conn, event["id"])
    with pytest.raises(event_remove.EventRemovalError, match="already removed"):
        event_remove.plan_removal(
            None, event, tracks, ids, storage, tmp_path / "master.db", None
        )
    with pytest.raises(KeyError):
        event_remove.plan_removal(
            None, event, tracks, [999], storage, tmp_path / "master.db", None
        )


# --- 3. execution -------------------------------------------------------------------


def _execute_harness(monkeypatch, *, fail=False):
    """mutate() + the two rb_write calls, recorded. No master.db needed."""
    calls = []

    @contextmanager
    def fake_mutate(db_path, backups_root, **kwargs):
        calls.append(("mutate", kwargs.get("expected_fingerprint")))
        yield "db"
        if fail:
            raise RuntimeError("database commit failed")
        if kwargs.get("invalidate_cache"):
            kwargs["invalidate_cache"]()

    monkeypatch.setattr(event_remove, "mutate", fake_mutate)
    monkeypatch.setattr(event_remove, "_verify_live_plan", lambda *a: calls.append(
        ("verify_live", None)
    ))
    monkeypatch.setattr(
        event_remove, "untag_content", lambda db, c, t: calls.append(("untag", c, t))
    )
    monkeypatch.setattr(
        event_remove,
        "soft_delete_content",
        lambda db, c: calls.append(("soft_delete", c)),
    )
    return calls


def _applied_event(conn, tmp_path, monkeypatch, tracks):
    """An applied event plus a canned preview plan, mocked at read time."""
    storage = tmp_path / "storage"
    event, ids = seeded_event(conn, storage, tracks=tracks)
    conn.execute("UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],))
    rows = list_event_tracks(conn, event["id"])
    return event, ids, rows, storage


def test_execution_untags_soft_deletes_and_then_trashes_the_file(
    conn, tmp_path, monkeypatch
):
    """The whole happy path, in order: Rekordbox first, files after."""
    event, ids, rows, storage = _applied_event(
        conn,
        tmp_path,
        monkeypatch,
        [
            ("Owned", "applied", "C1", None, None),
            ("Brought in", "applied", "C2", "brought.mp3", None),
            ("Stays", "applied", "C3", "stays.mp3", None),
        ],
    )
    owned = storage / "Music" / "Owned.mp3"
    owned.parent.mkdir(parents=True)
    owned.write_bytes(b"owned")
    staged = Path(rows[1]["staging_file_path"])
    kept = Path(rows[2]["staging_file_path"])
    query = rb_query(
        contents=[
            ("C1", "Owned", "Artist", str(owned)),
            ("C2", "Brought in", "Artist", str(staged)),
            ("C3", "Stays", "Artist", str(kept)),
        ],
        tag=("T1", event["default_tag"]),
        links=[(c, "T1", event["default_tag"]) for c in ("C1", "C2", "C3")],
    )
    monkeypatch.setattr(
        event_remove,
        "read_removal_plan",
        lambda db, ev, tr, tid, root: event_remove.plan_removal(
            query, ev, tr, tid, root, db, [["1", "2"]]
        ),
    )
    calls = _execute_harness(monkeypatch)
    db_path = tmp_path / "live" / "master.db"
    db_path.parent.mkdir()
    db_path.write_bytes(b"db")
    xml = db_path.with_name("masterPlaylists6.xml")
    xml.write_bytes(b"<original/>")
    deleted = []
    monkeypatch.setattr(
        event_remove, "delete_file", lambda p, **kw: deleted.append(str(p))
    )

    plan = event_remove.remove_tracks(
        conn, db_path, tmp_path / "backups", FakeCache(), storage, event,
        track_ids=ids[:2],
    )
    result = event_remove.remove_tracks(
        conn, db_path, tmp_path / "backups", FakeCache(), storage, event,
        track_ids=ids[:2], dry_run=False, plan=plan,
    )

    assert result["dry_run"] is False
    assert result["removed_tracks"] == ids[:2]
    assert result["removed_files"] == [str(staged)] and result["kept_files"] == []
    assert calls == [
        ("mutate", (("1", "2"),)),
        ("verify_live", None),
        ("untag", "C1", "T1"),
        ("untag", "C2", "T1"),
        ("soft_delete", "C2"),
    ]
    assert deleted == [str(staged)]
    # The event's own footprint and the untouched track survive intact.
    assert Path(event["staging_dir"]).is_dir() and kept.is_file()
    assert xml.read_bytes() == b"<original/>"
    assert conn.execute(
        "SELECT status FROM events WHERE id = ?", (event["id"],)
    ).fetchone()["status"] == "applied"
    after = {row["id"]: row for row in list_event_tracks(conn, event["id"])}
    assert after[ids[0]]["status"] == "removed"
    assert after[ids[0]]["content_id"] is None
    # The staged path is RETAINED so an undeleted file is never re-adopted.
    assert after[ids[1]]["staging_file_path"] == str(staged)
    assert after[ids[2]]["status"] == "applied"


def test_removal_never_touches_the_event_mytag_playlist_or_row():
    """Structural: the module that removes tracks has no way to remove the
    event. Cheaper and stricter than asserting it afterwards."""
    source = inspect.getsource(event_remove)
    for forbidden in (
        "soft_delete_mytag",
        "soft_delete_playlist",
        "DELETE FROM events",
        "rmdir",
        "DELETE FROM event_tracks",
    ):
        assert forbidden not in source


def test_execution_refuses_a_stale_foreign_or_unresolved_plan(
    conn, tmp_path, monkeypatch
):
    event, ids, rows, storage = _applied_event(
        conn, tmp_path, monkeypatch,
        [("Brought in", "applied", "C2", "brought.mp3", None)],
    )
    staged = Path(rows[0]["staging_file_path"])
    query = rb_query(
        contents=[("C2", "Brought in", "Artist", str(staged))],
        tag=("T1", event["default_tag"]),
        links=[("C2", "T1", event["default_tag"])],
    )
    monkeypatch.setattr(
        event_remove,
        "read_removal_plan",
        lambda db, ev, tr, tid, root: event_remove.plan_removal(
            query, ev, tr, tid, root, db, [["1", "2"]]
        ),
    )
    _execute_harness(monkeypatch)
    monkeypatch.setattr(event_remove, "delete_file", lambda p, **kw: None)
    args = (conn, tmp_path / "master.db", tmp_path / "b", FakeCache(), storage, event)
    plan = event_remove.remove_tracks(*args, track_ids=ids)

    # (a) a plan that does not match a freshly built one
    with pytest.raises(StaleSnapshotError, match="stale"):
        event_remove.remove_tracks(
            *args, track_ids=ids, dry_run=False,
            plan={**plan, "fingerprint": [["9", "9"]]},
        )
    # (b) a plan for another event
    with pytest.raises(event_remove.EventRemovalError, match="different event"):
        event_remove.remove_tracks(
            *args, track_ids=ids, dry_run=False,
            plan={**plan, "event_id": plan["event_id"] + 1},
        )
    # (c) a plan carrying unresolved cases
    with pytest.raises(event_remove.EventRemovalError, match="unresolved"):
        event_remove.remove_tracks(
            *args, track_ids=ids, dry_run=False,
            plan={**plan, "unresolved": [{"kind": "retained_by_other_mytag"}]},
        )
    assert staged.is_file()
    assert list_event_tracks(conn, event["id"])[0]["status"] == "applied"


def test_a_file_that_moved_after_the_preview_is_kept_and_reported(
    conn, tmp_path, monkeypatch
):
    """Post-commit the Rekordbox change stands, so a changed file is kept
    and REPORTED rather than deleted or turned into an error."""
    event, ids, rows, storage = _applied_event(
        conn, tmp_path, monkeypatch,
        [("Brought in", "applied", "C2", "brought.mp3", None)],
    )
    staged = Path(rows[0]["staging_file_path"])
    query = rb_query(
        contents=[("C2", "Brought in", "Artist", str(staged))],
        tag=("T1", event["default_tag"]),
        links=[("C2", "T1", event["default_tag"])],
    )
    monkeypatch.setattr(
        event_remove,
        "read_removal_plan",
        lambda db, ev, tr, tid, root: event_remove.plan_removal(
            query, ev, tr, tid, root, db, [["1", "2"]]
        ),
    )
    _execute_harness(monkeypatch)
    deleted = []
    monkeypatch.setattr(
        event_remove, "delete_file", lambda p, **kw: deleted.append(str(p))
    )
    args = (conn, tmp_path / "master.db", tmp_path / "b", FakeCache(), storage, event)
    plan = event_remove.remove_tracks(*args, track_ids=ids)
    # The user replaced the audio between the preview and the confirmation:
    # the pre-commit assertion aborts everything, nothing is written.
    staged.write_bytes(b"different audio entirely")
    with pytest.raises(StaleSnapshotError):
        event_remove.remove_tracks(*args, track_ids=ids, dry_run=False, plan=plan)
    assert deleted == [] and staged.is_file()

    # Same divergence appearing only AFTER the commit (the echo check and
    # the pre-commit assertion both passed): kept and reported.
    monkeypatch.setattr(event_remove, "read_removal_plan", lambda *a: plan)
    monkeypatch.setattr(event_remove, "_verify_precommit", lambda plan, staging: None)
    result = event_remove.remove_tracks(
        *args, track_ids=ids, dry_run=False, plan=plan
    )
    assert deleted == [] and staged.is_file()
    assert result["removed_files"] == []
    assert result["kept_files"] == [{"path": str(staged), "reason": "changed"}]


def test_permanent_delete_consent_is_asked_only_when_nothing_was_done(
    conn, tmp_path, monkeypatch
):
    """A never-applied batch commits nothing, so the 428 consent round trip
    can retry exactly; after a Rekordbox commit it never can, so the file is
    kept and reported instead of tearing the application state."""
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn, storage, tracks=[("Ready", "ready", None, "ready.mp3", None)]
    )
    staged = Path(list_event_tracks(conn, event["id"])[0]["staging_file_path"])
    seen = []

    def no_trash(path, *, consent_to_permanent_delete=False):
        seen.append(consent_to_permanent_delete)
        if not consent_to_permanent_delete:
            raise PermanentDeleteConsentRequired(Path(path), OSError("no trash"))

    monkeypatch.setattr(event_remove, "delete_file", no_trash)
    args = (conn, tmp_path / "master.db", tmp_path / "b", FakeCache(), storage, event)
    plan = event_remove.remove_tracks(*args, track_ids=ids)
    with pytest.raises(PermanentDeleteConsentRequired):
        event_remove.remove_tracks(*args, track_ids=ids, dry_run=False, plan=plan)
    # Nothing was written: the exact same plan is still executable.
    assert list_event_tracks(conn, event["id"])[0]["status"] == "ready"
    result = event_remove.remove_tracks(
        *args, track_ids=ids, dry_run=False, plan=plan,
        consent_to_permanent_delete=True,
    )
    assert seen == [False, True] and result["removed_files"] == [str(staged)]


def test_a_failed_rekordbox_write_deletes_no_file_and_removes_no_row(
    conn, tmp_path, monkeypatch
):
    """mutate() rolls the database back to its backup; this proves the files
    and the event rows never moved ahead of it."""
    event, ids, rows, storage = _applied_event(
        conn, tmp_path, monkeypatch,
        [("Brought in", "applied", "C2", "brought.mp3", None)],
    )
    staged = Path(rows[0]["staging_file_path"])
    query = rb_query(
        contents=[("C2", "Brought in", "Artist", str(staged))],
        tag=("T1", event["default_tag"]),
        links=[("C2", "T1", event["default_tag"])],
    )
    monkeypatch.setattr(
        event_remove,
        "read_removal_plan",
        lambda db, ev, tr, tid, root: event_remove.plan_removal(
            query, ev, tr, tid, root, db, [["1", "2"]]
        ),
    )
    _execute_harness(monkeypatch, fail=True)
    deleted = []
    monkeypatch.setattr(
        event_remove, "delete_file", lambda p, **kw: deleted.append(str(p))
    )
    args = (conn, tmp_path / "master.db", tmp_path / "b", FakeCache(), storage, event)
    plan = event_remove.remove_tracks(*args, track_ids=ids)
    with pytest.raises(RuntimeError, match="commit failed"):
        event_remove.remove_tracks(*args, track_ids=ids, dry_run=False, plan=plan)

    assert deleted == [] and staged.is_file()
    row = list_event_tracks(conn, event["id"])[0]
    assert row["status"] == "applied" and row["content_id"] == "C2"


def test_removing_the_last_pending_track_leaves_the_event_applied(
    conn, tmp_path, monkeypatch
):
    event, ids, rows, storage = _applied_event(
        conn, tmp_path, monkeypatch,
        [
            ("Applied", "applied", "C1", None, None),
            ("Left the playlist", "removed_upstream", None, "gone.mp3", None),
            ("Still missing", "missing", None, None, None),
        ],
    )
    conn.execute(
        "UPDATE events SET status = 'partially_applied' WHERE id = ?", (event["id"],)
    )
    monkeypatch.setattr(event_remove, "delete_file", lambda p, **kw: None)
    args = (conn, tmp_path / "master.db", tmp_path / "b", FakeCache(), storage, event)
    plan = event_remove.remove_tracks(*args, track_ids=ids[1:])
    result = event_remove.remove_tracks(
        *args, track_ids=ids[1:], dry_run=False, plan=plan
    )
    assert result["event_status"] == "applied"
    assert conn.execute(
        "SELECT status FROM events WHERE id = ?", (event["id"],)
    ).fetchone()["status"] == "applied"


def test_a_pending_event_is_never_promoted_by_a_removal(conn, tmp_path, monkeypatch):
    """recompute_event_status returns 'applied' as soon as nothing pending
    remains — a lie on an event that was never applied at all."""
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn, storage, tracks=[("Ready", "ready", None, "ready.mp3", None)]
    )
    monkeypatch.setattr(event_remove, "delete_file", lambda p, **kw: None)
    args = (conn, tmp_path / "master.db", tmp_path / "b", FakeCache(), storage, event)
    plan = event_remove.remove_tracks(*args, track_ids=ids)
    event_remove.remove_tracks(*args, track_ids=ids, dry_run=False, plan=plan)
    assert conn.execute(
        "SELECT status FROM events WHERE id = ?", (event["id"],)
    ).fetchone()["status"] == "pending"


def test_a_planned_path_outside_staging_is_never_deleted(conn, tmp_path, monkeypatch):
    """Belt and braces on the one call that destroys data: even a plan that
    passed every echo check cannot point the deletion outside the event."""
    storage = tmp_path / "storage"
    event, ids = seeded_event(
        conn, storage, tracks=[("Ready", "ready", None, "ready.mp3", None)]
    )
    outside = tmp_path / "precious.mp3"
    outside.write_bytes(b"not yours")
    plan = event_remove.read_removal_plan(
        tmp_path / "master.db", event, list_event_tracks(conn, event["id"]), ids, storage
    )
    plan["expected_file_deletions"] = [str(outside)]
    with pytest.raises(event_remove.EventMigrationError, match="escapes event staging"):
        event_remove._cleanup_files(
            plan,
            event_delete.event_staging(event, storage),
            consent=False,
            allow_consent_error=False,
        )
    assert outside.is_file()
