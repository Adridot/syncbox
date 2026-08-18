"""Tests for per-OS paths and the trash/consent contract (SPEC-UNIFIED 6.9)."""

import sys

import pytest

from syncbox import platform_os
from syncbox.platform_os import PermanentDeleteConsentRequired, delete_file


def test_app_data_dir_shape():
    d = platform_os.app_data_dir()
    if sys.platform == "darwin":
        assert d.parts[-3:] == ("Library", "Application Support", "Syncbox")
    assert d.name == "Syncbox"


def test_bundle_identifier_change_does_not_move_existing_state():
    # The macOS bundle identifier is owned by Tauri. Sidecar state has always
    # used the product directory, which must remain stable across that change.
    assert platform_os.APP_NAME == "Syncbox"
    assert "io.github.adridot.syncbox" not in str(platform_os.app_data_dir())


@pytest.fixture
def audio(tmp_path):
    f = tmp_path / "track.aiff"
    f.write_bytes(b"audio")
    return f


@pytest.fixture
def job_dir(tmp_path):
    directory = tmp_path / "job-7"
    (directory / "artwork").mkdir(parents=True)
    (directory / "track.aiff").write_bytes(b"audio")
    (directory / "artwork" / "cover.jpg").write_bytes(b"image")
    return directory


def test_trash_success(audio, monkeypatch):
    trashed = []
    monkeypatch.setattr(platform_os, "send2trash", trashed.append)
    assert delete_file(audio) == "trashed"
    assert trashed == [str(audio)]


def test_trash_failure_without_consent_deletes_nothing(audio, monkeypatch):
    def broken(path):
        raise OSError("The volume doesn't have a trash")  # send2trash#80 wording

    monkeypatch.setattr(platform_os, "send2trash", broken)
    with pytest.raises(PermanentDeleteConsentRequired) as info:
        delete_file(audio)
    assert audio.exists(), "no unlink may happen before consent"
    assert "permanent" in str(info.value)
    assert info.value.message_key == "safety.permanent_delete_consent"


def test_trash_failure_with_consent_deletes_permanently(audio, monkeypatch):
    def broken(path):
        raise OSError("no trash on this volume")

    monkeypatch.setattr(platform_os, "send2trash", broken)
    assert delete_file(audio, consent_to_permanent_delete=True) == "deleted_permanently"
    assert not audio.exists()


def test_consent_is_not_a_bypass_when_trash_works(audio, monkeypatch):
    # Consent given but the trash works: the file is trashed, not unlinked.
    trashed = []
    monkeypatch.setattr(platform_os, "send2trash", trashed.append)
    assert delete_file(audio, consent_to_permanent_delete=True) == "trashed"
    assert trashed and audio.exists()  # our fake did not really move it


def test_directory_trash_success(job_dir, monkeypatch):
    trashed = []
    monkeypatch.setattr(platform_os, "send2trash", trashed.append)
    assert delete_file(job_dir) == "trashed"
    assert trashed == [str(job_dir)]


def test_directory_trash_failure_without_consent_deletes_nothing(job_dir, monkeypatch):
    monkeypatch.setattr(
        platform_os,
        "send2trash",
        lambda path: (_ for _ in ()).throw(OSError("no trash")),
    )
    with pytest.raises(PermanentDeleteConsentRequired):
        delete_file(job_dir)
    assert (job_dir / "artwork" / "cover.jpg").is_file()


def test_directory_trash_failure_with_consent_deletes_recursively(job_dir, monkeypatch):
    monkeypatch.setattr(
        platform_os,
        "send2trash",
        lambda path: (_ for _ in ()).throw(OSError("no trash")),
    )
    assert (
        delete_file(job_dir, consent_to_permanent_delete=True)
        == "deleted_permanently"
    )
    assert not job_dir.exists()


def test_recursive_delete_failure_is_propagated(job_dir, monkeypatch):
    monkeypatch.setattr(
        platform_os,
        "send2trash",
        lambda path: (_ for _ in ()).throw(OSError("no trash")),
    )
    monkeypatch.setattr(
        platform_os.shutil,
        "rmtree",
        lambda path: (_ for _ in ()).throw(OSError("cannot remove directory")),
    )
    with pytest.raises(OSError, match="cannot remove directory"):
        delete_file(job_dir, consent_to_permanent_delete=True)
    assert job_dir.is_dir()


def test_permanent_delete_unlinks_a_symlink_without_following_it(
    audio, job_dir, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        platform_os,
        "send2trash",
        lambda path: (_ for _ in ()).throw(OSError("no trash")),
    )
    file_link = tmp_path / "link.aiff"
    file_link.symlink_to(audio)
    dir_link = tmp_path / "link-job"
    dir_link.symlink_to(job_dir)

    for link in (file_link, dir_link):
        assert delete_file(link, consent_to_permanent_delete=True) == (
            "deleted_permanently"
        )
        assert not link.exists() and not link.is_symlink()
    # The link went, never what it pointed at.
    assert audio.is_file() and (job_dir / "artwork" / "cover.jpg").is_file()
