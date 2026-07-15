#!/usr/bin/env python3
"""Build verified disposable Rekordbox data directories for manual checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
SIDECAR_SRC = REPO / "sidecar" / "src"
TESTDATA = REPO / "poc" / "testdata"
MANUAL_ROOT = TESTDATA / "manual-validation-20260715"
SMARTFIX_SOURCE = MANUAL_ROOT / "smartfix-final" / "rekordbox"
EVENT_SOURCE = MANUAL_ROOT / "event-canonical-final" / "fixture"
DATABASE_NAMES = ("master.db", "master.db-wal", "master.db-shm")
SANDBOX_SET_NAME = "rekordbox-sandboxes-final"
MANIFEST_KEYS = {"schema_version", "content_id", "staging_audio", "anlz_files"}
ANLZ_SUFFIXES = {".DAT", ".EXT", ".2EX"}

sys.path.insert(0, str(SIDECAR_SRC))

from syncbox.safety.process_guard import assert_mutation_ready  # noqa: E402


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _file_state(path: Path) -> tuple[int, int, int, str]:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode):
        raise ValueError(f"sandbox source must be a regular file: {path.name}")
    return (
        stat.S_IMODE(details.st_mode),
        details.st_size,
        details.st_mtime_ns,
        _digest(path),
    )


def _assert_no_symlink_components(path: Path, anchor: Path) -> None:
    current = anchor
    for part in path.relative_to(anchor).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"sandbox path traverses a symlink: {path.name}")


def _files(root: Path) -> tuple[Path, ...]:
    _assert_no_symlink_components(root, Path(root.anchor))
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"sandbox source must be a real directory: {root.name}")
    result = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories.sort()
        filenames.sort()
        for name in directories:
            path = current_path / name
            details = path.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                raise ValueError(f"sandbox source contains a non-directory: {path.name}")
        for name in filenames:
            path = current_path / name
            _file_state(path)
            result.append(path)
    return tuple(result)


def _directories(root: Path) -> tuple[Path, ...]:
    result = []
    for current, directories, _filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories.sort()
        for name in directories:
            path = current_path / name
            details = path.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                raise ValueError(f"sandbox source contains a non-directory: {path.name}")
            result.append(path)
    return tuple(result)


def _tree_state(root: Path) -> dict[str, tuple[int, int, int, str]]:
    return {
        path.relative_to(root).as_posix(): _file_state(path)
        for path in _files(root)
    }


def _record_digest(records: dict[str, tuple[int, int, int, str]]) -> str:
    payload = json.dumps(records, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"sandbox destination already exists: {destination.name}")
    source_before = _tree_state(source)
    directories = _directories(source)
    destination.mkdir()
    for directory in directories:
        (destination / directory.relative_to(source)).mkdir()
    for path in _files(source):
        relative = path.relative_to(source)
        target = destination / relative
        before = _file_state(path)
        shutil.copy2(path, target, follow_symlinks=False)
        after = _file_state(path)
        if after != before:
            raise RuntimeError(f"sandbox source changed while copying: {relative}")
        copied = _file_state(target)
        if copied[1] != before[1] or copied[3] != before[3]:
            raise RuntimeError(f"sandbox copy verification failed: {relative}")
    for directory in reversed(directories):
        shutil.copystat(
            directory,
            destination / directory.relative_to(source),
            follow_symlinks=False,
        )
    shutil.copystat(source, destination, follow_symlinks=False)
    if _tree_state(source) != source_before:
        raise RuntimeError("sandbox source tree changed while copying")
    if _tree_state(destination) != source_before:
        raise RuntimeError("sandbox copied tree differs from its source")
    if len(_directories(destination)) != len(directories):
        raise RuntimeError("sandbox copied directory set is incomplete")


def _overlay(source: Path, target: Path) -> None:
    _assert_no_symlink_components(source, Path(source.anchor))
    _assert_no_symlink_components(target, Path(target.anchor))
    before = _file_state(source)
    temporary = target.with_name(f".{target.name}.syncbox-copy")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"temporary overlay already exists: {temporary.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, temporary, follow_symlinks=False)
    if _file_state(source) != before:
        raise RuntimeError(f"overlay source changed while copying: {source.name}")
    copied = _file_state(temporary)
    if copied[1] != before[1] or copied[3] != before[3]:
        raise RuntimeError(f"overlay copy verification failed: {source.name}")
    os.replace(temporary, target)
    applied = _file_state(target)
    if applied[1] != before[1] or applied[3] != before[3]:
        raise RuntimeError(f"overlay verification failed: {source.name}")


def _apply_database(source: Path, rekordbox: Path) -> None:
    for name in DATABASE_NAMES:
        source_path = source / name
        target = rekordbox / name
        if source_path.exists() or source_path.is_symlink():
            _overlay(source_path, target)
        elif name == "master.db":
            raise ValueError("event database fixture is missing master.db")
        elif target.exists() or target.is_symlink():
            _file_state(target)
            target.unlink()
    journal = rekordbox / "master.db-journal"
    if journal.exists() or journal.is_symlink():
        journal.unlink()
    _overlay(source / "masterPlaylists6.xml", rekordbox / "masterPlaylists6.xml")


def _event_anlz_paths() -> tuple[Path, ...]:
    manifest_path = EVENT_SOURCE / "event-migration.json"
    _assert_no_symlink_components(manifest_path, Path(manifest_path.anchor))
    _file_state(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"event migration manifest is invalid: {error}") from error
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise ValueError("event migration manifest keys differ from the fixture contract")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("event migration manifest schema_version must be 1")
    values = manifest["anlz_files"]
    if not isinstance(values, list) or not values:
        raise ValueError("event migration anlz_files must be a non-empty array")

    paths = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value or value != value.strip() or "\\" in value:
            raise ValueError(f"anlz_files[{index}] must be a relative POSIX path")
        pure = PurePosixPath(value)
        if (
            pure.is_absolute()
            or pure.as_posix() != value
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise ValueError(f"anlz_files[{index}] must be a normalized relative path")
        path = Path(*pure.parts)
        if (
            len(path.parts) < 2
            or path.parts[0] != "share"
            or not path.name.upper().startswith("ANLZ")
            or path.suffix.upper() not in ANLZ_SUFFIXES
        ):
            raise ValueError("each anlz_files entry must match share/**/ANLZ*.{DAT,EXT,2EX}")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise ValueError("event migration anlz_files must not contain duplicates")
    return tuple(paths)


def prepare(source: Path, output_root: Path, *, backup_confirmed: bool) -> dict:
    source = source.expanduser().absolute()
    output_root = output_root.expanduser().absolute()
    _assert_no_symlink_components(source, Path(source.anchor))
    _assert_no_symlink_components(output_root, Path(output_root.anchor))
    assert_mutation_ready(source / "master.db")
    if not backup_confirmed:
        raise ValueError("a complete Rekordbox library backup must be confirmed")
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError("manual output root must be a real directory")
    if not output_root.is_relative_to(TESTDATA.absolute()):
        raise ValueError("manual output root must stay below poc/testdata")

    final_root = output_root / SANDBOX_SET_NAME
    if final_root.exists() or final_root.is_symlink():
        raise ValueError(f"manual sandbox output already exists: {final_root.name}")

    source_before = _tree_state(source)
    smartfix_source_before = _tree_state(SMARTFIX_SOURCE)
    event_source_before = _tree_state(EVENT_SOURCE)
    anlz_paths = _event_anlz_paths()
    with tempfile.TemporaryDirectory(prefix="rekordbox-sandboxes-", dir=output_root) as raw:
        stage = Path(raw) / SANDBOX_SET_NAME
        stage.mkdir()
        smartfix = stage / "smartfix-sandbox"
        event = stage / "event-sandbox"
        _copy_tree(source, smartfix)
        _copy_tree(smartfix, event)

        _apply_database(SMARTFIX_SOURCE, smartfix)
        _apply_database(EVENT_SOURCE, event)
        for relative in anlz_paths:
            _overlay(EVENT_SOURCE / relative, event / relative)

        assert_mutation_ready(source / "master.db")
        source_after = _tree_state(source)
        if source_after != source_before:
            raise RuntimeError("the live Rekordbox data directory changed during copying")
        if _tree_state(SMARTFIX_SOURCE) != smartfix_source_before:
            raise RuntimeError("the Smart Fix source changed during copying")
        if _tree_state(EVENT_SOURCE) != event_source_before:
            raise RuntimeError("the event migration source changed during copying")
        smartfix_state = _tree_state(smartfix)
        event_state = _tree_state(event)
        evidence = {
            "backup_confirmed": True,
            "event_files": len(event_state),
            "event_manifest_sha256": _record_digest(event_state),
            "live_files": len(source_before),
            "live_directories": len(_directories(source)),
            "live_manifest_sha256": _record_digest(source_before),
            "live_source_unchanged": True,
            "rekordbox_process_guard": "closed_before_and_after",
            "schema": 1,
            "fixture_sources_unchanged": True,
            "smartfix_files": len(smartfix_state),
            "smartfix_manifest_sha256": _record_digest(smartfix_state),
        }
        (stage / "sandbox-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(stage, final_root)
    return evidence


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path.home() / "Library" / "Pioneer" / "rekordbox",
    )
    parser.add_argument("--output-root", type=Path, default=MANUAL_ROOT)
    parser.add_argument("--backup-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        evidence = prepare(
            args.source_dir,
            args.output_root,
            backup_confirmed=args.backup_confirmed,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Manual Rekordbox sandbox preparation blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
