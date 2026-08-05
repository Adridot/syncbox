"""Tests for library sync orchestration + apply-to-Rekordbox
(SPEC-UNIFIED 5.6, D16/D20/D22)."""

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from syncbox import appdb, library_service, missing_service, repos, spotify
from syncbox.library_service import ConflictError, apply_to_rekordbox, sync_one_source
from syncbox.spotify import SpotifyAuth, SpotifyClient

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "sidecar" / "tests" / "testdata"
FIXTURE = TESTDATA / "master.db"
PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="real master.db fixture not present"
)


# --- fakes (test_spotify.py FakeTransport pattern) --------------------------------


class FakeSecrets(dict):
    def get(self, name):  # type: ignore[override]
        return super().get(name)

    def set(self, name, value):
        self[name] = value


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, data=None, headers=None, method="GET"):
        self.calls.append({"url": url, "method": method})
        return self.responses.pop(0)


def make_client(*responses):
    secrets = FakeSecrets()
    secrets.set(spotify.ACCESS_TOKEN, "acc")
    transport = FakeTransport(*responses)
    auth = SpotifyAuth(lambda: "client-123", secrets, transport=transport)
    return SpotifyClient(auth, transport=transport, sleep=lambda _s: None), transport


def api_ok(payload):
    return (200, {}, json.dumps(payload).encode())


def item(track_id, title, artist, duration_ms=200_000, isrc=None, extra_ids=None):
    external_ids = dict(extra_ids or {})
    if isrc:
        external_ids["isrc"] = isrc
    return {
        "item": {
            "id": track_id,
            "name": title,
            "artists": [{"name": artist}],
            "duration_ms": duration_ms,
            "external_ids": external_ids,
            "type": "track",
        }
    }


def playlist_payload(items, snapshot="snap-1", next_url=None, name="My List"):
    return {
        "name": name,
        "snapshot_id": snapshot,
        "items": {"items": list(items), "next": next_url},
    }


class FakeCache:
    def __init__(self, rows):
        self.rows = rows
        self.invalidations = 0

    def get(self, storage_root):
        return self.rows

    @property
    def current_fingerprint(self):
        return ("fake-fp",)

    def invalidate(self):
        self.invalidations += 1


CANDIDATES = [
    {
        "content_id": "C1",
        "title": "Strobe",
        "artist": "deadmau5",
        "duration_ms": 200_000,
        "isrc": "USUS11100310",
    }
]


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    yield connection
    connection.close()


@pytest.fixture
def source(conn):
    return repos.add_source(conn, PLAYLIST_ID, name="old", tags=["House"])


# --- sync_one_source ---------------------------------------------------------------


def test_sync_paginates_matches_and_persists(conn, source, tmp_path):
    page2_url = "https://api.spotify.com/v1/playlists/x/items?offset=100"
    client, transport = make_client(
        api_ok(
            playlist_payload(
                [item("t1", "Strobe", "deadmau5", isrc="USUS11100310")],
                next_url=page2_url,
            )
        ),
        api_ok({"items": [item("t2", "Unknown Song", "Nobody")], "next": None}),
    )
    result = sync_one_source(
        conn, client, FakeCache(CANDIDATES), tmp_path / "storage", source
    )

    assert result["skipped"] is False
    assert transport.calls[1]["url"] == page2_url  # followed 'next'

    tracks = {t["spotify_track_id"]: t for t in repos.list_source_tracks(conn, source["id"])}
    assert tracks["t1"]["status"] == "matched"
    assert tracks["t1"]["content_id"] == "C1"
    assert tracks["t1"]["match_method"] == "isrc"
    assert tracks["t1"]["confidence"] == 100
    assert tracks["t1"]["tags"] == ["House"]  # inherited from source.tags
    assert tracks["t2"]["status"] == "missing"

    refreshed = repos.get_source(conn, source["id"])
    assert refreshed["status"] == "synced"
    assert refreshed["snapshot_id"] == "snap-1"
    assert refreshed["name"] == "My List"

    runs = repos.list_sync_runs(conn, source["id"])
    assert len(runs) == 1
    assert runs[0]["stats"]["total"] == 2
    assert runs[0]["stats"]["matched"] == 1
    assert runs[0]["stats"]["missing"] == 1


