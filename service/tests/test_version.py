from __future__ import annotations

import app.version as version_module
from app.version import app_version


def test_app_version_prefers_env(monkeypatch):
    monkeypatch.setenv("RBSYNC_APP_VERSION", "1.2.3")
    assert app_version() == "1.2.3"


def test_app_version_reads_package_json(monkeypatch):
    monkeypatch.delenv("RBSYNC_APP_VERSION", raising=False)
    # package.json at repo root is the canonical source in dev.
    assert app_version() == version_module._read_package_json_version()


def test_app_version_fallback(monkeypatch):
    monkeypatch.delenv("RBSYNC_APP_VERSION", raising=False)
    monkeypatch.setattr(version_module, "_read_package_json_version", lambda: None)
    assert app_version() == "0.0.0"
