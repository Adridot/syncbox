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
    "backup_retention": 20,
    "language": "en",
    # G4 matching knobs (SPEC-DESIGN 4): thresholds/weights/policy only -
    # the algorithm (ISRC-first, D19 pipeline, buckets) is locked. Defaults
    # mirror the SPEC-01 2.1 constants in matching.py; reset = PUT defaults.
    "match_confidence_threshold": 82,
    "match_ambiguity_margin": 6,
    "match_weights": {"title": 0.52, "artist": 0.36, "duration": 0.12},
    "isrc_collision_policy": "guarded",
    "deezer_acquisition_enabled": False,
}

ISRC_COLLISION_POLICIES = ("guarded", "trust_isrc", "strict")

# Blank-preserving keys: an empty incoming value means "leave as stored",
# because settings forms round-trip masked/empty credential fields.
CREDENTIAL_KEYS = frozenset({"spotify_client_id"})

# Unknown keys are rejected so a typo cannot silently create a parallel
# setting.


def _validate(key: str, value) -> None:
    """G4 value rules (trust boundary: PUT /api/settings)."""
    if key == "match_weights":
        if set(value) != {"title", "artist", "duration"}:
            raise ValueError(
                "match_weights needs exactly the keys title/artist/duration"
            )
        for weight in value.values():
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise ValueError("match_weights values must be numbers")
            if weight < 0:
                raise ValueError("match_weights values must be >= 0")
        if round(sum(value.values()), 2) != 1.0:
            raise ValueError("match_weights must sum to 1.00")
    elif key == "isrc_collision_policy" and value not in ISRC_COLLISION_POLICIES:
        raise ValueError(
            f"isrc_collision_policy must be one of {ISRC_COLLISION_POLICIES}"
        )
    elif key in ("match_confidence_threshold", "match_ambiguity_margin"):
        if not 0 <= value <= 100:
            raise ValueError(f"{key} must be between 0 and 100")


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
                _validate(key, value)
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