def test_sync_never_matches_a_streaming_twin(conn, source, tmp_path):
    """A streaming reference sharing the track's ISRC/title is NOT a local
    file: the synced track stays 'missing' instead of matching it."""
    streaming_twin = [
        {
            "content_id": "C9",
            "title": "Strobe",
            "artist": "deadmau5",
            "duration_ms": 200_000,
            "isrc": "USUS11100310",
            "spotify_track_id": "190jyVPH",
            "file_missing": False,
        }
    ]
    client, _ = make_client(
        api_ok(
            playlist_payload([item("t1", "Strobe", "deadmau5", isrc="USUS11100310")])
        )
    )
    sync_one_source(
        conn, client, FakeCache(streaming_twin), tmp_path / "storage", source
    )
    (track,) = repos.list_source_tracks(conn, source["id"])
    assert track["status"] == "missing"
    assert track["content_id"] is None


def test_sync_skips_when_snapshot_unchanged_but_records_a_run(
    conn, source, tmp_path, monkeypatch
):
    client, _ = make_client(
        api_ok(playlist_payload([item("t1", "Strobe", "deadmau5")], snapshot="snap-1"))
    )
    sync_one_source(conn, client, FakeCache(CANDIDATES), tmp_path, source)
    before = repos.list_source_tracks(conn, source["id"])

    source = repos.get_source(conn, source["id"])  # snapshot_id now snap-1
    payload = playlist_payload([], snapshot="snap-1")
    payload["images"] = [{"url": "https://i.scdn.co/cover.jpg"}]
    client2, transport2 = make_client(api_ok(payload))

    def fail_if_tracks_are_rewritten(*_args, **_kwargs):
        pytest.fail("valid links must not rewrite library tracks")

    monkeypatch.setattr(repos, "replace_source_tracks", fail_if_tracks_are_rewritten)
    result = sync_one_source(conn, client2, FakeCache(CANDIDATES), tmp_path, source)
    assert result["skipped"] is True
    assert len(transport2.calls) == 1  # meta fetch only, no pagination
    assert repos.list_source_tracks(conn, source["id"]) == before  # untouched
    runs = repos.list_sync_runs(conn, source["id"])
    assert len(runs) == 2
    assert runs[0]["stats"] == {"skipped": True}
    # cover backfill: a pre-0003 source gets its cover even on the skip path
    assert repos.get_source(conn, source["id"])["cover_url"] == "https://i.scdn.co/cover.jpg"


def test_unchanged_snapshot_repairs_stale_link_without_playlist_pagination(
    conn, source, tmp_path
):
    client, _ = make_client(
        api_ok(
            playlist_payload(
                [item("t1", "Strobe", "deadmau5", isrc="USUS11100310")],
                snapshot="snap-1",
            )
        )
    )
    sync_one_source(conn, client, FakeCache(CANDIDATES), tmp_path, source)
    source = repos.get_source(conn, source["id"])

    replacement = [
        {
            "content_id": "C2",
            "title": "Strobe",
            "artist": "deadmau5",
            "duration_ms": 200_000,
            "isrc": "USUS11100310",
        }
    ]
    # C1 is absent from this active snapshot, simulating a soft-deleted target.
    payload = playlist_payload([], snapshot="snap-1", next_url="unused-next-page")
    client2, transport2 = make_client(api_ok(payload))

    result = sync_one_source(conn, client2, FakeCache(replacement), tmp_path, source)

    assert result == {
        "skipped": False,
        "snapshot_id": "snap-1",
        "stats": {"total": 1, "matched": 1, "reconciled": 1},
    }
    assert len(transport2.calls) == 1
    (track,) = repos.list_source_tracks(conn, source["id"])
    assert track["status"] == "matched"
    assert track["content_id"] == "C2"
    assert track["match_method"] == "isrc"
    runs = repos.list_sync_runs(conn, source["id"])
    assert len(runs) == 2
    assert runs[0]["stats"] == {"total": 1, "matched": 1, "reconciled": 1}


