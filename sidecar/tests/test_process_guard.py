"""Tests for the Rekordbox process guard (SPEC-UNIFIED 3.1 / 5.1).

The guard is the first line of the _mutate unit-of-work: it must detect the
real rekordbox / rekordboxAgent processes strictly (no lookalike false
positives), survive per-process psutil errors mid-iteration, and raise a
user-facing error whose wording never leaks a PID, an '/Applications/' path,
or a '--type=' process flag.
"""

import sys

import psutil
import pytest

from syncbox.safety import process_guard
from syncbox.safety.process_guard import (
    MutationBlockedError,
    assert_mutation_ready,
    is_rekordbox_running,
)

RB_APP_EXE = "/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox"
RB_AGENT_EXE = (
    "/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/"
    "rekordboxAgent.app/Contents/MacOS/rekordboxAgent"
)


class FakeProcess:
    """Minimal stand-in for psutil.Process records from process_iter."""

    def __init__(self, name=None, exe=None, error=None):
        self._info = {"name": name, "exe": exe}
        self._error = error

    @property
    def info(self):
        if self._error is not None:
            raise self._error
        return self._info


BENIGN = [
    FakeProcess(name="Finder", exe="/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder"),
    FakeProcess(name="python3.14", exe="/usr/local/bin/python3.14"),
]


def patch_processes(monkeypatch, procs, platform="darwin"):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(
        process_guard.psutil, "process_iter", lambda *a, **k: iter(procs)
    )


# --- macOS detection ---------------------------------------------------------


@pytest.mark.parametrize(
    "exe",
    [
        RB_APP_EXE,
        RB_AGENT_EXE,
        # Agent bundle installed outside the main app bundle.
        "/Library/Application Support/Pioneer/rekordboxAgent.app/Contents/MacOS/rekordboxAgent",
        # Case-insensitive bundle match.
        "/Users/dj/Applications/REKORDBOX.APP/Contents/MacOS/REKORDBOX",
        # Bare executable outside a bundle still matches on basename.
        "/usr/local/bin/rekordbox",
        "/opt/pioneer/rekordboxAgent",
    ],
)
def test_macos_positive_paths(monkeypatch, exe):
    patch_processes(monkeypatch, BENIGN + [FakeProcess(name="whatever", exe=exe)])
    assert is_rekordbox_running() is True


def test_macos_agent_only_is_detected(monkeypatch):
    # rekordboxAgent survives closing the Rekordbox window: the agent alone
    # must block mutations.
    patch_processes(monkeypatch, BENIGN + [FakeProcess(name="rekordboxAgent", exe=RB_AGENT_EXE)])
    assert is_rekordbox_running() is True


@pytest.mark.parametrize(
    "name,exe",
    [
        ("rekordbox_helper", "/usr/local/bin/rekordbox_helper"),
        ("viewer", "/Users/x/rekordbox-notes/viewer"),
        ("myrekordbox", "/Users/x/apps/myrekordbox"),
        ("rekordboxx", "/Users/x/tools/rekordboxx"),
        # On macOS the filter is path-based: a bare matching *name* with no
        # usable executable path must not match (anti-false-positive).
        ("rekordbox", None),
        ("rekordbox", ""),
    ],
)
def test_macos_lookalikes_do_not_match(monkeypatch, name, exe):
    patch_processes(monkeypatch, BENIGN + [FakeProcess(name=name, exe=exe)])
    assert is_rekordbox_running() is False


def test_macos_nothing_running(monkeypatch):
    patch_processes(monkeypatch, BENIGN)
    assert is_rekordbox_running() is False


# --- Windows detection (simulated platform) ----------------------------------


@pytest.mark.parametrize("name", ["rekordbox.exe", "rekordboxAgent.exe", "REKORDBOXAGENT.EXE"])
def test_windows_positive_names(monkeypatch, name):
    procs = BENIGN + [FakeProcess(name=name, exe=r"C:\Program Files\Pioneer\rekordbox\rekordbox.exe")]
    patch_processes(monkeypatch, procs, platform="win32")
    assert is_rekordbox_running() is True


