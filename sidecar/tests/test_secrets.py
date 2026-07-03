"""Tests for the encrypted secrets store - unsigned path (SPEC-UNIFIED 6.7/3.6)."""

import stat

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
