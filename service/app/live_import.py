from __future__ import annotations

import re
import unicodedata
from pathlib import Path


SUPPORTED_AUDIO_EXTENSIONS = {
    ".aac",
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".wav",
    ".wave",
}


def build_live_import_package(
    events_root: Path, event_name: str, *, unique: bool = False
) -> dict[str, object]:
    # Event scaffolding passes unique=True so each event gets its OWN fresh folder.
    # Reusing an existing slug's folder is wrong twice over there: it mixes two
    # events' audio, and on a cloud drive (Dropbox/iCloud) macOS won't let this
    # process write into a folder another process created — `<slug>.m3u8` then
    # fails with PermissionError and the whole create 500s. Live M3U8 import keeps
    # the default (unique=False): it intentionally targets an existing named
    # folder to list the audio already in it.
    event_slug = (
        unique_event_slug(events_root, event_name)
        if unique
        else safe_event_slug(event_name)
    )
    event_dir = events_root / event_slug
    audio_dir = event_dir / "audio"
    playlist_path = event_dir / f"{event_slug}.m3u8"

    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_files = list_audio_files(audio_dir)
    write_m3u8_playlist(playlist_path, audio_files)

    return {
        "eventName": event_name.strip(),
        "eventSlug": event_slug,
        "eventDir": str(event_dir),
        "audioDir": str(audio_dir),
        "playlistPath": str(playlist_path),
        "trackCount": len(audio_files),
        "audioFiles": [str(path) for path in audio_files],
    }


def safe_event_slug(event_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", event_name.strip())
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()
    return slug or "untitled-event"


def unique_event_slug(events_root: Path, event_name: str) -> str:
    """A slug whose folder under ``events_root`` doesn't exist yet.

    ``Path.exists()`` uses stat(), which works on cloud-synced folders even when
    they can't be listed, so an existing event folder is reliably detected.
    """
    base = safe_event_slug(event_name)
    candidate = base
    suffix = 2
    while (events_root / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def list_audio_files(audio_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in audio_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        ],
        key=lambda path: path.name.lower(),
    )


def write_m3u8_playlist(playlist_path: Path, audio_files: list[Path]) -> None:
    lines = ["#EXTM3U"]
    lines.extend(str(path) for path in audio_files)
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
