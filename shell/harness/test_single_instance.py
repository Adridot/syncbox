"""Single-instance regression harness - PRODUCTION shell + sidecar
(retargeted from poc/02-lifecycle-treekill/test_single_instance.py; M4-PLAN 1.2).

Run with the project venv python (builds nothing - build the shell first):
    (cd shell/src-tauri && cargo build)
    sidecar/.venv/bin/python shell/harness/test_single_instance.py

Asserts, against target/debug/syncbox-shell on the production port 8765:
  - launch 1 spawns exactly one sidecar (SIDECAR_SPAWNED, /health OK)
  - launch 2 exits quickly on its own, reaches no setup, spawns nothing
  - SINGLE_INSTANCE_CALLBACK fires in the FIRST instance's pid
  - during the overlap window exactly one sidecar / one :8765 listener
  - primary's timed exit runs the full handshake (SHUTDOWN intent=true),
    port released, no processes left
"""

import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
# M5.5: SYNCBOX_SHELL_BIN retargets the harness at the packaged app binary
# (Syncbox.app/Contents/MacOS/syncbox-shell), which spawns the frozen sidecar.
SHELL_BIN = os.environ.get("SYNCBOX_SHELL_BIN") or os.path.join(
    REPO, "shell/src-tauri/target/debug/syncbox-shell"
)
LOG = os.path.join(HERE, "build/single-instance.log")
PORT = 8765
# Dev: the venv python execs the framework binary, so match on the args (the
# leading [-] keeps pgrep from parsing the pattern as its own options).
# Packaged: the frozen binary carries its own name.
SIDECAR_PATTERN = (
    "[s]yncbox-sidecar" if os.environ.get("SYNCBOX_SHELL_BIN") else "[-]u -m syncbox"
)


def log_lines():
    if not os.path.exists(LOG):
        return []
    with open(LOG, errors="replace") as f:
        return [l.strip() for l in f if l.strip()]


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


def sidecar_pids():
    out = subprocess.run(
        ["pgrep", "-f", SIDECAR_PATTERN], capture_output=True, text=True
    )
    return [int(x) for x in out.stdout.split()]


def main():
    assert os.path.isfile(SHELL_BIN), f"build the shell first: {SHELL_BIN}"
    assert not lsof_listeners(), f"port {PORT} busy before test"
    assert not sidecar_pids(), "stray sidecar running before test"
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if os.path.exists(LOG):
        os.remove(LOG)

    env = {
        **os.environ,
        "SYNCBOX_DATA_DIR": tempfile.mkdtemp(prefix="syncbox-harness-"),
        "SYNCBOX_EXIT_AFTER_SECS": "14",
    }
    log_file = open(LOG, "ab")  # both instances append their stderr markers here

    print("launching instance 1 (primary)...", flush=True)
    p1 = subprocess.Popen([SHELL_BIN], env=env,
                          stdout=subprocess.DEVNULL, stderr=log_file)
    try:
        wait_for(lambda: any("SIDECAR_SPAWNED" in l for l in log_lines()), 15, "SIDECAR_SPAWNED")
        wait_for(health_ok, 15, "/health from primary's sidecar")
        print("  primary up, sidecar healthy", flush=True)

        print("launching instance 2 (should self-exit)...", flush=True)
        t0 = time.perf_counter()
        p2 = subprocess.Popen([SHELL_BIN], env=env,
                              stdout=subprocess.DEVNULL, stderr=log_file)
        rc2 = p2.wait(timeout=10)
        dt2 = time.perf_counter() - t0
        print(f"  instance 2 exited on its own: rc={rc2} after {dt2:.2f}s", flush=True)

        wait_for(lambda: any("SINGLE_INSTANCE_CALLBACK" in l for l in log_lines()),
                 5, "SINGLE_INSTANCE_CALLBACK in log")

        lines = log_lines()
        spawned = [l for l in lines if "SIDECAR_SPAWNED" in l]
        callbacks = [l for l in lines if "SINGLE_INSTANCE_CALLBACK" in l]
        started = [l for l in lines if "PRIMARY_INSTANCE_STARTED" in l]
        assert len(spawned) == 1, f"expected exactly 1 sidecar spawn, log shows {len(spawned)}"
        assert len(started) == 1, f"second instance reached setup: {started}"
        assert len(callbacks) >= 1
        assert f"shell_pid={p1.pid}" in callbacks[0], \
            f"callback fired in wrong process: {callbacks[0]} (primary={p1.pid})"
        print(f"  callback fired in primary (shell_pid={p1.pid}); "
              f"1 spawn line, 1 setup line — no second sidecar attempt", flush=True)

        listeners = lsof_listeners()
        pids = sidecar_pids()
        print(f"  overlap-window state: listeners={listeners} sidecar_pids={pids}", flush=True)
        assert len(listeners) == 1, f"expected one :{PORT} listener, got {listeners}"
        assert len(pids) == 1, f"expected one sidecar process, got {pids}"

        print("waiting for primary's timed shutdown...", flush=True)
        rc1 = p1.wait(timeout=30)
        wait_for(lambda: any("SHUTDOWN intent=true" in l for l in log_lines()),
                 5, "intent-flagged shutdown line")
        shutdown = [l for l in log_lines() if "SHUTDOWN intent=true" in l]
        assert len(shutdown) == 1, f"missing/duplicated shutdown line: {shutdown}"
        stopped = [l for l in log_lines() if "SIDECAR_STOPPED" in l]
        assert stopped and "clean" in stopped[0], f"handshake was not clean: {stopped}"
        wait_for(lambda: not lsof_listeners(), 5, "port release after shutdown")
        wait_for(lambda: not sidecar_pids(), 5, "sidecar process gone")
        print(f"  primary exited rc={rc1}, clean intent-flagged handshake, "
              f"port {PORT} released, no sidecar left", flush=True)

        print("\nfull shell log:")
        for l in log_lines():
            print(f"    {l}")
        print("\nSINGLE-INSTANCE ASSERTIONS PASSED", flush=True)
    finally:
        log_file.close()
        for pid in sidecar_pids():
            subprocess.run(["kill", "-9", str(pid)])
        if p1.poll() is None:
            p1.kill()
            p1.wait()


if __name__ == "__main__":
    sys.exit(main())
