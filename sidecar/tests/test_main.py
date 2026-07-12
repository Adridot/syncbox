"""Composition root and read-only frozen-runtime diagnostic seam."""

import json

from starlette.testclient import TestClient

from syncbox.__main__ import compose, main
from syncbox.quality import QualityResult


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
