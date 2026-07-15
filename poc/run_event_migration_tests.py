#!/usr/bin/env python3
"""Run the retained-event-track migration test against copied local fixtures."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
SIDECAR = REPO / "sidecar"
SIDECAR_SRC = SIDECAR / "src"
PYTHON = SIDECAR / ".venv" / "bin" / "python"
TESTDATA = REPO / "poc" / "testdata"
MANIFEST = TESTDATA / "event-migration.json"
FIXTURE_ENV = "SYNCBOX_EVENT_MIGRATION_FIXTURE"
STORAGE_ENV = "SYNCBOX_EVENT_MIGRATION_STORAGE_ROOT"
NODE_ID = "tests/test_events_service.py::test_retained_track_migration_on_real_db"
MANUAL_VOLUME = Path("/Volumes/SyncboxPOC")

REQUIRED_NAMES = ("master.db", "masterPlaylists6.xml")
OPTIONAL_NAMES = ("master.db-wal", "master.db-shm", "master.db-journal")
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


def _relative_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty relative POSIX path")
    if "\\" in value:
        raise ValueError(f"{field} must use POSIX path separators: {value!r}")

    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{field} must be a normalized relative path: {value!r}")
    return Path(*path.parts)


def _assert_regular_fixture(path: Path) -> None:
    try:
        relative = path.relative_to(TESTDATA)
    except ValueError as error:
        raise ValueError(f"fixture is outside poc/testdata: {path}") from error

    current = TESTDATA
    if current.is_symlink():
        raise ValueError(f"fixture path must not traverse a symlink: {current}")
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"fixture path must not traverse a symlink: {current}")

    if not path.is_file():
        raise ValueError(f"fixture is missing or not a regular file: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"fixture is empty: {path}")


def _fixture_paths() -> tuple[dict[str, object], tuple[Path, ...]]:
    _assert_regular_fixture(MANIFEST)
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"event migration manifest is not valid UTF-8 JSON: {error}"
        ) from error

    if not isinstance(manifest, dict):
        raise ValueError("event migration manifest must be a JSON object")
    if set(manifest) != MANIFEST_KEYS:
        missing = sorted(MANIFEST_KEYS - set(manifest))
        extra = sorted(set(manifest) - MANIFEST_KEYS)
        raise ValueError(
            f"event migration manifest keys differ; missing={missing}, extra={extra}"
        )
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("event migration manifest schema_version must be 1")
    content_id = manifest["content_id"]
    if (
        not isinstance(content_id, str)
        or not content_id
        or content_id != content_id.strip()
    ):
        raise ValueError(
            "event migration manifest content_id must be a non-empty string"
        )

    audio = _relative_path(manifest["staging_audio"], "staging_audio")
    if len(audio.parts) < 2 or audio.parts[0] != "audio":
        raise ValueError("staging_audio must be below audio/")

    anlz_values = manifest["anlz_files"]
    if not isinstance(anlz_values, list) or not anlz_values:
        raise ValueError("anlz_files must be a non-empty JSON array")
    anlz_paths = tuple(
        _relative_path(value, f"anlz_files[{index}]")
        for index, value in enumerate(anlz_values)
    )
    if len(set(anlz_paths)) != len(anlz_paths):
        raise ValueError("anlz_files must not contain duplicates")
    for path in anlz_paths:
        if (
            len(path.parts) < 2
            or path.parts[0] != "share"
            or not path.name.upper().startswith("ANLZ")
            or path.suffix.upper() not in ANLZ_SUFFIXES
        ):
            raise ValueError(
                "each anlz_files entry must match share/**/ANLZ*.{DAT,EXT,2EX}: "
                f"{path.as_posix()}"
            )

    paths = [MANIFEST, *(TESTDATA / name for name in REQUIRED_NAMES), TESTDATA / audio]
    paths.extend(TESTDATA / path for path in anlz_paths)
    paths.extend(
        TESTDATA / name
        for name in OPTIONAL_NAMES
        if (TESTDATA / name).exists() or (TESTDATA / name).is_symlink()
    )
    for path in paths:
        _assert_regular_fixture(path)
    return manifest, tuple(paths)


def _fixture_state(paths: tuple[Path, ...]) -> dict[Path, tuple[int, int, int, str]]:
    state = {}
    for path in paths:
        _assert_regular_fixture(path)
        stat = path.stat()
        state[path] = (stat.st_mode, stat.st_size, stat.st_mtime_ns, _digest(path))
    return state


def _copy_fixtures(paths: tuple[Path, ...], destination: Path) -> Path:
    for source in paths:
        target = destination / source.relative_to(TESTDATA)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
        target.chmod(target.stat().st_mode | 0o200)
    # macOS exposes /var through /private/var. Pass the canonical spelling so
    # strict Path equality matches the resolved ANLZ paths returned downstream.
    return (destination / MANIFEST.name).resolve(strict=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the copied-fixture retained-event-track migration test."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list the selected node ID")
    mode.add_argument("--check", action="store_true", help="validate fixtures only")
    parser.add_argument(
        "--retain",
        type=Path,
        help=(
            "retain the mutated manual fixture below poc/testdata; requires the "
            "dedicated /Volumes/SyncboxPOC test volume"
        ),
    )
    return parser.parse_args()


def _retained_output(raw: Path) -> Path:
    output = raw.expanduser().absolute()
    root = TESTDATA.absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as error:
        raise ValueError("retained output must stay below poc/testdata") from error
    if not relative.parts:
        raise ValueError("retained output cannot replace poc/testdata")

    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError("retained output must not traverse a symlink")
    if output.exists() or output.is_symlink():
        raise ValueError("retained output already exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError("retained output parent must be a real directory")
    return output


def _manual_volume() -> Path:
    volume = MANUAL_VOLUME
    if volume.is_symlink() or not volume.is_dir():
        raise ValueError("the dedicated /Volumes/SyncboxPOC test volume is not mounted")
    for name in ("_syncbox", "rekordbox"):
        if (volume / name).exists() or (volume / name).is_symlink():
            raise ValueError(f"the dedicated test volume already contains {name}")
    return volume


@contextmanager
def _runtime(retain: Path | None):
    if retain is None:
        with tempfile.TemporaryDirectory(prefix="syncbox-event-migration-") as raw:
            yield Path(raw)
        return
    output = _retained_output(retain)
    output.mkdir()
    yield output


def _clean_env() -> dict[str, str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for name in (
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTHONHOME",
        "PYTHONPATH",
        "SYNCBOX_DATA_DIR",
        FIXTURE_ENV,
        STORAGE_ENV,
    ):
        env.pop(name, None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def main() -> int:
    args = _parse_args()
    if args.retain is not None and (args.list or args.check):
        print("--retain cannot be combined with --list or --check", file=sys.stderr)
        return 2
    if args.list:
        print(NODE_ID)
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
        print(
            "Preflight failed: pytest is not importable in the project venv.",
            file=sys.stderr,
        )
        return 2

    try:
        manifest, paths = _fixture_paths()
        before = _fixture_state(paths)
    except (OSError, ValueError) as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
        return 2

    print(
        f"Fixture preflight passed for content {manifest['content_id']} "
        f"and {len(before)} file(s)."
    )
    if args.check:
        return 0

    manual_volume = None
    if args.retain is not None:
        try:
            assert_mutation_ready(TESTDATA / "master.db")
            manual_volume = _manual_volume()
        except (OSError, RuntimeError, ValueError) as error:
            print(f"Manual retention preflight failed: {error}", file=sys.stderr)
            return 2

    result = None
    run_error = None
    try:
        with _runtime(args.retain) as runtime:
            fixture_copy = _copy_fixtures(paths, runtime / "fixture")
            process_temp = runtime / "tmp"
            process_temp.mkdir()
            run_env = {
                **env,
                FIXTURE_ENV: str(fixture_copy),
                "TMPDIR": str(process_temp),
                "TMP": str(process_temp),
                "TEMP": str(process_temp),
            }
            if manual_volume is not None:
                run_env[STORAGE_ENV] = str(manual_volume)
            command = [
                str(PYTHON),
                "-m",
                "pytest",
                "-q",
                "-rs",
                "--color=no",
                "-p",
                "no:cacheprovider",
                f"--basetemp={runtime / 'pytest'}",
                NODE_ID,
            ]
            print(f"Running: {shlex.join(command)}")
            result = subprocess.run(
                command,
                cwd=SIDECAR,
                env=run_env,
                capture_output=True,
                text=True,
                check=False,
            )
    except BaseException as error:
        run_error = error

    try:
        after = _fixture_state(paths)
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
    forbidden_outcome = re.search(
        r"\b\d+ (?:skipped|xfailed|xpassed|failed|errors?|deselected)\b", output
    )
    if forbidden_outcome or not re.search(r"\b1 passed\b", output):
        print(
            "Fixture run failed: pytest did not report exactly one pass "
            "with zero skips.",
            file=sys.stderr,
        )
        return 4

    print("The retained-track migration test passed; source fixtures are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
