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


def test_assert_mutation_message_is_friendly_and_flags_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        safety,
        "find_rekordbox_processes",
        lambda: [
            safety.RunningProcess(pid=1, command="/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox"),
            safety.RunningProcess(pid=2, command="/Applications/rekordbox 7/Contents/MacOS/rekordboxAgent --type=gpu"),
        ],
    )

    with pytest.raises(safety.RekordboxRunningError) as exc_info:
        safety.assert_rekordbox_can_mutate()

    message = str(exc_info.value)
    # Concise: no raw command lines / pids dumped.
    assert "--type=" not in message
    assert "/Applications/" not in message
    assert "Rekordbox" in message and "rekordboxAgent" in message


def test_process_display_name() -> None:
    assert safety.process_display_name("/x/rekordboxAgent") == "rekordboxAgent"
    assert safety.process_display_name("/Applications/rekordbox 7/rekordbox.app/x/rekordbox") == "Rekordbox"
