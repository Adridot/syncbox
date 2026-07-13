"""Lifecycle edge regression harness for the real shell and sidecar.

Build the shell first, then run with the sidecar environment Python:
    (cd shell/src-tauri && cargo build)
    sidecar/.venv/bin/python shell/harness/test_lifecycle_edges.py

Set SYNCBOX_SHELL_BIN to the packaged app executable to repeat the same
checks against the embedded frozen sidecar.

Validates:
- a foreign listener on port 8765 is identified, preserved, and never sent
  POST /shutdown;
- an exact Syncbox protocol listener left by an earlier shell is reaped,
  replaced, and then stopped cleanly;
- immediate shell exits never leave a listener or child behind.
"""

import http.server
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHELL_OVERRIDE = os.environ.get("SYNCBOX_SHELL_BIN")
SHELL_BIN = (
    Path(SHELL_OVERRIDE)
    if SHELL_OVERRIDE
    else REPO / "shell/src-tauri/target/debug/syncbox-shell"
)
PORT = 8765


def wait_for(predicate, deadline_s, what):
    started = time.perf_counter()
    while time.perf_counter() - started < deadline_s:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting for {what}")


def health():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=0.3) as response:
            return json.load(response)
    except Exception:
        return None


def port_accepting():
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def sidecar_command():
    if os.environ.get("SYNCBOX_SHELL_BIN"):
        app = SHELL_BIN.parent.parent.parent
        return [str(app / "Contents/Resources/sidecar/syncbox-sidecar")], None, {}
    return (
        [str(REPO / "sidecar/.venv/bin/python"), "-u", "-m", "syncbox"],
        REPO / "sidecar",
        {"PYTHONPATH": str(REPO / "sidecar/src")},
    )


def spawn_stale_sidecar():
    command, cwd, extra = sidecar_command()
    env = {
        **os.environ,
        **extra,
        "SYNCBOX_DATA_DIR": tempfile.mkdtemp(prefix="syncbox-stale-"),
    }
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def run_shell(exit_after):
    env = {
        **os.environ,
        "SYNCBOX_DATA_DIR": tempfile.mkdtemp(prefix="syncbox-shell-"),
        "SYNCBOX_EXIT_AFTER_SECS": str(exit_after),
    }
    return subprocess.run(
        [str(SHELL_BIN)],
        env=env,
        capture_output=True,
        timeout=30,
        check=False,
    )


class ForeignHandler(http.server.BaseHTTPRequestHandler):
    shutdown_requests = 0

    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        type(self).shutdown_requests += 1
        self.send_response(204)
        self.end_headers()

    def log_message(self, _format, *_args):
        pass


def test_foreign_listener_is_preserved():
    ForeignHandler.shutdown_requests = 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), ForeignHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = run_shell(2)
        stderr = result.stderr.decode(errors="replace")
        assert result.returncode == 0, stderr
        assert "PORT_COLLISION 127.0.0.1:8765" in stderr
        assert "SIDECAR_SPAWNED" not in stderr
        assert ForeignHandler.shutdown_requests == 0
        assert port_accepting()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    wait_for(lambda: not port_accepting(), 3, "foreign listener release")


def test_stale_sidecar_is_reaped_and_replaced():
    stale = spawn_stale_sidecar()
    print(f"  stale sidecar spawned pid={stale.pid}", flush=True)
    try:
        wait_for(
            lambda: health()
            == {"ok": True, "service": "syncbox-sidecar", "protocol": 1},
            20,
            "stale sidecar health",
        )
        print("  stale sidecar identity confirmed", flush=True)
        result = run_shell(3)
        stderr = result.stderr.decode(errors="replace")
        print(f"  shell exited rc={result.returncode}", flush=True)
        assert result.returncode == 0, stderr
        assert "STALE_SIDECAR_REAPED" in stderr
        assert "SIDECAR_SPAWNED" in stderr
        assert "SIDECAR_STOPPED clean" in stderr
        stale.wait(timeout=5)
        assert stale.returncode == 0
        wait_for(lambda: not port_accepting(), 5, "replacement sidecar shutdown")
    finally:
        if stale.poll() is None:
            os.killpg(stale.pid, signal.SIGKILL)
            stale.wait()


def test_immediate_shell_exit_never_leaves_a_listener():
    for _ in range(5):
        result = run_shell(0)
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        wait_for(lambda: not port_accepting(), 5, "port release after immediate exit")


def main():
    assert SHELL_BIN.is_file(), f"build the shell first: {SHELL_BIN}"
    assert not port_accepting(), f"port {PORT} busy before test"
    selected = set(sys.argv[1:])
    if not selected or "foreign" in selected:
        test_foreign_listener_is_preserved()
        print("[PASS] foreign listener preserved", flush=True)
        time.sleep(1)  # let the macOS single-instance registration disappear
    if not selected or "stale" in selected:
        test_stale_sidecar_is_reaped_and_replaced()
        print("[PASS] stale sidecar reaped and replaced", flush=True)
        time.sleep(1)
    if not selected or "immediate" in selected:
        test_immediate_shell_exit_never_leaves_a_listener()
        print("[PASS] immediate exits leave no listener", flush=True)
    print("LIFECYCLE EDGE ASSERTIONS PASSED", flush=True)


if __name__ == "__main__":
    main()
