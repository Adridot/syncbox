#!/usr/bin/env python3
"""Install and restore approved disposable Rekordbox data directories safely."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SIDECAR_SRC = REPO / "sidecar" / "src"
TESTDATA = REPO / "poc" / "testdata"
MANUAL_ROOT = TESTDATA / "manual-validation-20260715"
SANDBOX_ROOT = MANUAL_ROOT / "rekordbox-sandboxes-final"
LIVE = Path.home() / "Library" / "Pioneer" / "rekordbox"
HOLD = LIVE.with_name("rekordbox.syncbox-live-hold-20260715")
MANIFEST = MANUAL_ROOT / "live-restore-manifest.json"
STATE = MANUAL_ROOT / "manual-swap-state.json"
CHECKED_SMARTFIX = MANUAL_ROOT / "checked-smartfix-data"
CHECKED_EVENT = MANUAL_ROOT / "checked-event-data"

sys.path.insert(0, str(SIDECAR_SRC))
sys.path.insert(0, str(REPO / "poc"))

from prepare_manual_rekordbox_sandboxes import (  # noqa: E402
    _assert_no_symlink_components,
    _copy_tree,
    _directories,
    _record_digest,
    _tree_state,
)
from syncbox.safety.process_guard import assert_mutation_ready  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.syncbox-write")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"temporary evidence file already exists: {temporary.name}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _saved_manifest() -> dict[str, tuple[int, int, int, str]]:
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        records = payload["files"]
        if not isinstance(records, dict):
            raise TypeError
        return {name: tuple(value) for name, value in records.items()}
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("the private live restore manifest is invalid") from error


def _preflight() -> None:
    _assert_no_symlink_components(MANUAL_ROOT, Path(MANUAL_ROOT.anchor))
    if MANUAL_ROOT.is_symlink() or not MANUAL_ROOT.is_dir():
        raise ValueError("the private manual evidence directory is unavailable")
    assert_mutation_ready(LIVE / "master.db")


def _remove_partial_copy(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("refusing to remove a symlinked partial data directory")
    if path.exists():
        shutil.rmtree(path)


def install_smartfix() -> dict[str, object]:
    _preflight()
    source = SANDBOX_ROOT / "smartfix-sandbox"
    if HOLD.exists() or HOLD.is_symlink():
        raise ValueError("the live hold directory already exists")
    if MANIFEST.exists() or MANIFEST.is_symlink() or STATE.exists() or STATE.is_symlink():
        raise ValueError("manual swap evidence already exists")
    if CHECKED_SMARTFIX.exists() or CHECKED_EVENT.exists():
        raise ValueError("a checked manual data directory already exists")

    live_state = _tree_state(LIVE)
    source_state = _tree_state(source)
    manifest = {
        "directories": len(_directories(LIVE)),
        "files": live_state,
        "schema": 1,
        "sha256": _record_digest(live_state),
    }
    _write_json(MANIFEST, manifest)
    os.replace(LIVE, HOLD)
    try:
        _copy_tree(source, LIVE)
        if _tree_state(LIVE) != source_state:
            raise RuntimeError("the installed Smart Fix sandbox differs from its source")
        assert_mutation_ready(LIVE / "master.db")
    except Exception:
        _remove_partial_copy(LIVE)
        os.replace(HOLD, LIVE)
        MANIFEST.unlink(missing_ok=True)
        raise

    result = {
        "live_original_held": True,
        "phase": "smartfix",
        "rekordbox_process_guard": "closed_before_and_after",
        "schema": 1,
        "source_files": len(source_state),
        "source_manifest_sha256": _record_digest(source_state),
    }
    _write_json(STATE, result)
    return result


def install_event() -> dict[str, object]:
    _preflight()
    source = SANDBOX_ROOT / "event-sandbox"
    if not HOLD.is_dir() or HOLD.is_symlink():
        raise ValueError("the untouched live hold directory is unavailable")
    if CHECKED_SMARTFIX.exists() or CHECKED_SMARTFIX.is_symlink():
        raise ValueError("the checked Smart Fix directory already exists")
    if CHECKED_EVENT.exists() or CHECKED_EVENT.is_symlink():
        raise ValueError("the checked event directory already exists")
    if _tree_state(HOLD) != _saved_manifest():
        raise RuntimeError("the held live Rekordbox directory changed")

    source_state = _tree_state(source)
    os.replace(LIVE, CHECKED_SMARTFIX)
    try:
        _copy_tree(source, LIVE)
        if _tree_state(LIVE) != source_state:
            raise RuntimeError("the installed event sandbox differs from its source")
        assert_mutation_ready(LIVE / "master.db")
    except Exception:
        _remove_partial_copy(LIVE)
        os.replace(CHECKED_SMARTFIX, LIVE)
        raise

    result = {
        "live_original_held": True,
        "phase": "event",
        "rekordbox_process_guard": "closed_before_and_after",
        "schema": 1,
        "source_files": len(source_state),
        "source_manifest_sha256": _record_digest(source_state),
        "smartfix_data_quarantined": True,
    }
    _write_json(STATE, result)
    return result


def restore() -> dict[str, object]:
    if not HOLD.is_dir() or HOLD.is_symlink():
        raise ValueError("the untouched live hold directory is unavailable")
    assert_mutation_ready(HOLD / "master.db")
    expected = _saved_manifest()
    if _tree_state(HOLD) != expected:
        raise RuntimeError("the held live Rekordbox directory changed")

    if LIVE.exists() or LIVE.is_symlink():
        if LIVE.is_symlink() or not LIVE.is_dir():
            raise ValueError("the active manual data path is not a real directory")
        quarantine = CHECKED_EVENT if CHECKED_SMARTFIX.exists() else CHECKED_SMARTFIX
        if quarantine.exists() or quarantine.is_symlink():
            raise ValueError(f"manual quarantine already exists: {quarantine.name}")
        os.replace(LIVE, quarantine)
    os.replace(HOLD, LIVE)

    restored = _tree_state(LIVE)
    if restored != expected:
        raise RuntimeError("the restored live Rekordbox directory differs from its manifest")
    assert_mutation_ready(LIVE / "master.db")
    result = {
        "files": len(restored),
        "live_manifest_sha256": _record_digest(restored),
        "live_restored_exactly": True,
        "phase": "restored",
        "rekordbox_process_guard": "closed_before_and_after",
        "schema": 1,
    }
    _write_json(STATE, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install-smartfix", "install-event", "restore"))
    args = parser.parse_args()
    try:
        if args.action == "install-smartfix":
            result = install_smartfix()
        elif args.action == "install-event":
            result = install_event()
        else:
            result = restore()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Manual Rekordbox swap blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
