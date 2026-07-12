#!/usr/bin/env python3
"""Run the exact real-Rekordbox integration set against local copied fixtures."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SIDECAR = REPO / "sidecar"
PYTHON = SIDECAR / ".venv" / "bin" / "python"
TESTDATA = REPO / "poc" / "testdata"

NODE_IDS = (
    "tests/test_rb.py::test_snapshot_reads_real_db_readonly",
    "tests/test_rb.py::test_snapshot_filters_soft_deleted",
    "tests/test_mutate.py::test_integration_soft_delete_round_trip_on_real_db",
    "tests/test_rb_write.py::test_full_write_flow_through_mutate",
    "tests/test_rb_write.py::test_reassign_memberships_moves_active_links_to_keeper",
    "tests/test_rb_write.py::test_smartfixes_runner_end_to_end",
    "tests/test_library_service.py::test_apply_to_rekordbox_tags_and_imports",
    "tests/test_library_service.py::test_apply_conflicts_on_missing_mytag_and_writes_nothing",
    "tests/test_events_service.py::test_event_lifecycle_on_real_db",
    "tests/test_missing_service.py::test_relink_collection_file_writes_stored_form_and_preserves_links",
)

REQUIRED = (TESTDATA / "master.db", TESTDATA / "masterPlaylists6.xml")
OPTIONAL = (
    TESTDATA / "master.db-wal",
    TESTDATA / "master.db-shm",
    TESTDATA / "master.db-journal",
)


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _fixture_state() -> dict[Path, tuple[int, int, str]]:
    for path in REQUIRED:
        if path.is_symlink():
            raise ValueError(f"required fixture must not be a symlink: {path}")
        if not path.is_file():
            raise ValueError(f"required fixture is missing: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"required fixture is empty: {path}")

    paths = list(REQUIRED)
    for path in OPTIONAL:
        if path.is_symlink():
            raise ValueError(f"optional fixture must not be a symlink: {path}")
        if path.exists() and not path.is_file():
            raise ValueError(f"optional fixture is not a regular file: {path}")
        if path.is_file():
            paths.append(path)

    state = {}
    for path in paths:
        stat = path.stat()
        state[path] = (stat.st_size, stat.st_mtime_ns, _digest(path))
    return state


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ten copied-fixture Rekordbox integration tests."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list the selected node IDs")
    mode.add_argument("--check", action="store_true", help="validate fixtures only")
    return parser.parse_args()


def _clean_env() -> dict[str, str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def main() -> int:
    args = _parse_args()
    if args.list:
        print("\n".join(NODE_IDS))
        return 0

    if not PYTHON.is_file() or not os.access(PYTHON, os.X_OK):
        print(
            f"Preflight failed: project Python is missing or not executable: {PYTHON}",
            file=sys.stderr,
        )
        return 2

    env = _clean_env()
    pytest_probe = subprocess.run(
        [str(PYTHON), "-I", "-B", "-c", "import pytest"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if pytest_probe.returncode != 0:
        print("Preflight failed: pytest is not importable in the project venv.", file=sys.stderr)
        return 2

    try:
        before = _fixture_state()
    except (OSError, ValueError) as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
        return 2

    print(f"Fixture preflight passed for {len(before)} file(s).")
    if args.check:
        return 0

    result = None
    run_error = None
    try:
        with tempfile.TemporaryDirectory(prefix="syncbox-real-rb-") as base_temp:
            command = [
                str(PYTHON),
                "-m",
                "pytest",
                "-q",
                "-rs",
                "--color=no",
                "-p",
                "no:cacheprovider",
                f"--basetemp={base_temp}",
                *NODE_IDS,
            ]
            print(f"Running: {shlex.join(command)}")
            result = subprocess.run(
                command,
                cwd=SIDECAR,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
    except BaseException as error:
        run_error = error

    try:
        after = _fixture_state()
    except (OSError, ValueError) as error:
        print(f"Fixture verification failed: {error}", file=sys.stderr)
        return 3
    if after != before:
        print("Fixture verification failed: a source fixture changed.", file=sys.stderr)
        return 3

    if run_error is not None:
        raise run_error
    assert result is not None

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        return result.returncode

    output = f"{result.stdout}\n{result.stderr}"
    if (
        re.search(r"(?m)^SKIPPED ", output)
        or re.search(r"\b\d+ skipped\b", output)
        or not re.search(r"\b10 passed\b", output)
    ):
        print(
            "Fixture run failed: pytest did not report exactly ten passes with zero skips.",
            file=sys.stderr,
        )
        return 4

    print("All ten real-Rekordbox tests passed; source fixtures are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
