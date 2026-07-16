"""Tests for optional Deezer acquisition without installing streamrip."""

import hashlib
import io
import json
import ssl
import stat
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from syncbox import (
    acquisition,
    acquisition_migration,
    api,
    appdb,
    events_service,
    repos,
)
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
        "python_version": acquisition.OPTIONAL_PYTHON_VERSION,
        "pillow_version": acquisition.PILLOW_VERSION,
        "pillow_wheel": acquisition.PILLOW_WHEEL,
        "pillow_wheel_sha256": acquisition.PILLOW_WHEEL_SHA256,
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


def seed_event_missing(conn):
    event = conn.execute(
        "INSERT INTO events (name, slug, default_tag) VALUES ('Event', 'event', 'Event')"
    )
    track = conn.execute(
        "INSERT INTO event_tracks (event_id, title, artist, isrc, status) "
        "VALUES (?, 'Instant Crush', 'Daft Punk', ?, 'missing')",
        (event.lastrowid, ISRC),
    )
    return track.lastrowid


def test_deezer_arl_is_secret_not_setting_or_export(tmp_path):
    env = make_env(tmp_path)
    assert env.client.get("/api/acquisition/deezer").json()["has_arl"] is False

    bad = env.client.put("/api/acquisition/deezer/arl", json={"arl": "not-a-token"})
    assert bad.status_code == 400

    saved = env.client.put("/api/acquisition/deezer/arl", json={"arl": SECRET_SENTINEL})
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
    info = zipfile.ZipInfo(f"{acquisition.COMPONENT_NAME}/{acquisition.COMPONENT_NAME}")
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o755) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, b"#!/bin/sh\n")
    return archive


def _test_manifest(archive):
    return {
        "schema": 1,
        "component": acquisition.COMPONENT_NAME,
        "component_version": "0.2.2",
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
        "python_version": acquisition.OPTIONAL_PYTHON_VERSION,
        "pillow_version": acquisition.PILLOW_VERSION,
        "pillow_wheel": acquisition.PILLOW_WHEEL,
        "pillow_wheel_sha256": acquisition.PILLOW_WHEEL_SHA256,
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
                "pillow_version": acquisition.PILLOW_VERSION,
                "pillow_wheel": acquisition.PILLOW_WHEEL,
                "pillow_wheel_sha256": acquisition.PILLOW_WHEEL_SHA256,
                "artwork": "pillow_jpeg_ready",
                "cryptography": "aes_blowfish_ready",
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
        "download_url": "https://github.com/Adridot/syncbox/releases/download/v0.2.2/component.zip",
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "component_version": "0.2.2",
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
                {"result": "FULL_TRACK_DOWNLOADED", "output_filename": output.name}
            )
        )

    result = acquisition.run_deezer_download(
        tmp_path, SECRET_SENTINEL, ISRC, output_dir, runner=runner
    )

    assert result["result"] == "FULL_TRACK_DOWNLOADED"
    assert all(not Path(path).exists() for path in credential_paths)


def test_concurrent_downloads_keep_credentials_and_outputs_job_local(tmp_path):
    _install_marker(tmp_path)
    barrier = threading.Barrier(2)
    calls = {}

    def runner(command, **kwargs):
        isrc = command[command.index("--isrc") + 1]
        credential = Path(command[command.index("--credential-file") + 1])
        output_dir = Path(command[command.index("--output-dir") + 1])
        calls[isrc] = (credential, output_dir)
        barrier.wait(timeout=2)
        output = output_dir / f"{isrc}.mp3"
        output.write_bytes(isrc.encode())
        return SimpleNamespace(
            stdout=json.dumps(
                {"result": "FULL_TRACK_DOWNLOADED", "output_filename": output.name}
            )
        )

    jobs = [("USQX91300105", tmp_path / "job-1"), ("GBUM71029604", tmp_path / "job-2")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda job: acquisition.run_deezer_download(
                    tmp_path, SECRET_SENTINEL, job[0], job[1], runner=runner
                ),
                jobs,
            )
        )

    assert {Path(result["output_path"]).parent for result in results} == {
        output_dir for _, output_dir in jobs
    }
    assert all(not credential.exists() for credential, _ in calls.values())