def test_changed_snapshot_diffs_fresh_track_and_reconciles_carried_link(
    conn, source, tmp_path
):
    client, _ = make_client(
        api_ok(
            playlist_payload(
                [item("t1", "Old title", "Artist", isrc="OLD")], snapshot="snap-1"
            )
        )
    )
    original = [
        {
            "content_id": "C1",
            "title": "Old title",
            "artist": "Artist",
            "duration_ms": 200_000,
            "isrc": "OLD",
        }
    ]
    sync_one_source(conn, client, FakeCache(original), tmp_path, source)
    source = repos.get_source(conn, source["id"])

    candidates = [
        {
            "content_id": "C2",
            "title": "Fresh title",
            "artist": "Artist",
            "duration_ms": 200_000,
            "isrc": "NEW",
        },
        {
            "content_id": "C3",
            "title": "Fresh addition",
            "artist": "Other",
            "duration_ms": 210_000,
            "isrc": "ADDED",
        },
    ]
    client2, _ = make_client(
        api_ok(
            playlist_payload(
                [
                    item("t1", "Fresh title", "Artist", isrc="NEW"),
                    item(
                        "t2",
                        "Fresh addition",
                        "Other",
                        duration_ms=210_000,
                        isrc="ADDED",
                    ),
                ],
                snapshot="snap-2",
            )
        )
    )

    result = sync_one_source(conn, client2, FakeCache(candidates), tmp_path, source)

    tracks = {
        row["spotify_track_id"]: row
        for row in repos.list_source_tracks(conn, source["id"])
    }
    assert tracks["t1"]["content_id"] == "C2"
    assert tracks["t1"]["status"] == "matched"
    assert tracks["t2"]["content_id"] == "C3"
    assert tracks["t2"]["status"] == "matched"
    assert result["stats"] == {"total": 2, "matched": 2, "reconciled": 1}


def test_playlist_duplicate_is_ignored_and_absent_becomes_removed(conn, source, tmp_path):
    client, _ = make_client(
        api_ok(
            playlist_payload(
                [
                    item("t1", "Strobe", "deadmau5", isrc="USUS11100310"),
                    item("t1", "Strobe", "deadmau5", isrc="USUS11100310"),
                ]
            )
        )
    )
    sync_one_source(conn, client, FakeCache(CANDIDATES), tmp_path, source)
    rows = repos.list_source_tracks(conn, source["id"])
    # one row per (source, spotify_track_id); the duplicate OCCURRENCE is
    # dropped (5.6 ignores the occurrence, never the track itself), so the
    # first occurrence's real match survives
    assert [r["spotify_track_id"] for r in rows] == ["t1"]
    assert rows[0]["status"] == "matched"

    source = repos.get_source(conn, source["id"])
    client2, _ = make_client(api_ok(playlist_payload([], snapshot="snap-2")))
    sync_one_source(conn, client2, FakeCache(CANDIDATES), tmp_path, source)
    rows = repos.list_source_tracks(conn, source["id"])
    assert rows[0]["status"] == "removed_from_source"


def test_d20_barcode_is_never_used_as_isrc(conn, source, tmp_path):
    client, _ = make_client(
        api_ok(
            playlist_payload(
                [item("t1", "Strobe", "deadmau5", extra_ids={"barcode": "0123456789"})]
            )
        )
    )
    sync_one_source(conn, client, FakeCache([]), tmp_path, source)
    row = repos.list_source_tracks(conn, source["id"])[0]
    assert row["isrc"] is None  # barcode never stands in for ISRC (D20)


def test_null_and_local_tracks_are_skipped(conn, source, tmp_path):
    client, _ = make_client(
        api_ok(
            playlist_payload(
                [
                    {"item": None},
                    {"item": {"id": None, "name": "local file"}},
                    {"item": {"id": "episode", "type": "episode"}},
                    item("t1", "Strobe", "deadmau5"),
                ]
            )
        )
    )
    sync_one_source(conn, client, FakeCache([]), tmp_path, source)
    rows = repos.list_source_tracks(conn, source["id"])
    assert [r["spotify_track_id"] for r in rows] == ["t1"]


