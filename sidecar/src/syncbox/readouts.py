"""Dashboard collection readouts - pure aggregates over the snapshot rows
(SPEC-UNIFIED 11.3). Zero audio analysis, zero persistence, zero engine;
the quality readout speaks the QualityBadge vocabulary, never a binary red
"low quality" counter (rejected by 11.3).
"""

import re
from collections import Counter
from datetime import datetime

# Static musical-notation -> Camelot map (+ enharmonics). Values already in
# Camelot form ("8A", Mixed In Key tags) pass through; unmapped -> excluded
# from the percentage (11.3).
_CAMELOT = {
    "abm": "1A", "g#m": "1A", "b": "1B",
    "ebm": "2A", "d#m": "2A", "f#": "2B", "gb": "2B",
    "bbm": "3A", "a#m": "3A", "db": "3B", "c#": "3B",
    "fm": "4A", "ab": "4B", "g#": "4B",
    "cm": "5A", "eb": "5B", "d#": "5B",
    "gm": "6A", "bb": "6B", "a#": "6B",
    "dm": "7A", "f": "7B",
    "am": "8A", "c": "8B",
    "em": "9A", "g": "9B",
    "bm": "10A", "d": "10B",
    "f#m": "11A", "gbm": "11A", "a": "11B",
    "c#m": "12A", "dbm": "12A", "e": "12B",
}
_CAMELOT_FORM = re.compile(r"^(1[0-2]|[1-9])[AB]$")


def to_camelot(scale_name) -> str | None:
    if not scale_name:
        return None
    raw = str(scale_name).strip()
    if _CAMELOT_FORM.match(raw.upper()):
        return raw.upper()
    return _CAMELOT.get(raw.lower().replace(" ", ""))


def keys_analyzed(rows) -> dict:
    """Passive readout: share of tracks with a Camelot-mappable key. The
    ACTIVE harmonic set-prep feature stays excluded from v1 (7.4)."""
    total = len(rows)
    mapped = sum(1 for r in rows if to_camelot(r.get("key_name")))
    return {
        "total": total,
        "analyzed": mapped,
        "pct": round(100 * mapped / total) if total else 0,
    }


def never_played(rows) -> int:
    """DJPlayCount NULL/0 - Rekordbox's own semantics (un-reimported CDJ
    plays do not count; assumed, not a bug - 11.3)."""
    return sum(1 for r in rows if not _as_int(r.get("play_count")))


def added_this_month(rows, now: datetime) -> dict:
    added = 0
    latest = None
    for row in rows:
        stamp = _as_datetime(row.get("date_created"))
        if stamp is None:
            continue
        if (stamp.year, stamp.month) == (now.year, now.month):
            added += 1
        if latest is None or stamp > latest:
            latest = stamp
    return {"added_this_month": added, "last_import": latest.isoformat() if latest else None}


def genre_distribution(rows, top: int = 8) -> list[dict]:
    counts = Counter(r.get("genre") for r in rows if r.get("genre"))
    return [{"genre": g, "count": c} for g, c in counts.most_common(top)]


def quality_readout(rows) -> dict:
    """QualityBadge-aligned aggregate (verdicts computed on demand by the
    dedup scan; absent verdict counts as neutral 'ok')."""
    counts = Counter(r.get("quality_verdict") or "ok" for r in rows)
    return {
        "lossy_source_probable": counts.get("lossy_source_probable", 0),
        "incertain": counts.get("incertain", 0),
        "ok": counts.get("ok", 0),
    }


def _as_int(value):
    if value is None:
        return 0
    try:
        return int(value)  # pyrekordbox maps some int columns as VARCHAR
    except (TypeError, ValueError):
        return 0


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).split("+")[0].strip())
    except ValueError:
        return None
