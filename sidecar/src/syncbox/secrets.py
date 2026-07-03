"""Secrets at rest - unsigned-build path (SPEC-UNIFIED 6.7, POC #1 deferred).

Only Spotify OAuth tokens exist as secrets in v1 (6.5: no provider
credential of any kind). They are never written in cleartext to the
settings DB or exports (3.6).

# ponytail: sqlcipher3-encrypted store keyed by a per-install random key
# file (0600) in the app data dir. This is the documented unsigned-path
# tradeoff (research 07: unsigned PyInstaller binaries get Keychain
# errSecInteractionNotAllowed -25308, and unstable code identities
# invalidate Keychain ACLs on every release). The key never leaves the
# machine; the protection is at-rest hygiene, not defense against a local
# attacker with the user's account. Upgrade path: keyring/Keychain +
# migrate-and-purge once a stable Developer ID exists (M5 / POC #1 exit).
"""

import os
from pathlib import Path

import sqlcipher3


class SecretsStore:
    def __init__(self, data_dir):
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self._key_path = data_dir / "secrets.key"
        self._db_path = data_dir / "secrets.db"
        self._conn = None

    def _key(self) -> str:
        if not self._key_path.is_file():
            fd = os.open(self._key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(os.urandom(32).hex())
        return self._key_path.read_text().strip()

    def _connect(self):
        if self._conn is None:
            # check_same_thread=False for the same reason as appdb.connect:
            # every HTTP handler runs in a threadpool worker, all serialized
            # behind ONE lock (api.Deps.lock), so the connection is handed
            # between threads but never used concurrently. Without it the
            # SECOND request from a different worker thread dies with
            # ProgrammingError -> 500 (found live through GET /api/status).
            conn = sqlcipher3.connect(str(self._db_path), check_same_thread=False)
            # Raw-key form: PRAGMA key = "x'<64 hex>'" (no KDF passphrase).
            conn.execute(f"PRAGMA key = \"x'{self._key()}'\"")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS secret (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.commit()
            self._conn = conn
        return self._conn

    def get(self, name: str) -> str | None:
        row = self._connect().execute(
            "SELECT value FROM secret WHERE name = ?", (name,)
        ).fetchone()
        return row[0] if row else None

    def set(self, name: str, value: str) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO secret (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (name, value),
        )
        conn.commit()

    def delete(self, name: str) -> None:
        conn = self._connect()
        conn.execute("DELETE FROM secret WHERE name = ?", (name,))
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
