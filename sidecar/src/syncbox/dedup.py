"""Duplicate detection and explainable keeper choice
(SPEC-UNIFIED 5.4, SPEC-01 2.2; A3 hook per 5.12).

Uses the D19 normalization pipeline from matching.py - never a local fork.
"""

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from syncbox.matching import normalize, similarity

ISRC_CONFIDENCE = 99
ISRC_DIVERGENT_CONFIDENCE = 60
FUZZY_CONFIDENCE = 80
FUZZY_THRESHOLD = 0.87
FUZZY_THRESHOLD_NO_DURATION = 0.93
DURATION_TOLERANCE_MS = 2000
TITLE_COHERENCE = 82  # same guard constant family as the ISRC collision check


@dataclass
class DuplicateGroup:
    key: str  # sorted content ids joined by '|'
    content_ids: list[str]
    confidence: int
    method: str  # isrc | fuzzy
    warning: bool = False  # divergent-title ISRC group: excluded from bulk
    reasons: dict = field(default_factory=dict)


def _group_key(content_ids) -> str:
    return "|".join(sorted(str(c) for c in content_ids))


def _signature(track) -> str:
    return f"{normalize(track.get('artist'))} {normalize(track.get('title'))}".strip()


class _UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def find_duplicate_groups(tracks: list[dict], dismissed: set[str] = frozenset()):
    """Return DuplicateGroups. Track dicts carry: content_id, title, artist,
    duration_ms, isrc. Dismissed group keys ('not a duplicate', persisted,
    idempotent) are dropped; groups of fewer than 2 members are dropped."""
    groups: list[DuplicateGroup] = []
    in_isrc_group: set[str] = set()

    # --- ISRC buckets (strip+upper, empty ignored) ----------------------------
    buckets: dict[str, list[dict]] = {}
    for track in tracks:
        isrc = (track.get("isrc") or "").strip().upper()
        if isrc:
            buckets.setdefault(isrc, []).append(track)
    for members in buckets.values():
        if len(members) < 2:
            continue
        titles = [m.get("title") for m in members]
        coherent = all(
            similarity(titles[0], t) >= TITLE_COHERENCE for t in titles[1:]
        )
        group = DuplicateGroup(
            key=_group_key(m["content_id"] for m in members),
            content_ids=sorted(str(m["content_id"]) for m in members),
            confidence=ISRC_CONFIDENCE if coherent else ISRC_DIVERGENT_CONFIDENCE,
            method="isrc",
            warning=not coherent,
        )
        groups.append(group)
        in_isrc_group.update(group.content_ids)

    # --- fuzzy (signature similarity + duration window) -----------------------
    pool = [t for t in tracks if str(t["content_id"]) not in in_isrc_group]
    signatures = [_signature(t) for t in pool]
    known = sorted(
        (i for i in range(len(pool)) if pool[i].get("duration_ms")),
        key=lambda i: pool[i]["duration_ms"],
    )
    unknown = [i for i in range(len(pool)) if not pool[i].get("duration_ms")]
    uf = _UnionFind(len(pool))

    def try_pair(i, j, threshold):
        if fuzz.token_sort_ratio(signatures[i], signatures[j]) / 100 >= threshold:
            uf.union(i, j)

    # ponytail: pairwise inside a duration sliding window (dup candidates sit
    # within 2000 ms of each other), O(n * window); a full O(n^2) scan only for
    # the rare unknown-duration tracks at the stricter 0.93 threshold. Upgrade
    # to rapidfuzz.process blocking if a real collection measures slow.
    for wi, i in enumerate(known):
        for j in known[wi + 1 :]:
            if pool[j]["duration_ms"] - pool[i]["duration_ms"] > DURATION_TOLERANCE_MS:
                break
            try_pair(i, j, FUZZY_THRESHOLD)
    for i in unknown:
        for j in range(len(pool)):
            if i != j:
                try_pair(i, j, max(FUZZY_THRESHOLD, FUZZY_THRESHOLD_NO_DURATION))

    clusters: dict[int, list[dict]] = {}
    for i in range(len(pool)):
        clusters.setdefault(uf.find(i), []).append(pool[i])
    for members in clusters.values():
        if len(members) < 2:
            continue
        groups.append(
            DuplicateGroup(
                key=_group_key(m["content_id"] for m in members),
                content_ids=sorted(str(m["content_id"]) for m in members),
                confidence=FUZZY_CONFIDENCE,
                method="fuzzy",
            )
        )

    return [g for g in groups if g.key not in dismissed]


# --- keeper (D6: ordered, discrete, explainable) ------------------------------


def bitrate_bucket(bit_rate) -> int:
    """Discrete tiers, no lossless preference (D6): a 1411 kbps FLAC and a
    320 CBR MP3 land in the SAME top tier - DJ hardware may not read FLAC."""
    rate = bit_rate or 0
    if rate >= 320:
        return 4
    if rate >= 256:
        return 3
    if rate >= 192:
        return 2
    if rate >= 128:
        return 1
    return 0


def _quality_rank(track) -> tuple:
    # The A3 verdict PRIMES over declared bitRate (5.4/5.12): a
    # lossy_source_probable track ranks below EVERY non-flagged copy at the
    # quality criterion - this is what makes the misleading fake-FLAC-1411
    # lose against a genuine 320 despite its higher declared bitrate. The
    # effect is binary: 'incertain' and 'ok' are both neutral, never a
    # penalty (5.12).
    flagged = track.get("quality_verdict") == "lossy_source_probable"
    return (0 if flagged else 1, bitrate_bucket(track.get("bit_rate")))


def _keeper_sort_key(track) -> tuple:
    return (
        1 if track.get("protected") else 0,  # (1) protected is always keeper
        0 if track.get("file_missing") else 1,  # (2) present file beats missing
        _quality_rank(track),  # (3) verdict, then bitrate bucket
        -(track.get("date_created_order") or 0),  # (4) older wins, stable
        str(track["content_id"]),  # full determinism
    )


REASON_LEVELS = [
    ("protected", lambda t: bool(t.get("protected"))),
    ("file_present", lambda t: not t.get("file_missing")),
    ("quality", _quality_rank),
    ("date", lambda t: -(t.get("date_created_order") or 0)),
]


def choose_keeper(tracks: list[dict]) -> tuple[dict, str]:
    """Return (keeper, reason_key). The reason is the FIRST criterion of the
    ordered D6 scale that separates the keeper from at least one other member
    - shown to the user (explainable keeper, no opaque weighted sum)."""
    if not tracks:
        raise ValueError("empty duplicate group")
    keeper = max(tracks, key=_keeper_sort_key)
    for reason, criterion in REASON_LEVELS:
        keeper_value = criterion(keeper)
        if any(criterion(t) != keeper_value for t in tracks if t is not keeper):
            return keeper, reason
    return keeper, "identical"