def test_legacy_playlist_payload_remains_supported(conn, source, tmp_path):
    legacy_item = item("t1", "Strobe", "deadmau5")
    legacy_item = {"track": legacy_item["item"]}
    payload = {
        "name": "Legacy",
        "snapshot_id": "legacy-1",
        "tracks": {"items": [legacy_item], "next": None},
    }
    client, _ = make_client(api_ok(payload))

    sync_one_source(conn, client, FakeCache([]), tmp_path, source)

    assert repos.list_source_tracks(conn, source["id"])[0]["spotify_track_id"] == "t1"


def test_sync_fails_closed_when_playlist_items_are_unavailable(
    conn, source, tmp_path
):
    existing = {
        "spotify_track_id": "t1",
        "title": "Keep",
        "artist": "Artist",
        "status": "missing",
    }
    repos.replace_source_tracks(conn, source["id"], [existing])
    before = repos.list_source_tracks(conn, source["id"])
    client, _ = make_client(api_ok({"name": "Metadata only", "snapshot_id": "s2"}))

    with pytest.raises(ConflictError, match="owned by the connected account"):
        sync_one_source(conn, client, FakeCache([]), tmp_path, source)

    assert repos.list_source_tracks(conn, source["id"]) == before
    assert repos.list_sync_runs(conn, source["id"]) == []


def test_sync_carries_ignored_prior_status(conn, source, tmp_path):
    """D22: prior_status stored on entering 'ignored' must SURVIVE a sync
    (ignored rows are carried as-is, 5.6) so a later unignore still works."""
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {
                "spotify_track_id": "t1",
                "title": "Strobe",
                "artist": "deadmau5",
                "status": "ignored",
                "prior_status": "missing",
            }
        ],
    )
    client, _ = make_client(
        api_ok(playlist_payload([item("t1", "Strobe", "deadmau5")]))
    )
    sync_one_source(conn, client, FakeCache(CANDIDATES), tmp_path, source)

    row = repos.list_source_tracks(conn, source["id"])[0]
    assert row["status"] == "ignored"  # carried as-is (5.6)
    assert row["prior_status"] == "missing"  # NOT erased by the sync
    assert repos.restore_track(conn, row["id"])["status"] == "missing"


def test_sync_reclassifies_ready_rows_with_vanished_staged_file(conn, source, tmp_path):
    """staged-file-integrity: a prior 'ready' whose staged file is gone (or
    is not a regular file) is reclassified 'missing' with a cleared path at
    sync; a ready row whose file is present carries unchanged; acquisition
    jobs are kept as history."""
    staged_ok = tmp_path / "kept.mp3"
    staged_ok.write_bytes(b"x")
    staged_dir = tmp_path / "a-directory"
    staged_dir.mkdir()
    vanished = str(tmp_path / "vanished.mp3")
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {"spotify_track_id": "t1", "status": "ready", "staging_file_path": vanished},
            {"spotify_track_id": "t2", "status": "ready",
             "staging_file_path": str(staged_dir)},
            {"spotify_track_id": "t3", "status": "ready",
             "staging_file_path": str(staged_ok)},
        ],
    )
    rows = {r["spotify_track_id"]: r for r in repos.list_source_tracks(conn, source["id"])}
    conn.execute(
        "INSERT INTO acquisition_jobs (scope, ref, status, output_path) "
        "VALUES ('library', ?, 'downloaded', ?)",
        (str(rows["t1"]["id"]), vanished),
    )
    client, _ = make_client(
        api_ok(
            playlist_payload(
                [item("t1", "Gone", "A"), item("t2", "Dir", "B"), item("t3", "Kept", "C")]
            )
        )
    )
    sync_one_source(conn, client, FakeCache([]), tmp_path, source)

    tracks = {t["spotify_track_id"]: t for t in repos.list_source_tracks(conn, source["id"])}
    assert tracks["t1"]["status"] == "missing"
    assert tracks["t1"]["staging_file_path"] is None
    assert tracks["t2"]["status"] == "missing"  # a directory is not a staged file
    assert tracks["t2"]["staging_file_path"] is None
    assert tracks["t3"]["status"] == "ready"  # file present: carried unchanged
    assert tracks["t3"]["staging_file_path"] == str(staged_ok)
    job = conn.execute("SELECT status, output_path FROM acquisition_jobs").fetchone()
    assert tuple(job) == ("downloaded", vanished)  # jobs stay as history
    # actionable again: the reclassified rows surface in the Missing center
    missing_ids = {
        e["spotify_track_id"] for e in missing_service.list_missing(conn, "library")
    }
    assert {"t1", "t2"} <= missing_ids


