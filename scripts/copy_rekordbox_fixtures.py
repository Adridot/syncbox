#!/usr/bin/env python3
"""Copy private Rekordbox fixtures after strict process and backup checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SIDECAR_SRC = REPO / "sidecar" / "src"
TESTDATA = REPO / "sidecar" / "tests" / "testdata"
SOURCE_NAMES = (
    "master.db",
    "masterPlaylists6.xml",
    "master.db-wal",
    "master.db-shm",
    "master.db-journal",
)
REQUIRED_NAMES = frozenset(SOURCE_NAMES[:2])

sys.path.insert(0, str(SIDECAR_SRC))

from syncbox.safety.process_guard import assert_mutation_ready  # noqa: E402


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _state(path: Path) -> tuple[int, int, int, str]:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode):
        raise ValueError(f"fixture source must be a regular file: {path.name}")
    return (
        stat.S_IMODE(details.st_mode),
        details.st_size,
        details.st_mtime_ns,
        _digest(path),
    )


def _assert_no_symlink_components(path: Path, anchor: Path) -> None:
    relative = path.relative_to(anchor)
    current = anchor
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"fixture path traverses a symlink: {path.name}")


def _source_files(source_dir: Path) -> tuple[Path, ...]:
    source_dir = source_dir.expanduser().absolute()
    anchor = Path(source_dir.anchor)
    _assert_no_symlink_components(source_dir, anchor)

    selected = []
    for name in SOURCE_NAMES:
        path = source_dir / name
        if path.exists() or path.is_symlink():
            _assert_no_symlink_components(path, anchor)
            details = _state(path)
            if name not in REQUIRED_NAMES and details[1] == 0:
                continue
            selected.append(path)
        elif name in REQUIRED_NAMES:
            raise ValueError(f"required Rekordbox source file is missing: {name}")
    return tuple(selected)


def copy_fixtures(source_dir: Path, *, backup_confirmed: bool) -> dict[str, object]:
    assert_mutation_ready(source_dir.expanduser() / "master.db")
    if not backup_confirmed:
        raise ValueError("a complete Rekordbox library backup must be confirmed")
    sources = _source_files(source_dir)

    if TESTDATA.is_symlink() or not TESTDATA.is_dir():
        raise ValueError("sidecar/tests/testdata must be a real directory")
    collisions = [path.name for path in sources if (TESTDATA / path.name).exists()]
    if collisions:
        raise ValueError(f"private fixture already exists: {', '.join(collisions)}")

    initial = {path: _state(path) for path in sources}
    copied = []
    with tempfile.TemporaryDirectory(prefix="fixture-copy-", dir=TESTDATA) as raw_stage:
        stage = Path(raw_stage)
        for source in sources:
            before = _state(source)
            target = stage / source.name
            shutil.copyfile(source, target, follow_symlinks=False)
            after = _state(source)
            if after != before:
                raise RuntimeError(f"Rekordbox source changed while copying: {source.name}")
            if _digest(target) != before[3] or target.stat().st_size != before[1]:
                raise RuntimeError(f"fixture copy verification failed: {source.name}")
            copied.append(target)

        final = {path: _state(path) for path in sources}
        if final != initial:
            raise RuntimeError("Rekordbox source set changed during fixture creation")
        for target in copied:
            os.replace(target, TESTDATA / target.name)

    evidence = {
        "backup_confirmed": True,
        "rekordbox_process_guard": "closed",
        "files": [
            {
                "name": path.name,
                "bytes": initial[path][1],
                "sha256": initial[path][3],
            }
            for path in sources
        ],
        "source_unchanged": True,
    }
    return evidence


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create ignored private fixtures from a closed Rekordbox library."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path.home() / "Library" / "Pioneer" / "rekordbox",
    )
    parser.add_argument(
        "--backup-confirmed",
        action="store_true",
        help="confirm that a complete Rekordbox library backup already exists",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = copy_fixtures(
            args.source_dir,
            backup_confirmed=args.backup_confirmed,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Fixture copy blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
