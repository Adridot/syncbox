"""POC #4 orchestrator - EventSource/SSE inside the REAL WKWebView (Tauri v2, macOS).

Run with the venv python:
  export PATH="$HOME/.cargo/bin:$PATH"
  sidecar/.venv/bin/python poc/04-sse-webview/run_poc.py

Steps (fully automated, no human interaction):
  1. Overlay the POC #4 main.rs + index.html onto the shared POC #2 shell (originals
     backed up to build/ and restored at the end), cargo build (warm cache).
  2. Start: compiled PyInstaller sidecar :8899 (POC #3, no CORS), venv CORS SSE app
     :8897, results server :8898. All in their own process groups.
  3. Launch the shell app. The embedded page runs phases A/B1/B2/C (see index.html).
  4. On the phase-C marker, SIGKILL the venv SSE app mid-stream (sidecar-death probe).
  5. Wait for build/result.json, tree-kill everything, restore the shell files.
  6. Assert: 3 ticks arrived INCREMENTALLY (gaps ~ server delays, not one burst),
     readyState transitions sane, mid-stream kill surfaced as a prompt error event.
     Report the exact Origin header WKWebView sent (spec 6.3 allowlist gap evidence).
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = "/Users/adriendidot/Documents/Dev/syncbox"
POC = f"{ROOT}/poc/04-sse-webview"
BUILD = f"{POC}/build"
VENV_PY = f"{ROOT}/sidecar/.venv/bin/python"
SHELL = f"{ROOT}/poc/02-lifecycle-treekill/shell"
SHELL_BIN = f"{SHELL}/src-tauri/target/debug/poc-shell"
SIDECAR_BIN = f"{ROOT}/poc/03-bundle-size-coldstart/build/dist/syncbox-sidecar-poc/syncbox-sidecar-poc"

MAIN_RS = f"{SHELL}/src-tauri/src/main.rs"
INDEX = f"{SHELL}/ui/index.html"
PROCS = []


def spawn(argv, **kw):
    p = subprocess.Popen(argv, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    PROCS.append(p)
    return p


def killpg(p, sig=signal.SIGKILL):
    # Group first; EPERM can surface on macOS when a group member is unsignalable
    # (observed with the GUI shell's WebKit XPC helpers) -> fall back to the direct pid.
    try:
        os.killpg(p.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        p.kill()
    except Exception:
        pass
    try:
        p.wait(timeout=3)
    except Exception:
        pass


def wait_http(url, timeout_s=20.0, data=None):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            urllib.request.urlopen(url, data=data, timeout=1).read()
            return time.time() - t0
        except Exception:
            time.sleep(0.1)
    raise AssertionError(f"{url} not up after {timeout_s}s")


def restore_shell():
    if os.path.exists(f"{BUILD}/main.rs.poc2.bak"):
        shutil.copy2(f"{BUILD}/main.rs.poc2.bak", MAIN_RS)
        shutil.copy2(f"{BUILD}/index.html.poc2.bak", INDEX)
        print("shell files restored to POC #2 originals")


def main():
    os.makedirs(BUILD, exist_ok=True)
    for f in ("result.json", "events.jsonl", "origins.jsonl"):
        try:
            os.remove(f"{BUILD}/{f}")
        except FileNotFoundError:
            pass

    # -- 1. overlay shell sources (backup originals), build --------------------------
    shutil.copy2(MAIN_RS, f"{BUILD}/main.rs.poc2.bak")
    shutil.copy2(INDEX, f"{BUILD}/index.html.poc2.bak")
    shutil.copy2(f"{POC}/shell-overlay/main.rs", MAIN_RS)
    shutil.copy2(f"{POC}/shell-overlay/index.html", INDEX)
    env = dict(os.environ, PATH=os.path.expanduser("~/.cargo/bin") + ":" + os.environ["PATH"])
    t0 = time.time()
    r = subprocess.run(["cargo", "build"], cwd=f"{SHELL}/src-tauri", env=env,
                       capture_output=True, text=True, timeout=600)
    print(f"cargo build rc={r.returncode} in {time.time()-t0:.1f}s")
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise AssertionError("cargo build failed")

    # -- 2. servers -------------------------------------------------------------------
    spawn([SIDECAR_BIN])                                             # :8899 no-CORS
    spawn([VENV_PY, f"{POC}/sidecar_cors.py", f"{BUILD}/origins.jsonl"])  # :8897
    spawn([VENV_PY, f"{POC}/results_server.py", BUILD])              # :8898
    print(f"sidecar :8899 healthy in {wait_http('http://127.0.0.1:8899/health'):.2f}s")
    print(f"cors app :8897 healthy in {wait_http('http://127.0.0.1:8897/health'):.2f}s")
    # Real POST roundtrip so a bound-but-not-listening server can't slip through.
    print(f"results  :8898 healthy in "
          f"{wait_http('http://127.0.0.1:8898/orchestrator-ping', data=b'{}'):.2f}s")

    # -- 3. launch shell, 4. kill venv app on phase-C marker --------------------------
    sse_app = PROCS[1]
    shell = spawn([SHELL_BIN])
    print(f"shell launched pid={shell.pid}")
    kill_epoch = None
    t_launch = time.time()
    while time.time() - t_launch < 75:
        if os.path.exists(f"{BUILD}/result.json"):
            break
        if kill_epoch is None and os.path.exists(f"{BUILD}/events.jsonl"):
            with open(f"{BUILD}/events.jsonl") as f:
                if any('"C_kill_midstream"' in ln and '"/marker"' in ln for ln in f):
                    time.sleep(0.2)  # let the stream visibly continue a beat
                    kill_epoch = time.time()
                    killpg(sse_app, signal.SIGKILL)  # sidecar-death simulation
                    print(f"SIGKILLed venv SSE app mid-stream at epoch {kill_epoch:.3f}")
        time.sleep(0.2)
    assert os.path.exists(f"{BUILD}/result.json"), "result.json never arrived (75s)"

    # -- 5. teardown ------------------------------------------------------------------
    for p in PROCS:
        killpg(p)
    restore_shell()
    left = [p.pid for p in PROCS if p.poll() is None]
    ports = subprocess.run(
        ["lsof", "-nP", "-iTCP:8897", "-iTCP:8898", "-iTCP:8899", "-sTCP:LISTEN"],
        capture_output=True, text=True).stdout.strip()
    print(f"leftover POC pids: {left or 'NONE'}; POC ports still LISTENing: {ports or 'NONE'}")

    # -- 6. assertions ----------------------------------------------------------------
    with open(f"{BUILD}/result.json") as f:
        rec = json.load(f)
    res = rec["body"]
    origins = [json.loads(ln) for ln in open(f"{BUILD}/origins.jsonl")]

    print("\n===== MEASURED =====")
    print(f"page origin (JS)     : {res['page_origin']}  (href={res['href']})")
    print(f"secure context       : {res['is_secure_context']}")
    print(f"results-POST Origin  : {rec['origin']}")
    for o in origins:
        print(f"SSE req {o['path']:12s} Origin={o['origin']}  "
              f"allowed_by_spec_6_3={o['allowed_by_spec_6_3']}")
    print(f"user agent           : {res['user_agent']}")

    def ticks(ph):
        return [e for e in ph["events"] if e["type"] == "tick"]

    for name in ("A_no_cors_sidecar", "B1_cors_plain", "B2_cors_padded", "C_kill_midstream"):
        ph = res["phases"][name]
        print(f"\n[{name}] done_reason={ph['done_reason']} "
              f"state_at_end={ph.get('state_at_end')} states={ph['states']}")
        for e in ph["events"]:
            print(f"   t={e['t']:>8.1f}ms {e}")

    # Phase A: no ACAO on the compiled sidecar -> what does WKWebView do?
    a = res["phases"]["A_no_cors_sidecar"]
    a_ticks = ticks(a)
    print(f"\nPhase A: {len(a_ticks)} ticks, reason={a['done_reason']} "
          f"(no-CORS response; spec 6.3 posture for a tauri:// origin)")

    # Phase B1: THE gate assertion - all 3 ticks, incrementally.
    b1 = ticks(res["phases"]["B1_cors_plain"])
    assert len(b1) == 3, f"B1: expected 3 ticks, got {len(b1)}"
    assert [e["data"] for e in b1] == ["0", "1", "2"], f"B1 order: {b1}"
    gaps = [round(b1[i + 1]["t"] - b1[i]["t"], 1) for i in range(2)]
    spread = round(b1[2]["t"] - b1[0]["t"], 1)
    print(f"B1 inter-event gaps: {gaps} ms, total spread {spread} ms (server delays: 400 ms)")
    assert all(g >= 200 for g in gaps), f"B1 NOT incremental (burst): gaps={gaps}"
    assert spread >= 500, f"B1 NOT incremental: spread={spread}"
    st = {s["at"]: s["readyState"] for s in res["phases"]["B1_cors_plain"]["states"]}
    assert st.get("constructed") == 0 and st.get("open") == 1, f"B1 readyState: {st}"
    assert res["phases"]["B1_cors_plain"]["state_after_close"] == 2

    # Phase B2: padded variant for comparison (workaround necessity check).
    b2 = ticks(res["phases"]["B2_cors_padded"])
    assert len(b2) == 3, f"B2: expected 3 ticks, got {len(b2)}"
    gaps2 = [round(b2[i + 1]["t"] - b2[i]["t"], 1) for i in range(2)]
    print(f"B2 (2KB padded) gaps: {gaps2} ms")
    # First-event latency after open (buffering shows up here if anywhere):
    for tag, phn in (("B1", "B1_cors_plain"), ("B2", "B2_cors_padded")):
        ph = res["phases"][phn]
        t_open = next(s["t"] for s in ph["states"] if s["at"] == "open")
        t_first = ticks(ph)[0]["t"]
        print(f"{tag} first tick {round(t_first - t_open, 1)} ms after onopen")

    # Phase C: mid-stream SIGKILL must surface as a prompt error event, not a hang.
    c = res["phases"]["C_kill_midstream"]
    c_ticks = ticks(c)
    assert len(c_ticks) >= 2, f"C: expected >=2 ticks before kill, got {len(c_ticks)}"
    assert c["done_reason"] == "error", f"C: expected error after SIGKILL, got {c['done_reason']}"
    err = next(e for e in c["events"] if e["type"] == "error")
    err_epoch = res["started_epoch_ms"] / 1000 + err["t"] / 1000
    latency = err_epoch - kill_epoch
    print(f"C: error event {latency*1000:.0f} ms after SIGKILL "
          f"(readyState in error handler: {err['readyState']})")
    assert kill_epoch is not None and latency < 3.0, f"C: error too late/hang: {latency:.2f}s"

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        for p in PROCS:
            killpg(p)
        restore_shell()
