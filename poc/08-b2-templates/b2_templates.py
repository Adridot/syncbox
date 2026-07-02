"""POC #8 - B2 purchase-link builder prototype (SPEC-UNIFIED 5.13).

Stdlib only. Fixed literal store catalog; D19-style normalization; urllib.parse.quote.
The builder performs ZERO network calls - the user's browser opens the URL.
Run this file to execute the assert-based checks and print the owner sample table.
"""

import re
import unicodedata
from urllib.parse import quote, urlsplit

# ponytail: fixed 2-store catalog, a build-time constant (not a model entity, 5.13).
# Removing a dead store = delete its entry -> its button disappears (Juno lesson).
CATALOG = [
    {"name": "Beatport", "template": "https://www.beatport.com/search?q={query}"},
    {"name": "Bandcamp", "template": "https://bandcamp.com/search?q={query}&item_type=t"},
]

_PARENS = re.compile(r"[(\[][^)\]]*[)\]]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text):
    """D19-style normalization shared with matching (5.3): NFKD -> ASCII, lowercase,
    parenthesized/bracketed content removed, & -> and, non-alphanumeric -> space."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = text.lower()
    text = _PARENS.sub(" ", text)
    text = text.replace("&", " and ")
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


def purchase_links(artist, title, catalog=CATALOG):
    query = normalize(f"{artist or ''} {title or ''}")
    if not query:
        return []  # nothing usable -> no buttons (purchase_link_unavailable upstream)
    q = quote(query)
    return [{"store": s["name"], "url": s["template"].format(query=q)} for s in catalog]


def _well_formed(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.netloc and " " not in url


if __name__ == "__main__":
    # --- encoding edge cases ---------------------------------------------------
    cases = [
        ("Rüfüs Du Sol", "Innerbloom (Frankey & Sandrino Remix)"),  # accents + parens + &
        ("Above & Beyond", "Sun & Moon"),  # ampersands
        ("Fred again..", "Delilah (pull me out of this)"),  # dots + parens
        ("AC/DC", "Thunderstruck"),  # slash
        ("D'Angelo", "Sugah Daddy"),  # apostrophe
        ("Âme", "Rej"),  # diacritic
        ("A" * 300, "B" * 300),  # very long
        ("", "Strobe"),  # empty artist
        ("宇多田ヒカル", "光"),  # non-Latin: NFKD/ASCII drops it entirely
        ("🎵🎧", "🔥"),  # emoji only
    ]
    for artist, title in cases:
        links = purchase_links(artist, title)
        for link in links:
            assert _well_formed(link["url"]), f"malformed URL for {artist!r}/{title!r}: {link}"
    # Fully non-ASCII input degrades to zero links, never a crash or a junk URL.
    assert purchase_links("宇多田ヒカル", "光") == []
    assert purchase_links("🎵🎧", "🔥") == []
    assert purchase_links("", "") == []
    assert purchase_links(None, None) == []

    # & -> and, parens stripped, accents folded
    beatport = purchase_links("Rüfüs Du Sol", "Innerbloom (Frankey & Sandrino Remix)")[0]["url"]
    assert "rufus%20du%20sol%20innerbloom" == beatport.split("q=")[1], beatport

    # --- store-disappeared fallback is data-driven ------------------------------
    without_beatport = [s for s in CATALOG if s["name"] != "Beatport"]
    links = purchase_links("Bicep", "Glue", catalog=without_beatport)
    assert [link["store"] for link in links] == ["Bandcamp"]

    print("All assertions passed.\n")

    # --- owner sample table (open in a browser to judge first-result quality) ---
    samples = [
        ("Daft Punk", "One More Time"),
        ("Charlotte de Witte", "Doppler"),
        ("Amelie Lens", "Higher"),
        ("Bicep", "Glue"),
        ("Rüfüs Du Sol", "Innerbloom"),
        ("Peggy Gou", "(It Goes Like) Nanana"),
        ("Âme", "Rej"),
        ("Fred again..", "Delilah (pull me out of this)"),
    ]
    for artist, title in samples:
        print(f"{artist} - {title}")
        for link in purchase_links(artist, title):
            print(f"  {link['store']}: {link['url']}")
