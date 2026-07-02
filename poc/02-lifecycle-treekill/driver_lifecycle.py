"""POC #2 - sidecar lifecycle / tree-kill driver (macOS side).

Disposable assert-based script. Run with the project venv python:
    sidecar/.venv/bin/python poc/02-lifecycle-treekill/driver_lifecycle.py

Covers SPEC-UNIFIED 6.6 / section 8 item 2 (macOS half; Windows deferred pre-M5):
  T1  real process topology of the PyInstaller onedir sidecar (psutil)
  T2  naive child-only kill -> check for orphaned descendants holding :8899 (lsof)
  T3  tree-kill done right: own process group, killpg, port released, immediate re-spawn
  T4  shutdown handshake order: SIGTERM to group -> bounded wait -> SIGKILL fallback,
      time-to-port-release measured (production maps: HTTP shutdown cmd -> SIGTERM -> SIGKILL)
  T6  crash vs intentional exit distinguished by an internal intent flag, NOT exit codes
"""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import psutil

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIDECAR = os.path.join(
    REPO, "poc/03-bundle-size-coldstart/build/dist/syncbox-sidecar-poc/syncbox-sidecar-poc"
)
PORT = 8899
RESULTS = []


def log(msg):
    print(f"  {msg}", flush=True)


def section(name):
    print(f"\n=== {name} ===", flush=True)


def port_accepting(timeout=0.2):
    """True if something accepts TCP connections on 127.0.0.1:PORT."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def lsof_listeners():
    """PIDs holding a LISTEN socket on PORT, per lsof (ground truth)."""
    out = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{PORT}", "-sTCP:LISTEN", "-t"],
        capture_output=True, text=True,
    )
    return [int(x) for x in out.stdout.split()]


def wait_health(deadline_s=20):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < deadline_s:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=0.3)
            return time.perf_counter() - t0
        except Exception:
            time.sleep(0.05)
    raise AssertionError(f"sidecar not healthy within {deadline_s}s")


def wait_port_released(deadline_s=10):
    """Poll connect() until refused; returns seconds elapsed."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < deadline_s:
        if not port_accepting(timeout=0.1):
            return time.perf_counter() - t0
        time.sleep(0.01)
    raise AssertionError(f"port {PORT} still accepting after {deadline_s}s")


def spawn(own_group):
    """Spawn the sidecar. own_group=True -> its own session/process group (setsid)."""
    return subprocess.Popen(
        [SIDECAR],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=own_group,
    )


def snapshot_tree(pid):
    p = psutil.Process(pid)
    return p, p.children(recursive=True)


def cleanup(popen):
    # killpg ONLY if the child leads its own group; a group kill on a child that
    # inherited the driver's pgid would kill the driver itself (observed live:
    # first version of this script suicided here on the T1 non-isolated spawn).
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
    section("T1 - process topology of PyInstaller onedir sidecar (macOS)")
    p = spawn(own_group=False)
    try:
        ready = wait_health()
        proc, kids = snapshot_tree(p.pid)
        pgid = os.getpgid(p.pid)
        log(f"spawned pid={p.pid} name={proc.name()} ready_in={ready:.2f}s")
        log(f"children (recursive): {[(k.pid, k.name()) for k in kids]}")
        log(f"threads={proc.num_threads()} pgid={pgid} driver_pgid={os.getpgid(0)}")
        log(f"lsof listeners on :{PORT}: {lsof_listeners()}")
        single = len(kids) == 0
        assert lsof_listeners() == [p.pid], "listener is not the spawned pid"
        RESULTS.append(
            ("T1", f"onedir topology = {'SINGLE process, 0 children' if single else f'{len(kids)} children'}; "
                   f"default spawn inherits parent pgid ({pgid})")
        )
        return single
    finally:
        cleanup(p)
        wait_port_released()


