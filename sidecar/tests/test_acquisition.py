"""Tests for optional Deezer acquisition without installing streamrip."""

import hashlib
import io
import json
import os
import shutil
import sqlite3
import ssl
import stat
import threading
import time
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
from syncbox.platform_os import PermanentDeleteConsentRequired
from syncbox.safety.mutate import StaleSnapshotError
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

    # The slug-equality rule subsumes the old escape check: a staging_dir
    # outside <storage>/_syncbox/events/<slug> is refused either way.
    with pytest.raises(ValueError, match="does not match event"):
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
    (source.parent / "artwork").mkdir()
    (source.parent / "artwork" / "cover.jpg").write_bytes(b"cover")
    (source.parent / "unexpected.txt").write_text("owned by the job")
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
        lambda path, **kwargs: shutil.rmtree(path),
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
    assert result["cleaned_directories"] == 1
    assert destination.read_bytes() == b"legacy audio"
    assert not source.parent.exists()
    migrated = env.conn.execute(
        "SELECT output_path, legacy_output_path FROM acquisition_jobs WHERE id = ?",
        (job,),
    ).fetchone()
    assert tuple(migrated) == (str(destination), None)
    assert env.conn.execute(
        "SELECT staging_file_path FROM event_tracks WHERE id = ?", (track["id"],)
    ).fetchone()[0] == str(destination)


class _EmptyRO:
    def execute(self, sql, params=()):
        return []

    def close(self):
        pass


def _seed_cleanup_only_job(env, *, status="downloaded"):
    event = events_service.create_event(
        env.conn, env.storage, f"Residual {status}", manual=True
    )
    track = events_service.add_track(
        env.conn, event, title="Residual", artist="Artist"
    )
    destination = Path(event["staging_dir"]) / "audio" / "published.mp3"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"published audio")
    job = env.conn.execute(
        "INSERT INTO acquisition_jobs "
        "(scope, ref, title, artist, status, event_id, event_track_id, output_path) "
        "VALUES ('event', ?, 'Residual', 'Artist', ?, ?, ?, ?)",
        (str(track["id"]), status, event["id"], track["id"], str(destination)),
    ).lastrowid
    env.conn.execute(
        "UPDATE event_tracks SET status = 'ready', staging_file_path = ? WHERE id = ?",
        (str(destination), track["id"]),
    )
    directory = acquisition.acquisition_output_dir(env.storage, job)
    (directory / "artwork").mkdir(parents=True)
    (directory / "artwork" / "cover.jpg").write_bytes(b"cover")
    return job, destination, directory


def test_cleanup_only_plan_is_versioned_visible_and_executes_without_migration(
    tmp_path, monkeypatch
):
    env = make_env(tmp_path)
    job, destination, directory = _seed_cleanup_only_job(env)
    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: _EmptyRO())

    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)

    assert plan["plan_version"] == acquisition_migration.PLAN_VERSION == 2
    assert plan["items"] == []
    assert len(plan["cleanup_directories"]) == 1
    cleanup = plan["cleanup_directories"][0]
    assert cleanup["job_id"] == job
    assert cleanup["directory_path"] == str(directory.resolve())
    assert cleanup["directory_state"]["kind"] == "directory"
    assert cleanup["directory_state"]["inode"]

    monkeypatch.setattr(
        acquisition_migration,
        "mutate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("cleanup-only execution must not mutate Rekordbox")
        ),
    )
    monkeypatch.setattr(
        acquisition_migration, "delete_file", lambda path, **kwargs: shutil.rmtree(path)
    )
    result = acquisition_migration.execute(
        env.conn,
        env.deps.db_path,
        env.deps.backups_root,
        env.deps.cache(),
        env.storage,
        plan,
    )

    assert destination.is_file()
    assert not directory.exists()
    assert result["migrated_files"] == 0
    assert result["cleaned_directories"] == 1


