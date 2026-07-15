"""Validate optional-component installation through a live base sidecar.

By default this launches the source sidecar. Set SYNCBOX_SIDECAR_BIN to test
the frozen onedir, or SYNCBOX_SHELL_BIN to test the packaged Tauri shell.
The release archive is always checked against the manifest embedded in the
base sidecar. No Deezer credential is read or required.
"""

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PORT = 8766
SOURCE_PYTHON = REPO / "sidecar/.venv/bin/python"
SOURCE_CWD = REPO / "sidecar"
DEFAULT_ARCHIVE = (
    REPO
    / "optional-component/dist/syncbox-deezer-component-0.2.2-macos-arm64.zip"
)


def request(path, *, method="GET", body=None, timeout=3):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    with urllib.request.urlopen(
        urllib.request.Request(
            f"http://127.0.0.1:{PORT}{path}",
            data=data,
            headers=headers,
            method=method,
        ),
        timeout=timeout,
    ) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def port_accepting():
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def wait_for(predicate, seconds, description):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        try:
            if predicate():
                return time.monotonic() - start
        except Exception:
            pass
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting for {description}")


def main():
    shell = os.environ.get("SYNCBOX_SHELL_BIN")
    frozen = os.environ.get("SYNCBOX_SIDECAR_BIN")
    archive = Path(
        os.environ.get("SYNCBOX_DEEZER_COMPONENT_ARCHIVE", DEFAULT_ARCHIVE)
    ).resolve(strict=True)
    assert not port_accepting(), f"port {PORT} busy before test"

    if shell:
        mode = "packaged"
        command, cwd = [str(Path(shell).resolve(strict=True))], None
    elif frozen:
        mode = "frozen"
        command, cwd = [str(Path(frozen).resolve(strict=True))], None
    else:
        mode = "source"
        command, cwd = [str(SOURCE_PYTHON), "-u", "-m", "syncbox"], SOURCE_CWD

    with tempfile.TemporaryDirectory(prefix="syncbox-component-harness-") as raw_data:
        data_dir = Path(raw_data)
        log_path = data_dir / "host.log"
        env = {
            **os.environ,
            "SYNCBOX_DATA_DIR": raw_data,
            "SYNCBOX_DEEZER_COMPONENT_ARCHIVE": str(archive),
        }
        if mode == "source":
            env["PYTHONPATH"] = str(REPO / "sidecar/src")
        if mode == "packaged":
            env["SYNCBOX_EXIT_AFTER_SECS"] = "30"

        started = time.monotonic()
        with log_path.open("wb") as output:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=output,
                start_new_session=mode != "packaged",
            )
            try:
                try:
                    ready = wait_for(
                        lambda: request("/health", timeout=0.3).get("ok"),
                        20,
                        "sidecar health",
                    )
                except AssertionError as error:
                    output.flush()
                    host_log = log_path.read_text(errors="replace")
                    raise AssertionError(
                        f"{error}; host rc={process.poll()}; log={host_log!r}"
                    ) from error
                request(
                    "/api/settings",
                    method="PUT",
                    body={"deezer_acquisition_enabled": True},
                )
                installed = request(
                    "/api/acquisition/component/install",
                    method="POST",
                    body={},
                    timeout=60,
                )["component"]
                status = request("/api/acquisition/deezer")
                assert installed["installed"] is True
                assert status["component"]["installed"] is True
                assert status["has_arl"] is False
                root = data_dir / "optional/streamrip-deezer" / installed[
                    "streamrip_commit"
                ]
                assert (root / "syncbox-deezer-component").is_file()
                assert not (root / "bin/python").exists()

                if mode == "packaged":
                    process.wait(timeout=40)
                else:
                    request("/shutdown", method="POST", timeout=3)
                    assert process.wait(timeout=10) == 0
                wait_for(lambda: not port_accepting(), 5, "port release")
            finally:
                if process.poll() is None:
                    if mode != "packaged":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        process.kill()
                    process.wait()

        result = {
            "ok": True,
            "mode": mode,
            "ready_seconds": round(ready, 2),
            "total_seconds": round(time.monotonic() - started, 2),
            "component_version": installed["component_version"],
            "streamrip_version": installed["streamrip_version"],
            "streamrip_commit": installed["streamrip_commit"],
            "archive_sha256": installed["sha256"],
            "credential_present": status["has_arl"],
            "external_python_required": False,
            "port_released": True,
        }
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
