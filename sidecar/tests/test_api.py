"""Tests for the REST API layer (api.py): route wiring over the real
services, guard-error mapping (409/423/428, never a 500), and one live SSE
progress stream with a fake slow job (F16 real pct)."""

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from syncbox import api, appdb, repos
from syncbox.platform_os import PermanentDeleteConsentRequired
from syncbox.quality import QualityResult
from syncbox.safety import process_guard
from syncbox.safety.process_guard import MutationBlockedError

PLAYLIST_ID = "A" * 22  # valid 22-char base62 shape


class FakeCache:
    """SnapshotCache stand-in: fixed rows, fixed fingerprint, counts invalidations."""

    def __init__(self, rows=(), fingerprint=(("db", 1),)):
        self.rows = list(rows)
        self._fingerprint = fingerprint
        self.invalidated = 0

    def get(self, storage_root):
        return self.rows

    @property
    def current_fingerprint(self):
        return self._fingerprint

    def invalidate(self):
        self.invalidated += 1


def rb_row(content_id, **over):
    row = {
        "content_id": str(content_id),
        "title": f"Track {content_id}",
        "artist": "Artist",
        "duration_ms": 200_000,
        "isrc": None,
        "bit_rate": 320,
        "file_path": f"/music/{content_id}.mp3",
        "resolved_path": None,
        "file_missing": False,
        "protected": False,
        "key_name": None,
        "genre": None,
        "play_count": 0,
        "stock_date": None,
        "date_created": None,
        "date_created_order": 0,
        "rating": 0,
        "file_size": 0,
        "sample_rate": 44100,
        "bit_depth": 16,
        "file_type": 1,
        "analysed": 0,
        "cue_count": 0,
        "playlist_count": 0,
        "tag_count": 0,
    }
    row.update(over)
    return row


def make_env(tmp_path, rows=(), spotify_client=None, spotify_auth=None):
    conn = appdb.open_app_db(tmp_path / "app.db")
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    db_file = tmp_path / "master.db"
    if not db_file.exists():
        db_file.write_bytes(b"fake rekordbox db")
    cache = FakeCache(rows)
    deps = api.Deps(
        conn,
        cache=cache,
        spotify_client=spotify_client,
        spotify_auth=spotify_auth,
        log_path=tmp_path / "app.log",
    )
    deps.settings.update(
        {"rekordbox_db_path": str(db_file), "storage_root": str(storage)}
    )
    app = api.build_app(deps)
    return SimpleNamespace(
        conn=conn,
        deps=deps,
        cache=cache,
        app=app,
        client=TestClient(app),
        storage=storage,
        db_file=db_file,
    )


def seed_source(conn, tracks, tags=()):
    source = repos.add_source(conn, PLAYLIST_ID, name="PL", tags=tags)
    repos.replace_source_tracks(conn, source["id"], tracks)
    return source, repos.list_source_tracks(conn, source["id"])


# --- transport integration ---------------------------------------------------------


def test_build_app_keeps_transport_routes(tmp_path):
    env = make_env(tmp_path)
    assert env.client.get("/health").json() == {"ok": True}
    # SSE and shutdown stay canonical; the REST surface lives under /api.
    assert env.client.post("/shutdown").status_code == 202


def test_db_path_expands_tilde(tmp_path):
    # Regression: a stored '~/...' path used to reach sqlite un-expanded and
    # fail with ENOENT at scan time. deps.db_path/storage_root must expand it;
    # the empty "not configured yet" sentinel must survive untouched.
    env = make_env(tmp_path)
    env.deps.settings.update({"rekordbox_db_path": "~/Library/x/master.db"})
    assert env.deps.db_path == str(Path("~/Library/x/master.db").expanduser())
    assert "~" not in env.deps.db_path
    env.deps.settings.update({"storage_root": ""})
    assert env.deps.storage_root == ""


