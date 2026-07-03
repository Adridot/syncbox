"""Composition root (__main__.compose): the app it builds is actually wired."""

from starlette.testclient import TestClient

from syncbox.__main__ import compose


def test_compose_builds_a_live_wired_app(tmp_path):
    app = compose(tmp_path)
    client = TestClient(app)

    # transport routes alive
    assert client.get("/health").json() == {"ok": True}

    # app DB opened + migrated: settings answer with defaults
    settings = client.get("/api/settings").json()
    assert settings["language"] in ("en", "fr")

    # log_path wired: doctor/logs sees the file basicConfig created
    logs = client.get("/api/doctor/logs").json()
    assert logs["configured"] is True

    # SpotifyAuth wired end to end (secrets store + client_id getter)
    response = client.get("/api/spotify/authorize")
    assert response.status_code == 200
    assert response.json()["url"].startswith("https://accounts.spotify.com/authorize")

    # data lives under the given dir, not the OS location
    assert (tmp_path / "syncbox.db").is_file()
    assert (tmp_path / "logs" / "syncbox.log").is_file()
