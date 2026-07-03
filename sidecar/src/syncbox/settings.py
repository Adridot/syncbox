"""Settings: ONE store, SQLite-backed, defaults applied at read
(SPEC-UNIFIED 5.10).

Rules that are load-bearing here:
- defaults are applied when READING, never written back at boot (a boot
  must not blank stored credentials - bug class B4/T5);
- a blank credential value in an update PRESERVES the stored value
  ("protection blank");
- OAuth tokens are NOT settings - they live in the encrypted SecretsStore
  (3.6); settings export therefore never contains a cleartext secret.
"""

import json
from pathlib import Path

DEFAULTS = {
    "spotify_client_id": "",
    "rekordbox_db_path": "",
    "storage_root": "",
    "backup_retention": 15,
    "language": "en",
}

# Blank-preserving keys: an empty incoming value means "leave as stored",
# because settings forms round-trip masked/empty credential fields.
CREDENTIAL_KEYS = frozenset({"spotify_client_id"})

# ponytail: the key catalog grows with M3/M4 (event folders, matching
# thresholds per SPEC-DESIGN 4); unknown keys are rejected so a typo cannot
# silently create a parallel setting.


class Settings:
    def __init__(self, conn):
        self._conn = conn

    def get(self, key: str):
        if key not in DEFAULTS:
            raise KeyError(key)
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return DEFAULTS[key]
        return json.loads(row[0])

    def all(self) -> dict:
        return {key: self.get(key) for key in DEFAULTS}

    def update(self, values: dict) -> dict:
        """Apply a partial update; returns the effective settings after it."""
        unknown = set(values) - set(DEFAULTS)
        if unknown:
            raise KeyError(f"unknown settings: {sorted(unknown)}")
        self._conn.execute("BEGIN")
        try:
            for key, value in values.items():
                if key in CREDENTIAL_KEYS and (value is None or value == ""):
                    continue  # blank credential preserves the stored value
                if not isinstance(value, type(DEFAULTS[key])):
                    raise TypeError(
                        f"setting {key!r} expects {type(DEFAULTS[key]).__name__}"
                    )
                self._conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)),
                )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return self.all()


def validate_directory(raw: str) -> tuple[bool, str]:
    """Path validation for the 4 configured folders (F15: validate them all)."""
    if not raw:
        return False, "empty"
    p = Path(raw).expanduser()
    if not p.is_absolute():
        return False, "not absolute"
    if not p.is_dir():
        return False, "not found"
    return True, "ok"
