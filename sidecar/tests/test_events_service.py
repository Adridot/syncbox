"""Events service tests (SPEC-UNIFIED 5.7 + 11.1/11.2, SPEC-01 1.8).

Unit tests run on the app DB + fakes (no master.db); the lifecycle
integration test needs the real fixture and always works on a copy under
tmp_path (apply -> reapply delta -> delete with preview).
"""

import hashlib
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from syncbox import appdb, events_service
from syncbox.events_service import (
    add_track,
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

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "poc" / "testdata"
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
        conn.execute(
            "UPDATE events SET status = ? WHERE id = ?", (status, event["id"])
        )
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
        conn, event, spotify_track_id="sp:1", resolver=spotify("Shared Song", "USAAA0000001")
    )
    same_b = add_track(
        conn, event, spotify_track_id="sp:2", resolver=spotify("Shared Song", "USAAA0000001")
    )
    diff_isrc = add_track(
        conn, event, spotify_track_id="sp:3", resolver=spotify("Shared Song", "GBZZZ0000009")
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


# --- status recompute + strict no-op (11.2) ----------------------------------------


def test_recompute_event_status():
    assert recompute_event_status([]) == "applied"
    assert recompute_event_status(["applied", "ignored"]) == "applied"
    for pending in ("matched", "ready", "missing", "ambiguous"):
        assert recompute_event_status(["applied", pending]) == "partially_applied"


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
    def fake_mutate(db_path, backups_root, *, retention=15, expected_fingerprint=None, open_db, invalidate_cache=None):
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
        events_service, "find_or_create_mytag", lambda db, n, c: SimpleNamespace(ID="T1")
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
    def fake_mutate(db_path, backups_root, *, retention=15, expected_fingerprint=None, open_db, invalidate_cache=None):
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
    def fake_mutate(db_path_, backups_root, *, retention=15, expected_fingerprint=None, open_db, invalidate_cache=None):
        yield "db"
        # pyrekordbox rewrites the xml as part of its commit
        xml_path.write_bytes(b"<pyrekordbox rewrote this/>")

    _fake_apply_helpers(monkeypatch, fake_mutate)

    result = apply_event(conn, db_path, tmp_path / "b", FakeCache([]), storage, event)
    assert result["applied"] == 1
    assert xml_path.read_bytes() == original  # byte-identical restore (1.6)
    bak = Path(event["staging_dir"]) / "masterPlaylists6.xml.bak"
    assert bak.read_bytes() == original  # covers the commit->restore window


def test_delete_event_flows_consent_to_delete_file(conn, tmp_path, monkeypatch):
    """D21/6.9: the consent_to_permanent_delete flag must reach
    platform_os.delete_file for every staged artifact - both values."""

    class EmptyRO:
        def execute(self, sql, params):
            return SimpleNamespace(fetchall=lambda: [])

        def close(self):
            pass

    consents = []

    def fake_delete(path, *, consent_to_permanent_delete=False):
        consents.append(consent_to_permanent_delete)
        Path(path).unlink()
        return "trashed"

    monkeypatch.setattr(events_service, "open_readonly", lambda p: EmptyRO())
    monkeypatch.setattr(events_service, "delete_file", fake_delete)

    for consent in (True, False):
        event = create_event(conn, tmp_path / "storage", f"Consent {consent}")
        (Path(event["staging_dir"]) / "a.mp3").write_bytes(b"x")
        done = delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "b",
            FakeCache([]),
            tmp_path / "storage",
            event,
            dry_run=False,
            consent_to_permanent_delete=consent,
        )
        assert len(done["removed_files"]) == 1
        assert get_event(conn, event["id"]) is None
    assert consents == [True, False]  # the flag flowed through, per call


# --- delete preview rules (SPEC-01 1.8) --------------------------------------------


