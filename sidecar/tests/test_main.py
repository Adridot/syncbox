"""Composition root and read-only frozen-runtime diagnostic seam."""

import hashlib
import json
import logging

from starlette.testclient import TestClient

from syncbox import acquisition
from syncbox.__main__ import compose, main
from syncbox.quality import QualityResult
from syncbox.spotify import ACCESS_TOKEN, REFRESH_TOKEN


class FakeOAuthListener:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self, callback, *, oauth_lock, timeout):
        self.started += 1
        return True

    def stop(self):
        self.stopped += 1

    def wait_closed(self, timeout=4):
        return None


def test_compose_builds_a_live_wired_app(tmp_path):
    listener = FakeOAuthListener()
    app = compose(tmp_path, oauth_listener=listener)
    client = TestClient(app)

    # transport routes alive
    assert client.get("/health").json() == {
        "ok": True,
        "service": "syncbox-sidecar",
        "protocol": 1,
    }

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
    assert listener.started == 1

    # data lives under the given dir, not the OS location
    assert (tmp_path / "syncbox.db").is_file()
    assert (tmp_path / "logs" / "syncbox.log").is_file()
    app.state.secrets.close()
    app.state.deps.conn.close()


def test_composed_exports_and_logs_exclude_encrypted_oauth_tokens(tmp_path):
    sentinel = "SYNCBOX-PHASE6-COMPOSED-OAUTH-SENTINEL"
    deezer_sentinel = "SYNCBOX-PHASE6-COMPOSED-DEEZER-SENTINEL"
    app = compose(tmp_path, oauth_listener=FakeOAuthListener())
    client = TestClient(app)
    app.state.secrets.set(ACCESS_TOKEN, sentinel)
    app.state.secrets.set(REFRESH_TOKEN, f"{sentinel}-refresh")
    app.state.secrets.set(acquisition.DEEZER_ARL_SECRET, deezer_sentinel)

    settings = tmp_path / "settings.json"
    data = tmp_path / "data.db"
    assert client.post("/api/settings/export", json={"path": str(settings)}).status_code == 200
    assert client.post("/api/data/export", json={"path": str(data)}).status_code == 200
    logging.getLogger("syncbox").info("Phase 6 composed export scan completed")

    logs = client.get("/api/doctor/logs").json()
    assert logs["configured"] is True
    assert any("composed export scan completed" in line for line in logs["lines"])
    assert sentinel.encode() not in settings.read_bytes()
    assert sentinel.encode() not in data.read_bytes()
    assert sentinel.encode() not in (tmp_path / "logs" / "syncbox.log").read_bytes()
    assert deezer_sentinel.encode() not in settings.read_bytes()
    assert deezer_sentinel.encode() not in data.read_bytes()
    assert deezer_sentinel.encode() not in (tmp_path / "logs" / "syncbox.log").read_bytes()
    assert app.state.secrets.get(ACCESS_TOKEN) == sentinel
    assert app.state.secrets.get(acquisition.DEEZER_ARL_SECRET) == deezer_sentinel
    app.state.secrets.close()
    app.state.deps.conn.close()


def test_quality_cli_is_read_only_and_skips_app_composition(
    tmp_path, monkeypatch, capsys
):
    audio = tmp_path / "Folder With Spaces" / "音楽.flac"
    audio.parent.mkdir()
    audio.write_bytes(b"fixture path only")
    seen = []

    monkeypatch.setattr(
        "syncbox.__main__.quality.analyze",
        lambda path: seen.append(path)
        or QualityResult("incertain", 16_000.0, "spectral_cutoff_ambiguous"),
    )
    monkeypatch.setattr(
        "syncbox.__main__.compose",
        lambda: (_ for _ in ()).throw(AssertionError("compose must not run")),
    )

    assert main(["--quality-analyze", str(audio)]) == 0
    assert seen == [str(audio)]
    assert json.loads(capsys.readouterr().out) == {
        "verdict": "incertain",
        "cutoff_hz": 16_000.0,
        "reason": "spectral_cutoff_ambiguous",
    }


