"""Tests for optional Deezer acquisition without installing streamrip."""

import json
from types import SimpleNamespace

from starlette.testclient import TestClient

from syncbox import acquisition, api, appdb, repos
from syncbox.safety.process_guard import MutationBlockedError
from syncbox.secrets import SecretsStore

PLAYLIST_ID = "B" * 22
ARL = "a" * 96
ISRC = "USQX91300105"


class FakeCache:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def get(self, storage_root):
        return self.rows

    def invalidate(self):
        pass


def _install_marker(data_dir):
    python = acquisition.component_python(data_dir)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("# fake optional python", encoding="utf-8")
    python.chmod(0o755)
    acquisition.component_root(data_dir).mkdir(parents=True, exist_ok=True)
    marker = {
        "streamrip_version": acquisition.STREAMRIP_VERSION,
        "streamrip_commit": acquisition.STREAMRIP_COMMIT,
        "certifi_version": acquisition.CERTIFI_VERSION,
    }
    (acquisition.component_root(data_dir) / "syncbox-component.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )


def make_env(tmp_path, *, rows=(), runner=None, installer=None):
    conn = appdb.open_app_db(tmp_path / "syncbox.db")
    storage = tmp_path / "storage"
    storage.mkdir()
    db_file = tmp_path / "master.db"
    db_file.write_bytes(b"fake")
    secrets = SecretsStore(tmp_path)
    deps = api.Deps(
        conn,
        cache=FakeCache(rows),
        app_db_path=tmp_path / "syncbox.db",
        data_dir=tmp_path,
        secrets=secrets,
        acquisition_runner=runner,
        acquisition_installer=installer,
    )
    deps.settings.update(
        {
            "rekordbox_db_path": str(db_file),
            "storage_root": str(storage),
        }
    )
    app = api.build_app(deps)
    return SimpleNamespace(
        conn=conn,
        deps=deps,
        secrets=secrets,
        client=TestClient(app),
        storage=storage,
    )


def seed_library_missing(conn):
    source = repos.add_source(conn, PLAYLIST_ID, name="PL")
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {
                "spotify_track_id": "t1",
                "title": "Instant Crush",
                "artist": "Daft Punk",
                "isrc": ISRC,
                "status": "missing",
            }
        ],
    )
    return repos.list_source_tracks(conn, source["id"])[0]


def test_deezer_arl_is_secret_not_setting_or_export(tmp_path):
    env = make_env(tmp_path)
    assert env.client.get("/api/acquisition/deezer").json()["has_arl"] is False

    bad = env.client.put("/api/acquisition/deezer/arl", json={"arl": "not-a-token"})
    assert bad.status_code == 400

    saved = env.client.put("/api/acquisition/deezer/arl", json={"arl": ARL})
    assert saved.status_code == 200
    assert saved.json()["has_arl"] is True
    assert ARL not in saved.text
    assert env.secrets.get(acquisition.DEEZER_ARL_SECRET) == ARL

    export_path = tmp_path / "settings.json"
    env.client.post("/api/settings/export", json={"path": str(export_path)})
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert ARL not in json.dumps(exported)
    assert "deezer_arl" not in exported["settings"]

    deleted = env.client.delete("/api/acquisition/deezer/arl")
    assert deleted.json()["has_arl"] is False


def test_component_install_requires_explicit_enablement(tmp_path):
    calls = []

    def installer(data_dir):
        calls.append(data_dir)
        _install_marker(data_dir)
        return acquisition.component_status(data_dir)

    env = make_env(tmp_path, installer=installer)
    blocked = env.client.post("/api/acquisition/component/install")
    assert blocked.status_code == 400

    env.deps.settings.update({"deezer_acquisition_enabled": True})
    installed = env.client.post("/api/acquisition/component/install")
    assert installed.status_code == 200
    assert installed.json()["component"]["installed"] is True
    assert calls == [tmp_path]


def test_library_acquisition_job_downloads_to_staging(tmp_path):
    track = None

    def runner(data_dir, arl, isrc, output_dir):
        assert arl == ARL
        assert isrc == ISRC
        output = output_dir / "download.mp3"
        output.write_bytes(b"audio")
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(tmp_path, runner=runner)
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, ARL)
    track = seed_library_missing(env.conn)

    response = env.client.post(
        "/api/acquisition/jobs", json={"scope": "library", "row_id": track["id"]}
    )

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "downloaded"
    assert job["output_path"].endswith("download.mp3")
    updated = repos.get_track(env.conn, track["id"])
    assert updated["status"] == "ready"
    assert updated["staging_file_path"] == job["output_path"]


def test_collection_relink_block_keeps_downloaded_file(tmp_path, monkeypatch):
    def runner(data_dir, arl, isrc, output_dir):
        output = output_dir / "download.mp3"
        output.write_bytes(b"audio")
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(
        tmp_path,
        rows=[
            {
                "content_id": "42",
                "title": "Instant Crush",
                "artist": "Daft Punk",
                "isrc": ISRC,
                "file_missing": True,
                "file_path": "/missing.mp3",
            }
        ],
        runner=runner,
    )
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, ARL)
    monkeypatch.setattr(
        api.missing_service,
        "relink_collection_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(MutationBlockedError()),
    )

    response = env.client.post(
        "/api/acquisition/jobs",
        json={"scope": "collection", "content_id": "42", "relink": True},
    )

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "relink_blocked"
    assert job["error"] == "rekordbox_open"
    assert job["output_path"].endswith("download.mp3")


def test_acquisition_failure_is_a_job_not_500(tmp_path):
    env = make_env(tmp_path, runner=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, ARL)
    track = seed_library_missing(env.conn)

    response = env.client.post(
        "/api/acquisition/jobs", json={"scope": "library", "row_id": track["id"]}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "RuntimeError"
