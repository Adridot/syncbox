"""B2 legal purchase links - pure URL templating, zero network
(SPEC-UNIFIED 5.13/6.5, validated by POC #7).

The app NEVER contacts a store: the user's browser opens these URLs. No
scraping, no store API, no result resolution, no credential. The catalog is
a build-time literal: removing a dead store's entry removes its button
(Juno lesson, closed 2026-06-01).
"""

from urllib.parse import quote

from syncbox.matching import normalize  # D19: the one shared pipeline

# The v1 store catalog is fixed at build time.
CATALOG = [
    {"name": "Beatport", "template": "https://www.beatport.com/search?q={query}"},
    {"name": "Bandcamp", "template": "https://bandcamp.com/search?q={query}&item_type=t"},
]

# Only these statuses expose purchase links; removed_from_source is excluded
# (SPEC-UNIFIED 5.13, SPEC-DESIGN 11.2 fix list).
PURCHASABLE_STATUSES = frozenset(
    {"missing", "acquisition_failed", "purchase_link_unavailable"}
)


def purchase_links(artist, title, catalog=CATALOG) -> list[dict]:
    """[{store, url}] for one track; [] when nothing usable remains after
    normalization (caller surfaces purchase_link_unavailable)."""
    query = normalize(f"{artist or ''} {title or ''}")
    if not query:
        return []
    encoded = quote(query)
    return [
        {"store": store["name"], "url": store["template"].format(query=encoded)}
        for store in catalog
    ]


def links_for_track(status: str, artist, title) -> list[dict]:
    """Status-gated variant used by the missing-tracks views."""
    if status not in PURCHASABLE_STATUSES:
        return []
    return purchase_links(artist, title)