# ------------------------------------------------------- T2 naive child kill
def t2_naive_kill(single_process):
    section("T2 - naive kill of direct child only (research failure mode)")
    p = spawn(own_group=False)
    try:
        wait_health()
        _, kids_before = snapshot_tree(p.pid)
        log(f"descendants before kill: {[(k.pid, k.name()) for k in kids_before]}")
        p.kill()  # SIGKILL to the direct child pid ONLY - the naive child.kill()
        p.wait(timeout=5)
        time.sleep(0.3)  # give any orphan time to show up in lsof
        orphans = lsof_listeners()
        surviving = [k for k in kids_before if psutil.pid_exists(k.pid)]
        log(f"surviving descendants: {surviving}")
        log(f"lsof listeners on :{PORT} after naive kill: {orphans}")
        assert not orphans, f"orphaned listener(s) on :{PORT}: {orphans}"
        assert not surviving, f"surviving descendants: {surviving}"
        if single_process:
            RESULTS.append(
                ("T2", "onedir macOS is single-process -> naive child.kill() leaves NO orphan; "
                       "the #11686 orphan-worker failure mode is one-file/Windows-shaped, "
                       "theoretical for macOS onedir (tree-kill still mandated by spec 6.6)")
            )
        else:
            RESULTS.append(("T2", "multi-process topology; orphan check passed (unexpected shape)"))
    finally:
        cleanup(p)
        try:
            wait_port_released()
        except AssertionError:
            pass


# ----------------------------------------------------------- T3 tree-kill OK
def t3_treekill_respawn():
    section("T3 - tree-kill via own process group + port release + immediate re-spawn")
    p = spawn(own_group=True)  # start_new_session=True -> setsid -> pgid == pid
    try:
        wait_health()
        pgid = os.getpgid(p.pid)
        assert pgid == p.pid, f"expected own group (pgid==pid), got pgid={pgid}"
        log(f"sidecar pid={p.pid} pgid={pgid} (own group, isolated from driver pgid={os.getpgid(0)})")
        _, kids = snapshot_tree(p.pid)

        t0 = time.perf_counter()
        os.killpg(pgid, signal.SIGKILL)  # kill the WHOLE group
        p.wait(timeout=5)
        released_in = wait_port_released()
        survivors = [k for k in kids if psutil.pid_exists(k.pid)]
        assert not survivors, f"group kill left survivors: {survivors}"
        assert lsof_listeners() == [], "port still held after killpg"
        log(f"killpg(SIGKILL) -> group dead, port released in {released_in*1000:.0f}ms "
            f"(total {(time.perf_counter()-t0)*1000:.0f}ms)")

        # immediate re-spawn on the same port
        t1 = time.perf_counter()
        p2 = spawn(own_group=True)
        try:
            ready = wait_health()
            log(f"immediate re-spawn OK: healthy again {ready:.2f}s after spawn "
                f"({time.perf_counter()-t1:.2f}s after kill completed)")
            RESULTS.append(
                ("T3", f"killpg(SIGKILL) on own group: 0 survivors, :{PORT} released in "
                       f"{released_in*1000:.0f}ms, immediate re-spawn healthy in {ready:.2f}s")
            )
        finally:
            cleanup(p2)
            wait_port_released()
    finally:
        cleanup(p)


# ---------------------------------------------- T4 graceful-then-kill handshake
def t4_graceful_handshake():
    section("T4 - shutdown handshake: SIGTERM group -> bounded wait -> SIGKILL fallback")
    # Production order per SPEC-UNIFIED 6.6: (1) HTTP shutdown command (sidecar closes
    # SQLCipher, exits) -> (2) bounded wait -> (3) tree-kill fallback. This POC sidecar
    # has no shutdown route, so step (1) maps to SIGTERM-to-group here (uvicorn handles
    # SIGTERM as graceful shutdown); step (3) stays SIGKILL-to-group.
    GRACE_S = 3.0

    # --- run A: graceful path (SIGTERM suffices)
    p = spawn(own_group=True)
    try:
        wait_health()
        pgid = os.getpgid(p.pid)
        t0 = time.perf_counter()
        os.killpg(pgid, signal.SIGTERM)
        try:
            p.wait(timeout=GRACE_S)
            graceful = True
        except subprocess.TimeoutExpired:
            graceful = False
            os.killpg(pgid, signal.SIGKILL)
            p.wait(timeout=5)
        released = wait_port_released()
        total = time.perf_counter() - t0
        rc = p.returncode
        log(f"run A: SIGTERM -> exited gracefully={graceful} returncode={rc} "
            f"port released {released*1000:.0f}ms / total {total*1000:.0f}ms after SIGTERM")
        assert lsof_listeners() == []
        term_ms = total * 1000
    finally:
        cleanup(p)

    # --- run B: SIGKILL fallback path (simulate a hung sidecar by using SIGKILL after
    #     an artificially tiny grace window; proves the fallback chain executes and the
    #     port still releases)
    p = spawn(own_group=True)
    try:
        wait_health()
        pgid = os.getpgid(p.pid)
        t0 = time.perf_counter()
        os.killpg(pgid, signal.SIGTERM)
        try:
            p.wait(timeout=0.001)  # force the timeout branch
        except subprocess.TimeoutExpired:
            pass
        os.killpg(pgid, signal.SIGKILL)  # fallback fires
        p.wait(timeout=5)
        released = wait_port_released()
        total = time.perf_counter() - t0
        log(f"run B: SIGTERM + immediate SIGKILL fallback -> returncode={p.returncode} "
            f"port released {released*1000:.0f}ms / total {total*1000:.0f}ms")
        assert lsof_listeners() == []
        RESULTS.append(
            ("T4", f"graceful SIGTERM: port released {term_ms:.0f}ms after signal; "
                   f"SIGKILL fallback chain also releases port ({total*1000:.0f}ms); "
                   f"production maps step 1 to the HTTP shutdown command (absent in this POC binary)")
        )
    finally:
        cleanup(p)
        wait_port_released()


