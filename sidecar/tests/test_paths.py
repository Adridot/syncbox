"""Tests for load-bearing path resolution (SPEC-UNIFIED 3.2/3.3/5.2, SPEC-01 1.4/1.5).

The storage rule: a file under <storage_root>/rekordbox/... is stored
volume-relative (/<VolumeName>/..., VolumeName = basename of the storage
root); everything else is stored absolute. Volume-relative and absolute
spellings of the same file must be equal and hash-equal, and existence
checks must never enumerate the parent directory (macOS TCC cloud quirk).
"""

import os
from pathlib import Path

import pytest

from syncbox.safety.paths import (
    canonical_key,
    classify_ownership,
    path_lookup_keys,
    paths_equal,
    stored_form,
    tcc_exists,
)


@pytest.fixture
def root(tmp_path):
    # Volume name deliberately contains a space, like a real external SSD.
    r = tmp_path / "Music SSD"
    (r / "rekordbox" / "Collection").mkdir(parents=True)
    (r / "_syncbox" / "inbox").mkdir(parents=True)
    return r


# --- stored_form: the storage-root boundary -----------------------------------


def test_stored_form_under_rekordbox_is_volume_relative(root):
    p = root / "rekordbox" / "Collection" / "track.mp3"
    assert stored_form(p, root) == "/Music SSD/rekordbox/Collection/track.mp3"


def test_stored_form_inbox_is_absolute(root):
    p = root / "_syncbox" / "inbox" / "track.mp3"
    assert stored_form(p, root) == str(p)


def test_stored_form_outside_root_is_absolute(root):
    p = "/Users/dj/Downloads/track.mp3"
    assert stored_form(p, root) == p


@pytest.mark.parametrize(
    "relative",
    [
        # Sibling directory whose name shares the 'rekordbox' prefix.
        ("rekordbox-old", "track.mp3"),
        ("rekordboxx", "track.mp3"),
        # 'rekordbox' appearing deeper than the first level under the root.
        ("inbox", "rekordbox", "track.mp3"),
    ],
)
def test_stored_form_boundary_lookalikes_stay_absolute(root, relative):
    p = root.joinpath(*relative)
    assert stored_form(p, root) == str(p)


def test_stored_form_other_root_with_shared_prefix_stays_absolute(tmp_path, root):
    other = tmp_path / "Music SSD backup" / "rekordbox" / "track.mp3"
    assert stored_form(other, root) == str(other)


def test_stored_form_is_idempotent_on_volume_relative_input(root):
    rel = "/Music SSD/rekordbox/Collection/track.mp3"
    assert stored_form(rel, root) == rel


def test_stored_form_expands_user(root):
    expected = os.path.expanduser("~/staging/track.mp3")
    assert stored_form("~/staging/track.mp3", root) == expected


# --- path_lookup_keys ----------------------------------------------------------


def test_lookup_keys_bridge_db_row_and_staging_path(root):
    db_row = "/Music SSD/rekordbox/Collection/a.mp3"
    staging = str(root / "rekordbox" / "Collection" / "a.mp3")
    assert set(path_lookup_keys(db_row, root)) & set(path_lookup_keys(staging, root))


def test_lookup_keys_volume_relative_row_yields_absolute_form(root):
    db_row = "/Music SSD/rekordbox/Collection/a.mp3"
    keys = path_lookup_keys(db_row, root)
    assert keys[0] == db_row  # raw form first, order stable
    assert str(root / "rekordbox" / "Collection" / "a.mp3") in keys


def test_lookup_keys_absolute_path_yields_volume_relative_form(root):
    staging = root / "rekordbox" / "Collection" / "a.mp3"
    keys = path_lookup_keys(staging, root)
    assert "/Music SSD/rekordbox/Collection/a.mp3" in keys


def test_lookup_keys_are_unique_strings_stable_order(root):
    raw = str(root / "rekordbox" / "Collection" / "a.mp3")
    keys = path_lookup_keys(raw, root)
    assert isinstance(keys, tuple)
    assert all(isinstance(k, str) for k in keys)
    assert len(keys) == len(set(keys)), "duplicate lookup keys"
    assert keys == path_lookup_keys(raw, root), "order must be deterministic"


def test_lookup_keys_expanduser_form(root):
    keys = path_lookup_keys("~/staging/a.mp3", root)
    assert os.path.expanduser("~/staging/a.mp3") in keys


def test_lookup_keys_resolve_symlinked_spelling(root, tmp_path):
    real = root / "rekordbox" / "Collection" / "real.mp3"
    real.write_bytes(b"x")
    link_dir = tmp_path / "link"
    link_dir.symlink_to(root / "rekordbox" / "Collection")
    via_link = link_dir / "real.mp3"

    keys = path_lookup_keys(via_link, root)
    assert str(real.resolve()) in keys
    assert set(keys) & set(path_lookup_keys(real, root))


