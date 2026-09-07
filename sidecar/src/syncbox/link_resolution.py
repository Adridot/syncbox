"""Bounded catalogue enumeration outside the API's application lock."""

import json
import time
from urllib.parse import urlsplit

from syncbox import library_service, provider_http, spotify
from syncbox.link_imports import MAX_ITEMS, normalized_manifest
from syncbox.music_links import LinkError, SHARE_HOSTS, parse_link


def resolve(url, *, spotify_client=None, web_runner=None, cancelled=lambda: False):
    deadline = time.monotonic() + 120
    byte_count = 0

    def check():
        if cancelled():
            raise LinkError("operation_cancelled")
        if time.monotonic() >= deadline:
            raise LinkError("metadata_time_limit")

    def catalogue_get(path, provider):
        nonlocal byte_count
        check()
        if provider == "spotify":
            if spotify_client is None:
                raise LinkError("spotify_authentication_required")
            if path.startswith("https:"):
                parsed = provider_http.validate_url(path, {"api.spotify.com"})
                if not parsed.path.startswith("/v1/"):
                    raise LinkError("unsupported_network_destination")
            result = spotify_client.get(path, retry=False) if isinstance(spotify_client, spotify.SpotifyClient) else spotify_client.get(path)
        else:
            absolute = path if path.startswith("https:") else "https://api.deezer.com" + path
            status, _, body, _ = provider_http.request(absolute, hosts={"api.deezer.com"})
            if status == 429:
                raise LinkError("provider_rate_limited")
            if status != 200:
                raise LinkError("provider_metadata_unavailable")
            result = json.loads(body)
            if result.get("error"):
                raise LinkError("provider_item_unavailable")
        byte_count += len(json.dumps(result).encode())
        if byte_count > 8 * 1024 * 1024:
            raise LinkError("metadata_byte_limit")
        return result

    source = parse_link(url)
    if source["resource_type"] == "share":
        host_sets = {
            "spotify": {"open.spotify.com"}, "deezer": {"deezer.com", "www.deezer.com"},
            "soundcloud": {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"},
        }
        hosts = host_sets[source["provider"]] | {h for h, p in SHARE_HOSTS.items() if p == source["provider"]}
        status, _, _, final = provider_http.request(url, hosts=hosts, headers_only=True)
        if status != 200:
            raise LinkError("share_link_unavailable")
        resolved = parse_link(final)
        if resolved["provider"] != source["provider"] or resolved["resource_type"] == "share":
            raise LinkError("unsupported_share_target")
        source = resolved
    check()
    provider, kind, item_id = source["provider"], source["resource_type"], source["resource_id"]
    if provider in {"youtube", "soundcloud"}:
        if web_runner is None:
            raise LinkError("web_audio_component_missing")
        return normalized_manifest(web_runner({"operation": "metadata", "url": source["url"]}, cancelled=cancelled))
    entries = []
    if kind == "track" and provider == "spotify":
        meta = spotify.resolve_track_meta([item_id], spotify_client).get(item_id)
        if not meta:
            raise LinkError("provider_metadata_unavailable")
        entries = [{**meta, "item_id": item_id, "url": source["url"], "available": True}]
        title = meta.get("title")
    else:
        first = catalogue_get(f"/{kind}s/{item_id}" if provider == "spotify" else f"/{kind}/{item_id}", provider)
        title = first.get("name") if provider == "spotify" else first.get("title")
        if kind == "track":
            pages = [{"data": [first], "next": None}]
        else:
            page = first.get("items") if kind == "playlist" and isinstance(first.get("items"), dict) else first.get("tracks")
            if not isinstance(page, dict):
                raise LinkError("collection_items_inaccessible")
            pages = [page]
        seen = set()
        for page in pages:
            check()
            items = page.get("items" if provider == "spotify" else "data")
            if not isinstance(items, list):
                raise LinkError("invalid_collection_page")
            for item in items:
                if provider == "spotify":
                    track = (item.get("item") or item.get("track")) if kind == "playlist" and isinstance(item, dict) else item
                    mapped = library_service._spotify_track({"track": track}) if isinstance(track, dict) else None
                    available = bool(mapped and not track.get("is_local") and track.get("is_playable") is not False)
                    entry = {**(mapped or {}), "item_id": mapped["spotify_track_id"] if mapped else None, "available": available}
                    entry["url"] = f"https://open.spotify.com/track/{entry['item_id']}" if available else None
                else:
                    item = item if isinstance(item, dict) else {}
                    identity = str(item.get("id") or "")
                    entry = {"item_id": identity, "available": bool(identity and item.get("readable") is not False),
                             "url": f"https://www.deezer.com/track/{identity}", "title": item.get("title"),
                             "artist": (item.get("artist") or {}).get("name"), "duration_seconds": item.get("duration"), "isrc": item.get("isrc")}
                entries.append(entry)
                if len(entries) > MAX_ITEMS:
                    raise LinkError("collection_item_limit")
            next_url = page.get("next")
            if next_url:
                if next_url in seen or len(pages) >= 100:
                    raise LinkError("collection_page_limit")
                seen.add(next_url)
                pages.append(catalogue_get(next_url, provider))
    if provider == "spotify" and kind == "album":
        missing = [entry for entry in entries if entry["available"] and not entry.get("isrc")]
        for start in range(0, len(missing), 50):
            check()
            batch = missing[start:start + 50]
            metadata = spotify.resolve_track_meta([entry["item_id"] for entry in batch], spotify_client)
            for entry in batch:
                entry.update({key: value for key, value in metadata.get(entry["item_id"], {}).items() if value is not None})
    check()
    return normalized_manifest({**source, "title": title, "entries": entries})
