"""Composition root and read-only frozen-runtime diagnostic seam."""

import json
import logging

from starlette.testclient import TestClient

from syncbox import acquisition
from syncbox.__main__ import compose, main
from syncbox.quality import QualityResult
from syncbox.spotify import ACCESS_TOKEN, REFRESH_TOKEN


def test_compose_builds_a_live_wired_app(tmp_path):
    app = compose(tmp_path)
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

    # data lives under the given dir, not the OS location
    assert (tmp_path / "syncbox.db").is_file()
    assert (tmp_path / "logs" / "syncbox.log").is_file()


def test_composed_exports_and_logs_exclude_encrypted_oauth_tokens(tmp_path):
    sentinel = "SYNCBOX-PHASE6-COMPOSED-OAUTH-SENTINEL"
    deezer_sentinel = "SYNCBOX-PHASE6-COMPOSED-DEEZER-SENTINEL"
    app = compose(tmp_path)
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
    assert set(result["packages"]) == {
        "certifi",
        "miniaudio",
        "numpy",
        "pyrekordbox",
        "send2trash",
        "sqlcipher3-wheels",
    }
    assert result["streamrip_importable"] is False
    assert list(tmp_path.iterdir()) == []


def test_packaging_check_rejects_extra_arguments(capsys):
    assert main(["--packaging-check", "extra"]) == 2
    assert "--packaging-check" in capsys.readouterr().err
