"""Sidecar lifecycle / tree-kill regression harness - PRODUCTION targets
(retargeted from poc/02-lifecycle-treekill/driver_lifecycle.py; M4-PLAN 1.2).

Assert-based script. Run with the project venv python:
    sidecar/.venv/bin/python shell/harness/driver_lifecycle.py

Covers SPEC-UNIFIED 6.6 on the production sidecar (python -m syncbox, :8765):
  T1  process topology (psutil): single process, listener == spawned pid
  T2  naive child-only kill -> no orphaned :8765 listener
  T3  tree-kill done right: own process group, killpg, port released, re-spawn
  T4  PRODUCTION shutdown handshake: open the SQLCipher secrets connection
      (GET /api/status), POST /shutdown -> clean exit + port release; then the
      SIGTERM-group and SIGKILL-group fallback rungs
  T6  crash vs intentional exit distinguished by an internal intent flag
"""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import psutil

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PY = os.path.join(REPO, "sidecar/.venv/bin/python")
SIDECAR_CWD = os.path.join(REPO, "sidecar")
PORT = 8765
DATA_DIR = tempfile.mkdtemp(prefix="syncbox-harness-")
RESULTS = []


def log(msg):
    print(f"  {msg}", flush=True)


def section(name):
    print(f"\n=== {name} ===", flush=True)


def port_accepting(timeout=0.2):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def lsof_listeners():
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


def wait_health(deadline_s=20):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < deadline_s:
        try:
            http("/health", timeout=0.3)
            return time.perf_counter() - t0
        except Exception:
            time.sleep(0.05)
    raise AssertionError(f"sidecar not healthy within {deadline_s}s")


def wait_port_released(deadline_s=10):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < deadline_s:
        if not port_accepting(timeout=0.1):
            return time.perf_counter() - t0
        time.sleep(0.01)
    raise AssertionError(f"port {PORT} still accepting after {deadline_s}s")


def spawn(own_group):
    """Spawn the production sidecar; own_group -> setsid (pgid == pid).
    stderr goes to a per-run file so a boot failure is diagnosable."""
    stderr_path = os.path.join(DATA_DIR, "spawn-stderr.log")
    return subprocess.Popen(
        [VENV_PY, "-u", "-m", "syncbox"],
        cwd=SIDECAR_CWD,
        env={
            **os.environ,
            "PYTHONPATH": os.path.join(SIDECAR_CWD, "src"),
            "SYNCBOX_DATA_DIR": DATA_DIR,
        },
        stdout=subprocess.DEVNULL,
        stderr=open(stderr_path, "ab"),
        start_new_session=own_group,
    )


def snapshot_tree(pid):
    p = psutil.Process(pid)
    return p, p.children(recursive=True)


def cleanup(popen):
    # killpg ONLY if the child leads its own group (POC #2 learned this live).
    try:
        pgid = os.getpgid(popen.pid)
        if pgid == popen.pid:
            os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        popen.kill()
    except ProcessLookupError:
        pass
    popen.wait()


# ---------------------------------------------------------------- T1 topology
def t1_topology():
    section("T1 - process topology of the production sidecar (python -m syncbox)")
    p = spawn(own_group=False)
    try:
        ready = wait_health()
        proc, kids = snapshot_tree(p.pid)
        pgid = os.getpgid(p.pid)
        log(f"spawned pid={p.pid} name={proc.name()} ready_in={ready:.2f}s")
        log(f"children (recursive): {[(k.pid, k.name()) for k in kids]}")
        log(f"threads={proc.num_threads()} pgid={pgid} driver_pgid={os.getpgid(0)}")
        assert lsof_listeners() == [p.pid], "listener is not the spawned pid"
        single = len(kids) == 0
        RESULTS.append(
            ("T1", f"{'single process, 0 children' if single else f'{len(kids)} children'};"
                   f" listener == spawned pid")
        )
        return single
    finally:
        cleanup(p)
        wait_port_released()


# ------------------------------------------------------- T2 naive child kill
def t2_naive_kill():
    section("T2 - naive kill of direct child only")
    p = spawn(own_group=False)
    try:
        wait_health()
        _, kids_before = snapshot_tree(p.pid)
        p.kill()
        p.wait(timeout=5)
        time.sleep(0.3)
        orphans = lsof_listeners()
        surviving = [k for k in kids_before if psutil.pid_exists(k.pid)]
        assert not orphans, f"orphaned listener(s) on :{PORT}: {orphans}"
        assert not surviving, f"surviving descendants: {surviving}"
        RESULTS.append(("T2", "no orphan listener after naive child kill"))
    finally:
        cleanup(p)
        try:
            wait_port_released()
        except AssertionError:
            pass