def test_cleanup_plan_ignores_active_unowned_and_unsafe_directories(
    tmp_path, monkeypatch
):
    env = make_env(tmp_path)
    _, _, active_directory = _seed_cleanup_only_job(env, status="running")
    legacy_root = acquisition.acquisition_root(env.storage)
    unowned = legacy_root / "job-999"
    unowned.mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep")
    unsafe = legacy_root / "job-1000"
    unsafe.symlink_to(victim, target_is_directory=True)
    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: _EmptyRO())

    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)
    reasons = {item["source_path"]: item["reason"] for item in plan["ignored"]}

    assert plan["cleanup_directories"] == []
    assert reasons[str(active_directory)] == "active_job"
    assert reasons[str(unowned)] == "unowned_directory"
    assert reasons[str(unsafe)] == "unsafe_directory"
    assert (victim / "keep.txt").read_text() == "keep"


def test_cleanup_plan_ignores_an_unverified_published_owner(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    job, _, directory = _seed_cleanup_only_job(env)
    track_id = env.conn.execute(
        "SELECT event_track_id FROM acquisition_jobs WHERE id = ?", (job,)
    ).fetchone()[0]
    env.conn.execute(
        "UPDATE event_tracks SET staging_file_path = NULL WHERE id = ?", (track_id,)
    )
    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: _EmptyRO())

    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)

    assert plan["cleanup_directories"] == []
    assert any(
        item["source_path"] == str(directory)
        and item["reason"] == "unverified_destination"
        for item in plan["ignored"]
    )


@pytest.mark.parametrize("change", ["changed", "missing"])
def test_cleanup_revalidates_published_destination_before_removing_directory(
    tmp_path, monkeypatch, change
):
    env = make_env(tmp_path)
    _, destination, directory = _seed_cleanup_only_job(env)
    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: _EmptyRO())
    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)
    if change == "changed":
        destination.write_bytes(b"replacement")
    else:
        destination.unlink()

    with pytest.raises(StaleSnapshotError, match="destination changed"):
        acquisition_migration.execute(
            env.conn,
            env.deps.db_path,
            env.deps.backups_root,
            env.deps.cache(),
            env.storage,
            plan,
        )
    assert directory.is_dir()


def test_cleanup_revalidates_directory_identity_before_removal(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    _, _, directory = _seed_cleanup_only_job(env)
    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: _EmptyRO())
    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)
    shutil.rmtree(directory)
    directory.mkdir()
    (directory / "replacement.txt").write_text("keep")

    with pytest.raises(StaleSnapshotError, match="directory changed"):
        acquisition_migration.execute(
            env.conn,
            env.deps.db_path,
            env.deps.backups_root,
            env.deps.cache(),
            env.storage,
            plan,
        )
    assert (directory / "replacement.txt").read_text() == "keep"


def test_cleanup_missing_directory_is_idempotently_completed(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    _, destination, directory = _seed_cleanup_only_job(env)
    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: _EmptyRO())
    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)
    shutil.rmtree(directory)
    monkeypatch.setattr(
        acquisition_migration,
        "delete_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("an absent directory must not be deleted again")
        ),
    )

    result = acquisition_migration.execute(
        env.conn,
        env.deps.db_path,
        env.deps.backups_root,
        env.deps.cache(),
        env.storage,
        plan,
    )

    assert destination.is_file()
    assert result["migrated_files"] == 0
    assert result["cleaned_directories"] == 1


# --- PR #31 review regression tests --------------------------------------------------


