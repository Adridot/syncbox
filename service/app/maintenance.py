"""Pure, pyrekordbox-free logic for the Rekordbox cleanup maintenance tool.

The cleanup tool prunes the Rekordbox collection of:
  * untagged junk (sound effects, speeches, built-in rekordbox samples, and
    phantom rows whose ``FolderPath`` is a ``spotify:track:`` URI with no file),
  * untagged tracks that duplicate a song already present *with tags* in the
    collection, and
  * extra/alternate versions of an untagged song (the cleanest "base" version
    is kept, the others are dropped).

Everything here operates on plain dataclasses so it can be unit-tested without
a real Rekordbox database. The script in ``scripts/cleanup_rekordbox.py`` is the
only place that talks to pyrekordbox.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


# --- input / output shapes -------------------------------------------------


@dataclass(frozen=True)
class TrackRow:
    """A minimal view of a Rekordbox ``DjmdContent`` row."""

    content_id: str
    artist: str
    title: str
    folder_path: str
    is_tagged: bool


# Reasons, ordered roughly by "how obviously safe to delete".
REASON_JUNK = "junk"
REASON_DUP_OF_TAGGED = "dup_of_tagged"
REASON_ALT_VERSION = "alt_version"
REASON_UNIQUE_MAINSTREAM = "unique_mainstream"

ACTION_DELETE = "delete"
ACTION_KEEP = "keep"


@dataclass(frozen=True)
class CleanupDecision:
    content_id: str
    artist: str
    title: str
    folder_path: str
    action: str
    reason: str
    matched_tagged_title: str = ""


# --- normalization ---------------------------------------------------------


_VERSION_QUALIFIERS = re.compile(
    r"\b("
    r"radio edit|extended|remaster|remastered|remasterise|single version|"
    r"original|live|feat|featuring|version|mix|remix|edit|digitally|"
    r"anniversaire|pt|part"
    r")\b"
)


def strip_accents(value: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", value)
        if unicodedata.category(ch) != "Mn"
    )


def normalize_title(title: str) -> str:
    text = strip_accents(title.lower())
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)  # drop parentheticals
    text = re.sub(r"feat.*$", " ", text)  # drop trailing "feat ..."
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = _VERSION_QUALIFIERS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_artist(artist: str) -> str:
    text = strip_accents(artist.lower())
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    tokens = text.split()
    return tokens[0] if tokens else ""


def song_key(artist: str, title: str) -> tuple[str, str]:
    return (normalize_artist(artist), normalize_title(title))


# --- junk detection --------------------------------------------------------


_JUNK_TITLE_PATTERNS = re.compile(
    r"\(\d+\s*s\)"  # "(5s)", "(4s)" cue snippets
    r"|discours"
    r"|temoins"
    r"|^psg "
    r"|helico"
    r"|^bip "
    r"|reveil"
    r"|appareil photo"
    r"|bereal"
    r"|cash machine"
)


def is_junk(artist: str, title: str, folder_path: str) -> bool:
    if not folder_path.startswith("/"):
        # ``spotify:track:...`` placeholder rows have no real file on disk.
        return True
    artist_l = strip_accents(artist.lower()).strip()
    title_l = strip_accents(title.lower()).strip()
    if artist_l == "rekordbox":
        # Built-in rekordbox demo samples (Breaks/House/Techno).
        return True
    if not title_l:
        return True
    return bool(_JUNK_TITLE_PATTERNS.search(title_l))


# --- base-version selection ------------------------------------------------


def select_base_index(rows: list[TrackRow]) -> int:
    """Index of the "base" version to keep within a group of equivalent songs.

    Preference: fewest version qualifiers, then shortest title, then stable
    order (first seen). This keeps e.g. "L'Amour Toujours" over
    "L'Amour Toujours (Hardstyle Remix)".
    """

    def score(row: TrackRow) -> tuple[int, int]:
        lowered = strip_accents(row.title.lower())
        qualifier_hits = len(_VERSION_QUALIFIERS.findall(lowered))
        parenthetical = 1 if re.search(r"[\(\[]", row.title) else 0
        return (qualifier_hits + parenthetical, len(row.title))

    best = 0
    best_score = score(rows[0])
    for index in range(1, len(rows)):
        candidate = score(rows[index])
        if candidate < best_score:
            best_score = candidate
            best = index
    return best


# --- classification --------------------------------------------------------


def classify_untagged(
    tagged: Iterable[TrackRow],
    untagged: Iterable[TrackRow],
) -> list[CleanupDecision]:
    """Decide what to do with each untagged track.

    * junk -> delete
    * a tagged track shares the same ``song_key`` -> delete (dup_of_tagged)
    * otherwise group remaining untagged by ``song_key``; keep one base version
      (unique_mainstream) and delete the rest (alt_version).
    """

    tagged_titles: dict[tuple[str, str], str] = {}
    for row in tagged:
        tagged_titles.setdefault(song_key(row.artist, row.title), row.title)

    decisions: list[CleanupDecision] = []
    groups: dict[tuple[str, str], list[TrackRow]] = defaultdict(list)

    for row in untagged:
        if is_junk(row.artist, row.title, row.folder_path):
            decisions.append(
                CleanupDecision(
                    content_id=row.content_id,
                    artist=row.artist,
                    title=row.title,
                    folder_path=row.folder_path,
                    action=ACTION_DELETE,
                    reason=REASON_JUNK,
                )
            )
            continue
        groups[song_key(row.artist, row.title)].append(row)

    for key, rows in groups.items():
        matched_tagged = tagged_titles.get(key)
        if matched_tagged is not None:
            for row in rows:
                decisions.append(
                    CleanupDecision(
                        content_id=row.content_id,
                        artist=row.artist,
                        title=row.title,
                        folder_path=row.folder_path,
                        action=ACTION_DELETE,
                        reason=REASON_DUP_OF_TAGGED,
                        matched_tagged_title=matched_tagged,
                    )
                )
            continue

        base = select_base_index(rows)
        for index, row in enumerate(rows):
            if index == base:
                decisions.append(
                    CleanupDecision(
                        content_id=row.content_id,
                        artist=row.artist,
                        title=row.title,
                        folder_path=row.folder_path,
                        action=ACTION_KEEP,
                        reason=REASON_UNIQUE_MAINSTREAM,
                    )
                )
            else:
                decisions.append(
                    CleanupDecision(
                        content_id=row.content_id,
                        artist=row.artist,
                        title=row.title,
                        folder_path=row.folder_path,
                        action=ACTION_DELETE,
                        reason=REASON_ALT_VERSION,
                    )
                )

    return decisions


def summarize(decisions: Iterable[CleanupDecision]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for decision in decisions:
        counts[decision.reason] += 1
        counts[decision.action] += 1
    return dict(counts)