def test_sync_reclassifies_on_the_snapshot_fast_path(conn, source, tmp_path):
    """A stuck 'ready' row must come back actionable even when the Spotify
    snapshot is unchanged (the snapshot_id skip must not hide it)."""
    client, _ = make_client(api_ok(playlist_payload([item("t1", "Strobe", "deadmau5")])))
    sync_one_source(conn, client, FakeCache([]), tmp_path, source)
    row = repos.list_source_tracks(conn, source["id"])[0]
    conn.execute(
        "UPDATE library_tracks SET status = 'ready', staging_file_path = ? WHERE id = ?",
        (str(tmp_path / "gone.mp3"), row["id"]),
    )
    source = repos.get_source(conn, source["id"])  # snapshot_id now snap-1
    client2, transport2 = make_client(api_ok(playlist_payload([], snapshot="snap-1")))

    result = sync_one_source(conn, client2, FakeCache([]), tmp_path, source)

    assert result["skipped"] is False
    assert len(transport2.calls) == 1  # meta fetch only, no pagination
    updated = repos.get_track(conn, row["id"])
    assert updated["status"] == "missing"
    assert updated["staging_file_path"] is None


def test_apply_imports_valid_rows_and_reclassifies_vanished_staged_file(
    conn, source, tmp_path, monkeypatch
):
    """Mixed import: valid rows import normally, the vanished-file row is
    reclassified + reported, and rb_write never sees the vanished path (no
    FileNotFoundError, no rollback)."""
    staged = tmp_path / "storage" / "ok.mp3"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"audio")
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {"spotify_track_id": "t1", "status": "ready", "title": "Ok",
             "staging_file_path": str(staged)},
            {"spotify_track_id": "t2", "status": "ready", "title": "Gone",
             "staging_file_path": str(tmp_path / "storage" / "gone.mp3")},
        ],
    )
    rows = {r["spotify_track_id"]: r for r in repos.list_source_tracks(conn, source["id"])}
    added = []

    @contextmanager
    def fake_mutate(*args, **kwargs):
        yield "db"

    monkeypatch.setattr(library_service, "mutate", fake_mutate)
    monkeypatch.setattr(library_service, "_library_tag_ids", lambda *args: ["T1"])
    monkeypatch.setattr(
        library_service, "find_active_content_by_path", lambda *args: None
    )
    monkeypatch.setattr(
        library_service,
        "add_content",
        lambda db, path, meta, **kwargs: added.append(str(path))
        or SimpleNamespace(ID="C-new"),
    )
    monkeypatch.setattr(library_service, "apply_tag_delta", lambda *args, **kwargs: None)

    result = apply_to_rekordbox(
        conn, tmp_path / "master.db", tmp_path / "b", FakeCache([]),
        tmp_path / "storage", source["id"], [rows["t1"]["id"], rows["t2"]["id"]],
    )

    assert result == {
        "imported": 1,
        "tags_per_track": 1,
        "reclassified_missing": [rows["t2"]["id"]],
    }
    assert added == [str(staged)]  # the vanished path never reached rb_write
    ok = repos.get_track(conn, rows["t1"]["id"])
    gone = repos.get_track(conn, rows["t2"]["id"])
    assert (ok["status"], ok["content_id"]) == ("imported", "C-new")
    assert gone["status"] == "missing"
    assert gone["staging_file_path"] is None


def test_library_tag_ids_conflict_without_fixture(monkeypatch, tmp_path):
    """5.6 binding invariant, fixture-less: library MyTags must pre-exist -
    a missing one is a ConflictError naming it; categories never match."""

    class FakeRO:
        def execute(self, sql):
            return [("5", "House"), ("6", "House")]  # duplicate name: first wins

        def close(self):
            pass

    monkeypatch.setattr(library_service, "open_readonly", lambda path: FakeRO())
    assert library_service._library_tag_ids(tmp_path / "x.db", ["House"]) == ["5"]
    with pytest.raises(ConflictError, match="Nope"):
        library_service._library_tag_ids(tmp_path / "x.db", ["House", "Nope"])
    # no tags requested: no DB access at all
    monkeypatch.setattr(
        library_service, "open_readonly", lambda path: pytest.fail("must not open")
    )
    assert library_service._library_tag_ids(tmp_path / "x.db", []) == []


