#!/usr/bin/env python3
"""Create the ignored retained-track fixture from a closed Rekordbox library."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SIDECAR_SRC = REPO / "sidecar" / "src"
TESTDATA = REPO / "poc" / "testdata"
FIXTURE_DB = TESTDATA / "master.db"
MANIFEST = TESTDATA / "event-migration.json"

sys.path.insert(0, str(SIDECAR_SRC))

from syncbox import event_delete, rb  # noqa: E402
from syncbox.safety.process_guard import assert_mutation_ready  # noqa: E402

from copy_rekordbox_fixtures import (  # noqa: E402
    _assert_no_symlink_components,
    _digest,
    _state,
)


_CANDIDATE_SQL = """
SELECT c.ID, c.FolderPath, c.AnalysisDataPath
FROM djmdContent c
WHERE c.rb_local_deleted = 0
  AND c.FolderPath IS NOT NULL
  AND c.AnalysisDataPath IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM djmdCue q
      WHERE q.ContentID = c.ID AND q.rb_local_deleted = 0
  )
  AND EXISTS (
      SELECT 1 FROM djmdSongPlaylist p
      WHERE p.ContentID = c.ID AND p.rb_local_deleted = 0
  )
  AND EXISTS (
      SELECT 1 FROM djmdSongMyTag t
      WHERE t.ContentID = c.ID AND t.rb_local_deleted = 0
  )
ORDER BY c.ID
"""


def _regular_source(path: Path) -> Path:
    path = path.expanduser().absolute()
    _assert_no_symlink_components(path, Path(path.anchor))
    _state(path)
    return path


def _audio_candidates(stored_path: str) -> tuple[Path, ...]:
    raw = Path(stored_path).expanduser()
    candidates = [raw]
    parts = raw.parts
    if raw.is_absolute() and len(parts) > 2 and parts[1] not in {"Users", "Volumes"}:
        candidates.append(Path("/Volumes").joinpath(*parts[1:]))
    return tuple(dict.fromkeys(candidate.absolute() for candidate in candidates))


def _select_sources(source_dir: Path) -> tuple[str, Path, tuple[Path, ...]]:
    connection = rb.open_readonly(FIXTURE_DB)
    try:
        candidates = connection.execute(_CANDIDATE_SQL).fetchall()
    finally:
        connection.close()

    for content_id, stored_audio, analysis_path in candidates:
        audio = None
        for candidate in _audio_candidates(str(stored_audio)):
            try:
                audio = _regular_source(candidate)
            except (OSError, ValueError):
                continue
            break
        if audio is None:
            continue
        try:
            anlz = tuple(
                _regular_source(path)
                for path in event_delete._anlz_paths(
                    source_dir / "master.db", analysis_path
                )
            )
        except (OSError, ValueError, event_delete.EventMigrationError):
            continue
        if anlz:
            return str(content_id), audio, anlz
    raise ValueError(
        "no active content row has a regular audio file, ANLZ data, cues, "
        "playlist membership, and a MyTag"
    )


def prepare_fixture(source_dir: Path, *, backup_confirmed: bool) -> dict[str, object]:
    source_dir = source_dir.expanduser().absolute()
    assert_mutation_ready(source_dir / "master.db")
    if not backup_confirmed:
        raise ValueError("a complete Rekordbox library backup must be confirmed")
    _regular_source(source_dir / "master.db")
    _regular_source(FIXTURE_DB)
    if TESTDATA.is_symlink() or not TESTDATA.is_dir():
        raise ValueError("poc/testdata must be a real directory")
    if MANIFEST.exists() or (TESTDATA / "audio").exists() or (TESTDATA / "share").exists():
        raise ValueError("the event-migration fixture already exists")

    content_id, audio, anlz = _select_sources(source_dir)
    sources = (audio, *anlz)
    before = {path: _state(path) for path in sources}
    fixture_db_before = _state(FIXTURE_DB)

    suffix = audio.suffix.lower() or ".audio"
    audio_relative = Path("audio") / f"retained-track{suffix}"
    anlz_relatives = tuple(
        Path("share") / path.relative_to(source_dir / "share") for path in anlz
    )

    with tempfile.TemporaryDirectory(prefix="event-fixture-", dir=TESTDATA) as raw:
        stage = Path(raw)
        targets = (audio_relative, *anlz_relatives)
        for source, relative in zip(sources, targets, strict=True):
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            source_before = _state(source)
            shutil.copyfile(source, target, follow_symlinks=False)
            source_after = _state(source)
            if source_after != source_before:
                raise RuntimeError("a Rekordbox fixture source changed while copying")
            if target.stat().st_size != source_before[1] or _digest(target) != source_before[3]:
                raise RuntimeError("an event-migration fixture copy failed verification")

        manifest = {
            "schema_version": 1,
            "content_id": content_id,
            "staging_audio": audio_relative.as_posix(),
            "anlz_files": [path.as_posix() for path in anlz_relatives],
        }
        staged_manifest = stage / MANIFEST.name
        staged_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if {path: _state(path) for path in sources} != before:
            raise RuntimeError("the Rekordbox event source set changed during copying")
        if _state(FIXTURE_DB) != fixture_db_before:
            raise RuntimeError("the private master.db fixture changed during selection")

        for relative in (audio_relative, *anlz_relatives):
            destination = TESTDATA / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / relative, destination)
        os.replace(staged_manifest, MANIFEST)

    return {
        "backup_confirmed": True,
        "rekordbox_process_guard": "closed",
        "selected_content": True,
        "audio_bytes": before[audio][1],
        "audio_sha256": before[audio][3],
        "anlz_files": len(anlz),
        "anlz_bytes": sum(before[path][1] for path in anlz),
        "sources_unchanged": True,
        "fixture_database_unchanged": True,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path.home() / "Library" / "Pioneer" / "rekordbox",
    )
    parser.add_argument("--backup-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = prepare_fixture(
            args.source_dir,
            backup_confirmed=args.backup_confirmed,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Event fixture preparation blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
