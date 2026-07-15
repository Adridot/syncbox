"""Tests for the encrypted secrets store - unsigned path (SPEC-UNIFIED 6.7/3.6)."""

import stat

import pytest

from syncbox.secrets import SecretsStore

TOKEN = "spotify-refresh-token-EXTREMELY-SECRET-0123456789"


def test_round_trip_and_delete(tmp_path):
    store = SecretsStore(tmp_path)
    assert store.get("spotify.refresh_token") is None
    store.set("spotify.refresh_token", TOKEN)
    assert store.get("spotify.refresh_token") == TOKEN
    store.set("spotify.refresh_token", "rotated")
    assert store.get("spotify.refresh_token") == "rotated"
    store.delete("spotify.refresh_token")
    assert store.get("spotify.refresh_token") is None


def test_key_file_is_0600_hex(tmp_path):
    store = SecretsStore(tmp_path)
    store.set("s", "v")
    key_file = tmp_path / "secrets.key"
    assert key_file.is_file()
    mode = stat.S_IMODE(key_file.stat().st_mode)
    assert mode == 0o600
    key = key_file.read_text().strip()
    assert len(key) == 64
    int(key, 16)  # raises if not hex


def test_secret_never_in_cleartext_on_disk(tmp_path):
    # SPEC-UNIFIED 3.6: tokens are never written in cleartext. The sqlcipher
    # db file must not contain the token bytes.
    store = SecretsStore(tmp_path)
    store.set("spotify.refresh_token", TOKEN)
    store.close()
    raw = (tmp_path / "secrets.db").read_bytes()
    assert TOKEN.encode() not in raw
    assert b"refresh_token" not in raw  # even names are not readable


def test_persistence_across_instances(tmp_path):
    first = SecretsStore(tmp_path)
    first.set("s", "v")
    first.close()
    second = SecretsStore(tmp_path)
    assert second.get("s") == "v"
    second.close()


def test_existing_key_reused_not_rotated(tmp_path):
    first = SecretsStore(tmp_path)
    first.set("s", "v")
    first.close()
    key_before = (tmp_path / "secrets.key").read_text()
    second = SecretsStore(tmp_path)
    assert second.get("s") == "v"
    assert (tmp_path / "secrets.key").read_text() == key_before


def test_existing_key_permissions_are_hardened_to_0600(tmp_path):
    key_file = tmp_path / "secrets.key"
    key_file.write_text("ab" * 32)
    key_file.chmod(0o644)
    store = SecretsStore(tmp_path)
    store.set("s", "v")
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600


def test_symlink_and_invalid_existing_keys_are_rejected(tmp_path):
    target = tmp_path / "target.key"
    target.write_text("ab" * 32)
    (tmp_path / "secrets.key").symlink_to(target)
    with pytest.raises(ValueError, match="regular owner-only file"):
        SecretsStore(tmp_path).set("s", "v")

    (tmp_path / "secrets.key").unlink()
    (tmp_path / "secrets.key").write_text("not-a-key")
    with pytest.raises(ValueError, match="valid 32-byte key"):
        SecretsStore(tmp_path).set("s", "v")

    (tmp_path / "secrets.key").write_text("ab " * 32)
    store = SecretsStore(tmp_path)
    assert store._key() == "ab" * 32
    store.set("s", "v")
    assert store.get("s") == "v"


def test_store_survives_cross_thread_access(tmp_path):
    """The HTTP layer hands the store between threadpool workers (serialized
    behind api.Deps.lock). sqlite refuses cross-thread use unless the
    connection opts out - a regression here 500s GET /api/status."""
    import threading

    store = SecretsStore(tmp_path)
    store.set("spotify.refresh_token", "tok")  # connection born on this thread

    results = []

    def read():
        results.append(store.get("spotify.refresh_token"))

    worker = threading.Thread(target=read)
    worker.start()
    worker.join()
    assert results == ["tok"]
