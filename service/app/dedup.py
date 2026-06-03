"""Pure duplicate-detection logic for the Rekordbox collection.

No Rekordbox-DB coupling: every function here operates on plain dicts (the
"dedup snapshot" the adapter builds) so the whole detection/keeper/plan flow is
trivially unit-testable. The adapter feeds these functions and applies the
resulting plan against pyrekordbox.

Two detection strategies (confidence ladder):
  * ``isrc``  — two tracks share a non-empty ISRC -> same recording (high
    confidence). This is the signal Rekordbox's native "duplicate" ignores.
  * ``fuzzy`` — normalized "artist title" similarity above a threshold AND
    compatible durations (lower confidence, surfaced for review).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# Parenthetical / bracketed noise that does not change the recording identity
# for fuzzy matching ("(feat. X)", "- Radio Edit", "(2011 Remaster)"...).
_NOISE_WORDS = (
    "feat",
    "ft",
    "featuring",
    "remaster",
    "remastered",
    "radio edit",
    "radio mix",
    "extended",
    "extended mix",
    "original mix",
    "club mix",
    "original",
    "version",
    "edit",
    "mix",
    "bonus",
    "bonus track",
    "deluxe",
    "mono",
    "stereo",
    "remix",
    "live",
    "explicit",
    "clean",
)

_PAREN_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_FEAT_RE = re.compile(r"\b(feat|ft|featuring)\b.*$", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_WS_RE = re.compile(r"\s+")


# Ligatures NFKD does not split on its own.
_LIGATURES = {"œ": "oe", "æ": "ae", "ß": "ss", "ø": "o", "đ": "d", "ł": "l"}


def strip_accents(text: str) -> str:
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst).replace(src.upper(), dst)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _drop_noise_parentheticals(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        inner = match.group(0).strip("()[]{} ").lower()
        for word in _NOISE_WORDS:
            if word in inner:
                return " "
        return match.group(0)

    return _PAREN_RE.sub(repl, text)


def normalize_title(title: str) -> str:
    text = strip_accents(str(title or "")).lower()
    text = _drop_noise_parentheticals(text)
    text = text.replace("&", " and ")
    # Drop a trailing "- radio edit"/"- remaster" style suffix.
    if " - " in text:
        head, _, tail = text.partition(" - ")
        if any(word in tail for word in _NOISE_WORDS):
            text = head
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_artist(artist: str) -> str:
    text = strip_accents(str(artist or "")).lower()
    text = _FEAT_RE.sub("", text)
    text = text.replace("&", " and ").replace(",", " ")
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def fuzzy_signature(track: dict[str, Any]) -> str:
    return f"{normalize_artist(track.get('artist', ''))} {normalize_title(track.get('title', ''))}".strip()


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Keeper scoring
# ---------------------------------------------------------------------------

_LOSSLESS = {"FLAC", "ALAC", "AIFF", "AIF", "WAV", "AAC_LOSSLESS"}


def quality_score(track: dict[str, Any]) -> float:
    """Heuristic "how good a copy is this" score. Higher = better keeper.

    Combines audio quality (format, bitrate, sample/bit depth, size) with the
    work already invested (analysis, cues, playlist memberships, tags, rating)
    and a strong preference for a copy living in a protected (permanent/manual)
    root. A missing file is heavily penalised so an existing alternative wins.
    """
    score = 0.0

    file_type = str(track.get("fileType") or "").upper()
    if file_type in _LOSSLESS:
        score += 300.0

    score += _as_float(track.get("bitRate")) / 10.0
    score += _as_float(track.get("sampleRate")) / 1000.0
    score += _as_float(track.get("bitDepth")) * 5.0
    score += _as_float(track.get("fileSize")) / 1_000_000.0  # ~1 pt per MB

    if track.get("analysed"):
        score += 50.0
    if _as_float(track.get("bpm")) > 0:
        score += 20.0
    score += _as_int(track.get("cueCount")) * 10.0
    score += _as_int(track.get("playlistCount")) * 15.0
    score += _as_int(track.get("tagCount")) * 8.0
    score += _as_int(track.get("rating")) * 5.0

    if track.get("protected"):
        score += 500.0
    if track.get("fileMissing"):
        score -= 1000.0

    return round(score, 3)


def pick_keeper(tracks: list[dict[str, Any]]) -> str:
    """Return the contentId of the best copy to keep in a group."""
    best = max(
        tracks,
        key=lambda t: (
            quality_score(t),
            # Tie-breakers: prefer the oldest (most established) entry, then id.
            _date_sort_key(t.get("dateCreated")),
            str(t.get("contentId", "")),
        ),
    )
    return str(best.get("contentId", ""))


def _date_sort_key(value: Any) -> str:
    # Earlier dates sort first; we want the OLDEST as keeper tie-break, so
    # invert by returning a key that makes "max" pick the smallest date.
    text = str(value or "9999-99-99")
    return "".join(chr(255 - ord(c)) if c.isdigit() else c for c in text)


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def dismissed_key(content_ids: Iterable[str]) -> str:
    """Canonical, order-independent key for a set of duplicate contentIds."""
    return "|".join(sorted({str(cid) for cid in content_ids}))


def find_duplicate_groups(
    tracks: list[dict[str, Any]],
    *,
    strategies: list[str],
    fuzzy_threshold: float = 0.87,
    duration_tolerance_ms: int = 2000,
    dismissed: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Cluster ``tracks`` into duplicate groups.

    Returns a list of group dicts: ``{groupId, reason, confidence, tracks}``.
    ``reason`` is "isrc" when every pairing in the group shares an ISRC, else
    "fuzzy". Groups whose canonical key is in ``dismissed`` are dropped.
    """
    dismissed = dismissed or set()
    by_id = {str(t.get("contentId")): t for t in tracks}
    parent: dict[str, str] = {cid: cid for cid in by_id}
    reasons: dict[frozenset[str], str] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str, reason: str) -> None:
        ra, rb = find(a), find(b)
        reasons[frozenset((a, b))] = reason
        if ra != rb:
            parent[rb] = ra

    # --- ISRC strategy: O(n) bucketing by normalized ISRC --------------------
    if "isrc" in strategies:
        isrc_buckets: dict[str, list[str]] = {}
        for cid, track in by_id.items():
            isrc = str(track.get("isrc") or "").strip().upper()
            if isrc:
                isrc_buckets.setdefault(isrc, []).append(cid)
        for members in isrc_buckets.values():
            for other in members[1:]:
                union(members[0], other, "isrc")

    # --- Fuzzy strategy: bucket by rounded duration to cut comparisons -------
    if "fuzzy" in strategies:
        bucket_ms = max(duration_tolerance_ms, 1000)
        duration_buckets: dict[int, list[str]] = {}
        no_duration: list[str] = []
        for cid, track in by_id.items():
            dur = track.get("durationMs")
            if dur in (None, ""):
                no_duration.append(cid)
            else:
                duration_buckets.setdefault(int(_as_float(dur) // bucket_ms), []).append(cid)

        signatures = {cid: fuzzy_signature(track) for cid, track in by_id.items()}

        def maybe_pair(a: str, b: str) -> None:
            sig_a, sig_b = signatures[a], signatures[b]
            if not sig_a or not sig_b:
                return
            dur_a = by_id[a].get("durationMs")
            dur_b = by_id[b].get("durationMs")
            both_known = dur_a not in (None, "") and dur_b not in (None, "")
            if both_known and abs(_as_float(dur_a) - _as_float(dur_b)) > duration_tolerance_ms:
                return
            threshold = fuzzy_threshold if both_known else max(fuzzy_threshold, 0.93)
            if _ratio(sig_a, sig_b) >= threshold:
                union(a, b, "fuzzy")

        # Compare within each duration bucket and its right neighbour (so a pair
        # straddling a bucket boundary is still caught).
        sorted_keys = sorted(duration_buckets)
        for key in sorted_keys:
            members = duration_buckets[key] + duration_buckets.get(key + 1, [])
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    maybe_pair(members[i], members[j])
        # Tracks with no duration: compare against everything (rare).
        all_ids = list(by_id)
        for a in no_duration:
            for b in all_ids:
                if a != b:
                    maybe_pair(a, b)

    # --- Materialise clusters ------------------------------------------------
    clusters: dict[str, list[str]] = {}
    for cid in by_id:
        clusters.setdefault(find(cid), []).append(cid)

    groups: list[dict[str, Any]] = []
    for member_ids in clusters.values():
        if len(member_ids) < 2:
            continue
        if dismissed_key(member_ids) in dismissed:
            continue
        group_tracks = [by_id[cid] for cid in member_ids]
        all_isrc = _group_all_isrc(member_ids, reasons, parent, find)
        reason = "isrc" if all_isrc else "fuzzy"
        note: str | None = None
        if all_isrc:
            # ISRC is the recording id, but bootleg / tribute MP3s sometimes
            # carry a wrong or shared ISRC across genuinely different songs.
            # When titles inside an ISRC cluster disagree, downgrade confidence
            # and flag it so the UI warns and the bulk action skips it.
            if _titles_consistent(group_tracks):
                confidence = 99
            else:
                confidence = 60
                note = "Same ISRC but titles differ — the source tags may be wrong. Review before removing."
        else:
            confidence = 80
        keeper = pick_keeper(group_tracks)
        for track in group_tracks:
            track["qualityScore"] = quality_score(track)
            track["isKeeper"] = str(track.get("contentId")) == keeper
        group_tracks.sort(key=lambda t: (not t["isKeeper"], -t["qualityScore"]))
        groups.append(
            {
                "groupId": dismissed_key(member_ids),
                "reason": reason,
                "confidence": confidence,
                "note": note,
                "keeperContentId": keeper,
                "tracks": group_tracks,
            }
        )

    # Highest-confidence, biggest groups first.
    groups.sort(key=lambda g: (-g["confidence"], -len(g["tracks"])))
    return groups


def _titles_consistent(group_tracks: list[dict[str, Any]], *, min_ratio: float = 0.5) -> bool:
    """True if the normalized titles inside a group are mutually similar.

    Used to distinguish a genuine ISRC duplicate (titles agree up to casing /
    accents / "feat." noise) from a mis-tagged ISRC shared across different
    songs (titles wildly disagree).
    """
    titles = [normalize_title(t.get("title", "")) for t in group_tracks]
    titles = [t for t in titles if t]
    if len(titles) < 2:
        return True
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            a, b = titles[i], titles[j]
            # A containment match (one title inside the other) counts as
            # consistent, e.g. "thank god" vs "thank god radio".
            if a in b or b in a:
                continue
            if _ratio(a, b) < min_ratio:
                return False
    return True


def _group_all_isrc(
    member_ids: list[str],
    reasons: dict[frozenset[str], str],
    parent: dict[str, str],
    find: Any,
) -> bool:
    """True if every recorded pairing reason inside this cluster is 'isrc'."""
    root = find(member_ids[0])
    relevant = [
        reason
        for pair, reason in reasons.items()
        if all(find(cid) == root for cid in pair)
    ]
    return bool(relevant) and all(reason == "isrc" for reason in relevant)


# ---------------------------------------------------------------------------
# Resolution planning
# ---------------------------------------------------------------------------


def build_resolution_plan(
    group_tracks_by_id: dict[str, dict[str, Any]],
    *,
    keeper_content_id: str,
    remove_content_ids: list[str],
    allow_file_delete: bool,
) -> dict[str, Any]:
    """Decide, for one group, what is removed, what files may be deleted on
    disk, and what is skipped because it is protected.

    Never proposes deleting the keeper, and never proposes deleting a file that
    lives under a protected root (permanent/manual collection) — only its
    Rekordbox row is soft-deleted in that case.
    """
    remove: list[str] = []
    files_to_delete: list[str] = []
    skipped_protected: list[str] = []

    for content_id in remove_content_ids:
        content_id = str(content_id)
        if content_id == str(keeper_content_id):
            continue
        track = group_tracks_by_id.get(content_id)
        if track is None:
            continue
        remove.append(content_id)
        if allow_file_delete and not track.get("fileMissing"):
            if track.get("protected"):
                skipped_protected.append(content_id)
            elif track.get("filePath"):
                files_to_delete.append(str(track["filePath"]))

    return {
        "keeper_content_id": str(keeper_content_id),
        "remove_content_ids": remove,
        "files_to_delete": files_to_delete,
        "skipped_protected": skipped_protected,
    }