# ------------------------------------------- T6 crash vs intentional (intent flag)
class Supervisor:
    """Minimal supervisor skeleton: the intent flag is set BEFORE an intentional
    shutdown; the exit-watcher classifies by flag, never by exit code/signal."""

    def __init__(self):
        self.intent_shutdown = False
        self.proc = None

    def start(self):
        self.proc = spawn(own_group=True)
        wait_health()

    def shutdown(self):
        self.intent_shutdown = True  # <-- flag FIRST, then kill (spec 6.6 hard condition)
        os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        self.proc.wait(timeout=5)

    def classify_exit(self):
        rc = self.proc.returncode
        return ("intentional" if self.intent_shutdown else "crash"), rc


def t6_intent_flag():
    section("T6 - crash vs intentional exit via internal intent flag (not exit codes)")

    # scenario 1: external SIGKILL = crash simulation (flag NOT set)
    sup = Supervisor()
    sup.start()
    try:
        os.kill(sup.proc.pid, signal.SIGKILL)  # external killer, supervisor unaware
        sup.proc.wait(timeout=5)
        verdict1, rc1 = sup.classify_exit()
        log(f"scenario 1 (external SIGKILL): returncode={rc1} -> classified '{verdict1}' -> supervisor would RESTART")
        assert verdict1 == "crash"
    finally:
        cleanup(sup.proc)
        wait_port_released()

    # scenario 2: intentional shutdown (flag set before kill)
    sup2 = Supervisor()
    sup2.start()
    try:
        sup2.shutdown()
        verdict2, rc2 = sup2.classify_exit()
        log(f"scenario 2 (intentional shutdown): returncode={rc2} -> classified '{verdict2}' -> supervisor would NOT restart")
        assert verdict2 == "intentional"
    finally:
        cleanup(sup2.proc)
        wait_port_released()

    assert rc1 == rc2, "expected identical exit codes to prove they cannot discriminate"
    log(f"exit codes identical in both scenarios ({rc1} == {rc2}): exit code alone CANNOT "
        f"distinguish crash from intentional kill -> intent flag is the only reliable signal")
    RESULTS.append(
        ("T6", f"both scenarios exit rc={rc1} (SIGKILL); intent flag set before kill correctly "
               f"classifies intentional vs crash where exit codes cannot")
    )


def main():
    assert os.path.isfile(SIDECAR), f"sidecar binary missing: {SIDECAR}"
    assert not port_accepting(), f"port {PORT} already in use - clean up before running"

    single = t1_topology()
    t2_naive_kill(single)
    t3_treekill_respawn()
    t4_graceful_handshake()
    t6_intent_flag()

    section("SUMMARY")
    for tag, line in RESULTS:
        print(f"  [{tag}] {line}")
    print("\nALL LIFECYCLE ASSERTIONS PASSED", flush=True)


if __name__ == "__main__":
    sys.exit(main())
