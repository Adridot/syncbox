"""Tests for optional Deezer acquisition without installing streamrip."""

import hashlib
import io
import json
import ssl
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from syncbox import acquisition, api, appdb, repos
from syncbox.safety.process_guard import MutationBlockedError
from syncbox.secrets import SecretsStore

PLAYLIST_ID = "B" * 22
SECRET_SENTINEL = "a" * 96
ISRC = "USQX91300105"


class FakeCache:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def get(self, storage_root):
        return self.rows

    def invalidate(self):
        pass


def _install_marker(data_dir):
    executable = acquisition.component_executable(data_dir)
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    acquisition.component_root(data_dir).mkdir(parents=True, exist_ok=True)
    manifest = acquisition._component_manifest()
    marker = {
        "component_version": manifest["component_version"],
        "sha256": manifest["sha256"],
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

    saved = env.client.put(
        "/api/acquisition/deezer/arl", json={"arl": SECRET_SENTINEL}
    )
    assert saved.status_code == 200
    assert saved.json()["has_arl"] is True
    assert SECRET_SENTINEL not in saved.text
    assert env.secrets.get(acquisition.DEEZER_ARL_SECRET) == SECRET_SENTINEL

    export_path = tmp_path / "settings.json"
    env.client.post("/api/settings/export", json={"path": str(export_path)})
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert SECRET_SENTINEL not in json.dumps(exported)
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


def _component_archive(tmp_path):
    archive = tmp_path / "component.zip"
    info = zipfile.ZipInfo(
        f"{acquisition.COMPONENT_NAME}/{acquisition.COMPONENT_NAME}"
    )
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o755) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, b"#!/bin/sh\n")
    return archive


def _test_manifest(archive):
    return {
        "schema": 1,
        "component": acquisition.COMPONENT_NAME,
        "component_version": "0.2.1",
        "platform": "macos",
        "architecture": "arm64",
        "archive": "component.zip",
        "root": acquisition.COMPONENT_NAME,
        "executable": acquisition.COMPONENT_NAME,
        "size": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "download_url": "https://example.invalid/component.zip",
        "streamrip_version": acquisition.STREAMRIP_VERSION,
        "streamrip_commit": acquisition.STREAMRIP_COMMIT,
        "certifi_version": acquisition.CERTIFI_VERSION,
    }


def test_component_archive_is_verified_checked_and_installed_atomically(
    tmp_path, monkeypatch
):
    archive = _component_archive(tmp_path)
    manifest = _test_manifest(archive)
    monkeypatch.setattr(acquisition, "_component_manifest", lambda: manifest)
    monkeypatch.setenv(acquisition.COMPONENT_ARCHIVE_ENV, str(archive))

    completed = SimpleNamespace(
        stdout=json.dumps(
            {
                "result": "CHECK_PASSED",
                "streamrip_version": acquisition.STREAMRIP_VERSION,
                "streamrip_commit": acquisition.STREAMRIP_COMMIT,
                "certifi_version": acquisition.CERTIFI_VERSION,
            }
        )
    )
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return completed

    status = acquisition.install_component(tmp_path / "data", runner=runner)

    assert status["installed"] is True
    assert len(calls) == 1
    assert Path(calls[0][0]).name == acquisition.COMPONENT_NAME
    assert calls[0][1:] == ["--check"]
    assert (
        stat.S_IMODE(acquisition._marker_path(tmp_path / "data").stat().st_mode)
        == 0o600
    )
    assert not list((tmp_path / "data").rglob("component-*.zip"))


def test_component_archive_hash_mismatch_is_rejected_before_execution(
    tmp_path, monkeypatch
):
    archive = _component_archive(tmp_path)
    manifest = {**_test_manifest(archive), "sha256": "0" * 64}
    monkeypatch.setattr(acquisition, "_component_manifest", lambda: manifest)
    monkeypatch.setenv(acquisition.COMPONENT_ARCHIVE_ENV, str(archive))

    try:
        acquisition.install_component(
            tmp_path / "data",
            runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("unverified component must not execute")
            ),
        )
    except RuntimeError as error:
        assert str(error) == "optional component archive integrity check failed"
    else:
        raise AssertionError("tampered component archive was accepted")


@pytest.mark.parametrize(
    "name",
    (
        "/tmp/escape",
        f"{acquisition.COMPONENT_NAME}/../escape",
        f"{acquisition.COMPONENT_NAME}\\escape",
        "wrong-root/executable",
    ),
)
def test_component_archive_rejects_unsafe_paths(tmp_path, name):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(name, b"payload")

    with pytest.raises(RuntimeError, match="archive (path|root) is invalid"):
        acquisition._safe_extract(
            archive,
            tmp_path / "stage",
            {"root": acquisition.COMPONENT_NAME},
        )


def test_component_archive_rejects_escaping_symlink(tmp_path):
    archive = tmp_path / "symlink.zip"
    item = zipfile.ZipInfo(f"{acquisition.COMPONENT_NAME}/escape")
    item.create_system = 3
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(item, b"../../escape")

    with pytest.raises(RuntimeError, match="symlink escapes"):
        acquisition._safe_extract(
            archive,
            tmp_path / "stage",
            {"root": acquisition.COMPONENT_NAME},
        )


def test_component_download_uses_verified_tls_and_exact_bytes(tmp_path, monkeypatch):
    payload = b"component archive"
    manifest = {
        "download_url": "https://github.com/Adridot/syncbox/releases/download/v0.2.1/component.zip",
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "component_version": "0.2.1",
    }
    captured = {}

    def urlopen(request, **kwargs):
        captured["request"] = request
        captured.update(kwargs)
        return io.BytesIO(payload)

    monkeypatch.delenv(acquisition.COMPONENT_ARCHIVE_ENV, raising=False)
    monkeypatch.setattr(acquisition.urllib.request, "urlopen", urlopen)
    destination = io.BytesIO()

    acquisition._copy_component_archive(manifest, destination)

    assert destination.getvalue() == payload
    assert captured["request"].full_url == manifest["download_url"]
    assert captured["context"].verify_mode == ssl.CERT_REQUIRED
    assert captured["context"].check_hostname is True


def test_download_secret_uses_only_one_shot_file_not_process_arguments(tmp_path):
    _install_marker(tmp_path)
    output_dir = tmp_path / "downloads"
    credential_paths = []

    def runner(command, **kwargs):
        assert SECRET_SENTINEL not in " ".join(command)
        credential = command[command.index("--credential-file") + 1]
        credential_paths.append(credential)
        credential_path = Path(credential)
        assert stat.S_IMODE(credential_path.stat().st_mode) == 0o600
        assert credential_path.read_text() == SECRET_SENTINEL
        output = output_dir / "download.mp3"
        output.write_bytes(b"audio")
        return SimpleNamespace(
            stdout=json.dumps(
                {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}
            )
        )

    result = acquisition.run_deezer_download(
        tmp_path, SECRET_SENTINEL, ISRC, output_dir, runner=runner
    )

    assert result["result"] == "FULL_TRACK_DOWNLOADED"
    assert all(not Path(path).exists() for path in credential_paths)


def test_library_acquisition_job_downloads_to_staging(tmp_path):
    track = None

    def runner(data_dir, arl, isrc, output_dir):
        assert arl == SECRET_SENTINEL
        assert isrc == ISRC
        output = output_dir / "download.mp3"
        output.write_bytes(b"audio")
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(tmp_path, runner=runner)
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
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
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
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
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
    track = seed_library_missing(env.conn)

    response = env.client.post(
        "/api/acquisition/jobs", json={"scope": "library", "row_id": track["id"]}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "RuntimeError"
