"""Smart Fixes (A1) - the FIXED catalog of structural metadata fixes and the
dry-run planner (SPEC-UNIFIED 5.11, safety properties proven in POC #9).

Pure module: no DB access. The runner that executes a plan goes through the
M1 mutate unit-of-work with the freshness fingerprint - there is no other
write path. Composition is deterministic (catalog order), idempotent (each
fix is a fixpoint), and the dry-run payload IS the exact mutate payload.

# ponytail: fixed catalog, no user rule engine in v1 (5.11). The naive
# all-caps casing fix stays OUT: POC #9 measured 13 legitimate all-caps
# stylizations (DAKITI, SNAP, #SELFIE...) on the real fixture that it would
# have overwritten. Add a casing fix only behind a proven-safe heuristic.
"""

import re
import unicodedata

_URL = re.compile(
    r"\s*[-|(\[]*\s*(?:https?://|www\.)[^\s)\]]+[)\]]?\s*$", re.IGNORECASE
)
_WHITESPACE = re.compile(r"\s+")
_MOJIBAKE_MARKERS = ("Ã", "â€", "Â")


def strip_trailing_url(value: str) -> str:
    """Remove trailing site junk: 'Title - www.dj-leaks.example' -> 'Title'."""
    return _URL.sub("", value).rstrip(" -|")


def collapse_whitespace(value: str) -> str:
    """NBSP and friends to space, runs collapsed, ends trimmed."""
    cleaned = "".join(
        " " if unicodedata.category(ch) == "Zs" else ch for ch in value
    )
    return _WHITESPACE.sub(" ", cleaned).strip()


def fix_mojibake(value: str) -> str:
    """Repair UTF-8-read-as-latin1 ('Ã©' -> 'é') - only when the reverse
    round-trip succeeds AND the input shows typical mojibake markers; never
    a blind re-decode."""
    if not any(marker in value for marker in _MOJIBAKE_MARKERS):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired


# Deterministic order is load-bearing (5.11/POC #9): URL junk must go before
# whitespace collapsing so the leftover separator is trimmed too.
TITLE_FIXES = [
    ("fix_mojibake", fix_mojibake),
    ("strip_trailing_url", strip_trailing_url),
    ("collapse_whitespace", collapse_whitespace),
]
ARTIST_FIXES = [
    ("fix_mojibake", fix_mojibake),
    ("collapse_whitespace", collapse_whitespace),
]
CATALOG = {"title": TITLE_FIXES, "artist": ARTIST_FIXES}


def compose(field: str, value: str | None) -> str | None:
    """The composed FINAL result for one field (single previewed outcome)."""
    if value is None:
        return None
    result = value
    for _name, fn in CATALOG[field]:
        result = fn(result)
    return result


def plan(rows: list[dict], *, include_protected_ids=frozenset()):
    """Build the exact dry-run payload.

    rows: {content_id, title, artist, protected, display_name?}.
    Returns (payload, skipped_protected):
    - payload: [{content_id, field, before, after}] - no no-op entries;
    - skipped_protected: protected tracks WITH pending diffs, enumerated by
      name for the dry-run listing (5.11). Protected rows are mutated only
      when their id is in include_protected_ids - the per-call, never
      persisted opt-in.
    """
    payload = []
    skipped_protected = []
    for row in rows:
        diffs = []
        for field in CATALOG:
            before = row.get(field)
            after = compose(field, before)
            if after is not None and after != before:
                diffs.append(
                    {
                        "content_id": row["content_id"],
                        "field": field,
                        "before": before,
                        "after": after,
                    }
                )
        if not diffs:
            continue
        if row.get("protected") and row["content_id"] not in include_protected_ids:
            skipped_protected.append(
                {
                    "content_id": row["content_id"],
                    "name": row.get("display_name")
                    or f"{row.get('artist') or '?'} - {row.get('title') or '?'}",
                }
            )
            continue
        payload.extend(diffs)
    return payload, skipped_protected
