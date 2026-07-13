"""Supervisor restart regression harness - production shell + sidecar.

Run with the project venv python (build the shell first):
    (cd shell/src-tauri && cargo build)
    sidecar/.venv/bin/python shell/harness/test_supervisor_restart.py

Asserts the M4-PLAN 1.2 supervisor loop: an externally killed sidecar
(crash, intent flag NOT set) is restarted with bounded backoff (1/2/4 s,
3 attempts); the 4th crash exhausts the counter, logs BACKEND_DOWN and
leaves nothing listening automatically. The harness then exercises the same
manual restart command used by the overlay and verifies recovery.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
# M5.5: SYNCBOX_SHELL_BIN retargets the harness at the packaged app binary.
SHELL_BIN = os.environ.get("SYNCBOX_SHELL_BIN") or os.path.join(
    REPO, "shell/src-tauri/target/debug/syncbox-shell"
)
LOG = os.path.join(HERE, "build/supervisor-restart.log")
PORT = 8765


def log_lines():
    if not os.path.exists(LOG):
        return []
    with open(LOG, errors="replace") as f:
        return [l.strip() for l in f if l.strip()]


def count(marker):
    return sum(1 for l in log_lines() if marker in l)


def wait_for(pred, deadline_s, what):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < deadline_s:
        if pred():
            return time.perf_counter() - t0
        time.sleep(0.1)
    raise AssertionError(f"timeout waiting for {what}")


def health_ok():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=0.3)
        return True
    except Exception:
        return False


def lsof_listeners():
    out = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{PORT}", "-sTCP:LISTEN", "-t"],
        capture_output=True, text=True,
    )
    return [int(x) for x in out.stdout.split()]


def main():
    assert os.path.isfile(SHELL_BIN), f"build the shell first: {SHELL_BIN}"
    assert not lsof_listeners(), f"port {PORT} busy before test"
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if os.path.exists(LOG):
        os.remove(LOG)

    env = {
        **os.environ,
        "SYNCBOX_DATA_DIR": tempfile.mkdtemp(prefix="syncbox-harness-"),
        "SYNCBOX_EXIT_AFTER_SECS": "90",
        "SYNCBOX_RESTART_AFTER_EXHAUSTION": "1",
    }
    log_file = open(LOG, "ab")
    print("launching shell...", flush=True)
    p1 = subprocess.Popen([SHELL_BIN], env=env,
                          stdout=subprocess.DEVNULL, stderr=log_file)
    try:
        wait_for(health_ok, 20, "initial sidecar health")
        print("  initial sidecar healthy", flush=True)

        # 3 crashes -> 3 bounded restarts (attempt=1..3), healthy again each time
        for round_n in (1, 2, 3):
            [pid] = lsof_listeners()
            os.kill(pid, signal.SIGKILL)  # external crash, intent flag NOT set
            wait_for(lambda: count("SIDECAR_RESTARTING") >= round_n, 15,
                     f"restart marker #{round_n}")
            wait_for(health_ok, 20, f"health after restart #{round_n}")
            marker = [l for l in log_lines() if f"attempt={round_n}" in l]
            assert marker, f"missing attempt={round_n} marker"
            print(f"  crash #{round_n} -> {marker[0]}", flush=True)

        # 4th crash exhausts the counter before the harness invokes the real
        # manual restart command used by the overlay.
        [pid] = lsof_listeners()
        os.kill(pid, signal.SIGKILL)
        wait_for(lambda: count("BACKEND_DOWN") >= 1, 15, "BACKEND_DOWN marker")
        assert p1.poll() is None, "shell must stay alive to show the overlay"
        wait_for(lambda: count("RESTART_SIDECAR_REQUESTED") >= 1, 5,
                 "manual restart request")
        lines_before_manual = log_lines()
        request_index = next(
            index for index, line in enumerate(lines_before_manual)
            if "RESTART_SIDECAR_REQUESTED" in line
        )
        assert sum(
            "SIDECAR_SPAWNED" in line for line in lines_before_manual[:request_index]
        ) == 4, "sidecar restarted automatically past the bound"
        wait_for(lambda: count("HARNESS_MANUAL_RESTART started=true") >= 1, 5,
                 "manual restart result")
        wait_for(health_ok, 20, "health after manual restart")
        assert count("SIDECAR_SPAWNED") == 5
        print("  crash #4 -> BACKEND_DOWN; manual restart -> healthy", flush=True)

        print("\nfull shell log:")
        for l in log_lines():
            print(f"    {l}")
        print("\nSUPERVISOR-RESTART ASSERTIONS PASSED", flush=True)
    finally:
        log_file.close()
        if p1.poll() is None:
            p1.kill()
            p1.wait()
        for pid in lsof_listeners():
            subprocess.run(["kill", "-9", str(pid)])


if __name__ == "__main__":
    sys.exit(main())