def _enable_acquisition(env, tmp_path):
    _install_marker(tmp_path)
    env.deps.settings.update({"deezer_acquisition_enabled": True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)


def _seed_missing_library_tracks(conn, count: int) -> list[dict]:
    source = repos.add_source(conn, PLAYLIST_ID, name="PL")
    repos.replace_source_tracks(
        conn,
        source["id"],
        [
            {
                "spotify_track_id": f"t{index}",
                "title": f"Track {index}",
                "artist": "Artist",
                "isrc": f"USQX913001{index:02d}",
                "status": "missing",
            }
            for index in range(count)
        ],
    )
    return repos.list_source_tracks(conn, source["id"])


def _wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met within the timeout")


def test_two_workers_on_two_connections_never_run_the_same_job(tmp_path):
    """Review P1: an atomically claimed FIFO never hands one job to two workers."""
    executions = []
    guard = threading.Lock()

    def runner(data_dir, arl, isrc, output_dir):
        with guard:
            executions.append(Path(output_dir).name)
        time.sleep(0.05)
        output = Path(output_dir) / "track.mp3"
        output.write_bytes(b"audio-" + Path(output_dir).name.encode())
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(tmp_path, runner=runner)
    _enable_acquisition(env, tmp_path)
    tracks = _seed_missing_library_tracks(env.conn, 3)

    # Both workers run BEFORE the batch lands (in production a second worker
    # cannot even exist — the port bind in __main__ is the lock; this test
    # proves the claim itself never double-assigns under raw concurrency).
    first = api.AcquisitionWorker(env.deps)
    second = api.AcquisitionWorker(env.deps)
    first.start()
    second.start()
    try:
        queued = env.client.post(
            "/api/acquisition/jobs/batch",
            json={
                "items": [
                    {"scope": "library", "row_id": track["id"]} for track in tracks
                ]
            },
        )
        assert queued.status_code == 202
        job_ids = [job["id"] for job in queued.json()["jobs"]]
        assert len(job_ids) == 3
        _wait_for(
            lambda: all(
                row["status"] == "downloaded"
                for row in env.conn.execute(
                    "SELECT status FROM acquisition_jobs"
                ).fetchall()
            )
        )
    finally:
        assert first.stop()
        assert second.stop()

    # Every job ran EXACTLY once and carries the claim of a known instance.
    assert sorted(executions) == [f"job-{job_id}" for job_id in sorted(job_ids)]
    rows = env.conn.execute(
        "SELECT claimed_by, phase, published_path, published_sha256, output_path "
        "FROM acquisition_jobs ORDER BY id"
    ).fetchall()
    claimants = {row["claimed_by"] for row in rows}
    assert None not in claimants
    assert claimants <= {first.instance_id, second.instance_id}
    # The durable publication state was persisted for each job.
    for row in rows:
        assert row["phase"] == "published"
        assert row["published_path"] == row["output_path"]
        assert row["published_sha256"] == hashlib.sha256(
            Path(row["output_path"]).read_bytes()
        ).hexdigest()


def test_single_worker_preserves_fifo_order(tmp_path):
    """Review P1: claims come strictly in job-id order."""
    executions = []

    def runner(data_dir, arl, isrc, output_dir):
        executions.append(Path(output_dir).name)
        output = Path(output_dir) / "track.mp3"
        output.write_bytes(b"audio")
        return {"result": "FULL_TRACK_DOWNLOADED", "output_path": str(output)}

    env = make_env(tmp_path, runner=runner)
    _enable_acquisition(env, tmp_path)
    tracks = _seed_missing_library_tracks(env.conn, 3)
    queued = env.client.post(
        "/api/acquisition/jobs/batch",
        json={
            "items": [{"scope": "library", "row_id": track["id"]} for track in tracks]
        },
    )
    job_ids = [job["id"] for job in queued.json()["jobs"]]

    worker = api.AcquisitionWorker(env.deps)
    worker.start()
    try:
        _wait_for(
            lambda: all(
                row["status"] == "downloaded"
                for row in env.conn.execute(
                    "SELECT status FROM acquisition_jobs"
                ).fetchall()
            )
        )
    finally:
        assert worker.stop()

    assert executions == [f"job-{job_id}" for job_id in sorted(job_ids)]


def test_symlinked_acquisition_parent_never_touches_link_target(tmp_path):
    """Review P1: <storage>/_syncbox/acquisition symlinked to /victim must not
    let any workspace cleanup or migration source traverse the link."""

    def runner(*args, **kwargs):
        raise AssertionError("no download may start on an unsafe workspace")

    env = make_env(tmp_path, runner=runner)
    _enable_acquisition(env, tmp_path)
    track = seed_library_missing(env.conn)

    victim = tmp_path / "victim"
    (victim / "job-1").mkdir(parents=True)
    precious = victim / "job-1" / "precious.txt"
    precious.write_bytes(b"keep me")
    sync_dir = env.storage / "_syncbox"
    sync_dir.mkdir(exist_ok=True)
    (sync_dir / "acquisition").symlink_to(victim, target_is_directory=True)

    job = env.client.post(
        "/api/acquisition/jobs", json={"scope": "library", "row_id": track["id"]}
    ).json()

    assert job["status"] == "failed"
    assert "symbolic links" in job["error"]
    assert precious.read_bytes() == b"keep me"
    assert (victim / "job-1").is_dir()

    with pytest.raises(ValueError, match="symbolic links"):
        acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)


