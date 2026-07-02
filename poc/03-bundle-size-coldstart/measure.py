"""POC #3 measurement: cold-start = spawn -> first HTTP 200 on /health, median of 3."""

import json
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

BIN = Path(__file__).parent / "build/dist/syncbox-sidecar-poc/syncbox-sidecar-poc"
URL = "http://127.0.0.1:8899/health"


def one_run():
    t0 = time.perf_counter()
    p = subprocess.Popen([str(BIN)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while True:
            try:
                with urllib.request.urlopen(URL, timeout=0.25) as r:
                    if r.status == 200:
                        body = json.loads(r.read())
                        return time.perf_counter() - t0, body["import_to_ready_s"]
            except (urllib.error.URLError, OSError):
                pass
            if time.perf_counter() - t0 > 30:
                raise RuntimeError("sidecar did not become ready in 30s")
            time.sleep(0.01)
    finally:
        p.terminate()
        p.wait(timeout=10)


if __name__ == "__main__":
    runs = [one_run() for _ in range(3)]
    print("cold-start spawn->200 (s):", [round(t, 3) for t, _ in runs])
    print("median (s):", round(statistics.median([t for t, _ in runs]), 3))
    print("import_to_ready inside process (s):", [i for _, i in runs])
