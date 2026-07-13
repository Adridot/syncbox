"""Secrets at rest - unsigned-build path (SPEC-UNIFIED 6.7, POC #1 deferred).

Only Spotify OAuth tokens exist as secrets in v1 (6.5: no provider
credential of any kind). They are never written in cleartext to the
settings DB or exports (3.6).

The sqlcipher3 store is keyed by a per-install random 0600 file in the app
data directory. Unsigned PyInstaller binaries have unstable code identities,
so Keychain migration remains deferred until a stable Developer ID exists.
The key never leaves the machine; this protects data at rest, not against a
local attacker using the same account.
"""

import os
import stat
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
        try:
            fd = os.open(
                self._key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as handle:
                handle.write(os.urandom(32).hex())
                handle.flush()
                os.fsync(handle.fileno())

        try:
            fd = os.open(
                self._key_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
        except OSError as exc:
            raise ValueError("secrets.key must be a regular owner-only file") from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("secrets.key must be a regular owner-only file")
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "r") as handle:
                fd = -1
                key = handle.read().strip()
        finally:
            if fd >= 0:
                os.close(fd)

        try:
            raw = bytes.fromhex(key)
        except ValueError as exc:
            raise ValueError("secrets.key is not a valid 32-byte key") from exc
        if len(raw) != 32:
            raise ValueError("secrets.key is not a valid 32-byte key")
        return raw.hex()

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
