"""Canonical music resource identities; parsing performs no network work."""

import re
from urllib.parse import parse_qs, urlsplit

from syncbox.spotify import spotify_id_from_path

PROVIDERS = {"spotify", "deezer", "youtube", "soundcloud"}
SHARE_HOSTS = {"spotify.link": "spotify", "deezer.page.link": "deezer",
               "link.deezer.com": "deezer", "on.soundcloud.com": "soundcloud",
               "snd.sc": "soundcloud", "soundcloud.app.goo.gl": "soundcloud"}


class LinkError(ValueError):
    pass


def parse_link(value, *, choice=None):
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 32 for c in value):
        raise LinkError("invalid_music_link")
    value = value.strip()
    spotify_id = spotify_id_from_path(value)
    if spotify_id:
        value = f"https://open.spotify.com/track/{spotify_id}"
    elif re.fullmatch(r"spotify:(album|playlist):[A-Za-z0-9]{22}", value):
        _, kind, item = value.split(":")
        value = f"https://open.spotify.com/{kind}/{item}"
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.port not in (None, 443) or parsed.username or parsed.password:
            raise ValueError()
    except ValueError:
        raise LinkError("invalid_music_link") from None
    host = parsed.hostname
    path = parsed.path.strip("/")
    query = parse_qs(parsed.query)
    provider = kind = item = url = None
    if host in SHARE_HOSTS and re.fullmatch(r"[A-Za-z0-9_/-]{1,200}", path):
        provider, kind, url = SHARE_HOSTS[host], "share", f"https://{host}/{path}"
    elif host == "open.spotify.com":
        path = re.sub(r"^intl-[a-z]{2}/", "", path)
        found = re.fullmatch(r"(track|album|playlist)/([A-Za-z0-9]{22})", path)
        if found:
            provider, (kind, item) = "spotify", found.groups()
            url = f"https://open.spotify.com/{kind}/{item}"
    elif host in {"deezer.com", "www.deezer.com"}:
        found = re.fullmatch(r"(?:[a-z]{2}/)?(track|album|playlist)/([1-9][0-9]{0,19})", path)
        if found:
            provider, (kind, item) = "deezer", found.groups()
            url = f"https://www.deezer.com/{kind}/{item}"
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        video = path if host == "youtu.be" else (query.get("v") or [None])[0] if path == "watch" else None
        if path.startswith(("shorts/", "embed/")):
            video = path.split("/")[1]
        playlist = (query.get("list") or [None])[0] if video or path == "playlist" else None
        if video and not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise LinkError("invalid_video_id")
        if playlist and not re.fullmatch(r"[A-Za-z0-9_-]{10,150}", playlist):
            raise LinkError("invalid_playlist_id")
        if video and playlist:
            if choice not in {"track", "playlist"}:
                raise LinkError("video_or_playlist_choice_required")
            video, playlist = (video, None) if choice == "track" else (None, playlist)
        if video:
            provider, kind, item, url = "youtube", "track", video, f"https://www.youtube.com/watch?v={video}"
        elif playlist:
            provider, kind, item, url = "youtube", "playlist", playlist, f"https://www.youtube.com/playlist?list={playlist}"
        elif host == "music.youtube.com" and re.fullmatch(r"browse/MP[A-Za-z0-9_-]{5,150}", path):
            provider, kind, item, url = "youtube", "album", path.split("/")[1], f"https://music.youtube.com/{path}"
    elif host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}:
        parts = path.split("/")
        if all(re.fullmatch(r"[A-Za-z0-9_-]{1,200}", part) for part in parts):
            if len(parts) == 3 and parts[1] == "sets":
                provider, kind = "soundcloud", "playlist"
            elif len(parts) == 2 and parts[0] not in {"discover", "search", "you", "charts"} and parts[1] not in {"tracks", "albums", "sets", "likes", "reposts", "popular-tracks"}:
                provider, kind = "soundcloud", "track"
            url = f"https://soundcloud.com/{path}"
    if not provider:
        raise LinkError("unsupported_music_resource")
    return {"provider": provider, "resource_type": kind, "resource_id": item, "url": url}