def _seed_published_job(env, *, ref, library_track_id, content=b"published audio"):
    destination_dir = env.storage / "rekordbox" / "Collection"
    destination_dir.mkdir(parents=True, exist_ok=True)
    published = destination_dir / "crush.mp3"
    published.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    job_id = env.conn.execute(
        "INSERT INTO acquisition_jobs (scope, ref, title, artist, isrc, status, "
        "library_track_id, phase, published_path, published_sha256, output_path) "
        "VALUES ('library', ?, 'Instant Crush', 'Daft Punk', ?, 'running', "
        "?, 'published', ?, ?, ?)",
        (str(ref), ISRC, library_track_id, str(published), digest, str(published)),
    ).lastrowid
    return job_id, published


def test_crash_before_track_ready_resumes_from_published_output(tmp_path):
    """Review P2: restart between publication and the owner update finishes
    from the existing file — no re-download, no ' - 2' duplicate."""

    def runner(*args, **kwargs):
        raise AssertionError("resume must not download again")

    env = make_env(tmp_path, runner=runner)
    _enable_acquisition(env, tmp_path)
    track = seed_library_missing(env.conn)
    job_id, published = _seed_published_job(
        env, ref=track["id"], library_track_id=track["id"]
    )

    worker = api.AcquisitionWorker(env.deps)
    worker.start()
    try:
        _wait_for(
            lambda: api._job_row(env.conn, job_id)["status"] == "downloaded"
        )
    finally:
        assert worker.stop()

    job = api._job_row(env.conn, job_id)
    assert job["output_path"] == str(published)
    resumed = repos.get_track(env.conn, track["id"])
    assert resumed["status"] == "ready"
    assert resumed["staging_file_path"] == str(published)
    assert sorted(path.name for path in published.parent.iterdir()) == ["crush.mp3"]


def test_crash_after_track_ready_never_fails_the_pair(tmp_path):
    """Review P2: restart after the owner already turned 'ready' completes the
    job instead of downgrading both to failed."""

    def runner(*args, **kwargs):
        raise AssertionError("resume must not download again")

    env = make_env(tmp_path, runner=runner)
    _enable_acquisition(env, tmp_path)
    track = seed_library_missing(env.conn)
    job_id, published = _seed_published_job(
        env, ref=track["id"], library_track_id=track["id"]
    )
    env.conn.execute(
        "UPDATE library_tracks SET status = 'ready', staging_file_path = ? "
        "WHERE id = ?",
        (str(published), track["id"]),
    )

    worker = api.AcquisitionWorker(env.deps)
    worker.start()
    try:
        _wait_for(
            lambda: api._job_row(env.conn, job_id)["status"] == "downloaded"
        )
    finally:
        assert worker.stop()

    resumed = repos.get_track(env.conn, track["id"])
    assert resumed["status"] == "ready"
    assert sorted(path.name for path in published.parent.iterdir()) == ["crush.mp3"]