def test_download_rejects_directory_as_output(tmp_path):
    _install_marker(tmp_path)
    output_dir = tmp_path / "downloads"

    def runner(command, **kwargs):
        nested = output_dir / "nested"
        nested.mkdir()
        return SimpleNamespace(
            stdout=json.dumps(
                {"result": "FULL_TRACK_DOWNLOADED", "output_filename": nested.name}
            )
        )

    with pytest.raises(RuntimeError, match="not a regular file"):
        acquisition.run_deezer_download(
            tmp_path, SECRET_SENTINEL, ISRC, output_dir, runner=runner
        )


def test_publish_download_rejects_symbolic_links(tmp_path):
    source = tmp_path / "source.flac"
    source.write_bytes(b"audio")
    source_link = tmp_path / "source-link.flac"
    source_link.symlink_to(source)
    destination = tmp_path / "destination"

    with pytest.raises(ValueError, match="output is a symbolic link"):
        acquisition.publish_download(source_link, destination)

    destination.mkdir()
    destination_link = tmp_path / "destination-link"
    destination_link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="destination is a symbolic link"):
        acquisition.publish_download(source, destination_link)


def test_event_download_destination_cannot_escape_managed_storage(tmp_path):
    env = make_env(tmp_path)
    event = env.conn.execute(
        "INSERT INTO events (name, slug, default_tag, staging_dir) "
        "VALUES ('Event', 'event', 'Event', ?)",
        (str(tmp_path / "outside"),),
    )
    track = env.conn.execute(
        "INSERT INTO event_tracks (event_id, title, status) "
        "VALUES (?, 'Track', 'missing')",
        (event.lastrowid,),
    )

    with pytest.raises(ValueError, match="escapes managed storage"):
        api._acquisition_entry(
            env.deps, "event", str(track.lastrowid), require_isrc=False
        )


def test_acquisition_job_transitions_are_bounded_and_idempotent(tmp_path):
    env = make_env(tmp_path)
    cursor = env.conn.execute(
        "INSERT INTO acquisition_jobs (scope, ref, status) VALUES ('library', '1', 'queued')"
    )
    job_id = cursor.lastrowid

    assert api._update_job(env.conn, job_id, status="running")["status"] == "running"
    assert api._update_job(env.conn, job_id, status="running")["status"] == "running"
    assert (
        api._update_job(env.conn, job_id, status="downloaded")["status"] == "downloaded"
    )
    with pytest.raises(ValueError, match="invalid acquisition job transition"):
        api._update_job(env.conn, job_id, status="running")


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
    assert Path(job["output_path"]).parent == env.storage / "rekordbox" / "Collection"
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
        json={
            "scope": "collection",
            "content_id": "42",
            "relink": True,
            "anlz_consent": True,
        },
    )

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "relink_blocked"
    assert job["error"] == "rekordbox_open"
    assert job["output_path"].endswith("download.mp3")


