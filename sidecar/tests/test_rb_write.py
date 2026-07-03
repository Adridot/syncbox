"""Tests for the Rekordbox write helpers (SPEC-01 1.1/1.6/1.7, poc/05).

signed32/smartlist tests are pure; the integration flow needs the real
fixture and runs the FULL mutate unit-of-work on a copy.
"""

import shutil
from pathlib import Path

import pytest

from syncbox import rb
from syncbox.rb_write import signed32, smartlist_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "poc" / "testdata"
FIXTURE = TESTDATA / "master.db"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="real master.db fixture not present"
)


# --- pure: the OWNED conditional signed-32 conversion ---------------------------


def test_signed32_is_conditional_not_unconditional():
    # Spec example (SPEC-01 1.7) verified against real RB data in poc/05
    assert signed32(2662450573) == -1632516723
    # IDs < 2^31 STAY POSITIVE - pyrekordbox's unconditional shift is the
    # #110-family quirk Syncbox must not reproduce
    assert signed32(1248102774) == 1248102774
    assert signed32(2**31) == -(2**31)
    assert signed32(2**31 - 1) == 2**31 - 1


def test_smartlist_payload_shape():
    big_pl, big_tag = 3644759451, 2662450573
    payload = smartlist_payload(str(big_pl), str(big_tag))
    assert f'Id="{signed32(big_pl)}"' in payload  # -650207845
    assert f'ValueLeft="{signed32(big_tag)}"' in payload  # -1632516723
    assert 'Operator="8"' in payload  # contains

    small = smartlist_payload("1248102774", "999")
    assert 'Id="1248102774"' in small  # stays positive (real RB behavior)
    assert 'ValueLeft="999"' in small


# --- integration: full write flow through mutate on the real fixture ------------


@needs_fixture
def test_full_write_flow_through_mutate(tmp_path, monkeypatch):
    from syncbox.rb_write import (
        apply_tag_delta,
        create_or_repair_smart_playlist,
        ensure_playlist_folder,
        find_or_create_artist,
        find_or_create_mytag,
        open_rekordbox,
        soft_delete_content,
        reactivate_content,
        tag_content,
    )
    from syncbox.safety.mutate import mutate

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    shutil.copy2(TESTDATA / "masterPlaylists6.xml", live / "masterPlaylists6.xml")
    backups = tmp_path / "backups"

    cache = rb.SnapshotCache(db_path)
    rows = cache.get(tmp_path / "storage")
    target = rows[0]["content_id"]
    fingerprint_before = cache.current_fingerprint

    created = {}
    with mutate(
        db_path,
        backups,
        expected_fingerprint=fingerprint_before,
        open_db=open_rekordbox,
        invalidate_cache=cache.invalidate,
    ) as db:
        tag = find_or_create_mytag(db, "IT Event", "Situation")
        tag_content(db, target, tag.ID)
        tag_content(db, target, tag.ID)  # idempotent
        folder = ensure_playlist_folder(db, "Event Imports")
        playlist = create_or_repair_smart_playlist(db, "IT Event", folder.ID, tag.ID)
        created.update(tag_id=tag.ID, folder_id=folder.ID, playlist_id=playlist.ID)
        assert isinstance(playlist.ID, str) and isinstance(tag.ID, str)

    # cache invalidated by the unit-of-work
    assert cache.current_fingerprint is None

    # verify on disk through an independent read-only connection
    conn = rb.open_readonly(db_path)
    pl_row = conn.execute(
        "SELECT SmartList, Attribute, ParentID FROM djmdPlaylist WHERE ID = ?",
        (created["playlist_id"],),
    ).fetchone()
    assert pl_row[1] == 4 and pl_row[2] == created["folder_id"]
    assert f'Id="{signed32(int(created["playlist_id"]))}"' in pl_row[0]
    assert f'ValueLeft="{signed32(int(created["tag_id"]))}"' in pl_row[0]
    links = conn.execute(
        "SELECT COUNT(*) FROM djmdSongMyTag WHERE ContentID=? AND MyTagID=? "
        "AND rb_local_deleted=0",
        (target, created["tag_id"]),
    ).fetchone()[0]
    assert links == 1  # idempotent tagging created exactly one link
    conn.close()

    # --- repair path: same playlist reused, never duplicated (11.2) -----------
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        again = create_or_repair_smart_playlist(
            db, "IT Event", created["folder_id"], created["tag_id"]
        )
        assert again.ID == created["playlist_id"]

    # --- tag delta remove (D16) + soft-delete round trip -----------------------
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        apply_tag_delta(db, target, remove_tag_ids=[created["tag_id"]])
        soft_delete_content(db, target)

    conn = rb.open_readonly(db_path)
    link_deleted = conn.execute(
        "SELECT rb_local_deleted FROM djmdSongMyTag WHERE ContentID=? AND MyTagID=?",
        (target, created["tag_id"]),
    ).fetchone()[0]
    tuple_row = conn.execute(
        "SELECT rb_local_deleted, rb_local_synced, rb_data_status, "
        "rb_local_data_status FROM djmdContent WHERE ID=?",
        (target,),
    ).fetchone()
    conn.close()
    assert int(link_deleted) == 1  # delta remove = reversible soft delete
    assert tuple(int(x) for x in tuple_row) == (1, 0, 258, 0)  # exact 1.1 tuple

    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        reactivate_content(db, target)

    conn = rb.open_readonly(db_path)
    status = conn.execute(
        "SELECT rb_data_status, rb_local_deleted FROM djmdContent WHERE ID=?",
        (target,),
    ).fetchone()
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    assert tuple(int(x) for x in status) == (256, 0)
    assert integrity == "ok"

    # artist self-heal / find-or-create sanity
    with mutate(db_path, backups, open_db=open_rekordbox) as db:
        first = find_or_create_artist(db, "Syncbox IT Artist")
        second = find_or_create_artist(db, "Syncbox IT Artist")
        assert first.ID == second.ID

    # every mutation left a timestamped backup behind (5 mutate calls)
    assert len(list(backups.iterdir())) == 5


@needs_fixture
def test_smartfixes_runner_end_to_end(tmp_path):
    from syncbox import smartfixes_run
    from syncbox.safety.mutate import StaleSnapshotError

    live = tmp_path / "live"
    live.mkdir()
    db_path = live / "master.db"
    shutil.copy2(FIXTURE, db_path)
    backups = tmp_path / "backups"
    cache = rb.SnapshotCache(db_path)

    dry = smartfixes_run.dry_run(cache, tmp_path / "storage")
    assert dry["fingerprint"] is not None
    # real fixture has structural fixes to make (poc/09 measured ~240)
    assert len(dry["payload"]) > 0
    assert all(c["before"] != c["after"] for c in dry["payload"])

    result = smartfixes_run.execute(db_path, backups, cache, dry)
    assert result["fields_applied"] == len(dry["payload"])

    # idempotence: a fresh dry-run after mutate is empty (5.11)
    dry2 = smartfixes_run.dry_run(cache, tmp_path / "storage")
    assert dry2["payload"] == []

    # freshness guard: stale dry-run against a changed DB aborts pre-backup
    with open(db_path, "ab") as f:
        f.write(b"x")
    with pytest.raises(StaleSnapshotError):
        smartfixes_run.execute(db_path, backups, cache, dry)