def test_delete_preview_protection_rules(tmp_path):
    storage = tmp_path / "store"
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "a.mp3").write_bytes(b"x")
    (staging / "masterPlaylists6.xml.bak").write_bytes(b"<xml/>")
    event = {"name": "Gala Night", "default_tag": "Gala Night", "staging_dir": str(staging)}
    protected_path = "/store/rekordbox/Collection/track3.flac"  # volume-relative

    def query(sql, params):
        if sql == events_service._TAG_SQL:
            assert params == {"tag": "Gala Night", "category": "Situation"}
            return [("42",)]
        if sql == events_service._TAGGED_SQL:
            return [
                ("101", "Solo", "/somewhere/inbox/a.mp3"),
                ("102", "Tagged Elsewhere", "/somewhere/inbox/b.mp3"),
                ("103", "In Collection", protected_path),
            ]
        if sql == events_service._OTHER_TAGS_SQL:
            return [(1 if params["content_id"] == "102" else 0,)]
        if sql == events_service._PLAYLISTS_SQL:
            assert params["legacy"] == "Gala Night - Smart"
            return [("9", "Gala Night"), ("10", "Gala Night - Smart")]
        raise AssertionError(f"unexpected sql: {sql}")

    preview = events_service._delete_preview(query, event, storage)

    assert preview["tag_id"] == "42"
    by_id = {c["content_id"]: c for c in preview["contents"]}
    assert (by_id["101"]["action"], by_id["101"]["reason"]) == ("soft_delete", "event_only")
    assert (by_id["102"]["action"], by_id["102"]["reason"]) == ("keep", "carries_other_mytag")
    assert (by_id["103"]["action"], by_id["103"]["reason"]) == ("keep", "protected_path")
    assert {p["name"] for p in preview["playlists"]} == {
        "Gala Night",
        "Gala Night - Smart",
    }
    assert preview["artifacts"] == sorted(
        [str(staging / "a.mp3"), str(staging / "masterPlaylists6.xml.bak")]
    )


def test_delete_preview_without_tag_is_empty(tmp_path):
    event = {"name": "Ghost", "default_tag": "Ghost", "staging_dir": None}

    def query(sql, params):
        if sql == events_service._TAG_SQL:
            return []
        if sql == events_service._PLAYLISTS_SQL:
            return []
        raise AssertionError("content queries must not run without a tag")

    preview = events_service._delete_preview(query, event, tmp_path)
    assert preview == {"tag_id": None, "contents": [], "playlists": [], "artifacts": []}


# --- integration: apply -> reapply(delta) -> delete on the real fixture ------------


@needs_fixture
def test_event_lifecycle_on_real_db(tmp_path, monkeypatch):
    from syncbox import rb
    from syncbox.rb_write import (
        create_or_repair_smart_playlist,
        ensure_playlist_folder,
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

    # --- delete setup: a protected content + a legacy '<name> - Smart' playlist --
    with mutate(
        db_path, backups, open_db=open_rekordbox, invalidate_cache=cache.invalidate
    ) as db:
        tag_content(db, row_x["content_id"], tag_id)
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
    actions = {c["content_id"]: (c["action"], c["reason"]) for c in preview["contents"]}
    assert actions[row_x["content_id"]] == ("keep", "carries_other_mytag")
    assert actions[row_a["content_id"]] == ("soft_delete", "event_only")
    assert actions[content_b] == ("soft_delete", "event_only")
    assert {p["name"] for p in preview["playlists"]} == {
        "IT Event Lifecycle",
        "IT Event Lifecycle - Smart",
    }
    assert str(staged_b) in preview["artifacts"]
    assert str(staged_c) in preview["artifacts"]
    assert len(list(backups.iterdir())) == 4  # dry-run wrote nothing

    # --- real delete ---------------------------------------------------------------
    deletions = []

    def fake_delete(path, *, consent_to_permanent_delete=False):
        Path(path).unlink()
        deletions.append(str(path))
        return "trashed"

    monkeypatch.setattr(events_service, "delete_file", fake_delete)
    done = delete_event(
        conn, db_path, backups, cache, storage_root, event, dry_run=False
    )
    assert done["dry_run"] is False
    # executed payload == previewed payload (B10/D11 exact preview)
    assert {c["content_id"]: c["action"] for c in done["contents"]} == {
        c["content_id"]: c["action"] for c in preview["contents"]
    }

    # artifacts cleaned only after the durable commit; staging fully gone (T8/T12)
    assert not staging.exists()
    assert str(staged_b) in deletions and str(staged_c) in deletions
    assert _sha256(xml_path) == xml_sha_pre_delete  # byte-identical restore (1.6)

    ro = rb.open_readonly(db_path)
    for gone in (row_a["content_id"], content_b):
        tup = ro.execute(
            "SELECT rb_local_deleted, rb_local_synced, rb_data_status,"
            " rb_local_data_status FROM djmdContent WHERE ID = ?",
            (gone,),
        ).fetchone()
        assert tuple(int(x) for x in tup) == (1, 0, 258, 0)  # exact 1.1 tuple
    # protected content survives with its other tags; only the event link died
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
