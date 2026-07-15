#!/usr/bin/env python3
"""Prepare an ignored, disposable Smart Fix database for manual Rekordbox checks."""

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
SOURCE_DB = TESTDATA / "master.db"
SOURCE_XML = TESTDATA / "masterPlaylists6.xml"

sys.path.insert(0, str(SIDECAR_SRC))
sys.path.insert(0, str(REPO / "poc"))

from syncbox import rb, smartfixes_run  # noqa: E402
from syncbox.safety.process_guard import assert_mutation_ready  # noqa: E402

from copy_rekordbox_fixtures import _digest, _state  # noqa: E402


def _output_path(raw: Path) -> Path:
    output = raw.expanduser().absolute()
    root = TESTDATA.absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as error:
        raise ValueError("manual fixture output must stay below poc/testdata") from error
    if not relative.parts:
        raise ValueError("manual fixture output cannot replace poc/testdata")

    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError("manual fixture output must not traverse a symlink")
    if output.exists() or output.is_symlink():
        raise ValueError("manual fixture output already exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError("manual fixture output parent must be a real directory")
    return output


def prepare(output: Path, *, backup_confirmed: bool) -> dict[str, object]:
    assert_mutation_ready(SOURCE_DB)
    if not backup_confirmed:
        raise ValueError("a complete Rekordbox library backup must be confirmed")
    output = _output_path(output)

    sources = (SOURCE_DB, SOURCE_XML)
    before = {path: _state(path) for path in sources}
    stage = Path(tempfile.mkdtemp(prefix="manual-smartfix-", dir=output.parent))
    try:
        rekordbox = stage / "rekordbox"
        rekordbox.mkdir()
        for source in sources:
            source_before = _state(source)
            destination = rekordbox / source.name
            shutil.copyfile(source, destination, follow_symlinks=False)
            if _state(source) != source_before:
                raise RuntimeError(f"fixture source changed while copying: {source.name}")
            if (
                destination.stat().st_size != source_before[1]
                or _digest(destination) != source_before[3]
            ):
                raise RuntimeError(f"manual fixture copy failed: {source.name}")

        db_path = rekordbox / SOURCE_DB.name
        backups = stage / "backups"
        storage = stage / "storage"
        storage.mkdir()
        cache = rb.SnapshotCache(db_path)
        preview = smartfixes_run.dry_run(cache, storage)
        if not preview["payload"]:
            raise RuntimeError("the private fixture has no supported Smart Fix")
        result = smartfixes_run.execute(
            db_path,
            backups,
            cache,
            storage,
            preview,
        )
        if result["fields_applied"] != len(preview["payload"]):
            raise RuntimeError("Smart Fix result count does not match the preview")

        written = {row["content_id"]: row for row in cache.get(storage)}
        for change in preview["payload"]:
            if written[change["content_id"]][change["field"]] != change["after"]:
                raise RuntimeError("a previewed Smart Fix value was not written exactly")
        if smartfixes_run.dry_run(cache, storage)["payload"]:
            raise RuntimeError("Smart Fix preparation did not reach an idempotent fixpoint")
        if {path: _state(path) for path in sources} != before:
            raise RuntimeError("a private source fixture changed during preparation")

        database_files = []
        for name in ("master.db", "master.db-wal", "master.db-shm", "master.db-journal"):
            path = rekordbox / name
            if not path.exists():
                continue
            state = _state(path)
            database_files.append(
                {"bytes": state[1], "name": name, "sha256": state[3]}
            )
        evidence = {
            "backup_confirmed": True,
            "database_files": database_files,
            "fields_applied": result["fields_applied"],
            "idempotent": True,
            "rekordbox_process_guard": "closed",
            "schema": 1,
            "source_fixtures_unchanged": True,
            "tracks_touched": result["tracks_touched"],
        }
        (stage / "evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(stage, output)
        return evidence
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--backup-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        evidence = prepare(args.output, backup_confirmed=args.backup_confirmed)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Manual Smart Fix fixture preparation blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
