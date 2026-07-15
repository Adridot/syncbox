"""Conservative, fixed Smart Fixes catalog and exact dry-run planner.

The module is pure: it does not access Rekordbox or the filesystem. Rules are
ordered, deterministic, and designed as fixpoints. Ambiguous metadata remains
unchanged for explicit review instead of being guessed.
"""

import html
import re
import unicodedata


FIELDS = ("title", "artist", "remixer")

_URL = r"(?:https?://|www\.)[^\s()\[\]]+"
_DOMAIN = (
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,24}(?:/[^\s()\[\]]*)?"
)
_SITE = rf"(?:{_URL}|{_DOMAIN})"
_TRAILING_SITE_PATTERNS = (
    re.compile(rf"\s+[-–—|]\s+{_URL}\s*$", re.IGNORECASE),
    re.compile(
        rf"\s+(?:[-–—|]\s+)?(?:\(\s*{_SITE}\s*\)|\[\s*{_SITE}\s*\])\s*$",
        re.IGNORECASE,
    ),
)
_XML_ENTITY = re.compile(r"&(amp|quot|apos|lt|gt);")
_MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "ðŸ", "ï»¿")
_GROUP = re.compile(r"\((?P<paren>[^()\[\]]*)\)|\[(?P<bracket>[^()\[\]]*)\]")
_FEATURE_BODY = re.compile(
    r"(?P<marker>feat\.?|ft\.?|featuring)\s+(?P<guest>.+?)",
    re.IGNORECASE,
)
_FEATURE_MARKER = re.compile(
    r"(?:^|[\s(\[])(?:feat\.?|ft\.?|featuring)(?:\s|$)", re.IGNORECASE
)
_REMIX_BODY = re.compile(r"(?P<name>.+?)\s+remix", re.IGNORECASE)
_ORPHAN_SEPARATOR = re.compile(r"\s+[-–—|]\s*$")
_RESERVED_REMIXERS = {
    "album",
    "club",
    "dance",
    "dub",
    "extended",
    "instrumental",
    "original",
    "radio",
    "vip",
    "vocal",
}
_MAX_ARTIST_NAME_LENGTH = 255


def decode_entities(value: str) -> str:
    """Decode only the five exact, semicolon-terminated XML entities."""
    while True:
        decoded = _XML_ENTITY.sub(lambda match: html.unescape(match.group(0)), value)
        if decoded == value:
            return value
        value = decoded


def collapse_whitespace(value: str) -> str:
    """Apply NFC and collapse Unicode whitespace without compatibility folding."""
    normalized = unicodedata.normalize("NFC", value).lstrip("\ufeff")
    return " ".join(normalized.split())


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)


def _safe_decoded(value: str) -> bool:
    return not any(
        unicodedata.category(character) == "Cc" and not character.isspace()
        for character in value
    )


def fix_mojibake(value: str) -> str:
    """Reverse latin-1/CP1252 mojibake only on one strictly better decode."""
    result = value
    while (score := _mojibake_score(result)) > 0:
        candidates = set()
        for encoding in ("latin-1", "cp1252"):
            try:
                candidate = result.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if _mojibake_score(candidate) < score and _safe_decoded(candidate):
                candidates.add(candidate)
        if len(candidates) != 1:
            break
        result = candidates.pop()
    return result


def strip_trailing_url(value: str) -> str:
    """Strip a trailing site only when a wrapper or separator proves intent."""
    result = value
    while True:
        for pattern in _TRAILING_SITE_PATTERNS:
            match = pattern.search(result)
            if match is not None:
                prefix = result[: match.start()].rstrip()
                if prefix:
                    result = prefix
                    break
        else:
            return result


TEXT_FIXES = (
    ("fix_mojibake", fix_mojibake),
    ("decode_entities", decode_entities),
    ("collapse_whitespace", collapse_whitespace),
    ("strip_trailing_url", strip_trailing_url),
)
CATALOG = {field: TEXT_FIXES for field in FIELDS}


def compose(field: str, value: str | None) -> str | None:
    """Return the final composed scalar value for one supported field."""
    if value is None:
        return None
    result = value
    for _name, function in CATALOG[field]:
        result = function(result)
    return result if result else value


