"""Safety tests for the private Rekordbox fixture copier."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load_copier():
    path = REPO / "scripts" / "copy_rekordbox_fixtures.py"
    spec = importlib.util.spec_from_file_location("copy_rekordbox_fixtures", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _library(root: Path) -> Path:
    root.mkdir()
    (root / "master.db").write_bytes(b"private database")
    (root / "masterPlaylists6.xml").write_text("<DJ_PLAYLISTS />\n")
    (root / "master.db-wal").write_bytes(b"wal")
    return root


def test_copy_requires_backup_confirmation(monkeypatch, tmp_path):
    copier = _load_copier()
    source = _library(tmp_path / "source")
    monkeypatch.setattr(copier, "TESTDATA", tmp_path / "testdata")
    (tmp_path / "testdata").mkdir()
    guarded = []
    monkeypatch.setattr(copier, "assert_mutation_ready", guarded.append)

    with pytest.raises(ValueError, match="backup must be confirmed"):
        copier.copy_fixtures(source, backup_confirmed=False)
    assert guarded == [source / "master.db"]


def test_copy_is_regular_verified_and_source_preserving(monkeypatch, tmp_path):
    copier = _load_copier()
    source = _library(tmp_path / "source")
    testdata = tmp_path / "testdata"
    testdata.mkdir()
    monkeypatch.setattr(copier, "TESTDATA", testdata)
    guarded = []
    monkeypatch.setattr(copier, "assert_mutation_ready", guarded.append)
    before = {path.name: copier._state(path) for path in source.iterdir()}

    result = copier.copy_fixtures(source, backup_confirmed=True)

    assert guarded == [source / "master.db"]
    assert result["source_unchanged"] is True
    assert {item["name"] for item in result["files"]} == {
        "master.db",
        "masterPlaylists6.xml",
        "master.db-wal",
    }
    assert {path.name: copier._state(path) for path in source.iterdir()} == before
    for name, state in before.items():
        target = testdata / name
        assert target.is_file() and not target.is_symlink()
        assert target.stat().st_size == state[1]
        assert copier._digest(target) == state[3]


def test_copy_rejects_symlink_sources(monkeypatch, tmp_path):
    copier = _load_copier()
    source = _library(tmp_path / "source")
    (source / "master.db-wal").unlink()
    (source / "master.db-wal").symlink_to("master.db")
    testdata = tmp_path / "testdata"
    testdata.mkdir()
    monkeypatch.setattr(copier, "TESTDATA", testdata)
    monkeypatch.setattr(copier, "assert_mutation_ready", lambda _path: None)

    with pytest.raises(ValueError, match="traverses a symlink"):
        copier.copy_fixtures(source, backup_confirmed=True)


def test_copy_ignores_empty_optional_database_sidecars(monkeypatch, tmp_path):
    copier = _load_copier()
    source = _library(tmp_path / "source")
    (source / "master.db-wal").write_bytes(b"")
    testdata = tmp_path / "testdata"
    testdata.mkdir()
    monkeypatch.setattr(copier, "TESTDATA", testdata)
    monkeypatch.setattr(copier, "assert_mutation_ready", lambda _path: None)

    result = copier.copy_fixtures(source, backup_confirmed=True)

    assert {item["name"] for item in result["files"]} == {
        "master.db",
        "masterPlaylists6.xml",
    }
    assert not (testdata / "master.db-wal").exists()


def test_copy_refuses_to_replace_existing_private_fixture(monkeypatch, tmp_path):
    copier = _load_copier()
    source = _library(tmp_path / "source")
    testdata = tmp_path / "testdata"
    testdata.mkdir()
    (testdata / "master.db").write_bytes(b"existing")
    monkeypatch.setattr(copier, "TESTDATA", testdata)
    monkeypatch.setattr(copier, "assert_mutation_ready", lambda _path: None)

    with pytest.raises(ValueError, match="already exists"):
        copier.copy_fixtures(source, backup_confirmed=True)
    assert (testdata / "master.db").read_bytes() == b"existing"
