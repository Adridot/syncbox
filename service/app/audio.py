from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .live_import import SUPPORTED_AUDIO_EXTENSIONS


def read_audio_metadata(path: Path) -> dict[str, Any]:
    title = path.stem
    artist = ""
    duration_ms: int | None = None
    isrc: str | None = None

    try:
        from mutagen import File as MutagenFile
    except Exception:
        return {
            "title": title,
            "artist": artist,
            "duration_ms": duration_ms,
            "isrc": isrc,
        }

    try:
        audio = MutagenFile(str(path), easy=True)
    except Exception:
        audio = None

    if audio is not None:
        title = first_tag(audio, "title") or title
        artist = first_tag(audio, "artist") or artist
        isrc = first_tag(audio, "isrc") or first_tag(audio, "barcode")
        info = getattr(audio, "info", None)
        length = getattr(info, "length", None)
        if length:
            duration_ms = int(float(length) * 1000)

    return {
        "title": title,
        "artist": artist,
        "duration_ms": duration_ms,
        "isrc": isrc,
    }


def first_tag(audio: Any, key: str) -> str | None:
    value = audio.get(key)
    if not value:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def find_downloaded_file(
    folder: Path,
    isrc: str | None,
    title: str,
    artist: str,
) -> str | None:
    """Find a just-downloaded audio file in a specific folder.

    Strategy:
    1. Construct candidate filenames from the Deemix template (%artist% - %title%)
       and test existence directly — avoids directory listing which fails on
       cloud-synced paths (Dropbox CloudStorage, iCloud Drive, etc.).
    2. Fall back to os.scandir + metadata matching if the directory is listable.
    """
    from .matching import text_similarity

    _ILLEGAL = r'[\\/:*?"<>|]'

    def component_forms(s: str, *, strip_trailing: bool = True) -> set[str]:
        # Deemix may either drop the illegal characters or replace them with "_"
        # (its default, e.g. '... "Another Round")' -> '... _Another Round_)'),
        # so try both. It also strips trailing dots/spaces from the *final*
        # component only (the title, e.g. "APT." -> "Artist - APT.mp3"); an
        # interior component (the artist) keeps its dot ("Boney M. - Ma Baker"),
        # so the artist is tried with strip_trailing both ways at the call site.
        base = s.strip()
        forms = {re.sub(_ILLEGAL, "", base), re.sub(_ILLEGAL, "_", base)}
        if strip_trailing:
            forms = {f.rstrip(" .") for f in forms}
        return {f for f in forms if f}

    def title_variants(t: str) -> set[str]:
        # Spotify and Deezer format version/feature suffixes differently: Spotify
        # appends after a dash ("What A Life - From the Motion Picture …",
        # "Song - Radio Edit"), Deezer/Deemix wraps it in parentheses
        # ("… (Radio Edit)"). The file on disk uses the Deezer form, so when the
        # title has a " - " suffix also try the parenthesised variant — this keeps
        # cloud lookup working even after the acquisition job (which carried the
        # exact Deezer name) has been cleared.
        variants = {t}
        head, sep, tail = t.partition(" - ")
        if sep and tail:
            variants.add(f"{head} ({tail})")
        return variants

    # Build expected filenames from the Deemix naming template "%artist% - %title%"
    # and common variants produced by overwriteFiles:"rename" and playlist numbering.
    if title:
        title_forms: set[str] = set()
        for variant in title_variants(title):
            title_forms |= component_forms(variant)
        if artist:
            artist_forms = component_forms(artist) | component_forms(
                artist, strip_trailing=False
            )
            bases = {f"{art} - {ttl}" for art in artist_forms for ttl in title_forms}
        else:
            bases = set(title_forms)
        candidate_names = []
        for base in bases:
            for ext in (".mp3", ".flac", ".m4a", ".ogg"):
                candidate_names.append(f"{base}{ext}")
                for n in range(1, 8):
                    candidate_names.append(f"{base} ({n}){ext}")
                # Playlist batch adds a track number prefix (e.g. "001 - ")
                for prefix in ("001", "002", "003"):
                    candidate_names.append(f"{prefix} - {base}{ext}")
                    for n in range(1, 5):
                        candidate_names.append(f"{prefix} - {base} ({n}){ext}")

        for name in candidate_names:
            path = folder / name
            try:
                if path.exists():
                    return str(path)
            except (PermissionError, OSError):
                pass

    # Fallback: scan directory if accessible (works for local paths)
    try:
        for entry in os.scandir(str(folder)):
            if not entry.is_file():
                continue
            if Path(entry.name).suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue
            meta = read_audio_metadata(Path(entry.path))
            if isrc and meta.get("isrc") and meta["isrc"] == isrc:
                return entry.path
            if title:
                title_sim = text_similarity(title, meta.get("title") or "")
                artist_sim = text_similarity(artist, meta.get("artist") or "")
                if title_sim >= 80 or (title_sim >= 70 and artist_sim >= 70):
                    return entry.path
    except (PermissionError, OSError, FileNotFoundError):
        pass

    return None


