import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from syncbox import api, appdb, link_imports, link_resolution, performances, provider_http
from syncbox.music_links import LinkError
from test_api import make_env

SPOTIFY_ID = "A" * 22


@pytest.mark.parametrize('reset', [False, True])
def test_history_metadata_does_not_block_imports_and_discards_reset_results(tmp_path, monkeypatch, reset):
    env = make_env(tmp_path)
    performances.ingest(env.conn, [{
        'uuid': 'fixture-play', 'rb_history_id': '1', 'rb_history_name': 'Fixture',
        'content_id': '42', 'track_no': 1, 'title': None, 'artist': None,
        'spotify_track_id': SPOTIFY_ID, 'played_at': '2026-09-08 00:00:00',
    }])
    monkeypatch.setattr(performances, 'refresh', lambda *args, **kwargs: {'ingested': 0, 'resolved_titles': 0})
    entered, release = threading.Event(), threading.Event()

    def resolve(ids, client, **kwargs):
        kwargs['on_attempt'](SPOTIFY_ID)
        entered.set()
        assert release.wait(5)
        return {SPOTIFY_ID: {'title': 'Resolved title', 'artist': 'Fixture artist'}}

    monkeypatch.setattr(performances, 'resolve_track_meta', resolve)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(env.client.get, '/api/performances')
        try:
            assert entered.wait(2)
            assert pool.submit(env.client.get, '/api/settings').result(timeout=2).status_code == 200
            assert pool.submit(env.client.get, '/api/performances/live').result(timeout=2).status_code == 200
            with env.deps.lock:
                if reset:
                    env.deps.db_generation += 1
        finally:
            release.set()
        assert pending.result(timeout=2).status_code == 200
    assert env.conn.execute('SELECT title FROM plays').fetchone()[0] == (None if reset else 'Resolved title')


def test_album_pages_hydrate_simplified_spotify_tracks():
    calls = []
    def get(path):
        calls.append(path)
        if path.startswith("/albums/"):
            return {"name": "Album", "tracks": {"items": [{"id": SPOTIFY_ID, "name": "Simplified", "artists": []}], "next": "https://api.spotify.com/v1/albums/next"}}
        if path.endswith("/albums/next"):
            return {"items": [None], "next": None}
        assert path == "/tracks/" + SPOTIFY_ID
        return {"id": SPOTIFY_ID, "name": "Hydrated", "artists": [{"name": "Artist"}], "external_ids": {"isrc": "GBXXX1234567"}}
    result = link_resolution.resolve("https://open.spotify.com/album/" + SPOTIFY_ID, spotify_client=SimpleNamespace(get=get))
    assert len(calls) == 3
    assert len(result["entries"]) == 2
    assert result["entries"][0]["isrc"] == "GBXXX1234567"
    assert result["entries"][0]["title"] == "Hydrated"
    assert result["entries"][1]["available"] is False


def test_spotify_missing_items_and_mid_page_failure_never_succeed():
    url = "https://open.spotify.com/playlist/" + SPOTIFY_ID
    with pytest.raises(LinkError, match="authentication_required"):
        link_resolution.resolve(url)
    with pytest.raises(LinkError, match="inaccessible"):
        link_resolution.resolve(url, spotify_client=SimpleNamespace(get=lambda _: {"name": "Private"}))
    calls = []
    def failing(path):
        calls.append(path)
        if len(calls) > 1:
            raise OSError("fixture page failure")
        return {"items": {"items": [{"item": {"id": SPOTIFY_ID, "name": "First"}}], "next": "https://api.spotify.com/v1/playlists/next"}}
    with pytest.raises(OSError, match="page failure"):
        link_resolution.resolve(url, spotify_client=SimpleNamespace(get=failing))


def test_deezer_pages_and_child_identity_without_credentials(monkeypatch):
    calls = []
    total = 2
    def request(url, **kwargs):
        calls.append((url, kwargs))
        path = url.removeprefix("https://api.deezer.com")
        if path == "/album/123":
            # Real playlists embed at most 400 tracks with no `next`: the embedded list must be ignored.
            payload = {"title": "Album", "nb_tracks": 2, "tracks": {"data": [{"id": 999, "title": "Truncated embed"}]}}
        elif path == "/album/123/tracks?limit=100":
            payload = {"data": [{"id": 101, "title": "First", "artist": {"name": "Artist"}}], "total": total, "next": "https://api.deezer.com/album/123/tracks?limit=100&index=1"}
        else:
            payload = {"data": [{"id": 202, "readable": False}], "total": total, "next": None}
        return 200, {}, json.dumps(payload).encode(), url
    monkeypatch.setattr(provider_http, "request", request)
    result = link_resolution.resolve("https://www.deezer.com/album/123")
    assert [entry["item_id"] for entry in result["entries"]] == ["101", "202"]
    assert [entry["available"] for entry in result["entries"]] == [True, False]
    assert all("headers" not in options for _, options in calls)
    assert result["entries"][0]["url"] == "https://www.deezer.com/track/101"
    total = 3
    with pytest.raises(LinkError, match="collection_incomplete"):
        link_resolution.resolve("https://www.deezer.com/album/123")