# --- apply_to_rekordbox: preconditions (pure, no master.db needed) ------------------


def test_apply_refuses_non_importable_statuses_with_409_conflict(conn, source, tmp_path):
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {"spotify_track_id": "t1", "status": "missing"},
            {"spotify_track_id": "t2", "status": "matched", "content_id": "C1"},
        ],
    )
    rows = repos.list_source_tracks(conn, source["id"])
    with pytest.raises(ConflictError, match="matched/ready"):
        apply_to_rekordbox(
            conn, tmp_path / "no.db", tmp_path / "b", FakeCache([]), tmp_path,
            source["id"], [rows[0]["id"], rows[1]["id"]],
        )
    # nothing transitioned
    statuses = {t["spotify_track_id"]: t["status"] for t in repos.list_source_tracks(conn, source["id"])}
    assert statuses == {"t1": "missing", "t2": "matched"}


def test_apply_reclassifies_ready_without_staged_file_instead_of_conflicting(
    conn, source, tmp_path
):
    """staged-file-integrity: a 'ready' row with no usable staged file is no
    longer a 409 — it is reclassified 'missing' (path cleared) and reported,
    before any master.db access."""
    repos.replace_source_tracks(
        conn, source["id"], [{"spotify_track_id": "t1", "status": "ready"}]
    )
    row = repos.list_source_tracks(conn, source["id"])[0]
    result = apply_to_rekordbox(
        conn, tmp_path / "no.db", tmp_path / "b", FakeCache([]), tmp_path,
        source["id"], [row["id"]],
    )
    assert result == {
        "imported": 0,
        "tags_per_track": 0,
        "reclassified_missing": [row["id"]],
    }
    updated = repos.get_track(conn, row["id"])
    assert updated["status"] == "missing"
    assert updated["staging_file_path"] is None


def test_apply_refuses_matched_rows_without_content_link(conn, source, tmp_path):
    repos.replace_source_tracks(
        conn, source["id"], [{"spotify_track_id": "t1", "status": "matched"}]
    )
    row = repos.list_source_tracks(conn, source["id"])[0]
    with pytest.raises(ConflictError, match="without a Rekordbox link"):
        apply_to_rekordbox(
            conn, tmp_path / "no.db", tmp_path / "b", FakeCache([]), tmp_path,
            source["id"], [row["id"]],
        )


def test_apply_imports_ready_staged_file_and_persists_content_link(
    conn, source, tmp_path, monkeypatch
):
    staged = tmp_path / "storage" / "_syncbox" / "acquisition" / "job-1" / "song.mp3"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"audio")
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {
                "spotify_track_id": "t1",
                "status": "ready",
                "title": "Song",
                "artist": "Artist",
                "staging_file_path": str(staged),
            }
        ],
    )
    row = repos.list_source_tracks(conn, source["id"])[0]
    db = object()
    calls = []

    @contextmanager
    def fake_mutate(*args, **kwargs):
        yield db

    monkeypatch.setattr(library_service, "mutate", fake_mutate)
    monkeypatch.setattr(library_service, "_library_tag_ids", lambda *args: ["T1"])
    monkeypatch.setattr(
        library_service, "find_active_content_by_path", lambda *args: None
    )
    monkeypatch.setattr(
        library_service,
        "add_content",
        lambda database, path, metadata, **kwargs: SimpleNamespace(ID="C-new"),
    )
    monkeypatch.setattr(
        library_service,
        "apply_tag_delta",
        lambda database, content_id, **kwargs: calls.append((database, content_id, kwargs)),
    )

    result = apply_to_rekordbox(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        FakeCache([]),
        tmp_path / "storage",
        source["id"],
        [row["id"]],
    )

    updated = repos.get_track(conn, row["id"])
    assert result == {
        "imported": 1,
        "tags_per_track": 1,
        "reclassified_missing": [],
    }
    assert (updated["status"], updated["content_id"]) == ("imported", "C-new")
    assert calls == [(db, "C-new", {"add_tag_ids": ["T1"]})]


