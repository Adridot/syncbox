from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz

from .models import RekordboxTrack, SpotifyTrack


BRACKETED_TEXT = re.compile(r"\s*[\[(].*?[\])]\s*")
NON_WORD = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class MatchResult:
    status: str
    method: str
    confidence: int
    spotify_track_id: str
    rekordbox_content_id: str | None = None
    reason: str = ""


@lru_cache(maxsize=8192)
def normalize_text(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    ascii_value = BRACKETED_TEXT.sub(" ", ascii_value.lower())
    ascii_value = ascii_value.replace("&", " and ")
    return NON_WORD.sub(" ", ascii_value).strip()


def text_similarity(left: str, right: str) -> int:
    if not left or not right:
        return 0
    # token_sort_ratio is word-order-insensitive, so "Artist - Title" still lines
    # up with "Title - Artist" and multi-artist orderings match; rapidfuzz's C++
    # implementation is also ~10-100x faster than difflib over a large candidate
    # set (the hot path when scoring a Spotify track against the whole collection).
    return round(fuzz.token_sort_ratio(normalize_text(left), normalize_text(right)))


def duration_score(left_ms: int | None, right_ms: int | None) -> int:
    if not left_ms or not right_ms:
        return 0
    delta = abs(left_ms - right_ms)
    if delta <= 1500:
        return 100
    if delta <= 5000:
        return 80
    if delta <= 12000:
        return 55
    return 0


# Two recordings can legitimately share an ISRC across releases, but a real
# ISRC match should still have a comparable runtime. A large gap means the ISRC
# is wrong/colliding (e.g. a different song tagged with the same code), so we
# refuse the blind ISRC match and fall back to metadata scoring.
ISRC_DURATION_TOLERANCE_MS = 15000
# ...unless the titles clearly match: same ISRC + same title but different length
# is just another edit/version of the same song (e.g. "Peña Baiona"), which we
# still want to link. Only a *title* mismatch + duration mismatch is a collision.
ISRC_TITLE_MATCH_THRESHOLD = 82


def isrc_durations_compatible(left_ms: int | None, right_ms: int | None) -> bool:
    if not left_ms or not right_ms:
        # Cannot verify — trust the ISRC.
        return True
    return abs(left_ms - right_ms) <= ISRC_DURATION_TOLERANCE_MS


def match_spotify_track(
    spotify_track: SpotifyTrack,
    candidates: list[RekordboxTrack],
    minimum_confidence: int = 82,
) -> MatchResult:
    if spotify_track.isrc:
        for candidate in candidates:
            if candidate.isrc and candidate.isrc.upper() == spotify_track.isrc.upper():
                if not isrc_durations_compatible(
                    spotify_track.duration_ms, candidate.duration_ms
                ) and text_similarity(spotify_track.title, candidate.title) < ISRC_TITLE_MATCH_THRESHOLD:
                    # ISRC collision: same code, very different runtime AND a
                    # different title -> a wrong code, not the same song. Skip and
                    # let metadata scoring decide. (Same title + different runtime
                    # is just another edit, so we keep the match.)
                    continue
                return MatchResult(
                    status="matched",
                    method="isrc",
                    confidence=100,
                    spotify_track_id=spotify_track.id,
                    rekordbox_content_id=candidate.content_id,
                    reason="ISRC matched exactly.",
                )

    ranked: list[tuple[int, RekordboxTrack]] = []
    spotify_artist = " ".join(spotify_track.artists)
    for candidate in candidates:
        title = text_similarity(spotify_track.title, candidate.title)
        artist = text_similarity(spotify_artist, candidate.artist)
        duration = duration_score(spotify_track.duration_ms, candidate.duration_ms)
        confidence = round(title * 0.52 + artist * 0.36 + duration * 0.12)
        ranked.append((confidence, candidate))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < minimum_confidence:
        return MatchResult(
            status="missing",
            method="none",
            confidence=0,
            spotify_track_id=spotify_track.id,
            reason="No confident Rekordbox match found.",
        )

    best_confidence, best_candidate = ranked[0]
    second_confidence = ranked[1][0] if len(ranked) > 1 else 0
    if best_confidence - second_confidence < 6:
        return MatchResult(
            status="ambiguous",
            method="metadata",
            confidence=best_confidence,
            spotify_track_id=spotify_track.id,
            rekordbox_content_id=best_candidate.content_id,
            reason="Top metadata matches are too close for automatic linking.",
        )

    return MatchResult(
        status="matched",
        method="metadata",
        confidence=best_confidence,
        spotify_track_id=spotify_track.id,
        rekordbox_content_id=best_candidate.content_id,
        reason="Title, artist, and duration matched.",
    )