def test_relink_retry_reuses_published_output_without_redownload(
    tmp_path, monkeypatch
):
    """Review P2: a relink_blocked retry resumes the persisted output."""

    def runner(*args, **kwargs):
        raise AssertionError("relink retry must not download again")

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
    _enable_acquisition(env, tmp_path)
    destination_dir = env.storage / "rekordbox" / "Collection"
    destination_dir.mkdir(parents=True, exist_ok=True)
    published = destination_dir / "crush.mp3"
    published.write_bytes(b"published audio")
    digest = hashlib.sha256(b"published audio").hexdigest()
    previous = env.conn.execute(
        "INSERT INTO acquisition_jobs (scope, ref, title, artist, isrc, status, "
        "relink, anlz_consent, phase, published_path, published_sha256, output_path, error) "
        "VALUES ('collection', '42', 'Instant Crush', 'Daft Punk', ?, "
        "'relink_blocked', 1, 1, 'published', ?, ?, ?, 'rekordbox_open')",
        (ISRC, str(published), digest, str(published)),
    ).lastrowid
    relinked = []
    monkeypatch.setattr(
        api.missing_service,
        "relink_collection_file",
        lambda *args, **kwargs: relinked.append(args) or "stored/crush.mp3",
    )

    job = env.client.post(
        "/api/acquisition/jobs",
        json={"scope": "collection", "content_id": "42", "relink": True,
              "anlz_consent": True},
    ).json()

    assert job["id"] == previous
    assert job["status"] == "relinked"
    assert job["stored_path"] == "stored/crush.mp3"
    assert len(relinked) == 1
    assert sorted(path.name for path in destination_dir.iterdir()) == ["crush.mp3"]


def test_ref_spellings_share_one_active_job(tmp_path):
    """Review P2: '01' and '1' resolve to the same owner and the same job."""
    env = make_env(tmp_path)
    _enable_acquisition(env, tmp_path)
    track_id = seed_event_missing(env.conn)

    first = env.client.post(
        "/api/acquisition/jobs",
        json={"scope": "event", "row_id": f"0{track_id}", "enqueue": True},
    )
    second = env.client.post(
        "/api/acquisition/jobs",
        json={"scope": "event", "row_id": str(track_id), "enqueue": True},
    )

    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["ref"] == str(track_id)
    active = env.conn.execute(
        "SELECT COUNT(*) FROM acquisition_jobs WHERE status IN ('queued', 'running')"
    ).fetchone()[0]
    assert active == 1


def test_event_staging_dir_pointing_at_another_event_is_refused(tmp_path):
    """Review P2: event A must never publish into event B's directory."""
    env = make_env(tmp_path)
    _enable_acquisition(env, tmp_path)
    event_a = events_service.create_event(env.conn, env.storage, "Event A", manual=True)
    event_b = events_service.create_event(env.conn, env.storage, "Event B", manual=True)
    env.conn.execute(
        "UPDATE events SET staging_dir = ? WHERE id = ?",
        (event_b["staging_dir"], event_a["id"]),
    )
    track = events_service.add_track(
        env.conn, event_a, title="Instant Crush", artist="Daft Punk"
    )
    env.conn.execute(
        "UPDATE event_tracks SET isrc = ?, status = 'missing' WHERE id = ?",
        (ISRC, track["id"]),
    )

    response = env.client.post(
        "/api/acquisition/jobs", json={"scope": "event", "row_id": track["id"]}
    )
    assert response.status_code == 400
    assert "does not match event" in response.json()["message"]

    # Legacy migration applies the same slug binding.
    with pytest.raises(ValueError, match="does not match event"):
        acquisition.event_audio_destination(
            env.storage, event_b["staging_dir"], event_slug=event_a["slug"]
        )