def test_quality_cli_requires_exactly_one_path(capsys):
    assert main(["--quality-analyze"]) == 2
    assert "--quality-analyze PATH" in capsys.readouterr().err


def test_packaging_check_exercises_runtime_dependencies_without_app_data(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "syncbox.__main__.compose",
        lambda: (_ for _ in ()).throw(AssertionError("compose must not run")),
    )
    assert main(["--packaging-check"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["architecture"] == "arm64"
    assert result["packages"] == {
        "certifi": "2026.6.17",
        "miniaudio": "1.71",
        "numpy": "2.5.1",
        "pyrekordbox": "0.4.4",
        "send2trash": "2.1.0",
        "sqlcipher3-wheels": "0.6.2+syncbox.commoncrypto.1",
    }
    assert result["sqlcipher"] == "4.12.0 community"
    assert result["sqlcipher_provider"] == "commoncrypto"
    assert result["sqlcipher_provider_version"]
    assert result["sqlcipher_status"] == "1"
    assert result["api_port"] == 8766
    assert result["oauth_callback_port"] == 8765
    assert result["streamrip_importable"] is False
    assert list(tmp_path.iterdir()) == []


def test_packaging_check_rejects_extra_arguments(capsys):
    assert main(["--packaging-check", "extra"]) == 2
    assert "--packaging-check" in capsys.readouterr().err


def test_second_sidecar_fails_before_touching_the_first_instances_queue(
    tmp_path, monkeypatch
):
    """Review P1: single-instance ownership (the exclusive port bind) comes
    BEFORE any queue reset or worker start — a second sidecar exits without
    requeueing or claiming the live instance's running job."""
    from syncbox import appdb, server

    conn = appdb.open_app_db(tmp_path / "syncbox.db")
    conn.execute(
        "INSERT INTO acquisition_jobs (scope, ref, title, status, claimed_by) "
        "VALUES ('library', '1', 'Live', 'running', 'first-instance')"
    )
    conn.close()
    monkeypatch.setenv("SYNCBOX_DATA_DIR", str(tmp_path))

    constructed = []
    monkeypatch.setattr(
        "syncbox.__main__.api.AcquisitionWorker",
        lambda deps: constructed.append(deps),
    )

    def refuse_bind(*args, **kwargs):
        raise server.PortInUseError(server.HOST, server.PORT)

    monkeypatch.setattr("syncbox.__main__.server.bind_api_socket", refuse_bind)

    assert main([]) == 1

    assert constructed == []  # the worker was never even created
    conn = appdb.open_app_db(tmp_path / "syncbox.db")
    try:
        job = conn.execute(
            "SELECT status, claimed_by FROM acquisition_jobs"
        ).fetchone()
        assert (job["status"], job["claimed_by"]) == ("running", "first-instance")
    finally:
        conn.close()


def test_compose_recovers_an_interrupted_restore_before_opening_the_app_db(
    tmp_path,
):
    """Review P1: a durable restore journal left by a crash is resolved at
    startup, before anything opens the half-restored pair."""
    from syncbox.safety import backup as safety_backup

    target = tmp_path / "master.db"
    target.write_bytes(b"old epoch")
    staged = target.with_name(target.name + ".restore-tmp")
    staged.write_bytes(b"backup epoch")
    digest = hashlib.sha256(b"backup epoch").hexdigest()
    safety_backup._write_restore_journal(
        tmp_path,
        {
            "schema": 1,
            "created_at": "2026-07-16T00:00:00",
            "source": str(tmp_path),
            "snapshot": None,
            "db_path": str(target),
            "app_db_path": None,
            "replacements": [
                {"staged": str(staged), "target": str(target), "sha256": digest}
            ],
            "removals": [],
        },
    )

    app = compose(tmp_path, oauth_listener=FakeOAuthListener())

    assert target.read_bytes() == b"backup epoch"
    assert not (tmp_path / safety_backup._RESTORE_JOURNAL).exists()
    app.state.secrets.close()
    app.state.deps.conn.close()