# ----------------------------------------------------------- T3 tree-kill OK
def t3_treekill_respawn():
    section("T3 - tree-kill via own process group + port release + immediate re-spawn")
    p = spawn(own_group=True)
    try:
        wait_health()
        pgid = os.getpgid(p.pid)
        assert pgid == p.pid, f"expected own group (pgid==pid), got pgid={pgid}"
        os.killpg(pgid, signal.SIGKILL)
        p.wait(timeout=5)
        released_in = wait_port_released()
        assert lsof_listeners() == [], "port still held after killpg"
        log(f"killpg(SIGKILL) -> port released in {released_in*1000:.0f}ms")

        p2 = spawn(own_group=True)
        try:
            ready = wait_health()
            log(f"immediate re-spawn healthy in {ready:.2f}s")
            RESULTS.append(
                ("T3", f"killpg: port released {released_in*1000:.0f}ms; re-spawn healthy {ready:.2f}s")
            )
        finally:
            cleanup(p2)
            wait_port_released()
    finally:
        cleanup(p)


# ------------------------------------------- T4 production shutdown handshake
def t4_shutdown_handshake():
    section("T4 - production handshake: /api/status (SQLCipher open) -> POST /shutdown")
    # run A: the real 6.6 step 1 - HTTP shutdown with an OPEN SQLCipher
    # connection (GET /api/status forces the encrypted secrets store open).
    p = spawn(own_group=True)
    try:
        wait_health()
        status, body = http("/api/status")
        assert status == 200, f"/api/status -> {status}"
        log(f"/api/status answered {body!r} (SQLCipher secrets connection open)")
        t0 = time.perf_counter()
        status, _ = http("/shutdown", method="POST")
        assert status == 202
        rc = p.wait(timeout=10)
        released = wait_port_released()
        total = time.perf_counter() - t0
        log(f"run A: POST /shutdown -> rc={rc}, port released {released*1000:.0f}ms "
            f"/ total {total*1000:.0f}ms")
        assert rc == 0, f"clean handshake should exit 0, got {rc}"
        assert lsof_listeners() == []
        clean_ms = total * 1000
    finally:
        cleanup(p)

    # run B: SIGTERM-to-group rung (uvicorn graceful path)
    p = spawn(own_group=True)
    try:
        wait_health()
        pgid = os.getpgid(p.pid)
        t0 = time.perf_counter()
        os.killpg(pgid, signal.SIGTERM)
        p.wait(timeout=5)
        released = wait_port_released()
        log(f"run B: SIGTERM group -> rc={p.returncode}, port released "
            f"{(time.perf_counter()-t0)*1000:.0f}ms")
        assert lsof_listeners() == []
    finally:
        cleanup(p)

    # run C: SIGKILL fallback rung
    p = spawn(own_group=True)
    try:
        wait_health()
        pgid = os.getpgid(p.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            p.wait(timeout=0.001)
        except subprocess.TimeoutExpired:
            pass
        os.killpg(pgid, signal.SIGKILL)
        p.wait(timeout=5)
        wait_port_released()
        assert lsof_listeners() == []
        log(f"run C: SIGKILL fallback -> rc={p.returncode}, port released")
        RESULTS.append(
            ("T4", f"HTTP handshake with open SQLCipher conn: rc=0, {clean_ms:.0f}ms; "
                   "SIGTERM and SIGKILL rungs both release the port")
        )
    finally:
        cleanup(p)
        wait_port_released()


# ------------------------------------------- T6 crash vs intentional (intent flag)
class Supervisor:
    """The intent flag is set BEFORE an intentional shutdown; the exit-watcher
    classifies by flag, never by exit code/signal (mirrors main.rs)."""

    def __init__(self):
        self.intent_shutdown = False
        self.proc = None

    def start(self):
        self.proc = spawn(own_group=True)
        wait_health()

    def shutdown(self):
        self.intent_shutdown = True  # flag FIRST, then kill (6.6 hard condition)
        os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        self.proc.wait(timeout=5)

    def classify_exit(self):
        return ("intentional" if self.intent_shutdown else "crash"), self.proc.returncode


def t6_intent_flag():
    section("T6 - crash vs intentional exit via internal intent flag")
    sup = Supervisor()
    sup.start()
    try:
        os.kill(sup.proc.pid, signal.SIGKILL)  # external killer, supervisor unaware
        sup.proc.wait(timeout=5)
        verdict1, rc1 = sup.classify_exit()
        assert verdict1 == "crash"
    finally:
        cleanup(sup.proc)
        wait_port_released()

    sup2 = Supervisor()
    sup2.start()
    try:
        sup2.shutdown()
        verdict2, rc2 = sup2.classify_exit()
        assert verdict2 == "intentional"
    finally:
        cleanup(sup2.proc)
        wait_port_released()

    assert rc1 == rc2, "expected identical exit codes to prove they cannot discriminate"
    log(f"identical exit codes ({rc1}): only the intent flag classifies correctly")
    RESULTS.append(("T6", f"both scenarios rc={rc1}; intent flag classifies, exit codes cannot"))


def main():
    assert os.path.isfile(VENV_PY), f"venv python missing: {VENV_PY}"
    assert not port_accepting(), f"port {PORT} already in use - clean up before running"

    t1_topology()
    t2_naive_kill()
    t3_treekill_respawn()
    t4_shutdown_handshake()
    t6_intent_flag()

    section("SUMMARY")
    for tag, line in RESULTS:
        print(f"  [{tag}] {line}")
    print("\nALL LIFECYCLE ASSERTIONS PASSED", flush=True)


if __name__ == "__main__":
    sys.exit(main())
