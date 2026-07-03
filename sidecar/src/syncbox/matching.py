"""Spotify -> Rekordbox matching: ISRC first, then fuzzy
(SPEC-UNIFIED 5.3, SPEC-01 2.1 - constants are load-bearing).

D19: normalize() below is THE one normalization pipeline, shared by
matching, dedup and the B2 purchase-link builder. Never fork a variant.
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

# SPEC-01 2.1 constants - the exact values are the contract.
WEIGHT_TITLE = 0.52
WEIGHT_ARTIST = 0.36
WEIGHT_DURATION = 0.12
MIN_CONFIDENCE = 82
AMBIGUITY_MARGIN = 6
ISRC_DURATION_GUARD_MS = 15000
ISRC_TITLE_GUARD = 82

_PARENS = re.compile(r"[(\[][^)\]]*[)\]]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str | None) -> str:
    """D19 single pipeline: NFKD -> ASCII, lowercase, parenthesized/bracketed
    content removed, & -> and, non-alphanumeric -> space, collapsed."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = text.lower()
    text = _PARENS.sub(" ", text)
    text = text.replace("&", " and ")
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


def similarity(a: str | None, b: str | None) -> float:
    """token_sort_ratio over normalized inputs, 0-100."""
    return fuzz.token_sort_ratio(normalize(a), normalize(b))


def duration_score(delta_ms: int) -> int:
    """SPEC-01 2.1 buckets: <=1500 -> 100, <=5000 -> 80, <=12000 -> 55, else 0."""
    delta_ms = abs(delta_ms)
    if delta_ms <= 1500:
        return 100
    if delta_ms <= 5000:
        return 80
    if delta_ms <= 12000:
        return 55
    return 0


@dataclass(frozen=True)
class MatchResult:
    status: str  # matched | ambiguous | missing
    content_id: str | None
    method: str | None  # isrc | fuzzy | None
    confidence: int


def _isrc(value: str | None) -> str:
    return (value or "").strip().upper()


def _isrc_collision(spotify_track, candidate) -> bool:
    """ISRC match is rejected ONLY when BOTH duration and title disagree
    (SPEC-01 2.1). Missing duration (0/None) -> blind trust in the ISRC."""
    sp_ms = spotify_track.get("duration_ms") or 0
    rb_ms = candidate.get("duration_ms") or 0
    if not sp_ms or not rb_ms:
        return False
    if abs(sp_ms - rb_ms) <= ISRC_DURATION_GUARD_MS:
        return False
    return similarity(spotify_track.get("title"), candidate.get("title")) < ISRC_TITLE_GUARD


def fuzzy_confidence(spotify_track, candidate) -> int:
    title = similarity(spotify_track.get("title"), candidate.get("title"))
    artist = similarity(spotify_track.get("artist"), candidate.get("artist"))
    sp_ms = spotify_track.get("duration_ms") or 0
    rb_ms = candidate.get("duration_ms") or 0
    duration = duration_score(sp_ms - rb_ms) if sp_ms and rb_ms else 0
    return round(
        title * WEIGHT_TITLE + artist * WEIGHT_ARTIST + duration * WEIGHT_DURATION
    )


def match(
    spotify_track: dict,
    candidates: list[dict],
    *,
    min_confidence: int = MIN_CONFIDENCE,
    ambiguity_margin: int = AMBIGUITY_MARGIN,
) -> MatchResult:
    """Match one Spotify track against Rekordbox snapshot candidates.

    Candidate dicts carry: content_id, title, artist, duration_ms, isrc.
    Thresholds are parameters because SPEC-DESIGN 4 exposes them in
    Settings > Advanced; the ALGORITHM (ISRC-first, D19 pipeline, buckets)
    is locked and not configurable.
    """
    # --- ISRC exact first (uppercase compare) --------------------------------
    wanted = _isrc(spotify_track.get("isrc"))
    if wanted:
        for candidate in candidates:
            if _isrc(candidate.get("isrc")) == wanted and not _isrc_collision(
                spotify_track, candidate
            ):
                return MatchResult("matched", candidate["content_id"], "isrc", 100)

    # --- fuzzy ---------------------------------------------------------------
    scored = sorted(
        ((fuzzy_confidence(spotify_track, c), c) for c in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not scored or scored[0][0] < min_confidence:
        return MatchResult("missing", None, None, 0)
    best_score, best = scored[0]
    if len(scored) > 1 and (best_score - scored[1][0]) < ambiguity_margin:
        # Ambiguous still returns the best content_id (SPEC-01 2.1).
        return MatchResult("ambiguous", best["content_id"], "fuzzy", best_score)
    return MatchResult("matched", best["content_id"], "fuzzy", best_score)
