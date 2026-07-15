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