def test_migration_skips_owner_published_outputs(tmp_path, monkeypatch):
    """Review P2: a modern owner-published output is out of migration scope,
    never an 'unsafe_source' warning that would stick forever."""
    env = make_env(tmp_path)
    event = events_service.create_event(env.conn, env.storage, "Modern", manual=True)
    track = events_service.add_track(env.conn, event, title="New", artist="Artist")
    published = Path(event["staging_dir"]) / "audio" / "new.mp3"
    published.parent.mkdir(parents=True, exist_ok=True)
    published.write_bytes(b"owner audio")
    env.conn.execute(
        "INSERT INTO acquisition_jobs (scope, ref, title, artist, status, "
        "event_id, event_track_id, output_path) "
        "VALUES ('event', ?, 'New', 'Artist', 'downloaded', ?, ?, ?)",
        (str(track["id"]), event["id"], track["id"], str(published)),
    )

    class FakeRO:
        def execute(self, sql, params=()):
            return []

        def close(self):
            pass

    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: FakeRO())

    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)
    assert plan["items"] == []
    assert plan["ignored"] == []


class _ContentRO:
    """Read-only master.db stub: one active content row with a FolderPath."""

    def __init__(self, content_id, folder_path):
        self.content_id = str(content_id)
        self.folder_path = folder_path

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    def execute(self, sql, params=()):
        if "WHERE ID" in sql:
            wanted = str(params[0]) if params else None
            if wanted == self.content_id:
                if "AnalysisDataPath" in sql:
                    return self._Result([(self.folder_path, None, 0)])
                return self._Result([(self.folder_path, 0)])
            return self._Result([])
        if "FolderPath" in sql:  # active paths listing
            return self._Result([(self.content_id, self.folder_path)])
        return self._Result([])

    def close(self):
        pass


def test_resume_after_428_keeps_source_on_any_change(tmp_path, monkeypatch):
    """Review P1: after a permanent-delete 428, the retried cleanup re-hashes
    the source and re-reads the live Rekordbox path before deleting anything."""
    env = make_env(tmp_path)
    event = events_service.create_event(env.conn, env.storage, "Resume", manual=True)
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
        "UPDATE event_tracks SET status = 'ready', staging_file_path = ?, "
        "content_id = '77' WHERE id = ?",
        (str(source), track["id"]),
    )

    live = _ContentRO("77", str(source))
    monkeypatch.setattr(acquisition_migration, "open_readonly", lambda path: live)

    mutations = []

    @contextmanager
    def fake_mutate(*args, **kwargs):
        mutations.append("rekordbox")
        yield object()

    monkeypatch.setattr(acquisition_migration, "mutate", fake_mutate)

    def fake_migrate_content_path(db, content_id, stored, **kwargs):
        # Mirror the real mutation: the live FolderPath now references the
        # migrated destination.
        live.folder_path = stored

    monkeypatch.setattr(
        acquisition_migration, "migrate_content_path", fake_migrate_content_path
    )

    def refuse_delete(path, *, consent_to_permanent_delete=False):
        raise PermanentDeleteConsentRequired(Path(path), OSError("no trash"))

    monkeypatch.setattr(acquisition_migration, "delete_file", refuse_delete)

    plan = acquisition_migration.build_plan(env.conn, env.storage, env.deps.db_path)
    assert len(plan["items"]) == 1
    with pytest.raises(PermanentDeleteConsentRequired):
        acquisition_migration.execute(
            env.conn,
            env.deps.db_path,
            env.deps.backups_root,
            env.deps.cache(),
            env.storage,
            plan,
        )
    assert mutations == ["rekordbox"]
    assert env.conn.execute(
        "SELECT legacy_output_path FROM acquisition_jobs WHERE id = ?", (job,)
    ).fetchone()[0] == str(source)
    destination = Path(plan["items"][0]["destination_path"])
    assert destination.is_file()  # copy landed before the 428

    # The Rekordbox path now references the DESTINATION (as the committed
    # mutation would): the baseline retry below must reach the deletion gate.
    live.folder_path = str(destination)

    deletions = []

    def record_delete(path, *, consent_to_permanent_delete=False):
        deletions.append(str(path))
        shutil.rmtree(path)

    monkeypatch.setattr(acquisition_migration, "delete_file", record_delete)

    # 1) Source modified after the 428: cleanup refuses, source is kept.
    original_stat = source.stat()
    source.write_bytes(b"tampered by the user")
    with pytest.raises(StaleSnapshotError, match="source changed"):
        acquisition_migration.execute(
            env.conn,
            env.deps.db_path,
            env.deps.backups_root,
            env.deps.cache(),
            env.storage,
            plan,
            consent_to_permanent_delete=True,
        )
    assert deletions == []
    assert source.read_bytes() == b"tampered by the user"

    # 2) Source restored but the live Rekordbox path moved elsewhere:
    #    deleting the source would orphan the live reference — refused.
    source.write_bytes(b"legacy audio")
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    live.folder_path = str(tmp_path / "elsewhere.mp3")
    with pytest.raises(StaleSnapshotError, match="Rekordbox path"):
        acquisition_migration.execute(
            env.conn,
            env.deps.db_path,
            env.deps.backups_root,
            env.deps.cache(),
            env.storage,
            plan,
            consent_to_permanent_delete=True,
        )
    assert deletions == []
    assert source.is_file()

    # Baseline: with source and Rekordbox path both intact, cleanup proceeds.
    live.folder_path = str(destination)
    result = acquisition_migration.execute(
        env.conn,
        env.deps.db_path,
        env.deps.backups_root,
        env.deps.cache(),
        env.storage,
        plan,
        consent_to_permanent_delete=True,
    )
    assert deletions == [str(source.parent)]
    assert result["removed_sources"] == [str(source)]
    assert mutations == ["rekordbox"]
    assert env.conn.execute(
        "SELECT legacy_output_path FROM acquisition_jobs WHERE id = ?", (job,)
    ).fetchone()[0] is None


