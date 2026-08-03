"""Untagged categorization (SPEC-UNIFIED 5.8, SPEC-01 2.4, D7).

Four categories, sorted junk(0) < dup_of_tagged(1) < alt_version(2) <
review(3), then artist, then title. Junk detection uses UNIVERSAL
structural rules (spotify:track: stub, empty title, artist 'rekordbox')
plus user-configurable patterns - never personal/French-specific patterns
(D7). song_key keeps the FULL normalized artist (fix B5), and the feat
clause is cut non-greedily (fix B7).
"""

import re

from syncbox.matching import normalize
from syncbox.spotify import SPOTIFY_TRACK_PREFIX

CATEGORY_RANK = {"junk": 0, "dup_of_tagged": 1, "alt_version": 2, "review": 3}

# Non-greedy feat cut (B7): only the trailing feat clause goes, applied on
# the NORMALIZED title (parenthesized feats are already stripped by D19).
_FEAT = re.compile(r"\s+feat(?:uring)?\b.*$")


def song_key(artist, title) -> tuple[str, str]:
    """(full normalized artist, normalized title) - B5: never just the first
    artist token."""
    return normalize(artist), normalize(title)


def base_title(title) -> str:
    """Title with version/feat qualifiers removed, for alt-version grouping."""
    return _FEAT.sub("", normalize(title)).strip()


def is_junk(track, user_patterns=()) -> bool:
    title = (track.get("title") or "").strip()
    artist = (track.get("artist") or "").strip()
    if not title:
        return True
    if title.startswith(SPOTIFY_TRACK_PREFIX):
        return True
    if artist.lower() == "rekordbox":
        return True
    for pattern in user_patterns:
        if re.search(pattern, title, re.IGNORECASE) or re.search(
            pattern, artist, re.IGNORECASE
        ):
            return True
    return False


def categorize(
    untagged_tracks: list[dict], tagged_tracks: list[dict], user_patterns=()
) -> list[dict]:
    """Return [{**track, category}] sorted by (rank, artist, title)."""
    tagged_keys = {song_key(t.get("artist"), t.get("title")) for t in tagged_tracks}
    tagged_bases = {
        (normalize(t.get("artist")), base_title(t.get("title")))
        for t in tagged_tracks
    }

    out = []
    for track in untagged_tracks:
        key = song_key(track.get("artist"), track.get("title"))
        base = (key[0], base_title(track.get("title")))
        if is_junk(track, user_patterns):
            category = "junk"
        elif key in tagged_keys:
            category = "dup_of_tagged"
        elif base in tagged_bases:
            category = "alt_version"
        else:
            category = "review"
        out.append({**track, "category": category})

    out.sort(
        key=lambda t: (
            CATEGORY_RANK[t["category"]],
            normalize(t.get("artist")),
            normalize(t.get("title")),
        )
    )
    return out
