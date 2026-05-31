from __future__ import annotations

import subprocess
from dataclasses import dataclass


REKORDBOX_PROCESS_QUERY = "rekordbox|rekordboxAgent"


@dataclass(frozen=True)
class RunningProcess:
    pid: int
    command: str


class RekordboxRunningError(RuntimeError):
    pass


def find_rekordbox_processes() -> list[RunningProcess]:
    result = subprocess.run(
        ["pgrep", "-fl", REKORDBOX_PROCESS_QUERY],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return []

    processes: list[RunningProcess] = []
    for line in result.stdout.splitlines():
        pid_text, _, command = line.partition(" ")
        if not pid_text.isdigit():
            continue
        if "pgrep -fl" in command:
            continue
        if not is_rekordbox_process_command(command):
            continue
        processes.append(RunningProcess(pid=int(pid_text), command=command))
    return processes


def is_rekordbox_process_command(command: str) -> bool:
    normalized = command.lower()
    return (
        "/rekordbox.app/" in normalized
        or "/rekordboxagent.app/" in normalized
        or normalized.endswith("/rekordbox")
        or normalized.endswith("/rekordboxagent")
        or normalized == "rekordbox"
        or normalized == "rekordboxagent"
    )


def process_display_name(command: str) -> str:
    """Friendly name for a Rekordbox-family process command line."""
    lowered = command.lower()
    if "rekordboxagent" in lowered:
        return "rekordboxAgent"
    if "rekordbox" in lowered:
        return "Rekordbox"
    return command.split("/")[-1] or command


def assert_rekordbox_can_mutate() -> None:
    processes = find_rekordbox_processes()
    if processes:
        names = sorted({process_display_name(process.command) for process in processes})
        running = " and ".join(names)
        hint = ""
        if "rekordboxAgent" in names:
            hint = (
                " Note: rekordboxAgent keeps running in the background after you "
                "close the Rekordbox window — quit it from the menu bar or via "
                "Activity Monitor."
            )
        raise RekordboxRunningError(
            f"Rekordbox is still running ({running}), so changes to the collection "
            f"are blocked. Quit it completely and try again.{hint}"
        )