def test_migration_0008_canonicalizes_and_dedupes_a_v6_database(tmp_path):
    """Review P2: a v6 database with duplicate spellings, orphans and
    non-canonical refs migrates to one active job per canonical owner."""
    db = tmp_path / "v6.db"
    conn = appdb.connect(db)
    try:
        for version, _name, sql in appdb._scripts()[:6]:
            conn.execute("BEGIN")
            for stmt in appdb._statements(sql):
                conn.execute(stmt)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.execute("COMMIT")
        conn.execute(
            "INSERT INTO events (name, slug, default_tag) VALUES ('E', 'e', 'E')"
        )
        conn.execute(
            "INSERT INTO event_tracks (event_id, title, status) "
            "VALUES (1, 'T', 'missing')"
        )
        # Duplicate active jobs through ref spellings, plus an orphan ref.
        conn.execute(
            "INSERT INTO acquisition_jobs (scope, ref, title, status) "
            "VALUES ('event', '1', 'canonical', 'queued')"
        )
        conn.execute(
            "INSERT INTO acquisition_jobs (scope, ref, title, status) "
            "VALUES ('event', '01', 'spelled', 'running')"
        )
        conn.execute(
            "INSERT INTO acquisition_jobs (scope, ref, title, status) "
            "VALUES ('event', '999', 'orphan', 'queued')"
        )

        assert appdb.migrate(conn) >= 8

        rows = conn.execute(
            "SELECT ref, status, event_track_id FROM acquisition_jobs ORDER BY id"
        ).fetchall()
        assert (rows[0]["ref"], rows[0]["status"], rows[0]["event_track_id"]) == (
            "1",
            "queued",
            1,
        )
        # The '01' spelling was canonicalized then superseded as a duplicate.
        assert (rows[1]["ref"], rows[1]["status"]) == ("1", "failed")
        # The orphan keeps its ref and no owner id.
        assert (rows[2]["ref"], rows[2]["event_track_id"]) == ("999", None)

        # The partial unique index guards the owner id itself.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO acquisition_jobs (scope, ref, title, status, "
                "event_track_id) VALUES ('event', 'another', 'dup', 'queued', 1)"
            )
    finally:
        conn.close()
