#!/usr/bin/env python3
"""Write deterministic ZIP archives for macOS release directory trees."""

from __future__ import annotations

import os
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def source_date_epoch() -> int:
    """Return the required release epoch from the build environment."""
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        raise RuntimeError("SOURCE_DATE_EPOCH is required for release packaging")
    try:
        epoch = int(raw)
    except ValueError as error:
        raise RuntimeError("SOURCE_DATE_EPOCH must be an integer") from error
    if epoch < 315532800:
        raise RuntimeError("SOURCE_DATE_EPOCH predates the ZIP 1980 epoch")
    return epoch


def _zip_datetime(epoch: int) -> tuple[int, int, int, int, int, int]:
    value = datetime.fromtimestamp(epoch, timezone.utc)
    return (value.year, value.month, value.day, value.hour, value.minute, value.second)


def _archive_name(root: Path, path: Path, archive_root: str, is_dir: bool) -> str:
    if path == root:
        name = archive_root
    else:
        name = f"{archive_root}/{path.relative_to(root).as_posix()}"
    return f"{name}/" if is_dir else name


def _write_node(
    archive: zipfile.ZipFile,
    root: Path,
    path: Path,
    archive_root: str,
    timestamp: tuple[int, int, int, int, int, int],
) -> None:
    details = path.lstat()
    is_dir = stat.S_ISDIR(details.st_mode)
    info = zipfile.ZipInfo(
        _archive_name(root, path, archive_root, is_dir),
        timestamp,
    )
    info.create_system = 3
    info.extra = b""
    info.comment = b""

    if is_dir:
        info.external_attr = ((stat.S_IFDIR | 0o755) << 16) | 0x10
        info.compress_type = zipfile.ZIP_STORED
        payload = b""
    elif stat.S_ISLNK(details.st_mode):
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        info.compress_type = zipfile.ZIP_STORED
        payload = os.readlink(path).encode()
    elif stat.S_ISREG(details.st_mode):
        mode = 0o755 if stat.S_IMODE(details.st_mode) & 0o111 else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        payload = path.read_bytes()
    else:
        raise RuntimeError(f"unsupported release artifact node: {path}")

    archive.writestr(info, payload, compresslevel=9)


def write_tree_archive(archive_path: Path, root: Path, archive_root: str) -> None:
    """Archive one directory tree with stable order, metadata, and compression."""
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"release artifact root must be a directory: {root}")
    if not archive_root or "/" in archive_root or archive_root in {".", ".."}:
        raise RuntimeError(f"invalid archive root: {archive_root!r}")

    timestamp = _zip_datetime(source_date_epoch())
    nodes = [
        root,
        *sorted(
            root.rglob("*"),
            key=lambda path: path.relative_to(root).as_posix(),
        ),
    ]
    temporary = archive_path.with_suffix(f"{archive_path.suffix}.tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        for path in nodes:
            _write_node(archive, root, path, archive_root, timestamp)
    os.replace(temporary, archive_path)
