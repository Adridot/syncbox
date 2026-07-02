"""POC #2 - T5: single-instance shell must not double-spawn the sidecar (macOS).

Run with the project venv python:
    sidecar/.venv/bin/python poc/02-lifecycle-treekill/test_single_instance.py

Orchestrates two launches of the Tauri poc-shell binary (built from shell/src-tauri,
single-instance plugin registered FIRST) and asserts:
  - launch 1 spawns exactly one sidecar (log SIDECAR_SPAWNED, /health OK)
  - launch 2 exits quickly on its own, logs nothing, spawns nothing
  - the SINGLE_INSTANCE_CALLBACK line is written by the FIRST instance's pid
  - during the overlap window exactly one sidecar process / one :8899 listener exists
  - primary shuts down with intent flag set, port released, no processes left
"""

import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SHELL_BIN = os.path.join(HERE, "shell/src-tauri/target/debug/poc-shell")
SIDECAR_BIN = os.path.join(
    REPO, "poc/03-bundle-size-coldstart/build/dist/syncbox-sidecar-poc/syncbox-sidecar-poc"
)
LOG = os.path.join(HERE, "build/single-instance.log")
PORT = 8899


def log_lines():
    if not os.path.exists(LOG):
        return []
    with open(LOG) as f:
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
    out = subprocess.run(["pgrep", "-f", "syncbox-sidecar-poc"], capture_output=True, text=True)
    return [int(x) for x in out.stdout.split()]


def main():
    assert os.path.isfile(SHELL_BIN), f"build the shell first: {SHELL_BIN}"
    assert not lsof_listeners(), f"port {PORT} busy before test"
    assert not sidecar_pids(), "stray sidecar running before test"
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if os.path.exists(LOG):
        os.remove(LOG)

    env = {**os.environ, "POC_LOG": LOG, "SIDECAR_BIN": SIDECAR_BIN}

    print("launching instance 1 (primary)...", flush=True)
    p1 = subprocess.Popen([SHELL_BIN], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for(lambda: any("SIDECAR_SPAWNED" in l for l in log_lines()), 15, "SIDECAR_SPAWNED")
        wait_for(health_ok, 15, "/health from primary's sidecar")
        print("  primary up, sidecar healthy", flush=True)

        print("launching instance 2 (should self-exit)...", flush=True)
        t0 = time.perf_counter()
        p2 = subprocess.Popen([SHELL_BIN], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        # the callback must have fired in the FIRST instance's process
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
        rc1 = p1.wait(timeout=20)
        lines = log_lines()
        shutdown = [l for l in lines if "SHUTDOWN intent=true" in l]
        assert len(shutdown) == 1, f"missing/duplicated shutdown line: {shutdown}"
        wait_for(lambda: not lsof_listeners(), 5, "port release after shutdown")
        wait_for(lambda: not sidecar_pids(), 5, "sidecar process gone")
        print(f"  primary exited rc={rc1}, intent-flagged shutdown logged, "
              f"port {PORT} released, no sidecar left", flush=True)

        print("\nfull shell log:")
        for l in log_lines():
            print(f"    {l}")
        print("\nT5 SINGLE-INSTANCE ASSERTIONS PASSED", flush=True)
    finally:
        for pid in sidecar_pids():
            subprocess.run(["kill", "-9", str(pid)])
        if p1.poll() is None:
            p1.kill()
            p1.wait()


if __name__ == "__main__":
    sys.exit(main())