def locate_downloaded_track_file(
    folders: list[Path | str],
    *,
    isrc: str | None = None,
    deezer_title: str | None = None,
    deezer_artist: str | None = None,
    fallback_title: str | None = None,
    fallback_artist: str | None = None,
) -> str | None:
    """Locate a track's downloaded audio file across candidate folders.

    The single shared "find the downloaded file" brain behind BOTH the event and
    library download-link paths. Deemix names files from the **Deezer** metadata
    it resolved (often differing from Spotify's, e.g. Spotify "Cambodia - Single
    Version" vs Deezer "Cambodia"), so try the Deezer names first, then the
    request (Spotify) names. Each attempt is an existence check (stat), which
    works on cloud folders that can't be listed.
    """
    attempts: list[tuple[str, str]] = []

    def add(title: str | None, artist: str | None) -> None:
        if title:
            pair = (str(title), str(artist or ""))
            if pair not in attempts:
                attempts.append(pair)

    add(deezer_title, deezer_artist)
    add(fallback_title, fallback_artist)
    # Last resort: the title with no artist prefix ("Title.mp3"). Rare for Deemix
    # (its template is "%artist% - %title%"), but it preserves the old library
    # lookup's bare-title probe so this stays a strict superset.
    add(fallback_title, "")
    for folder in folders:
        folder_path = Path(folder)
        for title, artist in attempts:
            found = find_downloaded_file(folder_path, isrc, title, artist)
            if found:
                return found
    return None


# Scanning a (cloud-synced) collection folder means an rglob + a mutagen read per
# file — easily ~1s. The library job-status refresh used to call this once per
# source on every tick, so with N sources the same folder was scanned N times
# every few seconds (the Library view took ~13s). Memoise per directory on its
# mtime, with a short TTL safety net in case the cloud FS doesn't bump the dir
# mtime when a file lands. A completed download changes the folder -> fresh scan.
_SCAN_CACHE: dict[str, tuple[Any, float, list[dict[str, Any]]]] = {}
_SCAN_TTL_S = 15.0


def scan_audio_files(audio_dir: Path, *, fresh: bool = False) -> list[dict[str, Any]]:
    """List audio files under ``audio_dir`` with cached metadata.

    Pass ``fresh=True`` when correctness depends on seeing files that may have
    landed within the cache TTL (e.g. confirming a just-finished download).
    Cloud filesystems don't always bump the directory mtime when a file lands,
    so the time-based cache could otherwise hide a brand-new file for up to the
    TTL and leave a download job stuck at "downloaded".
    """
    import time

    key = str(audio_dir)
    try:
        stat = audio_dir.stat()
        sig: Any = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        sig = None

    cached = _SCAN_CACHE.get(key)
    if (
        not fresh
        and cached is not None
        and sig is not None
        and cached[0] == sig
        and (time.monotonic() - cached[1]) < _SCAN_TTL_S
    ):
        return cached[2]

    results = _scan_audio_files_uncached(audio_dir)
    if sig is not None:
        _SCAN_CACHE[key] = (sig, time.monotonic(), results)
    return results


def _scan_audio_files_uncached(audio_dir: Path) -> list[dict[str, Any]]:
    files = [
        path
        for path in audio_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    ]
    results = []
    for path in sorted(files, key=lambda item: item.name.lower()):
        metadata = read_audio_metadata(path)
        results.append(
            {
                "file_path": str(path),
                "title": metadata["title"],
                "artist": metadata["artist"],
                "duration_ms": metadata["duration_ms"],
                "isrc": metadata["isrc"],
                "status": "unmatched",
            }
        )
    return results