def test_acquisition_failure_is_a_job_not_500(tmp_path):
    env = make_env(
        tmp_path,
        runner=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
    track = seed_library_missing(env.conn)

    response = env.client.post(
        "/api/acquisition/jobs", json={"scope": "library", "row_id": track["id"]}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "boom"
    assert repos.get_track(env.conn, track["id"])["status"] == "acquisition_failed"


def test_event_acquisition_failure_remains_visible_for_recovery(tmp_path):
    env = make_env(
        tmp_path,
        runner=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
    track_id = seed_event_missing(env.conn)

    response = env.client.post(
        "/api/acquisition/jobs", json={"scope": "event", "row_id": track_id}
    )

    row = env.conn.execute(
        "SELECT status FROM event_tracks WHERE id = ?", (track_id,)
    ).fetchone()
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert row["status"] == "acquisition_failed"


def test_download_failure_surfaces_component_reason(tmp_path):
    _install_marker(tmp_path)

    def runner(command, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout=json.dumps(
                {"result": "FAILED", "reason": "streamrip_NonStreamableError"}
            ),
            stderr="",
        )

    with pytest.raises(RuntimeError, match="streamrip_NonStreamableError"):
        acquisition.run_deezer_download(
            tmp_path, SECRET_SENTINEL, ISRC, tmp_path / "downloads", runner=runner
        )


def test_deezer_search_endpoint_maps_public_api_fields(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    monkeypatch.setattr(
        acquisition,
        "_deezer_api_get",
        lambda path, params=None: {
            "data": [
                {
                    "id": 3129569,
                    "title": "Kingston Town",
                    "duration": 226,
                    "preview": "https://cdn-preview.example/kt.mp3",
                    "artist": {"name": "UB40"},
                    "album": {
                        "title": "Labour of Love II",
                        "cover_medium": "https://img.example/kt.jpg",
                    },
                }
            ]
        },
    )

    response = env.client.get(
        "/api/acquisition/deezer/search", params={"q": "ub40 kingston"}
    )

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result == {
        "id": 3129569,
        "title": "Kingston Town",
        "artist": "UB40",
        "album": "Labour of Love II",
        "duration": 226,
        "preview_url": "https://cdn-preview.example/kt.mp3",
        "cover_url": "https://img.example/kt.jpg",
    }


def test_deezer_search_requires_enablement_and_query(tmp_path):
    env = make_env(tmp_path)
    assert (
        env.client.get("/api/acquisition/deezer/search", params={"q": "x"}).status_code
        == 400
    )
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    assert env.client.get("/api/acquisition/deezer/search").status_code == 400


def test_manual_deezer_pick_downloads_the_chosen_recording(tmp_path):
    seen = {}

    def runner(data_dir, arl, isrc, output_dir, track_id=None):
        seen["isrc"] = isrc
        seen["track_id"] = track_id
        output = Path(output_dir) / "manual.mp3"
        output.write_bytes(b"audio")
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(tmp_path, runner=runner)
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)

    # the row has NO usable ISRC: only the manual pick makes it downloadable
    source = repos.add_source(env.conn, PLAYLIST_ID, name="PL")
    repos.replace_source_tracks(
        env.conn,
        source["id"],
        [
            {
                "spotify_track_id": "t9",
                "title": "Final Song",
                "artist": "MO",
                "isrc": None,
                "status": "missing",
            }
        ],
    )
    track = repos.list_source_tracks(env.conn, source["id"])[0]

    response = env.client.post(
        "/api/acquisition/jobs",
        json={"scope": "library", "row_id": track["id"], "deezer_track_id": 124604316},
    )

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "downloaded"
    assert seen["track_id"] == 124604316
    assert seen["isrc"] is None
    assert repos.get_track(env.conn, track["id"])["status"] == "ready"


def test_collection_relink_asks_consent_before_downloading(tmp_path):
    downloads = []

    def runner(data_dir, arl, isrc, output_dir):
        downloads.append(isrc)
        raise AssertionError("no download may happen before ANLZ consent")

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

    response = env.client.post(
        "/api/acquisition/jobs",
        json={"scope": "collection", "content_id": "42", "relink": True},
    )

    assert response.status_code == 428
    assert downloads == []


def test_event_download_is_owned_by_the_event_and_job_cascades(tmp_path):
    def runner(data_dir, arl, isrc, output_dir):
        output = Path(output_dir) / "event.mp3"
        output.write_bytes(b"audio")
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(tmp_path, runner=runner)
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
    event = events_service.create_event(env.conn, env.storage, "Night Set", manual=True)
    track = events_service.add_track(
        env.conn,
        event,
        title="Instant Crush",
        artist="Daft Punk",
    )
    env.conn.execute(
        "UPDATE event_tracks SET isrc = ?, status = 'missing' WHERE id = ?",
        (ISRC, track["id"]),
    )

    job = env.client.post(
        "/api/acquisition/jobs", json={"scope": "event", "row_id": track["id"]}
    ).json()

    assert Path(job["output_path"]).parent == Path(event["staging_dir"]) / "audio"
    linked = env.conn.execute(
        "SELECT event_id, event_track_id FROM acquisition_jobs WHERE id = ?",
        (job["id"],),
    ).fetchone()
    assert tuple(linked) == (event["id"], track["id"])
    env.conn.execute("DELETE FROM events WHERE id = ?", (event["id"],))
    assert (
        env.conn.execute(
            "SELECT 1 FROM acquisition_jobs WHERE id = ?", (job["id"],)
        ).fetchone()
        is None
    )


def test_persistent_worker_resumes_a_queued_job_without_the_ui(tmp_path):
    finished = threading.Event()

    def runner(data_dir, arl, isrc, output_dir):
        output = Path(output_dir) / "queued.mp3"
        output.write_bytes(b"audio")
        finished.set()
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(tmp_path, runner=runner)
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
    track = seed_library_missing(env.conn)
    queued = env.client.post(
        "/api/acquisition/jobs",
        json={"scope": "library", "row_id": track["id"], "enqueue": True},
    )
    assert queued.status_code == 202
    assert queued.json()["status"] == "queued"

    worker = api.AcquisitionWorker(env.deps)
    worker.start()
    assert finished.wait(2)
    assert worker.stop()

    job = api._job_row(env.conn, queued.json()["id"])
    assert job["status"] == "downloaded"
    assert Path(job["output_path"]).parent == env.storage / "rekordbox" / "Collection"


def test_legacy_job_storage_migration_moves_safe_files_and_updates_app_state(
    tmp_path, monkeypatch
):
    env = make_env(tmp_path)
    event = events_service.create_event(
        env.conn, env.storage, "Legacy Set", manual=True
    )
    track = events_service.add_track(env.conn, event, title="Legacy", artist="Artist")
    job = env.conn.execute(
        "INSERT INTO acquisition_jobs "
        "(scope, ref, title, artist, status, event_id, event_track_id) "
        "VALUES ('event', ?, 'Legacy', 'Artist', 'downloaded', ?, ?)",
        (str(track["id"]), event["id"], track["id"]),
    ).lastrowid
    source = acquisition.acquisition_output_dir(env.storage, job) / "legacy.mp3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"legacy audio")
    env.conn.execute(
        "UPDATE acquisition_jobs SET output_path = ? WHERE id = ?", (str(source), job)
    )
    env.conn.execute(
        "UPDATE event_tracks SET status = 'ready', staging_file_path = ? WHERE id = ?",
        (str(source), track["id"]),
    )

    class FakeRO:
        def execute(self, sql, params=()):
            return []

        def close(self):
            pass

    @contextmanager
    def fake_mutate(*args, **kwargs):
        yield object()

    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: FakeRO())
    monkeypatch.setattr(acquisition_migration, "mutate", fake_mutate)
    monkeypatch.setattr(
        acquisition_migration,
        "delete_file",
        lambda path, **kwargs: Path(path).unlink(),
    )

    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)
    assert len(plan["items"]) == 1
    assert (
        Path(plan["items"][0]["destination_path"]).parent
        == Path(event["staging_dir"]) / "audio"
    )

    result = acquisition_migration.execute(
        env.conn,
        env.deps.db_path,
        env.deps.backups_root,
        env.deps.cache(),
        env.storage,
        plan,
    )

    destination = Path(plan["items"][0]["destination_path"])
    assert result["migrated"] == 1
    assert destination.read_bytes() == b"legacy audio"
    assert not source.exists()
    migrated = env.conn.execute(
        "SELECT output_path, legacy_output_path FROM acquisition_jobs WHERE id = ?",
        (job,),
    ).fetchone()
    assert tuple(migrated) == (str(destination), None)
    assert env.conn.execute(
        "SELECT staging_file_path FROM event_tracks WHERE id = ?", (track["id"],)
    ).fetchone()[0] == str(destination)
