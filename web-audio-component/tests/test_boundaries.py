import socket
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import build_opener, ProxyHandler, Request

import pytest
from yt_dlp.networking import Request as ProviderRequest
from yt_dlp.networking.exceptions import RequestError

import network
import runner


@pytest.mark.parametrize("url", [
    "http://www.youtube.com/watch?v=f7NwyBnIRTE", "file:///tmp/audio.mp3",
    "https://youtube.com.example.invalid/a", "https://user:secret@youtube.com/a",
    "https://youtube.com:444/a", "https://127.0.0.1/a", "https://example.org/a",
])
def test_reject_destination(url):
    with pytest.raises(network.BoundaryError):
        network.validate_destination(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"])
def test_reject_resolved_private_address_before_connect(address, monkeypatch):
    def unexpected(*args):
        pytest.fail("disallowed destination was connected")
    monkeypatch.setattr(network, "_socket_connect", unexpected)
    with pytest.raises(network.BoundaryError):
        network.public_socket((socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)), 1, None)


@pytest.mark.parametrize("reference", ["share", "child", "media"])
def test_redirect_and_response_bounds_with_local_fixture(reference):
    fetched = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            fetched.append(self.path)
            if self.path.startswith("/redirect/"):
                self.send_response(302)
                self.send_header("Location", "/refused")
            else:
                self.send_response(200)
            self.end_headers()
            self.wfile.write(b"fixture payload")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    def fixture_destination(url):
        if url != origin + "/redirect/" + reference and url != origin + "/large":
            raise network.BoundaryError("fixture_destination_refused")
    try:
        opener = build_opener(ProxyHandler({}), network.Boundary(network.Budget(1000), fixture_destination))
        with pytest.raises(network.BoundaryError, match="destination_refused"):
            opener.open(origin + "/redirect/" + reference, timeout=2)
        assert fetched == ["/redirect/" + reference]
        opener = build_opener(ProxyHandler({}), network.Boundary(network.Budget(10), fixture_destination))
        with pytest.raises(network.BoundaryError, match="byte_limit"):
            opener.open(origin + "/large", timeout=2).read()
        assert "/refused" not in fetched
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_process_tree_stop_terminates_grandchild(tmp_path):
    marker = tmp_path / "unexpected-grandchild-output"
    child_code = "import time,signal; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('armed',flush=True); time.sleep(2); Path(%r).touch()" % str(marker)
    leader_code = "import subprocess, sys, time; child=subprocess.Popen([sys.executable, '-c', %r],stdout=subprocess.PIPE); child.stdout.readline(); print('ready', flush=True); time.sleep(20)" % child_code
    process = subprocess.Popen([sys.executable, "-c", leader_code], start_new_session=True, stdout=subprocess.PIPE)
    assert process.stdout.readline() == b"ready\n"
    runner.stop_group(process)
    assert process.poll() is not None
    # Waiting exceeds the child's scheduled write and catches orphaned descendants.
    threading.Event().wait(2.2)
    assert not marker.exists()


def test_supervisor_timeout_stops_worker(monkeypatch):
    real_popen = subprocess.Popen
    processes = []
    def stalled_worker(*args, **kwargs):
        process = real_popen([sys.executable, "-c", "import time; time.sleep(20)"], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(runner.subprocess, "Popen", stalled_worker)
    monkeypatch.setitem(runner.TIMEOUTS, "metadata", .05)
    with pytest.raises(runner.ComponentError, match="operation_timeout"):
        runner.supervise({"operation": "metadata"})
    assert processes[0].poll() is not None


def test_supervisor_signal_cancels_worker_and_grandchild(tmp_path):
    ready = tmp_path / "ready"
    orphan = tmp_path / "orphan"
    grandchild = f"import time; from pathlib import Path; time.sleep(2); Path({str(orphan)!r}).touch()"
    worker = (
        "import subprocess, sys, time; from pathlib import Path; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
        f"Path({str(ready)!r}).touch(); time.sleep(20)"
    )
    supervisor = (
        "import runner, subprocess, sys\n"
        "real_popen = subprocess.Popen\n"
        f"runner.subprocess.Popen = lambda *a, **kw: real_popen([sys.executable, '-c', {worker!r}], **kw)\n"
        "try:\n    runner.supervise({'operation': 'metadata'})\n"
        "except runner.ComponentError as error:\n    print(str(error), flush=True)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", supervisor], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(Path(runner.__file__).parent)},
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            threading.Event().wait(.02)
        assert ready.exists()
        process.send_signal(signal.SIGTERM)
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 0, errors
        assert output == b"operation_cancelled\n"
        threading.Event().wait(2.2)
        assert not orphan.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_budget_is_shared_across_responses_and_requests():
    boundary = network.Boundary(network.Budget(5, max_requests=2))
    request = Request("https://www.youtube.com/")
    for payload in (b"abc", b"def"):
        boundary.http_request(request)
        response = BytesIO(payload)
        response.headers = {}
        bounded = boundary.http_response(request, response)
        if payload == b"abc":
            assert bounded.read() == payload
        else:
            with pytest.raises(network.BoundaryError, match="network_byte_limit"):
                bounded.read()
    with pytest.raises(network.BoundaryError, match="network_request_limit"):
        boundary.http_request(request)


def test_compressed_response_is_refused_before_read():
    boundary = network.Boundary(network.Budget(100))
    response = BytesIO(b"compressed fixture")
    response.headers = {"Content-Encoding": "gzip"}
    with pytest.raises(network.BoundaryError, match="compressed_network_response_refused"):
        boundary.http_response(Request("https://www.youtube.com/"), response)
    assert response.closed


def test_pinned_transport_refuses_destination_before_resolution(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("disallowed destination reached DNS resolution")
    monkeypatch.setattr(socket, "getaddrinfo", unexpected)
    with network.transport(network.Budget(100))(logger=runner.QuietLogger()) as handler:
        with pytest.raises(RequestError, match="unsupported_network_destination"):
            handler.send(ProviderRequest("https://example.invalid/"))


def test_pinned_transport_checks_resolved_socket_before_connect(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    def unexpected(*args, **kwargs):
        pytest.fail("private socket was connected")
    monkeypatch.setattr(network, "_socket_connect", unexpected)
    with network.transport(network.Budget(100))(logger=runner.QuietLogger()) as handler:
        with pytest.raises(RequestError, match="private_network_destination"):
            handler.send(ProviderRequest("https://www.youtube.com/"))


def test_video_playlist_choice_and_metadata_identity():
    with pytest.raises(runner.ComponentError, match="choice_required"):
        runner.identity("https://www.youtube.com/watch?v=f7NwyBnIRTE&list=PL6B3937A5D230E335")
    assert runner.identity("https://youtu.be/f7NwyBnIRTE?t=20")[2] == "f7NwyBnIRTE"
    assert runner.identity("https://api-v2.soundcloud.com/tracks/565801467") == ("soundcloud", "track", "565801467", "https://api-v2.soundcloud.com/tracks/565801467")
    with pytest.raises(runner.ComponentError, match="unsupported_resource"):
        runner.identity("https://api-v2.soundcloud.com/playlists/1")
    child = runner.entry({"id": "1757017227", "url": "https://soundcloud.com/trackistador/kevin-macleod-all-this", "uploader": "Not the artist"}, "soundcloud", 3)
    assert child["artist"] is None
    assert child["item_id"] == "1757017227"
    assert child["entry_key"] == "3:1757017227"
