"""Manual relink candidate scoring (SPEC-UNIFIED 5.5/5.8, SPEC-01 2.4).

Finds LOCAL files the user already lawfully owns that could replace a
missing file association. No remote lookup of any kind. Scoring: file-tag
ISRC match -> 100; otherwise best of title-vs-tag-title / title-vs-filename
similarity, kept at >= 70. Candidate list capped (~8) and the filesystem
walk is BOUNDED (fix F11: no unbounded rglob).

The relink WRITE (preserving cues/tags/playlists in master.db, with the
ANLZ consent warning) lives in the Rekordbox write layer - this module is
read-only discovery.
"""

from pathlib import Path

from mutagen import File as MutagenFile

from syncbox.matching import similarity

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".ogg"}
ISRC_SCORE = 100
MIN_SCORE = 70
CANDIDATE_CAP = 8
# A hard ceiling keeps scans deterministic and testable.
MAX_SCANNED_FILES = 20_000


def _file_tags(path: Path) -> tuple[str | None, str | None]:
    """(isrc, title) from the audio file's tags; never raises."""
    try:
        mf = MutagenFile(str(path), easy=True)
        if mf is None or not mf.tags:
            return None, None
        isrc = (mf.tags.get("isrc") or [None])[0]
        title = (mf.tags.get("title") or [None])[0]
        return isrc, title
    except Exception:
        return None, None


def iter_audio_files(roots, *, max_files: int = MAX_SCANNED_FILES):
    """Bounded walk over the search roots; per-entry errors are skipped
    (cloud/TCC listing failures must not abort the whole scan)."""
    scanned = 0
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        try:
            walker = root.rglob("*")
            while True:
                try:
                    entry = next(walker)
                except StopIteration:
                    break
                except OSError:
                    continue  # unreadable subtree: skip, keep walking
                scanned += 1
                if scanned > max_files:
                    return
                if entry.suffix.lower() in AUDIO_EXTS and entry.is_file():
                    yield entry
        except OSError:
            continue


def score_candidate(track: dict, path: Path) -> int:
    """track: {title, artist, isrc}. Returns 0 when below MIN_SCORE."""
    file_isrc, file_title = _file_tags(path)
    wanted_isrc = (track.get("isrc") or "").strip().upper()
    if wanted_isrc and file_isrc and file_isrc.strip().upper() == wanted_isrc:
        return ISRC_SCORE
    wanted = f"{track.get('artist') or ''} {track.get('title') or ''}"
    best = max(
        similarity(track.get("title"), file_title),
        similarity(wanted, path.stem),
        similarity(track.get("title"), path.stem),
    )
    return round(best) if best >= MIN_SCORE else 0


def find_candidates(
    track: dict, roots, *, cap: int = CANDIDATE_CAP, max_files: int = MAX_SCANNED_FILES
) -> list[dict]:
    """Top candidates [{path, score, duration_s?, format}] sorted by score
    desc then path for determinism."""
    scored = []
    for path in iter_audio_files(roots, max_files=max_files):
        score = score_candidate(track, path)
        if score:
            scored.append({"path": str(path), "score": score, "format": path.suffix[1:]})
    scored.sort(key=lambda c: (-c["score"], c["path"]))
    return scored[:cap]
