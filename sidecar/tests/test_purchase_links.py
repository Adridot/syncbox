"""Tests for B2 purchase links (SPEC-UNIFIED 5.13/6.5, POC #8)."""

from pathlib import Path
from urllib.parse import urlsplit

import syncbox.purchase_links as module
from syncbox.purchase_links import CATALOG, links_for_track, purchase_links


def test_builds_both_store_urls():
    links = purchase_links("Bicep", "Glue")
    assert [link["store"] for link in links] == ["Beatport", "Bandcamp"]
    assert links[0]["url"] == "https://www.beatport.com/search?q=bicep%20glue"
    assert "bandcamp.com/search?q=bicep%20glue" in links[1]["url"]


def test_normalization_is_the_d19_pipeline():
    links = purchase_links("Rüfüs Du Sol", "Innerbloom (Frankey & Sandrino Remix)")
    assert links[0]["url"].endswith("q=rufus%20du%20sol%20innerbloom")


def test_edge_cases_never_crash_never_malform():
    cases = [
        ("Above & Beyond", "Sun & Moon"),
        ("AC/DC", "Thunderstruck"),
        ("D'Angelo", "Sugah Daddy"),
        ("A" * 300, "B" * 300),
        ("", "Strobe"),
    ]
    for artist, title in cases:
        for link in purchase_links(artist, title):
            parts = urlsplit(link["url"])
            assert parts.scheme == "https" and parts.netloc
            assert " " not in link["url"]


def test_nothing_usable_yields_no_links():
    assert purchase_links("宇多田ヒカル", "光") == []  # D19 drops non-ASCII
    assert purchase_links("🎵", "🔥") == []
    assert purchase_links("", "") == []
    assert purchase_links(None, None) == []


def test_store_removal_is_data_driven():
    without_beatport = [s for s in CATALOG if s["name"] != "Beatport"]
    links = purchase_links("Bicep", "Glue", catalog=without_beatport)
    assert [link["store"] for link in links] == ["Bandcamp"]


def test_status_gate_excludes_removed_from_source():
    assert links_for_track("missing", "Bicep", "Glue")
    assert links_for_track("purchase_link_unavailable", "Bicep", "Glue")
    assert links_for_track("removed_from_source", "Bicep", "Glue") == []
    assert links_for_track("imported", "Bicep", "Glue") == []


def test_zero_network_code_in_module():
    source = Path(module.__file__).read_text()
    for forbidden in ("urlopen", "urllib.request", "requests", "httpx", "socket"):
        assert forbidden not in source
