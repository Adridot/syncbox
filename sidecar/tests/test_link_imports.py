import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from syncbox import appdb, events_service, link_imports, source_identity, staging
from syncbox.music_links import LinkError, parse_link


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    connection.execute("INSERT INTO events (name, slug, default_tag) VALUES ('Gig', 'gig', 'Gig')")
    yield connection
    connection.close()


def preview(conn, token="request_123", entries=None):
    row = link_imports.start(conn, 1, "https://www.deezer.com/album/123", token)
    claimed = link_imports.claim(conn, "worker")
    assert claimed["id"] == row["id"]
    entries = entries or [
        {"item_id": item, "url": f"https://www.deezer.com/track/{item}", "title": "Same title", "isrc": "GBXXX1234567", "available": True}
        for item in ("101", "101", "202")
    ]
    assert link_imports.finish(conn, row["id"], "worker", manifest={
        "url": row["canonical_url"], "provider": "deezer", "resource_id": "123", "entries": entries,
    })
    return link_imports.get(conn, 1, row["id"])


def test_atomic_snapshot_deduplicates_identity_and_replays(conn, monkeypatch):
    row = preview(conn)
    keys = [entry["entry_key"] for entry in row["manifest"]["entries"]]
    real_add = events_service.add_track
    calls = []
    def failing_add(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("fixture insertion failure")
        return real_add(*args, **kwargs)
    monkeypatch.setattr(events_service, "add_track", failing_add)
    with pytest.raises(RuntimeError, match="insertion failure"):
        link_imports.commit(conn, 1, row["id"], keys)
    assert events_service.list_event_tracks(conn, 1) == []
    assert link_imports.get(conn, 1, row["id"])["state"] == "ready"
    monkeypatch.setattr(events_service, "add_track", real_add)
    result = link_imports.commit(conn, 1, row["id"], keys)
    assert result["added"] == 2
    assert [o["outcome"] for o in result["outcomes"]] == ["added", "already_present", "added"]
    assert link_imports.commit(conn, 1, row["id"], keys[::-1]) == result
    with pytest.raises(LinkError, match="selection_conflict"):
        link_imports.commit(conn, 1, row["id"], keys[:1])
    tracks = events_service.list_event_tracks(conn, 1)
    assert [(t["source_item_id"], t["source_position"]) for t in tracks] == [("101", 1), ("202", 3)]
    assert all(t["origin"] == "manual" and t["status"] == "missing" for t in tracks)
    assert conn.execute("SELECT COUNT(*) FROM acquisition_jobs").fetchone()[0] == 0


def test_existing_rows_and_removed_rows_require_explicit_choice(conn):
    row = preview(conn)
    keys = [entry["entry_key"] for entry in row["manifest"]["entries"]]
    link_imports.commit(conn, 1, row["id"], keys)
    conn.execute("UPDATE event_tracks SET status = 'ready', origin = 'playlist', staging_file_path = '/fixture/owned.mp3' WHERE source_item_id = '101'")
    conn.execute("UPDATE event_tracks SET status = 'removed' WHERE source_item_id = '202'")
    before = events_service.list_event_tracks(conn, 1)
    next_row = preview(conn, "request_456")
    result = link_imports.commit(conn, 1, next_row["id"], keys)
    assert result["added"] == 0
    assert result["outcomes"][-1]["outcome"] == "restore_or_readd_required"
    assert events_service.list_event_tracks(conn, 1) == before
    conn.execute("UPDATE events SET status = 'partially_applied' WHERE id = 1")
    last = preview(conn, "request_789")
    result = link_imports.commit(conn, 1, last["id"], keys, readd_keys=[keys[-1]])
    assert result["added"] == 1
    assert events_service.list_event_tracks(conn, 1)[-1]["added_after_apply"] == 1


def test_request_identity_retry_dismissal_and_late_completion(conn):
    args = (conn, 1, "https://www.deezer.com/track/101", "request_123")
    row = link_imports.start(*args)
    assert link_imports.start(*args)["id"] == row["id"]
    with pytest.raises(LinkError, match="identity_conflict"):
        link_imports.start(conn, 1, "https://www.deezer.com/track/202", "request_123")
    link_imports.claim(conn, "first")
    assert link_imports.finish(conn, row["id"], "first", error="provider_unavailable")
    assert link_imports.retry(conn, 1, row["id"])["state"] == "queued"
    link_imports.claim(conn, "second")
    assert not link_imports.finish(conn, row["id"], "first", error="late_failure")
    link_imports.dismiss(conn, 1, row["id"])
    assert not link_imports.finish(conn, row["id"], "second", error="late_failure")
    assert link_imports.get(conn, 1, row["id"])["state"] == "dismissed"


def test_event_deletion_cascades_committed_and_pending_imports(conn):
    committed = preview(conn)
    link_imports.commit(conn, 1, committed["id"], ["1:101"])
    pending = link_imports.start(conn, 1, "https://www.deezer.com/track/202", "request_456")
    link_imports.claim(conn, "late_worker")
    conn.execute("UPDATE events SET delete_phase = 'cleanup' WHERE id = 1")
    assert not link_imports.finish(conn, pending["id"], "late_worker", error="failure")
    conn.execute("DELETE FROM events WHERE id = 1")
    conn.execute("INSERT INTO events (id, name, slug, default_tag) VALUES (1, 'New', 'new', 'New')")
    assert not link_imports.finish(conn, pending["id"], "late_worker", error="failure")
    assert conn.execute("SELECT COUNT(*) FROM event_link_imports").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM event_tracks").fetchone()[0] == 0


def test_manifest_limits_and_no_untrusted_fields(conn):
    manifest = {"provider": "youtube", "url": "https://www.youtube.com/playlist?list=PL6B3937A5D230E335",
                "entries": [{"item_id": "f7NwyBnIRTE", "url": "https://www.youtube.com/watch?v=f7NwyBnIRTE&token=secret", "available": True, "media_url": "secret", "uploader": "not artist"}, {"available": False}]}
    clean = link_imports.normalized_manifest(manifest)
    assert "secret" not in json.dumps(clean)
    assert clean["entries"][0]["artist"] is None
    assert clean["entries"][1]["available"] is False
    with pytest.raises(LinkError, match="item_limit"):
        link_imports.normalized_manifest({**manifest, "entries": manifest["entries"] * 501})
    with pytest.raises(LinkError, match="inaccessible"):
        link_imports.normalized_manifest({**manifest, "entries": []})


def test_direct_source_never_claims_similar_audio_without_identity(conn, tmp_path):
    event = events_service.get_event(conn, 1)
    conn.execute("UPDATE events SET staging_dir = ? WHERE id = 1", (str(tmp_path),))
    event = events_service.get_event(conn, 1)
    audio = tmp_path / "Similar original.mp3"
    audio.write_bytes(b"fixture original")
    track = events_service.add_track(conn, event, resolved_source={"provider": "deezer", "item_id": "101", "url": "https://www.deezer.com/track/101", "title": "Similar original", "isrc": "GBXXX1234567"})
    cache = SimpleNamespace(get=lambda _: [{"content_id": "999", "file_path": str(audio), "title": track["title"], "isrc": track["isrc"]}])
    assert events_service.match_event_tracks(conn, event, cache, tmp_path)[0]["status"] == "missing"
    assert events_service.claim_staged_files(conn, event) == []
    conn.execute("UPDATE event_tracks SET status = 'ready', staging_file_path = ? WHERE id = ?", (str(audio), track["id"]))
    rows = events_service.list_event_tracks(conn, 1)
    assert staging.reclassify_stale_ready(conn, "event_tracks", rows)[0]["status"] == "missing"
    conn.execute("INSERT INTO acquisition_jobs (provider, scope, ref, status, phase, effective_source_item_id, published_path, published_sha256) VALUES ('deezer', 'event', ?, 'downloaded', 'published', '101', ?, ?)", (str(track["id"]), str(audio), hashlib.sha256(audio.read_bytes()).hexdigest()))
    assert source_identity.eligible_file(conn, track, audio)
    assert events_service.match_event_tracks(conn, event, cache, tmp_path)[0]["content_id"] == "999"
    audio.write_bytes(b"replaced bytes")
    assert not source_identity.eligible_file(conn, track, audio)
    assert events_service.match_event_tracks(conn, event, cache, tmp_path)[0]["status"] == "missing"
    conn.execute("UPDATE event_tracks SET selected_local_path = ?, selected_local_sha256 = ? WHERE id = ?", (str(audio), hashlib.sha256(audio.read_bytes()).hexdigest(), track["id"]))
    assert events_service.match_event_tracks(conn, event, cache, tmp_path)[0]["status"] == "matched"


def test_migration_preserves_legacy_jobs_and_rows(tmp_path, monkeypatch):
    scripts = appdb._scripts()
    monkeypatch.setattr(appdb, "_scripts", lambda: scripts[:10])
    conn = appdb.open_app_db(tmp_path / "legacy.db")
    conn.execute("INSERT INTO events (name, slug, default_tag) VALUES ('Gig', 'gig', 'Gig')")
    for status in ("queued", "failed", "downloaded"):
        row = conn.execute("INSERT INTO event_tracks (event_id, spotify_track_id, status, origin) VALUES (1, ?, 'ready', 'manual') RETURNING id", (status,)).fetchone()
        conn.execute("INSERT INTO acquisition_jobs (scope, ref, status, event_id, event_track_id, phase, published_path) VALUES ('event', ?, ?, 1, ?, 'published', '/fixture/audio.mp3')", (str(row[0]), status, row[0]))
    before = [dict(r) for r in conn.execute("SELECT * FROM acquisition_jobs")]
    monkeypatch.setattr(appdb, "_scripts", lambda: scripts)
    appdb.migrate(conn)
    after = [dict(r) for r in conn.execute("SELECT * FROM acquisition_jobs")]
    assert [{k: row[k] for k in before[0]} for row in after] == before
    assert all(row["source_selector"] is None for row in after)
    assert all(r["source_provider"] == "spotify" and r["origin"] == "manual" and r["status"] == "ready" for r in conn.execute("SELECT * FROM event_tracks"))
    fresh = appdb.open_app_db(tmp_path / "fresh.db")
    assert appdb._schema(conn) == appdb._schema(fresh)
    conn.close()
    fresh.close()


@pytest.mark.parametrize("url,provider,kind", [
    ("https://open.spotify.com/intl-fr/album/" + "A" * 22 + "?si=tracking", "spotify", "album"),
    ("spotify:track:" + "A" * 22, "spotify", "track"),
    ("https://deezer.com/fr/playlist/123?utm_source=test", "deezer", "playlist"),
    ("https://youtu.be/f7NwyBnIRTE?t=20", "youtube", "track"),
    ("https://music.youtube.com/browse/MPREb_gTAcphH99wE", "youtube", "album"),
    ("https://soundcloud.com/artist/sets/album", "soundcloud", "playlist"),
    ("https://on.soundcloud.com/abc123", "soundcloud", "share"),
    ("https://api-v2.soundcloud.com/tracks/565801467?tracking=1", "soundcloud", "track"),
])
def test_canonical_links(url, provider, kind):
    result = parse_link(url)
    assert (result["provider"], result["resource_type"]) == (provider, kind)
    assert "tracking" not in result["url"]


def test_soundcloud_set_stub_children_keep_numeric_identity():
    # Sets beyond five tracks expose API stubs without a permalink (real set 1752070992).
    manifest = {"provider": "soundcloud", "url": "https://soundcloud.com/artist/sets/album", "entries": [
        {"item_id": "1706333112", "url": "https://soundcloud.com/artist/song", "available": True},
        {"item_id": "565801467", "url": "https://api-v2.soundcloud.com/tracks/565801467", "available": True}]}
    clean = link_imports.normalized_manifest(manifest)
    assert [entry["url"] for entry in clean["entries"]] == ["https://soundcloud.com/artist/song", "https://api-v2.soundcloud.com/tracks/565801467"]
    with pytest.raises(LinkError, match="invalid_manifest_identity"):
        link_imports.normalized_manifest({**manifest, "entries": [{"item_id": "565801467", "url": "https://api-v2.soundcloud.com/tracks/2", "available": True}]})


def test_ambiguous_video_and_unsupported_resource():
    url = "https://www.youtube.com/watch?v=f7NwyBnIRTE&list=PL6B3937A5D230E335"
    with pytest.raises(LinkError, match="choice_required"):
        parse_link(url)
    assert parse_link(url, choice="track")["resource_type"] == "track"
    assert parse_link(url, choice="playlist")["resource_type"] == "playlist"
    for invalid in ("https://youtube.com/channel/test", "https://example.org/a", "file:///tmp/audio.mp3", "https://soundcloud.com/artist/tracks", "https://user:password@www.deezer.com/track/1"):
        with pytest.raises(LinkError):
            parse_link(invalid)


def test_verified_provenance_follows_retained_file_migration(conn, tmp_path):
    event = events_service.get_event(conn, 1)
    track = events_service.add_track(conn, event, resolved_source={'provider': 'youtube', 'item_id': 'f7NwyBnIRTE', 'url': 'https://www.youtube.com/watch?v=f7NwyBnIRTE'})
    source, destination = tmp_path / 'staged.mp3', tmp_path / 'retained.mp3'
    source.write_bytes(b'owned recording')
    destination.write_bytes(source.read_bytes())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    conn.execute("INSERT INTO acquisition_jobs (provider, scope, ref, status, phase, effective_source_item_id, published_path, published_sha256) VALUES ('youtube', 'event', ?, 'downloaded', 'published', 'f7NwyBnIRTE', ?, ?)", (str(track['id']), str(source), digest))
    conn.execute('UPDATE event_tracks SET staging_file_path = ?, selected_local_path = ?, selected_local_sha256 = ? WHERE id = ?', (str(source), str(source), digest, track['id']))
    source_identity.relocate_provenance(conn, source, destination)
    source.unlink()
    stored = dict(conn.execute('SELECT * FROM event_tracks WHERE id = ?', (track['id'],)).fetchone())
    assert stored['selected_local_path'] == str(destination)
    assert source_identity.known_file(conn, stored) == str(destination)
    assert conn.execute('SELECT published_path FROM acquisition_jobs').fetchone()[0] == str(destination)
    # Replaying deletion cleanup preserves the same proof without moving it again.
    source_identity.relocate_provenance(conn, source, destination)
    assert source_identity.eligible_file(conn, stored, destination)


def test_apply_refuses_a_matched_content_id_that_now_points_to_another_file(conn, tmp_path, monkeypatch):
    event = events_service.get_event(conn, 1)
    track = events_service.add_track(conn, event, resolved_source={'provider': 'youtube', 'item_id': 'f7NwyBnIRTE', 'url': 'https://www.youtube.com/watch?v=f7NwyBnIRTE'})
    selected, unrelated = tmp_path / 'selected.mp3', tmp_path / 'other.mp3'
    selected.write_bytes(b'exact recording')
    unrelated.write_bytes(b'another recording')
    conn.execute("UPDATE event_tracks SET status = 'matched', content_id = '99', staging_file_path = ?, selected_local_path = ?, selected_local_sha256 = ? WHERE id = ?", (str(selected), str(selected), hashlib.sha256(selected.read_bytes()).hexdigest(), track['id']))
    cache = SimpleNamespace(get=lambda _: [{'content_id': '99', 'file_path': str(unrelated)}])
    monkeypatch.setattr(events_service, 'mutate', lambda *a, **kw: pytest.fail('no Rekordbox mutation for an invalid association'))
    result = events_service.apply_event(conn, tmp_path / 'master.db', tmp_path, cache, tmp_path, event, only_delta=True)
    assert result['noop'] and result['reclassified_missing'] == [track['id']]


def test_metadata_cannot_replace_requested_source_or_single_item(conn):
    row = link_imports.start(conn, 1, 'https://www.deezer.com/track/101', 'request_123')
    link_imports.claim(conn, 'worker')
    other = {'provider': 'youtube', 'url': 'https://www.youtube.com/watch?v=f7NwyBnIRTE', 'entries': [{'item_id': 'f7NwyBnIRTE', 'url': 'https://www.youtube.com/watch?v=f7NwyBnIRTE', 'available': True}]}
    assert link_imports.finish(conn, row['id'], 'worker', manifest=other)
    assert link_imports.get(conn, 1, row['id'])['error'] == 'invalid_manifest_source'
    with pytest.raises(LinkError, match='invalid_manifest_identity'):
        link_imports.normalized_manifest({'provider': 'deezer', 'url': 'https://www.deezer.com/track/101', 'entries': [{'item_id': '202', 'url': 'https://www.deezer.com/track/202', 'available': True}]})
    with pytest.raises(LinkError, match='video_or_playlist_choice_required'):
        parse_link('https://www.youtube.com/shorts/f7NwyBnIRTE?list=PL6B3937A5D230E335')
