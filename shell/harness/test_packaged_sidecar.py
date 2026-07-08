"""Packaged-sidecar regression harness (M5.1, SPEC-UNIFIED 6.11 + legal 6.5).

Assert-based script, house style of driver_lifecycle.py. Build first, then run
with the project venv python:
    cd sidecar && .venv/bin/pyinstaller --noconfirm sidecar.spec
    sidecar/.venv/bin/python shell/harness/test_packaged_sidecar.py

Covers what the freeze can silently break:
  A1  legal bundle audit: no download-shaped name in the dist tree NOR in the
      venv site-packages the freeze collects from (6.5 hard stop)
  A2  freeze anchors: migrations .sql shipped (importlib.resources fix),
      _cffi_backend collected (6.12)
  A3  boot: frozen binary answers /health on 8765, listener pid is the
      spawned process (not some stale dev sidecar), app DB migrated
  A4  clean shutdown: POST /shutdown -> exit 0, port released, intent flag
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DIST = REPO / "sidecar" / "dist" / "syncbox-sidecar"
BIN = DIST / "syncbox-sidecar"
SITE_PACKAGES = REPO / "sidecar" / ".venv" / "lib" / "python3.14" / "site-packages"
PORT = 8765

# 6.5: the freeze pulling in anything download-shaped is a hard stop.
FORBIDDEN = ["streamrip", "deemix", "ffmpeg", "yt_dlp", "yt-dlp", "soundcloud", "deezer"]

# First-ever exec of a fresh binary pays the macOS first-exec scan (~15 s
# measured in POC #3); warm runs are sub-second.
HEALTH_DEADLINE_S = 30


def section(name):
    print(f"\n=== {name} ===", flush=True)


def ok(msg):
    print(f"  ok: {msg}", flush=True)


def port_listeners():
    out = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{PORT}", "-sTCP:LISTEN", "-t"],
        capture_output=True, text=True,
    )
    return [int(x) for x in out.stdout.split()]


def http(path, method="GET", timeout=2.0):
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", method=method
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def main():
    assert BIN.is_file(), (
        f"frozen sidecar missing at {BIN} - build it first: "
        "cd sidecar && .venv/bin/pyinstaller --noconfirm sidecar.spec"
    )

    section("A1 legal bundle audit (6.5)")
    # Filenames in the dist tree catch native libs; top-level site-packages
    # names catch pure-Python packages (which hide inside the PYZ archive).
    hits = []
    for root, dirs, files in os.walk(DIST):
        for name in dirs + files:
            lowered = name.lower()
            hits += [f"dist: {name}" for tok in FORBIDDEN if tok in lowered]
    for entry in SITE_PACKAGES.iterdir():
        lowered = entry.name.lower()
        hits += [f"venv: {entry.name}" for tok in FORBIDDEN if tok in lowered]
    assert not hits, f"download-shaped names found (6.5 HARD STOP): {hits}"
    ok(f"no forbidden name in dist tree or venv ({len(FORBIDDEN)} tokens)")

    section("A2 freeze anchors")
    sql = sorted((DIST / "_internal" / "syncbox" / "migrations").glob("*.sql"))
    assert sql, "migration .sql not bundled - importlib.resources regression"
    cffi = list((DIST / "_internal").glob("_cffi_backend*"))
    assert cffi, "_cffi_backend missing (6.12: miniaudio/A3 breaks without it)"
    ok(f"{len(sql)} migration scripts + _cffi_backend bundled")

    section("A3 boot: /health from the spawned pid")
    assert not port_listeners(), f"port {PORT} already held - kill the stale sidecar first"
    data_dir = tempfile.mkdtemp(prefix="syncbox-packaged-")
    logf = open(Path(data_dir) / "stderr.log", "wb")
    proc = subprocess.Popen(
        [str(BIN)],
        env={**os.environ, "SYNCBOX_DATA_DIR": data_dir},
        stdout=logf, stderr=logf,
    )
    try:
        t0 = time.perf_counter()
        deadline = t0 + HEALTH_DEADLINE_S
        while time.perf_counter() < deadline:
            try:
                status, _ = http("/health", timeout=0.3)
                break
            except Exception:
                assert proc.poll() is None, (
                    f"frozen sidecar died at boot (exit {proc.returncode}) - "
                    f"see {data_dir}/stderr.log"
                )
                time.sleep(0.1)
        else:
            raise AssertionError(f"no /health within {HEALTH_DEADLINE_S}s")
        boot_s = time.perf_counter() - t0
        assert status == 200
        listeners = port_listeners()
        assert listeners == [proc.pid], (
            f"listener pids {listeners} != spawned pid {proc.pid} - "
            "a stale sidecar answered, or the frozen topology changed"
        )
        assert (Path(data_dir) / "syncbox.db").is_file(), "app DB not migrated"
        ok(f"healthy in {boot_s:.2f}s, listener == spawned pid, app DB migrated")

        section("A4 clean shutdown handshake")
        http("/shutdown", method="POST")
        assert proc.wait(timeout=10) == 0, f"exit code {proc.returncode}, want 0"
        t0 = time.perf_counter()
        while port_listeners():
            assert time.perf_counter() - t0 < 5, f"port {PORT} not released"
            time.sleep(0.05)
        logf.close()
        stderr_log = (Path(data_dir) / "stderr.log").read_text()
        assert "intentional=True" in stderr_log, "intent flag missing from shutdown log"
        ok("exit 0, port released, intentional=True")
    finally:
        if proc.poll() is None:
            proc.kill()
        logf.close()

    print("\nPACKAGED SIDECAR: ALL GREEN", flush=True)


if __name__ == "__main__":
    main()