def test_invalid_json_body_is_400_not_500(tmp_path):
    env = make_env(tmp_path)
    response = env.client.post(
        "/api/sources", content=b"not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


# --- sources -----------------------------------------------------------------------


def test_sources_crud(tmp_path):
    env = make_env(tmp_path)
    assert env.client.get("/api/sources").json() == {"sources": []}

    bad = env.client.post("/api/sources", json={"spotify_playlist_id": "nope"})
    assert bad.status_code == 400

    created = env.client.post(
        "/api/sources",
        json={"spotify_playlist_id": PLAYLIST_ID, "name": "Bangers", "tags": ["Techno"]},
    )
    assert created.status_code == 201
    source = created.json()
    assert source["tags"] == ["Techno"]

    dup = env.client.post("/api/sources", json={"spotify_playlist_id": PLAYLIST_ID})
    assert dup.status_code == 400

    patched = env.client.patch(
        f"/api/sources/{source['id']}", json={"name": "Renamed", "enabled": False}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["enabled"] == 0

    nothing = env.client.patch(f"/api/sources/{source['id']}", json={"status": "x"})
    assert nothing.status_code == 400  # machine-managed fields are not patchable

    removed = env.client.delete(f"/api/sources/{source['id']}")
    assert removed.status_code == 200
    assert env.client.get("/api/sources").json() == {"sources": []}
    assert env.client.delete(f"/api/sources/{source['id']}").status_code == 404


def test_source_tracks_filters(tmp_path):
    env = make_env(tmp_path)
    source, _ = seed_source(
        env.conn,
        [
            {"spotify_track_id": "t1", "title": "Alpha", "artist": "A", "status": "missing"},
            {"spotify_track_id": "t2", "title": "Beta", "artist": "B", "status": "matched"},
        ],
    )
    url = f"/api/sources/{source['id']}/tracks"
    assert len(env.client.get(url).json()["tracks"]) == 2
    only_missing = env.client.get(url, params={"status": "missing"}).json()["tracks"]
    assert [t["title"] for t in only_missing] == ["Alpha"]
    by_text = env.client.get(url, params={"q": "bet"}).json()["tracks"]
    assert [t["title"] for t in by_text] == ["Beta"]
    assert env.client.get("/api/sources/999/tracks").status_code == 404


def test_sync_requires_spotify_connection(tmp_path):
    env = make_env(tmp_path)
    source, _ = seed_source(env.conn, [])
    response = env.client.post(f"/api/sources/{source['id']}/sync")
    assert response.status_code == 409
    assert response.json()["error"] == "spotify_not_connected"


def test_sync_one_source_end_to_end(tmp_path):
    isrc = "QWERT1212121"
    payloads = {
        f"/playlists/{PLAYLIST_ID}": {
            "snapshot_id": "snap1",
            "name": "PL fresh",
            "tracks": {
                "items": [
                    {
                        "track": {
                            "id": "t1",
                            "name": "Song",
                            "artists": [{"name": "A"}],
                            "duration_ms": 200_000,
                            "external_ids": {"isrc": isrc},
                        }
                    }
                ],
                "next": None,
            },
        }
    }
    client = SimpleNamespace(get=lambda path: payloads[path])
    env = make_env(
        tmp_path, rows=[rb_row("42", isrc=isrc)], spotify_client=client
    )
    source, _ = seed_source(env.conn, [])
    response = env.client.post(f"/api/sources/{source['id']}/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["skipped"] is False
    assert body["stats"]["matched"] == 1
    tracks = repos.list_source_tracks(env.conn, source["id"])
    assert tracks[0]["content_id"] == "42"
    assert repos.get_source(env.conn, source["id"])["snapshot_id"] == "snap1"


def test_apply_wrong_status_is_409(tmp_path):
    env = make_env(tmp_path)
    source, tracks = seed_source(
        env.conn,
        [{"spotify_track_id": "t1", "title": "X", "artist": "A", "status": "new"}],
    )
    response = env.client.post(
        f"/api/sources/{source['id']}/apply", json={"track_ids": [tracks[0]["id"]]}
    )
    assert response.status_code == 409
    assert "matched/ready" in response.json()["message"]


def test_sync_all_publishes_per_source_progress(tmp_path, monkeypatch):
    """F16: sync-all progress units are real (one per source synced), never
    a single faked 100%."""
    published = []

    class RecordingProgress:
        def __init__(self, bus, kind):
            self.kind = kind

        def publish(self, done, total):
            published.append((self.kind, done, total))

        def done(self, **summary):
            published.append((self.kind, "done", summary))

    monkeypatch.setattr(api, "_Progress", RecordingProgress)
    second_id = "B" * 22
    payload = {"snapshot_id": "s1", "name": "PL", "tracks": {"items": [], "next": None}}
    payloads = {
        f"/playlists/{PLAYLIST_ID}": dict(payload),
        f"/playlists/{second_id}": dict(payload),
    }
    client = SimpleNamespace(get=lambda path: payloads[path])
    env = make_env(tmp_path, spotify_client=client)
    repos.add_source(env.conn, PLAYLIST_ID)
    repos.add_source(env.conn, second_id)

    response = env.client.post("/api/sources/sync")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 2
    progress = [
        (done, total)
        for kind, done, total in published
        if kind == "sources.sync_all" and isinstance(done, int)
    ]
    assert progress == [(1, 2), (2, 2)]  # one real unit per source


# --- library tracks ----------------------------------------------------------------


def test_rematch_single_track(tmp_path):
    isrc = "USABC1234567"
    env = make_env(tmp_path, rows=[rb_row("42", isrc=isrc, title="Song")])
    source, tracks = seed_source(
        env.conn,
        [
            {
                "spotify_track_id": "t1",
                "title": "Song",
                "artist": "Artist",
                "isrc": isrc,
                "status": "missing",
            }
        ],
    )
    response = env.client.post(f"/api/library/tracks/{tracks[0]['id']}/rematch")
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["content_id"], body["match_method"]) == (
        "matched",
        "42",
        "isrc",
    )
    assert body["confidence"] == 100

    repos.set_track_status(env.conn, tracks[0]["id"], "imported")
    refused = env.client.post(f"/api/library/tracks/{tracks[0]['id']}/rematch")
    assert refused.status_code == 409


def test_rematch_refuses_removed_from_source(tmp_path):
    """5.6/5.13: re-matching a removed_from_source row would erase the sync
    verdict and (once 'missing') re-expose purchase links 5.13 excludes."""
    isrc = "USABC1234567"
    env = make_env(tmp_path, rows=[rb_row("42", isrc=isrc, title="Song")])
    source, tracks = seed_source(
        env.conn,
        [
            {
                "spotify_track_id": "t1",
                "title": "Song",
                "artist": "Artist",
                "isrc": isrc,
                "status": "removed_from_source",
            }
        ],
    )
    refused = env.client.post(f"/api/library/tracks/{tracks[0]['id']}/rematch")
    assert refused.status_code == 409
    row = repos.get_track(env.conn, tracks[0]["id"])
    assert row["status"] == "removed_from_source"  # marker untouched


def test_ignore_restore_is_d22(tmp_path):
    env = make_env(tmp_path)
    source, tracks = seed_source(
        env.conn,
        [{"spotify_track_id": "t1", "title": "X", "artist": "A", "status": "matched"}],
    )
    track_id = tracks[0]["id"]
    ignored = env.client.post(f"/api/library/tracks/{track_id}/ignore").json()
    assert ignored["status"] == "ignored"
    assert ignored["prior_status"] == "matched"
    restored = env.client.post(f"/api/library/tracks/{track_id}/restore").json()
    assert restored["status"] == "matched"  # never 'new' (D22)
    assert restored["prior_status"] is None
    # No prior status left: a second restore is a clean 400, not a 500.
    assert env.client.post(f"/api/library/tracks/{track_id}/restore").status_code == 400


def test_bulk_tag_delta_d16(tmp_path):
    env = make_env(tmp_path)
    source, tracks = seed_source(
        env.conn,
        [
            {
                "spotify_track_id": "t1",
                "title": "X",
                "artist": "A",
                "status": "matched",
                "tags": ["A", "B"],
            }
        ],
    )
    response = env.client.post(
        "/api/library/tracks/tags",
        json={"track_ids": [tracks[0]["id"]], "add": ["C", "A"], "remove": ["B"]},
    )
    assert response.status_code == 200
    # Delta semantics: B removed, C added, A kept ONCE - never a union overwrite.
    assert response.json()["tracks"][0]["tags"] == ["A", "C"]
    empty = env.client.post(
        "/api/library/tracks/tags", json={"track_ids": [tracks[0]["id"]]}
    )
    assert empty.status_code == 400


# --- events ------------------------------------------------------------------------


def test_events_list_reports_pending_delta_badge(tmp_path):
    """11.2: the events list surfaces N additions waiting for a re-apply -
    not a constant 0."""
    env = make_env(tmp_path)
    event = env.client.post("/api/events", json={"name": "Delta Gig"}).json()
    env.client.post(f"/api/events/{event['id']}/tracks", json={"title": "Before"})
    env.conn.execute(
        "UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],)
    )
    env.client.post(f"/api/events/{event['id']}/tracks", json={"title": "After"})

    listing = env.client.get("/api/events").json()["events"]
    assert listing[0]["n_tracks"] == 2
    assert listing[0]["pending_delta"] == 1  # exactly the post-apply addition


def test_event_create_add_manual_track_and_detail(tmp_path):
    env = make_env(tmp_path)
    created = env.client.post("/api/events", json={"name": "Wedding Bash"})
    assert created.status_code == 201
    event = created.json()
    assert event["slug"] == "wedding-bash"
    assert (env.storage / "_rekordbox_sync" / "events" / "wedding-bash").is_dir()

    track = env.client.post(
        f"/api/events/{event['id']}/tracks", json={"title": "Song", "artist": "A"}
    )
    assert track.status_code == 201
    assert track.json()["status"] == "missing"

    # Spotify-link addition without a connected client -> actionable 409.
    no_client = env.client.post(
        f"/api/events/{event['id']}/tracks", json={"spotify_track_id": "x1"}
    )
    assert no_client.status_code == 409
    assert no_client.json()["error"] == "spotify_not_connected"

    detail = env.client.get(f"/api/events/{event['id']}").json()
    assert len(detail["tracks"]) == 1
    listing = env.client.get("/api/events").json()["events"]
    assert listing[0]["n_tracks"] == 1
    assert listing[0]["pending_delta"] == 0


def test_event_add_track_via_spotify_metadata_d20(tmp_path):
    payloads = {
        "/tracks/x1": {
            "id": "x1",
            "name": "Linked",
            "artists": [{"name": "B"}],
            "duration_ms": 111_000,
            # D20: barcode must NEVER be used as an ISRC stand-in.
            "external_ids": {"barcode": "0000", "isrc": "GBXXX7654321"},
        }
    }
    env = make_env(tmp_path, spotify_client=SimpleNamespace(get=lambda p: payloads[p]))
    event = env.client.post("/api/events", json={"name": "Gig"}).json()
    track = env.client.post(
        f"/api/events/{event['id']}/tracks", json={"spotify_track_id": "x1"}
    ).json()
    assert (track["title"], track["artist"]) == ("Linked", "B")
    assert track["isrc"] == "GBXXX7654321"


def test_event_rename_only_while_pending(tmp_path):
    env = make_env(tmp_path)
    event = env.client.post("/api/events", json={"name": "Old"}).json()
    renamed = env.client.patch(f"/api/events/{event['id']}", json={"name": "New"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New"
    assert renamed.json()["default_tag"] == "New"  # moves with the name pre-apply

    env.conn.execute(
        "UPDATE events SET status = 'applied' WHERE id = ?", (event["id"],)
    )
    blocked = env.client.patch(f"/api/events/{event['id']}", json={"name": "Nope"})
    assert blocked.status_code == 409


def test_event_match_uses_event_vocabulary(tmp_path):
    env = make_env(tmp_path, rows=[rb_row("7", title="Song", artist="A")])
    event = env.client.post("/api/events", json={"name": "Gig"}).json()
    env.client.post(
        f"/api/events/{event['id']}/tracks", json={"title": "Song", "artist": "A"}
    )
    matched = env.client.post(f"/api/events/{event['id']}/match").json()["tracks"]
    assert matched[0]["status"] == "matched"
    assert matched[0]["content_id"] == "7"
    assert env.client.post(f"/api/events/{event['id']}/claim").json() == {"claimed": []}


def test_event_apply_and_reapply_wire_only_delta(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    event = env.client.post("/api/events", json={"name": "Gig"}).json()
    calls = []

    def fake_apply(conn, db_path, backups_root, cache, storage_root, ev, *, only_delta=False, retention=15):
        calls.append({"only_delta": only_delta, "retention": retention, "event_id": ev["id"]})
        return {"noop": False, "applied": 2, "event_status": "applied", "tag_id": "1", "playlist_id": "2"}

    monkeypatch.setattr(api.events_service, "apply_event", fake_apply)
    assert env.client.post(f"/api/events/{event['id']}/apply").status_code == 200
    assert env.client.post(f"/api/events/{event['id']}/reapply").status_code == 200
    assert [c["only_delta"] for c in calls] == [False, True]
    assert calls[0]["event_id"] == event["id"]


def test_event_delete_preview_default_and_consent_428(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    event = env.client.post("/api/events", json={"name": "Gig"}).json()
    seen = []

    def fake_delete(conn, db_path, backups_root, cache, storage_root, ev, *, dry_run=True, consent_to_permanent_delete=False, retention=15):
        seen.append({"dry_run": dry_run, "consent": consent_to_permanent_delete})
        if not dry_run and not consent_to_permanent_delete:
            raise PermanentDeleteConsentRequired(Path("/vol/x.mp3"), OSError("no trash"))
        return {"dry_run": dry_run, "contents": [], "playlists": [], "artifacts": []}

    monkeypatch.setattr(api.events_service, "delete_event", fake_delete)
    preview = env.client.post(f"/api/events/{event['id']}/delete")
    assert preview.status_code == 200
    assert preview.json()["dry_run"] is True  # preview is the DEFAULT (D11/D23)

    blocked = env.client.post(
        f"/api/events/{event['id']}/delete", json={"dry_run": False}
    )
    assert blocked.status_code == 428
    payload = blocked.json()
    assert payload["consent"] == "permanent_delete"
    assert payload["message_key"] == "safety.permanent_delete_consent"
    assert payload["path"] == "/vol/x.mp3"

    ok = env.client.post(
        f"/api/events/{event['id']}/delete",
        json={"dry_run": False, "consent_to_permanent_delete": True},
    )
    assert ok.status_code == 200
    assert seen[-1] == {"dry_run": False, "consent": True}


# --- missing center ----------------------------------------------------------------


def test_missing_library_scope_lists_links_and_cycles_status(tmp_path):
    env = make_env(tmp_path)
    source, tracks = seed_source(
        env.conn,
        [
            {
                "spotify_track_id": "t1",
                "title": "Lost",
                "artist": "A",
                "isrc": "USXXX0000001",
                "status": "missing",
            }
        ],
    )
    listing = env.client.get("/api/missing/library").json()
    entry = listing["entries"][0]
    stores = {link["store"] for link in entry["purchase_links"]}
    assert stores == {"Beatport", "Bandcamp"}
    assert entry["relink_candidates"] == []

    row_id = entry["id"]
    bad = env.client.post(
        f"/api/missing/library/{row_id}/status", json={"status": "weird"}
    )
    assert bad.status_code == 400

    ignored = env.client.post(
        f"/api/missing/library/{row_id}/status", json={"status": "ignored"}
    ).json()
    assert ignored["prior_status"] == "missing"
    restored = env.client.post(f"/api/missing/library/{row_id}/restore").json()
    assert restored["status"] == "missing"  # D22: never 'new'

    assert env.client.get("/api/missing/bogus").status_code == 400


def test_missing_collection_relink_requires_anlz_consent(tmp_path):
    env = make_env(tmp_path)
    response = env.client.post(
        "/api/missing/collection/123/relink", json={"path": "/x.mp3"}
    )
    assert response.status_code == 428
    assert response.json()["consent"] == "anlz"
    # Consent given but the local file does not exist -> 404, nothing written.
    missing_file = env.client.post(
        "/api/missing/collection/123/relink",
        json={"path": str(tmp_path / "nope.mp3"), "anlz_consent": True},
    )
    assert missing_file.status_code == 404


def test_missing_relink_unknown_content_is_404_without_backup(tmp_path, monkeypatch):
    """A stale content_id (row deleted in Rekordbox since the snapshot) must
    map to a clean 404 - never a raw 500 - and waste no backup slot."""
    env = make_env(tmp_path)
    target = tmp_path / "found.mp3"
    target.write_bytes(b"\x00")

    class FakeRO:
        def execute(self, sql, params):
            return SimpleNamespace(fetchone=lambda: None)  # unknown content id

        def close(self):
            pass

    monkeypatch.setattr(api.missing_service, "open_readonly", lambda path: FakeRO())
    response = env.client.post(
        "/api/missing/collection/GONE/relink",
        json={"path": str(target), "anlz_consent": True},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert not env.deps.backups_root.exists()  # no backup for a dead mutation


# --- duplicates --------------------------------------------------------------------


def _isrc_pair_rows():
    return [
        rb_row("1", isrc="USDUP0000001", title="Song", artist="A", bit_rate=320),
        rb_row("2", isrc="USDUP0000001", title="Song", artist="A", bit_rate=128),
    ]


def test_duplicates_scan_verdicts_keeper_and_dismiss(tmp_path):
    env = make_env(tmp_path, rows=_isrc_pair_rows())
    scan = env.client.post("/api/duplicates/scan").json()
    assert scan["scanned"] == 2
    (group,) = scan["groups"]
    assert group["method"] == "isrc"
    assert group["confidence"] == 99
    # On-demand verdicts on group members ONLY, neutral without a local file.
    assert [m["quality_verdict"] for m in group["members"]] == ["ok", "ok"]
    assert group["keeper"] == {"content_id": "1", "reason": "quality"}
    assert scan["fingerprint"] == [["db", 1]]
    # Verdicts are never persisted - not even on the cached snapshot rows.
    assert all("quality_verdict" not in row for row in env.cache.rows)

    env.client.post("/api/duplicates/dismiss", json={"group_key": group["key"]})
    assert env.client.post("/api/duplicates/scan").json()["groups"] == []


def test_duplicates_resolve_order_and_reentry(tmp_path, monkeypatch):
    env = make_env(tmp_path, rows=_isrc_pair_rows())
    order = []
    states = {
        "1": ("/music/1.mp3", 0),
        "2": ("/music/2.mp3", 0),
        "3": ("/music/3.mp3", 1),  # already soft-deleted: the consent-retry case
    }

    class FakeRO:
        def execute(self, sql, params):
            return [(cid, *states[cid]) for cid in params if cid in states]

        def close(self):
            order.append("ro:close")

    @contextmanager
    def fake_mutate(db_path, backups_root, *, retention, expected_fingerprint=None, open_db, invalidate_cache=None):
        order.append(("mutate:enter", expected_fingerprint))
        yield "db"
        order.append("mutate:exit")
        if invalidate_cache:
            invalidate_cache()

    monkeypatch.setattr(api, "open_readonly", lambda path: FakeRO())
    monkeypatch.setattr(api, "mutate", fake_mutate)
    monkeypatch.setattr(
        api, "reassign_memberships", lambda db, a, b: order.append(f"reassign:{a}->{b}")
    )
    monkeypatch.setattr(
        api, "soft_delete_content", lambda db, cid: order.append(f"soft_delete:{cid}")
    )
    monkeypatch.setattr(api, "tcc_exists", lambda path: True)
    monkeypatch.setattr(
        api,
        "delete_file",
        lambda path, *, consent_to_permanent_delete: order.append(f"delete:{path}")
        or "trashed",
    )

    response = env.client.post(
        "/api/duplicates/resolve",
        json={
            "keeper_content_id": "1",
            "loser_content_ids": ["2", "3"],
            "fingerprint": [["db", 1]],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["soft_deleted"] == ["2"]  # "3" was already soft-deleted
    assert [f["result"] for f in body["files"]] == ["trashed", "trashed"]

    mutate_exit = order.index("mutate:exit")
    assert order.index("reassign:2->1") < order.index("soft_delete:2") < mutate_exit
    deletes = [i for i, step in enumerate(order) if str(step).startswith("delete:")]
    assert deletes and min(deletes) > mutate_exit  # files strictly AFTER commit (5.4)
    assert ("mutate:enter", (("db", 1),)) in order  # scan fingerprint guards the txn
    assert not any(step == "reassign:3->1" for step in order)


def test_duplicates_resolve_never_deletes_a_shared_keeper_file(tmp_path, monkeypatch):
    """5.4: two content rows can share ONE physical file (double import,
    manual relink onto the other copy - dedup groups on metadata, never on
    path). Resolving must not trash the keeper's own file via the loser."""
    env = make_env(tmp_path, rows=_isrc_pair_rows())
    shared = "/music/shared.mp3"
    states = {
        "1": (shared, 0),  # keeper
        "2": (shared, 0),  # loser sharing the keeper's file
        "3": ("/music/3.mp3", 0),  # loser with its own file
    }

    class FakeRO:
        def execute(self, sql, params):
            return [(cid, *states[cid]) for cid in params if cid in states]

        def close(self):
            pass

    deleted = []

    @contextmanager
    def fake_mutate(db_path, backups_root, *, retention, expected_fingerprint=None, open_db, invalidate_cache=None):
        yield "db"

    monkeypatch.setattr(api, "open_readonly", lambda path: FakeRO())
    monkeypatch.setattr(api, "mutate", fake_mutate)
    monkeypatch.setattr(api, "reassign_memberships", lambda db, a, b: None)
    monkeypatch.setattr(api, "soft_delete_content", lambda db, cid: None)
    monkeypatch.setattr(api, "tcc_exists", lambda path: True)
    monkeypatch.setattr(
        api,
        "delete_file",
        lambda path, *, consent_to_permanent_delete: deleted.append(str(path))
        or "trashed",
    )

    response = env.client.post(
        "/api/duplicates/resolve",
        json={
            "keeper_content_id": "1",
            "loser_content_ids": ["2", "3"],
            "consent_to_permanent_delete": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["soft_deleted"] == ["2", "3"]  # DB rows still soft-deleted
    # The shared file was NEVER deleted - reported as kept instead (5.4).
    assert deleted == ["/music/3.mp3"]
    results = {f["content_id"]: f["result"] for f in body["files"]}
    assert results == {"2": "kept_keeper_file", "3": "trashed"}


def test_duplicates_resolve_keeper_guard_equates_32_spellings(tmp_path, monkeypatch):
    """3.2: the volume-relative and absolute spellings of one file compare
    equal - a loser stored in the other spelling must not defeat the guard."""
    env = make_env(tmp_path, rows=_isrc_pair_rows())
    # Keeper absolute under the storage root; loser volume-relative spelling
    # of the SAME file (outside rekordbox/ so the protected guard passes).
    absolute = str(env.storage / "inbox" / "song.mp3")
    volume_relative = f"/{env.storage.name}/inbox/song.mp3"
    states = {"1": (absolute, 0), "2": (volume_relative, 0)}

    class FakeRO:
        def execute(self, sql, params):
            return [(cid, *states[cid]) for cid in params if cid in states]

        def close(self):
            pass

    deleted = []

    @contextmanager
    def fake_mutate(db_path, backups_root, *, retention, expected_fingerprint=None, open_db, invalidate_cache=None):
        yield "db"

    monkeypatch.setattr(api, "open_readonly", lambda path: FakeRO())
    monkeypatch.setattr(api, "mutate", fake_mutate)
    monkeypatch.setattr(api, "reassign_memberships", lambda db, a, b: None)
    monkeypatch.setattr(api, "soft_delete_content", lambda db, cid: None)
    monkeypatch.setattr(api, "tcc_exists", lambda path: True)
    monkeypatch.setattr(
        api,
        "delete_file",
        lambda path, *, consent_to_permanent_delete: deleted.append(str(path))
        or "trashed",
    )

    response = env.client.post(
        "/api/duplicates/resolve",
        json={"keeper_content_id": "1", "loser_content_ids": ["2"]},
    )
    assert response.status_code == 200
    assert deleted == []  # same file either spelling: never deleted
    assert [f["result"] for f in response.json()["files"]] == ["kept_keeper_file"]


def test_duplicates_resolve_validation_and_protection(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    protected_path = str(env.storage / "rekordbox" / "Collection" / "x.mp3")
    states = {"1": ("/music/1.mp3", 0), "2": (protected_path, 0)}

    class FakeRO:
        def execute(self, sql, params):
            return [(cid, *states[cid]) for cid in params if cid in states]

        def close(self):
            pass

    monkeypatch.setattr(api, "open_readonly", lambda path: FakeRO())

    same = env.client.post(
        "/api/duplicates/resolve",
        json={"keeper_content_id": "1", "loser_content_ids": ["1"]},
    )
    assert same.status_code == 400

    unknown = env.client.post(
        "/api/duplicates/resolve",
        json={"keeper_content_id": "9", "loser_content_ids": ["1"]},
    )
    assert unknown.status_code == 404

    protected = env.client.post(
        "/api/duplicates/resolve",
        json={"keeper_content_id": "1", "loser_content_ids": ["2"]},
    )
    assert protected.status_code == 409  # protected is NEVER deleted (5.4)


def test_duplicates_resolve_permanent_delete_consent_428(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    states = {"1": ("/music/1.mp3", 0), "2": ("/music/2.mp3", 1)}

    class FakeRO:
        def execute(self, sql, params):
            return [(cid, *states[cid]) for cid in params if cid in states]

        def close(self):
            pass

    def refuse(path, *, consent_to_permanent_delete):
        raise PermanentDeleteConsentRequired(Path(path), OSError("cloud volume"))

    monkeypatch.setattr(api, "open_readonly", lambda path: FakeRO())
    monkeypatch.setattr(api, "tcc_exists", lambda path: True)
    monkeypatch.setattr(api, "delete_file", refuse)
    response = env.client.post(
        "/api/duplicates/resolve",
        json={"keeper_content_id": "1", "loser_content_ids": ["2"]},
    )
    assert response.status_code == 428
    assert response.json()["consent"] == "permanent_delete"


# --- untagged ----------------------------------------------------------------------


def test_untagged_patterns_crud_and_bad_regex(tmp_path):
    env = make_env(tmp_path)
    assert env.client.post("/api/untagged/patterns", json={"pattern": "("}).status_code == 400
    created = env.client.post("/api/untagged/patterns", json={"pattern": "^promo"})
    assert created.status_code == 201
    listing = env.client.get("/api/untagged/patterns").json()["patterns"]
    assert [p["pattern"] for p in listing] == ["^promo"]
    env.client.delete(f"/api/untagged/patterns/{listing[0]['id']}")
    assert env.client.get("/api/untagged/patterns").json()["patterns"] == []


def test_untagged_list_categorizes(tmp_path):
    rows = [
        rb_row("1", title="", artist="X"),  # junk: empty title
        rb_row("2", title="Fresh One", artist="Y"),
        rb_row("3", title="Tagged", artist="Z", tag_count=2),
    ]
    env = make_env(tmp_path, rows=rows)
    tracks = env.client.get("/api/untagged").json()["tracks"]
    assert [t["category"] for t in tracks] == ["junk", "review"]


def test_untagged_delete_protected_guard_skip_report(tmp_path, monkeypatch):
    rows = [
        rb_row("1"),
        rb_row("2", protected=True),
        rb_row("3", tag_count=1),
    ]
    env = make_env(tmp_path, rows=rows)
    deleted = []

    @contextmanager
    def fake_mutate(db_path, backups_root, *, retention, expected_fingerprint=None, open_db, invalidate_cache=None):
        yield "db"

    monkeypatch.setattr(api, "mutate", fake_mutate)
    monkeypatch.setattr(
        api, "soft_delete_content", lambda db, cid: deleted.append(cid)
    )
    response = env.client.post(
        "/api/untagged/delete", json={"content_ids": ["1", "2", "3", "9"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["soft_deleted"] == ["1"] == deleted
    # D15: the protected guard applies with a REAL skip report.
    assert {(s["content_id"], s["reason"]) for s in body["skipped"]} == {
        ("2", "protected"),
        ("3", "tagged"),
        ("9", "not_found"),
    }


def test_mutation_blocked_maps_to_423(tmp_path, monkeypatch):
    env = make_env(tmp_path, rows=[rb_row("1")])

    def blocked(db_path):
        raise MutationBlockedError()

    monkeypatch.setattr(process_guard, "assert_mutation_ready", blocked)
    response = env.client.post("/api/untagged/delete", json={"content_ids": ["1"]})
    assert response.status_code == 423
    body = response.json()
    assert body["message_key"] == "safety.mutation_blocked"
    assert "quit Rekordbox" in body["message"]
    # Guard fires at step (a): no backup dir was ever created.
    assert not env.deps.backups_root.exists()


# --- smart fixes -------------------------------------------------------------------


def test_smartfixes_dry_run_and_execute_wiring(tmp_path, monkeypatch):
    rows = [rb_row("1", title="Song   Twice", artist="A")]
    env = make_env(tmp_path, rows=rows)
    dry = env.client.post("/api/smartfixes/dry-run", json={}).json()
    assert dry["payload"] == [
        {"content_id": "1", "field": "title", "before": "Song   Twice", "after": "Song Twice"}
    ]
    assert dry["skipped_protected"] == []
    assert dry["fingerprint"] == [["db", 1]]

    captured = {}

    def fake_execute(
        db_path,
        backups_root,
        cache,
        storage_root,
        dry_payload,
        *,
        include_protected_ids=frozenset(),
        retention=15,
    ):
        captured.update(dry_payload)
        captured["include_protected_ids"] = include_protected_ids
        captured["storage_root"] = storage_root
        return {"fields_applied": 1, "tracks_touched": 1}

    monkeypatch.setattr(api.smartfixes_run, "execute", fake_execute)
    response = env.client.post(
        "/api/smartfixes/execute", json={**dry, "include_protected_ids": ["9"]}
    )
    assert response.status_code == 200
    # JSON round-trip must restore the EXACT tuple fingerprint mutate compares.
    assert captured["fingerprint"] == (("db", 1),)
    # The per-call opt-in reaches the runner (5.11) with the storage root.
    assert captured["include_protected_ids"] == frozenset({"9"})
    assert captured["storage_root"] == str(env.storage)


def test_smartfixes_dry_run_protected_opt_in_wiring(tmp_path):
    """5.11: protected tracks are skipped by default and fixable ONLY via
    the per-call include_protected_ids body field - the HTTP layer must
    actually carry the ids into the planner."""
    rows = [rb_row("p1", title="Bad   Title", protected=True)]
    env = make_env(tmp_path, rows=rows)

    skipped = env.client.post("/api/smartfixes/dry-run", json={}).json()
    assert skipped["payload"] == []
    assert [s["content_id"] for s in skipped["skipped_protected"]] == ["p1"]

    opted = env.client.post(
        "/api/smartfixes/dry-run", json={"include_protected_ids": ["p1"]}
    ).json()
    assert [c["content_id"] for c in opted["payload"]] == ["p1"]
    assert opted["skipped_protected"] == []


def test_smartfixes_execute_refuses_protected_without_per_call_opt_in(
    tmp_path, monkeypatch
):
    """5.11 write-path guard: the opt-in is per-call, never remembered - a
    payload naming a protected track is refused server-side on execute
    unless include_protected_ids is re-sent, whatever the client claims."""
    rows = [rb_row("p1", title="Bad   Title", protected=True)]
    env = make_env(tmp_path, rows=rows)
    dry = env.client.post(
        "/api/smartfixes/dry-run", json={"include_protected_ids": ["p1"]}
    ).json()
    assert dry["payload"]  # the protected fix is in the confirmed payload

    # Execute WITHOUT re-sending the opt-in: refused before any backup.
    refused = env.client.post(
        "/api/smartfixes/execute",
        json={"payload": dry["payload"], "fingerprint": dry["fingerprint"]},
    )
    assert refused.status_code == 400
    assert "include_protected_ids" in refused.json()["message"]
    assert not env.deps.backups_root.exists()

    # Execute WITH the per-call opt-in: the write goes through.
    applied = []

    @contextmanager
    def fake_mutate(db_path, backups_root, *, retention, expected_fingerprint=None, open_db, invalidate_cache=None):
        yield "db"

    monkeypatch.setattr(api.smartfixes_run, "mutate", fake_mutate)
    monkeypatch.setattr(
        api.smartfixes_run,
        "set_content_fields",
        lambda db, cid, changes: applied.append((cid, changes)),
    )
    ok = env.client.post(
        "/api/smartfixes/execute", json={**dry, "include_protected_ids": ["p1"]}
    )
    assert ok.status_code == 200
    assert applied == [("p1", {"title": "Bad Title"})]


def test_smartfixes_execute_stale_snapshot_is_409(tmp_path, monkeypatch):
    env = make_env(tmp_path, rows=[rb_row("1", title="Song   Twice")])
    monkeypatch.setattr(process_guard, "assert_mutation_ready", lambda db_path: None)
    dry = env.client.post("/api/smartfixes/dry-run", json={}).json()
    dry["fingerprint"] = [["stale", 0]]  # the DB "changed" since the preview
    response = env.client.post("/api/smartfixes/execute", json=dry)
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "stale_snapshot"
    assert body["action"] == "rerun_dry_run"
    assert not env.deps.backups_root.exists()  # abort BEFORE any backup/write


# --- settings ----------------------------------------------------------------------


def test_settings_get_update_and_f15_path_validation(tmp_path):
    env = make_env(tmp_path)
    current = env.client.get("/api/settings").json()
    assert current["storage_root"] == str(env.storage)

    bad_root = env.client.put(
        "/api/settings", json={"storage_root": str(tmp_path / "missing-dir")}
    )
    assert bad_root.status_code == 400

    bad_db = env.client.put(
        "/api/settings", json={"rekordbox_db_path": str(env.storage / "nope.db")}
    )
    assert bad_db.status_code == 400

    unknown = env.client.put("/api/settings", json={"nope": 1})
    assert unknown.status_code == 400

    updated = env.client.put("/api/settings", json={"language": "fr"}).json()
    assert updated["language"] == "fr"


# --- readouts ----------------------------------------------------------------------


def test_readouts_aggregates(tmp_path):
    from datetime import datetime

    this_month = datetime.now().strftime("%Y-%m-05 10:00:00")
    rows = [
        rb_row("1", key_name="Am", play_count=3, genre="House", date_created=this_month),
        rb_row("2", key_name="8A", play_count=0, genre="House"),
        rb_row("3", key_name="unmappable", play_count=None, genre="Techno"),
    ]
    env = make_env(tmp_path, rows=rows)
    body = env.client.get("/api/readouts").json()
    assert body["total_tracks"] == 3
    assert body["keys_analyzed"] == {"total": 3, "analyzed": 2, "pct": 67}
    assert body["never_played"] == 2
    assert body["added_this_month"] == 1
    assert body["genres"][0] == {"genre": "House", "count": 2}
    assert body["quality"] == {"lossy_source_probable": 0, "incertain": 0, "ok": 3}


# --- doctor ------------------------------------------------------------------------


def test_doctor_backups_restore_and_retention(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    monkeypatch.setattr(process_guard, "assert_mutation_ready", lambda db_path: None)
    backups_root = env.deps.backups_root
    fake = backups_root / "rekordbox-db-20260101-000000"
    fake.mkdir(parents=True)
    (fake / "master.db").write_bytes(b"OLD CONTENT")
    (backups_root / "not-a-backup").mkdir()  # never listed, never restorable

    listing = env.client.get("/api/doctor/backups").json()["backups"]
    assert [b["name"] for b in listing] == ["rekordbox-db-20260101-000000"]
    assert listing[0]["files"] == ["master.db"]

    env.db_file.write_bytes(b"LIVE CONTENT")
    restored = env.client.post(f"/api/doctor/backups/{fake.name}/restore")
    assert restored.status_code == 200
    assert env.db_file.read_bytes() == b"OLD CONTENT"
    assert restored.json()["pre_restore_snapshot"]  # restore is itself reversible
    assert env.cache.invalidated >= 1

    assert env.client.post("/api/doctor/backups/..%2Fx/restore").status_code in (400, 404)
    missing = env.client.post(
        "/api/doctor/backups/rekordbox-db-19990101-000000/restore"
    )
    assert missing.status_code == 404

    assert env.client.post("/api/doctor/retention", json={"backup_retention": -1}).status_code == 400
    ok = env.client.post("/api/doctor/retention", json={"backup_retention": 5})
    assert ok.status_code == 200
    assert env.deps.settings.get("backup_retention") == 5


def test_doctor_logs_tail(tmp_path):
    env = make_env(tmp_path)
    assert env.client.get("/api/doctor/logs").json() == {"configured": False, "lines": []}
    Path(env.deps.log_path).write_text("one\ntwo\nthree\nfour\n")
    body = env.client.get("/api/doctor/logs", params={"lines": 2}).json()
    assert body["configured"] is True
    assert body["lines"] == ["three", "four"]


# --- spotify authorize -------------------------------------------------------------


def test_spotify_authorize(tmp_path):
    env = make_env(tmp_path)
    assert env.client.get("/api/spotify/authorize").status_code == 503
    env2 = make_env(
        tmp_path / "b",
        spotify_auth=SimpleNamespace(
            begin_authorization=lambda: "https://accounts.spotify.com/authorize?x=1",
            handle_callback=lambda params: {"ok": True},
        ),
    )
    body = env2.client.get("/api/spotify/authorize").json()
    assert body["url"].startswith("https://accounts.spotify.com/authorize")


# --- SSE progress (F16) --------------------------------------------------------------


def test_sse_stream_carries_real_job_progress(tmp_path, monkeypatch):
    rows = [
        rb_row("1", isrc="USDUP0000001", title="Song", artist="A", resolved_path="/x/1.mp3"),
        rb_row("2", isrc="USDUP0000001", title="Song", artist="A", resolved_path="/x/2.mp3"),
        rb_row("3", isrc="USDUP0000002", title="Other", artist="B", resolved_path="/x/3.mp3"),
        rb_row("4", isrc="USDUP0000002", title="Other", artist="B", resolved_path="/x/4.mp3"),
    ]
    env = make_env(tmp_path, rows=rows)

    def slow_analyze(path):
        time.sleep(0.02)  # the fake slow job: 4 real work units
        return QualityResult("ok", None, "test_neutral")

    monkeypatch.setattr(api.quality, "analyze", slow_analyze)

    # Starlette's TestClient buffers whole responses, so the INFINITE /events
    # stream can never be consumed through it (finite SSE transport is covered
    # by test_events_endpoint_streams_sse). The F16 invariant lives in what
    # gets PUBLISHED on the canonical bus: capture it at the bus seam, with
    # the real publish still running so the loop wiring stays exercised.
    received = []
    real_publish = env.deps.bus.publish

    async def spying_publish(event_type, payload):
        received.append((event_type, payload))
        await real_publish(event_type, payload)

    monkeypatch.setattr(env.deps.bus, "publish", spying_publish)

    with TestClient(env.app) as client:
        response = client.post("/api/duplicates/scan")

    progress = [p for kind, p in received if kind == "job.progress"]
    assert all(p["kind"] == "duplicates.scan" for p in progress)
    # F16: pct derives from real work units (4 group members analyzed).
    assert [(p["done"], p["total"], p["pct"]) for p in progress] == [
        (1, 4, 25),
        (2, 4, 50),
        (3, 4, 75),
        (4, 4, 100),
    ]
    done = [p for kind, p in received if kind == "job.done"]
    assert done and done[0]["groups"] == 2
    assert {p["job"] for p in progress} == {done[0]["job"]}
    assert response.status_code == 200
    assert len(response.json()["groups"]) == 2


# --- M4.2 sidecar surface completion (G1-G5) -----------------------------------------


def test_status_reports_rb_and_spotify_truthfully(tmp_path, monkeypatch):
    """G1: read-only status from the real guard probe + token presence."""
    env = make_env(
        tmp_path,
        spotify_auth=SimpleNamespace(
            connected=lambda: True, handle_callback=lambda params: {"ok": True}
        ),
    )
    monkeypatch.setattr(process_guard, "is_rekordbox_running", lambda: True)
    assert env.client.get("/api/status").json() == {
        "rb_open": True,
        "spotify_connected": True,
    }
    monkeypatch.setattr(process_guard, "is_rekordbox_running", lambda: False)
    bare = make_env(tmp_path / "bare")  # no spotify_auth wired
    assert bare.client.get("/api/status").json() == {
        "rb_open": False,
        "spotify_connected": False,
    }


def test_track_candidates_scored_shape(tmp_path):
    """G2 read half: matcher-scored shortlist, ISRC pinned first, capped."""
    rows = [
        rb_row("exact", title="Whatever", artist="Whoever", isrc="USX17600001"),
        rb_row("close", title="Song", artist="A"),
        rb_row("far", title="Completely Different", artist="Zzz"),
    ]
    env = make_env(tmp_path, rows=rows)
    _, tracks = seed_source(
        env.conn,
        [
            {
                "spotify_track_id": "t1",
                "title": "Song",
                "artist": "A",
                "isrc": "USX17600001",
                "status": "conflict",
            }
        ],
    )
    body = env.client.get(f"/api/library/tracks/{tracks[0]['id']}/candidates").json()
    assert body["track_id"] == tracks[0]["id"]
    candidates = body["candidates"]
    assert [c["content_id"] for c in candidates[:2]] == ["exact", "close"]
    assert candidates[0]["confidence"] == 100
    assert set(candidates[0]) == {
        "content_id",
        "title",
        "artist",
        "duration_ms",
        "bit_rate",
        "confidence",
    }
    confidences = [c["confidence"] for c in candidates]
    assert confidences == sorted(confidences, reverse=True)


def test_track_manual_match_transition(tmp_path):
    """G2 write half: manual confirm -> matched/manual/100; refusal rules
    mirror the automatic re-match."""
    env = make_env(tmp_path, rows=[rb_row("42")])
    _, tracks = seed_source(
        env.conn,
        [
            {"spotify_track_id": "t1", "title": "X", "artist": "A", "status": "conflict"},
            {"spotify_track_id": "t2", "title": "Y", "artist": "B", "status": "ignored"},
        ],
    )
    updated = env.client.post(
        f"/api/library/tracks/{tracks[0]['id']}/match", json={"content_id": "42"}
    ).json()
    assert updated["status"] == "matched"
    assert updated["content_id"] == "42"
    assert updated["match_method"] == "manual"
    assert updated["confidence"] == 100

    unknown = env.client.post(
        f"/api/library/tracks/{tracks[0]['id']}/match", json={"content_id": "999"}
    )
    assert unknown.status_code == 404

    refused = env.client.post(
        f"/api/library/tracks/{tracks[1]['id']}/match", json={"content_id": "42"}
    )
    assert refused.status_code == 409
    assert "ignored" in refused.json()["message"]


def test_missing_remove_soft_deletes_via_mutate(tmp_path, monkeypatch):
    """G3: remove = soft-delete through mutate (fingerprint checked), no
    audio deletion; protected and present-file rows are refused."""
    rows = [
        rb_row("1", file_missing=True),
        rb_row("2", file_missing=True, protected=True),
        rb_row("3"),  # file present
    ]
    env = make_env(tmp_path, rows=rows)
    deleted = []
    seen = {}

    @contextmanager
    def fake_mutate(db_path, backups_root, *, retention, expected_fingerprint=None, open_db, invalidate_cache=None):
        seen["fingerprint"] = expected_fingerprint
        yield "db"

    monkeypatch.setattr(api, "mutate", fake_mutate)
    monkeypatch.setattr(api, "soft_delete_content", lambda db, cid: deleted.append(cid))

    ok = env.client.post("/api/missing/collection/1/remove")
    assert ok.status_code == 200
    assert ok.json() == {"soft_deleted": "1"}
    assert deleted == ["1"]
    assert seen["fingerprint"] == env.cache.current_fingerprint

    assert env.client.post("/api/missing/collection/2/remove").status_code == 409
    assert env.client.post("/api/missing/collection/3/remove").status_code == 409
    assert env.client.post("/api/missing/collection/9/remove").status_code == 404


def test_missing_remove_blocked_is_423(tmp_path, monkeypatch):
    env = make_env(tmp_path, rows=[rb_row("1", file_missing=True)])

    def blocked(db_path):
        raise MutationBlockedError()

    monkeypatch.setattr(process_guard, "assert_mutation_ready", blocked)
    response = env.client.post("/api/missing/collection/1/remove")
    assert response.status_code == 423
    assert not env.deps.backups_root.exists()


def test_settings_g4_validation(tmp_path):
    """G4: weights sum==1.00, policy enum, threshold bounds - all 400."""
    env = make_env(tmp_path)
    put = lambda payload: env.client.put("/api/settings", json=payload)

    assert put({"match_weights": {"title": 0.5, "artist": 0.3, "duration": 0.1}}).status_code == 400
    assert put({"match_weights": {"title": 1.0}}).status_code == 400
    assert put({"isrc_collision_policy": "nope"}).status_code == 400
    assert put({"match_confidence_threshold": 101}).status_code == 400
    assert put({"match_ambiguity_margin": -1}).status_code == 400

    good = put(
        {
            "match_weights": {"title": 0.4, "artist": 0.4, "duration": 0.2},
            "isrc_collision_policy": "strict",
            "match_confidence_threshold": 90,
        }
    )
    assert good.status_code == 200
    body = good.json()
    assert body["match_weights"] == {"title": 0.4, "artist": 0.4, "duration": 0.2}
    assert body["isrc_collision_policy"] == "strict"
    # defaults present on GET (reset = PUT these back)
    fresh = make_env(tmp_path / "fresh").client.get("/api/settings").json()
    assert fresh["match_confidence_threshold"] == 82
    assert fresh["match_ambiguity_margin"] == 6
    assert fresh["match_weights"] == {"title": 0.52, "artist": 0.36, "duration": 0.12}
    assert fresh["isrc_collision_policy"] == "guarded"


def test_matcher_consumes_settings_thresholds(tmp_path):
    """G4: the re-match path reads thresholds/weights live from settings."""
    env = make_env(tmp_path, rows=[rb_row("42", title="Song", artist="A")])
    _, tracks = seed_source(
        env.conn,
        [{"spotify_track_id": "t1", "title": "Song", "artist": "A", "status": "conflict"}],
    )
    track_id = tracks[0]["id"]
    rematch = lambda: env.client.post(f"/api/library/tracks/{track_id}/rematch").json()

    # default threshold 82: title+artist agree (no duration) -> 88 -> matched
    assert rematch()["status"] == "matched"

    # raise the threshold above 88 -> the same track becomes missing
    env.client.put("/api/settings", json={"match_confidence_threshold": 90})
    env.conn.execute(
        "UPDATE library_tracks SET status = 'conflict' WHERE id = ?", (track_id,)
    )
    assert rematch()["status"] == "missing"

    # title-only weights push confidence to 100 -> matched again at 90
    env.client.put(
        "/api/settings",
        json={"match_weights": {"title": 1.0, "artist": 0.0, "duration": 0.0}},
    )
    result = rematch()
    assert result["status"] == "matched"
    assert result["confidence"] == 100


def test_spotify_playlist_preview(tmp_path):
    """G5: read-only resolved preview for AddSourceModal."""
    payload = {
        "name": "Peak Time",
        "owner": {"display_name": "Adrien"},
        "tracks": {"total": 42},
        "images": [{"url": "https://i.scdn.co/image/x"}],
    }
    env = make_env(tmp_path, spotify_client=SimpleNamespace(get=lambda path: payload))
    body = env.client.get("/api/spotify/playlists/PL1/preview").json()
    assert body == {
        "name": "Peak Time",
        "owner": "Adrien",
        "tracks_total": 42,
        "image_url": "https://i.scdn.co/image/x",
    }

    payload["images"] = []
    assert env.client.get("/api/spotify/playlists/PL1/preview").json()["image_url"] is None


def test_spotify_playlist_preview_errors_map(tmp_path):
    from syncbox.spotify import SpotifyApiError

    not_connected = make_env(tmp_path)  # no client wired
    response = not_connected.client.get("/api/spotify/playlists/PL1/preview")
    assert response.status_code == 409
    assert response.json()["error"] == "spotify_not_connected"

    def raise_api_error(path):
        raise SpotifyApiError(404, "playlist not found or private")

    failing = make_env(
        tmp_path / "err", spotify_client=SimpleNamespace(get=raise_api_error)
    )
    response = failing.client.get("/api/spotify/playlists/PL1/preview")
    assert response.status_code == 502
    body = response.json()
    assert body["error"] == "spotify_api_error"
    assert body["status_code"] == 404