@pytest.mark.parametrize("name", ["rekordbox_helper.exe", "rekordbox", "rekordboxAgent", None])
def test_windows_lookalikes_do_not_match(monkeypatch, name):
    patch_processes(monkeypatch, BENIGN + [FakeProcess(name=name)], platform="win32")
    assert is_rekordbox_running() is False


# --- psutil error resilience --------------------------------------------------


def test_access_denied_mid_iteration_keeps_scanning(monkeypatch):
    procs = [
        FakeProcess(error=psutil.AccessDenied(pid=1)),
        FakeProcess(error=psutil.NoSuchProcess(pid=2)),
        FakeProcess(error=psutil.ZombieProcess(pid=3)),
        FakeProcess(name="rekordbox", exe=RB_APP_EXE),
    ]
    patch_processes(monkeypatch, procs)
    assert is_rekordbox_running() is True


def test_all_processes_erroring_means_not_running(monkeypatch):
    procs = [
        FakeProcess(error=psutil.AccessDenied(pid=1)),
        FakeProcess(error=psutil.ZombieProcess(pid=2)),
    ]
    patch_processes(monkeypatch, procs)
    assert is_rekordbox_running() is False


# --- assert_mutation_ready ----------------------------------------------------


def test_mutation_ready_passes_when_rb_closed_and_db_exists(monkeypatch, tmp_path):
    db = tmp_path / "master.db"
    db.write_bytes(b"stub")
    patch_processes(monkeypatch, BENIGN)
    assert assert_mutation_ready(db) is None


def test_mutation_blocked_when_rekordbox_runs(monkeypatch, tmp_path):
    db = tmp_path / "master.db"
    db.write_bytes(b"stub")
    patch_processes(monkeypatch, BENIGN + [FakeProcess(exe=RB_APP_EXE)])
    with pytest.raises(MutationBlockedError):
        assert_mutation_ready(db)


def test_mutation_blocked_by_agent_alone(monkeypatch, tmp_path):
    db = tmp_path / "master.db"
    db.write_bytes(b"stub")
    patch_processes(monkeypatch, BENIGN + [FakeProcess(exe=RB_AGENT_EXE)])
    with pytest.raises(MutationBlockedError):
        assert_mutation_ready(db)


def test_missing_db_raises_file_not_found(monkeypatch, tmp_path):
    patch_processes(monkeypatch, BENIGN)
    with pytest.raises(FileNotFoundError):
        assert_mutation_ready(tmp_path / "does-not-exist" / "master.db")


def test_running_rb_takes_precedence_over_missing_db(monkeypatch, tmp_path):
    # SPEC-01 1.2 step (a) lists 'RB closed' first; the friendly block message
    # must win over the developer-facing missing-file error.
    patch_processes(monkeypatch, [FakeProcess(exe=RB_APP_EXE)])
    with pytest.raises(MutationBlockedError):
        assert_mutation_ready(tmp_path / "missing" / "master.db")


# --- message hygiene (SPEC-UNIFIED 3.1/5.1 wording constraint) ----------------


def test_blocked_message_hygiene(monkeypatch, tmp_path):
    db = tmp_path / "master.db"
    db.write_bytes(b"stub")
    patch_processes(monkeypatch, BENIGN + [FakeProcess(exe=RB_APP_EXE)])
    with pytest.raises(MutationBlockedError) as exc_info:
        assert_mutation_ready(db)
    msg = str(exc_info.value)
    assert msg, "the block message must not be empty"
    assert "/Applications/" not in msg
    assert "--type=" not in msg
    assert "pid" not in msg.lower()
    # No digits means no PID (and no leaked port/flag values) can survive.
    assert not any(ch.isdigit() for ch in msg)


def test_blocked_error_is_i18n_ready():
    err = MutationBlockedError()
    assert isinstance(err.message_key, str) and err.message_key
