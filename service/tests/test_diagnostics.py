from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.diagnostics as diagnostics_module
from app.db import LocalDatabase
from app.diagnostics import run_diagnostics
from app.models import DeemixStatus


class FakeAdapter:
    def __init__(self, root: Path):
        self._root = root

    def collection_stats(self):
        return {"available": True, "total": 1418}

    def status(self):
        return SimpleNamespace(rekordbox_running=False)

    def storage_layout(self):
        return SimpleNamespace(
            root=str(self._root),
            permanent=str(self._root / "permanent"),
            events=str(self._root / "events"),
        )

    def list_backups(self):
        return [{"name": "rekordbox-db-x"}]


@pytest.fixture
def database(tmp_path: Path) -> LocalDatabase:
    db = LocalDatabase(tmp_path / "syncbox.sqlite3")
    db.migrate()
    return db


def test_diagnostics_ok_when_everything_healthy(tmp_path, database, monkeypatch):
    for sub in ("permanent", "events"):
        (tmp_path / sub).mkdir()

    async def fake_deemix():
        return DeemixStatus(baseUrl="http://127.0.0.1:6595", available=True, authenticated=True, detail="")

    monkeypatch.setattr(diagnostics_module, "get_deemix_status", fake_deemix)
    database.set_setting("spotify_refresh_token", "token")

    report = asyncio.run(run_diagnostics(database, FakeAdapter(tmp_path)))

    keys = {check.key for check in report.checks}
    assert {"rekordbox_db", "storage_root", "deemix", "spotify", "backups"} <= keys
    assert report.status == "ok"


def test_diagnostics_warns_without_spotify_and_deemix(tmp_path, database, monkeypatch):
    for sub in ("permanent", "events"):
        (tmp_path / sub).mkdir()

    async def fake_deemix():
        return DeemixStatus(baseUrl="http://127.0.0.1:6595", available=False, authenticated=False, detail="offline")

    monkeypatch.setattr(diagnostics_module, "get_deemix_status", fake_deemix)

    report = asyncio.run(run_diagnostics(database, FakeAdapter(tmp_path)))

    assert report.status == "warn"
    spotify = next(check for check in report.checks if check.key == "spotify")
    assert spotify.status == "warn"
