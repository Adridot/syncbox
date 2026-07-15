"""Safety tests for the private Rekordbox fixture copier."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load_copier():
    path = REPO / "poc" / "copy_rekordbox_fixtures.py"
    spec = importlib.util.spec_from_file_location("copy_rekordbox_fixtures", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_manual_smartfix_preparer():
    path = REPO / "poc" / "prepare_manual_smartfix_fixture.py"
    spec = importlib.util.spec_from_file_location(
        "prepare_manual_smartfix_fixture", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_event_runner():
    path = REPO / "poc" / "run_event_migration_tests.py"
    spec = importlib.util.spec_from_file_location("run_event_migration_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_manual_sandbox_preparer():
    path = REPO / "poc" / "prepare_manual_rekordbox_sandboxes.py"
    spec = importlib.util.spec_from_file_location(
        "prepare_manual_rekordbox_sandboxes", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_manual_swap_manager():
    path = REPO / "poc" / "manage_manual_rekordbox_swap.py"
    spec = importlib.util.spec_from_file_location("manage_manual_rekordbox_swap", path)
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


def test_manual_smartfix_output_must_be_new_and_below_testdata(
    monkeypatch, tmp_path
):
    preparer = _load_manual_smartfix_preparer()
    testdata = tmp_path / "testdata"
    testdata.mkdir()
    monkeypatch.setattr(preparer, "TESTDATA", testdata)

    with pytest.raises(ValueError, match="below poc/testdata"):
        preparer._output_path(tmp_path / "outside")

    existing = testdata / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        preparer._output_path(existing)

    assert preparer._output_path(testdata / "new") == testdata / "new"


def test_retained_event_output_must_be_new_and_below_testdata(
    monkeypatch, tmp_path
):
    runner = _load_event_runner()
    testdata = tmp_path / "testdata"
    testdata.mkdir()
    monkeypatch.setattr(runner, "TESTDATA", testdata)

    with pytest.raises(ValueError, match="below poc/testdata"):
        runner._retained_output(tmp_path / "outside")

    existing = testdata / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        runner._retained_output(existing)

    assert runner._retained_output(testdata / "new") == testdata / "new"


def test_manual_sandbox_copy_is_regular_verified_and_source_preserving(tmp_path):
    preparer = _load_manual_sandbox_preparer()
    source = tmp_path / "source"
    nested = source / "share" / "PIONEER"
    nested.mkdir(parents=True)
    (source / "empty" / "nested").mkdir(parents=True)
    (source / "master.db").write_bytes(b"database")
    (nested / "ANLZ0000.DAT").write_bytes(b"analysis")
    before = preparer._tree_state(source)

    destination = tmp_path / "destination"
    preparer._copy_tree(source, destination)

    assert preparer._tree_state(source) == before
    assert preparer._tree_state(destination) == before
    assert (destination / "empty" / "nested").is_dir()
    assert all(
        not path.is_symlink() and (path.is_file() or path.is_dir())
        for path in destination.rglob("*")
    )


def test_manual_sandbox_copy_rejects_symlinks(tmp_path):
    preparer = _load_manual_sandbox_preparer()
    source = tmp_path / "source"
    source.mkdir()
    (source / "master.db").write_bytes(b"database")
    (source / "linked.db").symlink_to("master.db")

    with pytest.raises(ValueError, match="regular file"):
        preparer._copy_tree(source, tmp_path / "destination")


def test_manual_sandbox_rejects_symlinked_path_components(tmp_path):
    preparer = _load_manual_sandbox_preparer()
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(ValueError, match="traverses a symlink"):
        preparer._assert_no_symlink_components(linked / "output", Path("/"))


def test_manual_sandbox_rejects_event_manifest_path_escape(monkeypatch, tmp_path):
    preparer = _load_manual_sandbox_preparer()
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "event-migration.json").write_text(
        """{
  "schema_version": 1,
  "content_id": "123",
  "staging_audio": "audio/track.mp3",
  "anlz_files": ["../outside/ANLZ0000.DAT"]
}\n""",
        encoding="utf-8",
    )
    monkeypatch.setattr(preparer, "EVENT_SOURCE", fixture)

    with pytest.raises(ValueError, match="normalized relative path"):
        preparer._event_anlz_paths()


def test_manual_sandbox_removes_inapplicable_database_sidecars(tmp_path):
    preparer = _load_manual_sandbox_preparer()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "master.db").write_bytes(b"event database")
    (source / "master.db-shm").write_bytes(b"event shm")
    (source / "masterPlaylists6.xml").write_bytes(b"<event />")
    (destination / "master.db").write_bytes(b"live database")
    (destination / "master.db-wal").write_bytes(b"stale wal")
    (destination / "master.db-shm").write_bytes(b"stale shm")
    (destination / "masterPlaylists6.xml").write_bytes(b"<live />")

    preparer._apply_database(source, destination)

    assert (destination / "master.db").read_bytes() == b"event database"
    assert not (destination / "master.db-wal").exists()
    assert (destination / "master.db-shm").read_bytes() == b"event shm"
    assert (destination / "masterPlaylists6.xml").read_bytes() == b"<event />"


def test_manual_swap_installs_both_sandboxes_and_restores_exactly(
    monkeypatch, tmp_path
):
    manager = _load_manual_swap_manager()
    manual = tmp_path / "manual"
    sandboxes = manual / "rekordbox-sandboxes-final"
    live = tmp_path / "rekordbox"
    hold = tmp_path / "rekordbox.syncbox-live-hold-20260714"
    smartfix = sandboxes / "smartfix-sandbox"
    event = sandboxes / "event-sandbox"
    for root, payload in (
        (live, b"original"),
        (smartfix, b"smartfix"),
        (event, b"event"),
    ):
        (root / "empty").mkdir(parents=True)
        (root / "master.db").write_bytes(payload)

    monkeypatch.setattr(manager, "MANUAL_ROOT", manual)
    monkeypatch.setattr(manager, "SANDBOX_ROOT", sandboxes)
    monkeypatch.setattr(manager, "LIVE", live)
    monkeypatch.setattr(manager, "HOLD", hold)
    monkeypatch.setattr(manager, "MANIFEST", manual / "live-restore-manifest.json")
    monkeypatch.setattr(manager, "STATE", manual / "manual-swap-state.json")
    monkeypatch.setattr(manager, "CHECKED_SMARTFIX", manual / "checked-smartfix-data")
    monkeypatch.setattr(manager, "CHECKED_EVENT", manual / "checked-event-data")
    monkeypatch.setattr(manager, "assert_mutation_ready", lambda _path: None)
    original = manager._tree_state(live)

    assert manager.install_smartfix()["phase"] == "smartfix"
    assert (live / "master.db").read_bytes() == b"smartfix"
    assert manager._tree_state(hold) == original

    assert manager.install_event()["phase"] == "event"
    assert (live / "master.db").read_bytes() == b"event"
    assert (manual / "checked-smartfix-data" / "master.db").read_bytes() == b"smartfix"

    assert manager.restore()["live_restored_exactly"] is True
    assert manager._tree_state(live) == original
    assert not hold.exists()
    assert (manual / "checked-event-data" / "master.db").read_bytes() == b"event"
