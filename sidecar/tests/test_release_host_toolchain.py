"""The CI escape hatch only unpins the Apple host toolchain fields."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load():
    path = REPO / "scripts" / "build_macos_release.py"
    spec = importlib.util.spec_from_file_location("build_macos_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_everything_stays_pinned_by_default(monkeypatch):
    module = _load()
    monkeypatch.delenv("SYNCBOX_RELEASE_HOST_TOOLCHAIN", raising=False)
    assert all(
        module._is_pinned("toolchain", name) for name in module.HOST_TOOLCHAIN_KEYS
    )


def test_unpinned_mode_only_relaxes_host_keys(monkeypatch):
    module = _load()
    monkeypatch.setenv("SYNCBOX_RELEASE_HOST_TOOLCHAIN", "unpinned")
    for name in module.HOST_TOOLCHAIN_KEYS:
        assert not module._is_pinned("toolchain", name)
    for name in ("architecture", "cargo", "node", "pnpm", "rustc", "tauri_cli", "uv"):
        assert module._is_pinned("toolchain", name)
    assert module._is_pinned("base_python", "python")
    assert module._is_pinned("optional_python", "pillow")


def test_pinned_sdkroot_comes_from_release_metadata(monkeypatch):
    module = _load()
    monkeypatch.delenv("SYNCBOX_RELEASE_HOST_TOOLCHAIN", raising=False)
    metadata = {"toolchain": {"macos_sdk_path": "/pinned/sdk"}}
    assert module._sdkroot(metadata) == "/pinned/sdk"