def test_apply_unknown_source_or_track_raises_key_error(conn, source, tmp_path):
    with pytest.raises(KeyError):
        apply_to_rekordbox(
            conn, tmp_path / "no.db", tmp_path / "b", FakeCache([]), tmp_path, 999, []
        )
    with pytest.raises(KeyError):
        apply_to_rekordbox(
            conn, tmp_path / "no.db", tmp_path / "b", FakeCache([]), tmp_path,
            source["id"], [12345],
        )


# --- apply_to_rekordbox: integration on the real fixture ---------------------------


@needs_fixture
def test_apply_to_rekordbox_tags_and_imports(conn, source, tmp_path):
    from syncbox import rb
    from syncbox.rb_write import find_or_create_mytag, open_rekordbox
    from syncbox.safety.mutate import mutate

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    shutil.copy2(TESTDATA / "masterPlaylists6.xml", live / "masterPlaylists6.xml")
    backups = tmp_path / "backups"
    storage = tmp_path / "storage"

    cache = rb.SnapshotCache(db_path)
    target = cache.get(storage)[0]["content_id"]

    # 5.6: the library MyTag must PRE-EXIST - create it first via rb_write
    # inside a mutate, exactly like a user would have in Rekordbox.
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        tag = find_or_create_mytag(db, "Syncbox Lib IT", "Genre")
        tag_id = tag.ID

    repos.update_source(conn, source["id"], tags=["Syncbox Lib IT"])
    src = repos.get_source(conn, source["id"])
    repos.replace_source_tracks(
        conn,
        src["id"],
        [
            {"spotify_track_id": "t1", "status": "matched", "content_id": target,
             "title": "X", "tags": ["Syncbox Lib IT"]},
        ],
    )
    row = repos.list_source_tracks(conn, src["id"])[0]

    result = apply_to_rekordbox(
        conn, db_path, backups, cache, storage, src["id"], [row["id"]]
    )
    assert result == {
        "imported": 1,
        "tags_per_track": 1,
        "reclassified_missing": [],
    }
    assert repos.get_track(conn, row["id"])["status"] == "imported"

    # on-disk verification through an independent read-only connection
    ro = rb.open_readonly(db_path)
    links = ro.execute(
        "SELECT COUNT(*) FROM djmdSongMyTag WHERE ContentID = ? AND MyTagID = ? "
        "AND rb_local_deleted = 0",
        (target, tag_id),
    ).fetchone()[0]
    ro.close()
    assert links == 1

    # idempotent re-apply: no duplicate link row, still exactly one
    repos.set_track_status(conn, row["id"], "ready")
    apply_to_rekordbox(conn, db_path, backups, cache, storage, src["id"], [row["id"]])
    ro = rb.open_readonly(db_path)
    links = ro.execute(
        "SELECT COUNT(*) FROM djmdSongMyTag WHERE ContentID = ? AND MyTagID = ?",
        (target, tag_id),
    ).fetchone()[0]
    ro.close()
    assert links == 1


@needs_fixture
def test_apply_conflicts_on_missing_mytag_and_writes_nothing(conn, source, tmp_path):
    from syncbox import rb

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    backups = tmp_path / "backups"
    storage = tmp_path / "storage"

    cache = rb.SnapshotCache(db_path)
    target = cache.get(storage)[0]["content_id"]

    repos.update_source(conn, source["id"], tags=["No Such Syncbox Tag"])
    src = repos.get_source(conn, source["id"])
    repos.replace_source_tracks(
        conn,
        src["id"],
        [{"spotify_track_id": "t1", "status": "matched", "content_id": target}],
    )
    row = repos.list_source_tracks(conn, src["id"])[0]

    before = db_path.stat().st_mtime_ns
    with pytest.raises(ConflictError, match="No Such Syncbox Tag"):
        apply_to_rekordbox(conn, db_path, backups, cache, storage, src["id"], [row["id"]])
    assert db_path.stat().st_mtime_ns == before  # master.db untouched
    assert not backups.exists()  # conflict fired before any backup
    assert repos.get_track(conn, row["id"])["status"] == "matched"  # unchanged
