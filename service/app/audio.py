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

    def sanitize_filename(s: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]', "", s).strip()
        # Deemix strips trailing dots/spaces from filename components (Windows-safe),
        # e.g. the title "APT." is written to disk as "Artist - APT.mp3".
        return cleaned.rstrip(" .")

    # Build expected filenames from the Deemix naming template "%artist% - %title%"
    # and common variants produced by overwriteFiles:"rename" and playlist numbering.
    if title:
        base = f"{sanitize_filename(artist)} - {sanitize_filename(title)}" if artist else sanitize_filename(title)
        candidate_names = []
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


# Scanning a (cloud-synced) collection folder means an rglob + a mutagen read per
# file — easily ~1s. The library job-status refresh used to call this once per
# source on every tick, so with N sources the same folder was scanned N times
# every few seconds (the Library view took ~13s). Memoise per directory on its
# mtime, with a short TTL safety net in case the cloud FS doesn't bump the dir
# mtime when a file lands. A completed download changes the folder -> fresh scan.
_SCAN_CACHE: dict[str, tuple[Any, float, list[dict[str, Any]]]] = {}
_SCAN_TTL_S = 15.0


def scan_audio_files(audio_dir: Path) -> list[dict[str, Any]]:
    import time

    key = str(audio_dir)
    try:
        stat = audio_dir.stat()
        sig: Any = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        sig = None

    cached = _SCAN_CACHE.get(key)
    if (
        cached is not None
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