# --- canonical_key / paths_equal -----------------------------------------------


def test_volume_relative_and_absolute_are_equal_and_hash_equal(root):
    rel = "/Music SSD/rekordbox/Collection/a.mp3"
    abs_ = str(root / "rekordbox" / "Collection" / "a.mp3")
    assert canonical_key(rel, root) == canonical_key(abs_, root)
    assert hash(canonical_key(rel, root)) == hash(canonical_key(abs_, root))
    assert paths_equal(rel, abs_, root) is True
    assert paths_equal(abs_, rel, root) is True  # both directions


def test_paths_equal_negative(root):
    a = "/Music SSD/rekordbox/Collection/a.mp3"
    b = "/Music SSD/rekordbox/Collection/b.mp3"
    assert paths_equal(a, b, root) is False


def test_paths_equal_outside_root_absolute_only(root):
    a = "/Users/dj/Downloads/track.mp3"
    assert paths_equal(a, a, root) is True
    assert paths_equal(a, "/Users/dj/Downloads/other.mp3", root) is False


def test_canonical_equality_resolves_symlink_for_missing_file(root, tmp_path):
    link = tmp_path / "collection-link"
    link.symlink_to(root / "rekordbox" / "Collection")
    through_link = link / "missing.mp3"
    canonical = root / "rekordbox" / "Collection" / "missing.mp3"
    assert paths_equal(through_link, canonical, root)


# --- ownership classification -------------------------------------------------


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        (("_syncbox", "events", "gig", "track.mp3"), "app_managed"),
        (("_syncbox", "inbox", "track.mp3"), "app_managed"),
        (("rekordbox", "Collection", "track.mp3"), "permanent_library"),
        (("_syncbox", "backups", "track.mp3"), "external"),
        (("_syncbox", "events-old", "track.mp3"), "external"),
        (("rekordbox-old", "track.mp3"), "external"),
        (("Downloads", "track.mp3"), "external"),
    ],
)
def test_classify_ownership_uses_exact_segments_for_missing_paths(
    root, relative, expected
):
    assert classify_ownership(root.joinpath(*relative), root) == expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("/Music SSD/_syncbox/events/gig/track.mp3", "app_managed"),
        ("/Music SSD/_syncbox/inbox/track.mp3", "app_managed"),
        ("/Music SSD/rekordbox/Collection/track.mp3", "permanent_library"),
        ("/Music SSD/_syncbox/backups/track.mp3", "external"),
    ],
)
def test_classify_ownership_accepts_volume_relative_paths(root, stored, expected):
    assert classify_ownership(stored, root) == expected


def test_classify_ownership_expands_user_for_missing_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    root = "~/Music SSD"
    path = "~/Music SSD/_syncbox/inbox/track.mp3"
    assert classify_ownership(path, root) == "app_managed"


def test_classify_ownership_canonicalizes_parent_traversal(root):
    disguised_backup = root / "_syncbox" / "events" / ".." / "backups" / "db"
    assert classify_ownership(disguised_backup, root) == "external"


def test_classify_ownership_follows_symlink_out_of_managed_area(root, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    events = root / "_syncbox" / "events"
    events.mkdir()
    (events / "linked").symlink_to(external)
    assert classify_ownership(events / "linked" / "track.mp3", root) == "external"


# --- tcc_exists (SPEC-UNIFIED 3.3, SPEC-01 1.5) ---------------------------------


def test_tcc_exists_never_lists_the_parent(monkeypatch, tmp_path):
    # TCC quirk: listing a cloud folder fails from a service while a direct
    # stat works. Simulate the failure mode by forbidding directory listing.
    target = tmp_path / "cloud" / "track.mp3"
    target.parent.mkdir()
    target.write_bytes(b"x")

    def forbidden(*args, **kwargs):
        raise AssertionError("parent directory listing is forbidden (TCC)")

    monkeypatch.setattr(os, "scandir", forbidden)
    monkeypatch.setattr(os, "listdir", forbidden)

    assert tcc_exists(target) is True
    assert tcc_exists(tmp_path / "cloud" / "missing.mp3") is False


def test_tcc_exists_issues_a_fresh_syscall_per_call(tmp_path):
    # No memoization: a file that appears between calls must be seen.
    target = tmp_path / "cloud" / "late.mp3"
    target.parent.mkdir()
    assert tcc_exists(target) is False
    target.write_bytes(b"x")
    assert tcc_exists(target) is True


def test_tcc_exists_expands_user():
    assert tcc_exists("~") is True