def _terminal_groups(value: str) -> list[re.Match[str]]:
    expected_closer = None
    for character in value:
        if character in "([":
            if expected_closer is not None:
                return []
            expected_closer = ")" if character == "(" else "]"
        elif character in ")]":
            if character != expected_closer:
                return []
            expected_closer = None
    if expected_closer is not None:
        return []

    groups = []
    cursor = len(value)
    for match in reversed(list(_GROUP.finditer(value))):
        if value[match.end() : cursor].strip():
            break
        groups.append(match)
        cursor = match.start()
    groups.reverse()
    return groups


def _group_body(match: re.Match[str]) -> str:
    return match.group("paren") if match.group("paren") is not None else match.group("bracket")


def extract_featured_artist(
    title: str | None, artist: str | None
) -> tuple[str | None, str | None]:
    """Move one explicit terminal featured credit from title to artist."""
    if not title or not artist or not artist.strip() or _FEATURE_MARKER.search(artist):
        return title, artist

    matches = []
    for group in _terminal_groups(title):
        match = _FEATURE_BODY.fullmatch(_group_body(group).strip())
        if match is not None:
            matches.append((group, match))
    if len(matches) != 1:
        return title, artist

    group, credit = matches[0]
    guest = credit.group("guest").strip()
    if (
        not guest
        or _FEATURE_MARKER.search(guest)
        or re.search(r"(?:https?://|www\.)", guest, re.IGNORECASE)
        or _name_key(artist) == _name_key(guest)
    ):
        return title, artist

    prefix = title[: group.start()]
    suffix = title[group.end() :]
    prefix = _ORPHAN_SEPARATOR.sub("", prefix).rstrip()
    if not prefix:
        return title, artist
    cleaned_title = compose("title", f"{prefix} {suffix}")
    if not cleaned_title or not any(character.isalnum() for character in cleaned_title):
        return title, artist

    marker = credit.group("marker").casefold().rstrip(".")
    joiner = "featuring" if marker == "featuring" else "feat."
    credited_artist = f"{artist} {joiner} {guest}"
    if len(credited_artist) > _MAX_ARTIST_NAME_LENGTH:
        return title, artist
    return cleaned_title, credited_artist


def _name_key(value: str) -> str:
    return collapse_whitespace(value).casefold()


def _unique_known_artists(names) -> dict[str, str]:
    variants: dict[str, set[str]] = {}
    for name in names:
        if not name:
            continue
        cleaned = collapse_whitespace(str(name))
        if cleaned:
            variants.setdefault(_name_key(cleaned), set()).add(cleaned)
    return {
        key: next(iter(values))
        for key, values in variants.items()
        if len(values) == 1
    }


def extract_remixer(title: str | None, remixer: str | None, known_artists) -> str | None:
    """Fill an empty remixer from one terminal ``(Known Name Remix)`` block."""
    return _extract_remixer(
        title, remixer, _unique_known_artists(known_artists)
    )


def _extract_remixer(
    title: str | None, remixer: str | None, known_artists: dict[str, str]
) -> str | None:
    if not title or (remixer is not None and remixer.strip()):
        return remixer

    matches = []
    for group in _terminal_groups(title):
        match = _REMIX_BODY.fullmatch(_group_body(group).strip())
        if match is not None:
            matches.append(match)
    if len(matches) != 1:
        return remixer

    candidate = collapse_whitespace(matches[0].group("name"))
    key = _name_key(candidate)
    if not candidate or key in _RESERVED_REMIXERS:
        return remixer
    return known_artists.get(key, remixer)


def plan(rows: list[dict]) -> list[dict]:
    """Build the complete, canonical dry-run payload without ownership filters."""
    prepared = []
    for row in sorted(rows, key=lambda item: str(item["content_id"])):
        before = {field: row.get(field) for field in FIELDS}
        after = {field: compose(field, before[field]) for field in FIELDS}
        after["title"], after["artist"] = extract_featured_artist(
            after["title"], after["artist"]
        )
        prepared.append((row, before, after))

    known_artists = _unique_known_artists(
        values[field]
        for _row, _before, values in prepared
        for field in ("artist", "remixer")
        if values[field]
    )

    payload = []
    for row, before, after in prepared:
        after["remixer"] = _extract_remixer(
            after["title"], after["remixer"], known_artists
        )

        for field in FIELDS:
            if after[field] is not None and after[field] != before[field]:
                payload.append(
                    {
                        "content_id": str(row["content_id"]),
                        "field": field,
                        "before": before[field],
                        "after": after[field],
                    }
                )
    return payload
