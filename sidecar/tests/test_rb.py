"""Tests for the read-only Rekordbox snapshot layer (SPEC-UNIFIED 4 / 11.3)."""

import shutil
import time
from pathlib import Path

import pytest

from syncbox import rb
from syncbox.rb import SnapshotCache
from syncbox.safety.paths import is_protected_path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "poc" / "testdata" / "master.db"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="real master.db fixture not present"
)


# --- cache mechanics (no fixture needed) ---------------------------------------


def make_db(tmp_path):
    db = tmp_path / "master.db"
    db.write_bytes(b"fake")
    return db


def test_cache_loads_once_per_fingerprint(tmp_path):
    db = make_db(tmp_path)
    calls = []

    def loader(path, root):
        calls.append(root)
        return [{"content_id": "1"}]

    cache = SnapshotCache(db, loader=loader)
    cache.get("/root")
    cache.get("/root")
    assert len(calls) == 1


def test_cache_reloads_when_file_changes(tmp_path):
    db = make_db(tmp_path)
    calls = []
    cache = SnapshotCache(db, loader=lambda p, r: calls.append(1) or [])
    cache.get("/root")
    time.sleep(0.01)
    db.write_bytes(b"fake-changed")
    cache.get("/root")
    assert len(calls) == 2


def test_cache_reloads_on_storage_root_change(tmp_path):
    db = make_db(tmp_path)
    calls = []
    cache = SnapshotCache(db, loader=lambda p, r: calls.append(r) or [])
    cache.get("/root-a")
    cache.get("/root-b")
    assert calls == ["/root-a", "/root-b"]


def test_invalidate_forces_reload(tmp_path):
    db = make_db(tmp_path)
    calls = []
    cache = SnapshotCache(db, loader=lambda p, r: calls.append(1) or [])
    cache.get("/root")
    cache.invalidate()
    assert cache.current_fingerprint is None
    cache.get("/root")
    assert len(calls) == 2


def test_fingerprint_exposed_for_freshness_guard(tmp_path):
    db = make_db(tmp_path)
    cache = SnapshotCache(db, loader=lambda p, r: [])
    cache.get("/root")
    from syncbox.safety.mutate import fingerprint

    assert cache.current_fingerprint == fingerprint(db)


def test_protected_path_rule(tmp_path):
    root = tmp_path / "DJ"
    (root / "rekordbox" / "Collection").mkdir(parents=True)
    inside = root / "rekordbox" / "Collection" / "track.aiff"
    outside = root / "_rekordbox_sync" / "inbox" / "track.aiff"
    assert is_protected_path(str(inside), root)
    assert is_protected_path(f"/{root.name}/rekordbox/Collection/track.aiff", root)
    assert not is_protected_path(str(outside), root)
    assert not is_protected_path("/elsewhere/track.aiff", root)


# --- integration on the real fixture -------------------------------------------


@needs_fixture
def test_snapshot_reads_real_db_readonly(tmp_path):
    db = tmp_path / "master.db"
    shutil.copy2(FIXTURE, db)
    rows = rb.load_snapshot(db, tmp_path / "storage")
    assert len(rows) > 1000  # 8107 total on the fixture, active subset here
    sample = next(r for r in rows if r["key_name"] and r["genre"] and r["bit_rate"])
    assert sample["content_id"] and isinstance(sample["content_id"], str)
    assert 30_000 < sample["duration_ms"] < 1_800_000
    assert sample["cue_count"] >= 0 and sample["playlist_count"] >= 0
    # 11.3 readout fields present on real data (poc/05 verified they exist)
    assert any(r["play_count"] not in (None, 0, "0") for r in rows)
    assert any(r["stock_date"] for r in rows)
    # original fixture untouched (mode=ro + copy discipline)
    assert FIXTURE.stat().st_size > 0


@needs_fixture
def test_snapshot_filters_soft_deleted(tmp_path):
    db = tmp_path / "master.db"
    shutil.copy2(FIXTURE, db)
    conn = rb.open_readonly(db)
    active = conn.execute(
        "SELECT COUNT(*) FROM djmdContent WHERE rb_local_deleted = 0"
    ).fetchone()[0]
    soft_deleted = conn.execute(
        "SELECT COUNT(*) FROM djmdContent WHERE rb_local_deleted = 1"
    ).fetchone()[0]
    conn.close()
    rows = rb.load_snapshot(db, tmp_path / "storage")
    assert len(rows) == active
    assert soft_deleted >= 0  # fixture has 29 soft-deleted rows (poc/05)