def test_share_redirect_refused_before_disallowed_host_is_fetched(monkeypatch):
    fetched = []
    class Connection:
        def __init__(self, host, **kwargs):
            fetched.append(host)
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return SimpleNamespace(status=302, getheaders=lambda: [("Location", "https://example.invalid/track")], getheader=lambda _: "https://example.invalid/track")
        def close(self):
            pass
    monkeypatch.setattr(provider_http.http.client, "HTTPSConnection", Connection)
    with pytest.raises(ValueError, match="unsupported_network_destination"):
        link_resolution.resolve("https://deezer.page.link/sample")
    assert fetched == ["deezer.page.link"]


def wait_state(env, url, state):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        response = env.client.get(url)
        if response.json().get("state") == state:
            return response.json()
        threading.Event().wait(.02)
    pytest.fail(f"import did not reach {state}")


def test_worker_does_not_block_api_and_confirmation_survives_reopen(tmp_path):
    entered, release = threading.Event(), threading.Event()
    env = make_env(tmp_path)
    event = env.client.post("/api/events", json={"name": "Gig"}).json()
    def resolve(url, **kwargs):
        entered.set()
        assert release.wait(4)
        return {"provider": "deezer", "url": url, "entries": [{"item_id": "101", "url": "https://www.deezer.com/track/101", "title": "Track", "available": True}]}
    env.deps.link_resolver = resolve
    worker = api.LinkImportWorker(env.deps)
    worker.start()
    try:
        root = f"/api/events/{event['id']}/link-imports"
        response = env.client.post(root, json={"url": "https://www.deezer.com/track/101", "request_token": "request_123"})
        assert response.status_code == 202
        url = root + "/" + response.json()["id"]
        assert entered.wait(2)
        start = time.monotonic()
        assert env.client.get("/api/settings").status_code == 200
        assert time.monotonic() - start < 1
        release.set()
        wait_state(env, url, "ready")
        result = env.client.post(url + "/commit", json={"selected_keys": ["1:101"]}).json()
        assert result["added"] == 1
        assert env.client.post(url + "/commit", json={"selected_keys": ["1:101"]}).json() == result
        other = appdb.connect(env.deps.app_db_path)
        assert link_imports.get(other, event["id"], response.json()["id"])["result"] == result
        other.close()
    finally:
        release.set()
        assert worker.stop()


def test_interrupted_preview_requeues_and_reset_discards_late_work(tmp_path):
    env = make_env(tmp_path)
    event = env.client.post("/api/events", json={"name": "Gig"}).json()
    row = link_imports.start(env.conn, event["id"], "https://www.deezer.com/track/101", "request_123")
    link_imports.claim(env.conn, "dead_owner")
    entered, release = threading.Event(), threading.Event()
    def resolve(url, **kwargs):
        entered.set()
        assert release.wait(4)
        assert kwargs["cancelled"]()
        return {"provider": "deezer", "url": url, "entries": [{"item_id": "101", "url": url, "available": True}]}
    env.deps.link_resolver = resolve
    worker = api.LinkImportWorker(env.deps)
    fresh = appdb.open_app_db(tmp_path / "replacement.db")
    fresh.close()
    worker.start()
    try:
        assert entered.wait(2)
        response = env.client.post("/api/data/import", json={"path": str(tmp_path / "replacement.db")})
        assert response.status_code == 200
        release.set()
    finally:
        release.set()
        assert worker.stop()
    assert env.deps.conn.execute("SELECT COUNT(*) FROM event_link_imports").fetchone()[0] == 0
    assert env.deps.conn.execute("SELECT COUNT(*) FROM event_tracks").fetchone()[0] == 0


def test_collection_pagination_cancellation_and_byte_limits(monkeypatch):
    url = 'https://open.spotify.com/playlist/' + SPOTIFY_ID
    count = 0
    def endless(path):
        nonlocal count
        count += 1
        page = {'items': [{'track': {'id': SPOTIFY_ID, 'name': 'Track'}}], 'next': f'https://api.spotify.com/v1/playlists/next?page={count}'}
        return {'tracks': page} if count == 1 else page
    with pytest.raises(LinkError, match='collection_page_limit'):
        link_resolution.resolve(url, spotify_client=SimpleNamespace(get=endless))
    assert count == 100
    with pytest.raises(LinkError, match='operation_cancelled'):
        link_resolution.resolve(url, spotify_client=SimpleNamespace(get=lambda _: pytest.fail('cancelled before request')), cancelled=lambda: True)
    with pytest.raises(LinkError, match='metadata_byte_limit'):
        link_resolution.resolve(url, spotify_client=SimpleNamespace(get=lambda _: {'name': 'x' * (8 * 1024 * 1024)}))
