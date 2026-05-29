from types import SimpleNamespace

import pytest

from app import safety


def test_find_rekordbox_processes_parses_pgrep(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "123 /Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox\n"
                "456 node /tmp/sync playlists rekordbox/node_modules/.bin/vite\n"
            ),
        )

    monkeypatch.setattr(safety.subprocess, "run", fake_run)

    processes = safety.find_rekordbox_processes()

    assert len(processes) == 1
    assert processes[0].pid == 123


def test_assert_mutation_ready_blocks_when_process_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        safety,
        "find_rekordbox_processes",
        lambda: [safety.RunningProcess(pid=123, command="rekordbox")],
    )

    with pytest.raises(safety.RekordboxRunningError):
        safety.assert_rekordbox_can_mutate()
