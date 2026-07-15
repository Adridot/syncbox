#!/usr/bin/env python3
"""Compare release artifacts from two absolute source roots byte for byte."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path


SOURCE_EXCLUDED_DIRECTORIES = {
    ".git",
    ".idea",
    ".playwright-mcp",
    ".pnpm-store",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}
SOURCE_EXCLUDED_FILES = {".DS_Store"}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact_paths(root: Path) -> tuple[Path, Path]:
    version = json.loads((root / "ui" / "package.json").read_text())["version"]
    base = (
        root
        / "shell"
        / "src-tauri"
        / "target"
        / "aarch64-apple-darwin"
        / "release"
        / "bundle"
        / "macos"
        / f"Syncbox-{version}-macos-arm64.zip"
    )
    component = (
        root
        / "optional-component"
        / "dist"
        / f"syncbox-deezer-component-{version}-macos-arm64.zip"
    )
    return base.resolve(strict=True), component.resolve(strict=True)


def _entry_record(archive: zipfile.ZipFile, item: zipfile.ZipInfo) -> dict[str, object]:
    return {
        "date_time": item.date_time,
        "mode": stat.S_IMODE(item.external_attr >> 16),
        "type": stat.S_IFMT(item.external_attr >> 16),
        "compression": item.compress_type,
        "extra_sha256": _digest(item.extra),
        "comment_sha256": _digest(item.comment),
        "payload_sha256": _digest(archive.read(item.filename)),
    }


def _zip_records(path: Path) -> dict[str, dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        return {
            item.filename: _entry_record(archive, item)
            for item in archive.infolist()
        }


def _source_records(root: Path) -> dict[str, dict[str, object]]:
    records = {}
    for current, directories, files in os.walk(root, topdown=True):
        current_path = Path(current)
        if current_path == root / "poc" / "testdata":
            directories[:] = []
            files = [name for name in files if name == "README.md"]
        directories[:] = sorted(
            name
            for name in directories
            if name not in SOURCE_EXCLUDED_DIRECTORIES
            and (name != "testdata" or current_path == root / "poc")
        )
        for name in sorted(files):
            if name in SOURCE_EXCLUDED_FILES:
                continue
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            details = path.lstat()
            if stat.S_ISLNK(details.st_mode):
                payload = os.readlink(path).encode()
                kind = "symlink"
            elif stat.S_ISREG(details.st_mode):
                payload = path.read_bytes()
                kind = "file"
            else:
                raise ValueError(f"unsupported source node: {relative}")
            records[relative] = {
                "kind": kind,
                "mode": stat.S_IMODE(details.st_mode),
                "size": len(payload),
                "sha256": _digest(payload),
            }
    return records


def _record_set_digest(records: dict[str, dict[str, object]]) -> str:
    payload = json.dumps(
        records,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return _digest(payload)


def _differences(first: Path, second: Path) -> list[dict[str, object]]:
    first_records = _zip_records(first)
    second_records = _zip_records(second)
    differences = []
    for name in sorted(set(first_records) | set(second_records)):
        left = first_records.get(name)
        right = second_records.get(name)
        if left != right:
            differences.append({"entry": name, "first": left, "second": right})
    if not differences and first.read_bytes() != second.read_bytes():
        differences.append(
            {
                "entry": "<ZIP container>",
                "first": {"sha256": _digest(first.read_bytes())},
                "second": {"sha256": _digest(second.read_bytes())},
            }
        )
    return differences[:20]


def compare_roots(first_root: Path, second_root: Path) -> dict[str, object]:
    first_root = first_root.resolve(strict=True)
    second_root = second_root.resolve(strict=True)
    if first_root == second_root:
        raise ValueError("reproducibility roots must be different absolute paths")

    first_source = _source_records(first_root)
    second_source = _source_records(second_root)
    source_identical = first_source == second_source
    source_differences = []
    for name in sorted(set(first_source) | set(second_source)):
        left = first_source.get(name)
        right = second_source.get(name)
        if left != right:
            source_differences.append({"path": name, "first": left, "second": right})
        if len(source_differences) == 20:
            break

    results = []
    for first, second in zip(
        _artifact_paths(first_root),
        _artifact_paths(second_root),
        strict=True,
    ):
        first_bytes = first.read_bytes()
        second_bytes = second.read_bytes()
        first_records = _zip_records(first)
        second_records = _zip_records(second)
        differences = _differences(first, second)
        results.append(
            {
                "artifact": first.name,
                "first_bytes": len(first_bytes),
                "second_bytes": len(second_bytes),
                "first_sha256": _digest(first_bytes),
                "second_sha256": _digest(second_bytes),
                "byte_identical": first_bytes == second_bytes,
                "unpacked_tree_identical": first_records == second_records,
                "unpacked_tree_sha256": _record_set_digest(first_records),
                "entry_differences": differences,
            }
        )
    return {
        "different_absolute_roots": True,
        "source": {
            "file_count": len(first_source),
            "first_sha256": _record_set_digest(first_source),
            "second_sha256": _record_set_digest(second_source),
            "identical": source_identical,
            "differences": source_differences,
        },
        "artifacts": results,
        "ok": source_identical
        and all(
            item["byte_identical"] and item["unpacked_tree_identical"]
            for item in results
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare base and optional release ZIPs from two source roots."
    )
    parser.add_argument("first_root", type=Path)
    parser.add_argument("second_root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = compare_roots(args.first_root, args.second_root)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
