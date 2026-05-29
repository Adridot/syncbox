from __future__ import annotations

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


def scan_audio_files(audio_dir: Path) -> list[dict[str, Any]]:
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
