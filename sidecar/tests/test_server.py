"""Tests for the loopback HTTP+SSE service (SPEC-UNIFIED 6.3/6.6/6.10 + the
2026-07-02 CORS amendment, POC #4)."""

import asyncio
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
from starlette.testclient import TestClient

from syncbox import server
from syncbox.server import (
    JobBus,
    OAuthCallbackListener,
    OAuthCallbackPortInUseError,
    PortInUseError,
    create_app,
    ensure_port_free,
)

ALLOWED_ORIGINS = [
    "tauri://localhost",       # macOS WKWebView, measured in POC #4
    "http://tauri.localhost",  # Windows WebView2 per Tauri v2 docs
    "http://127.0.0.1:1420",
    "http://localhost:5173",
]


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_cors_allows_webview_and_loopback_origins(origin):
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    # allow_credentials must stay False: the header is simply absent
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example.com",
        "http://127.0.0.1.evil.com:8080",
        "tauri://evil",
        "http://192.168.1.10:8080",
    ],
)
def test_cors_rejects_non_loopback_origins(origin):
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers


def test_health_identifies_the_sidecar_protocol_exactly():
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": server.SERVICE_NAME,
        "protocol": server.PROTOCOL_VERSION,
    }
    assert response.headers["cache-control"] == "no-store"


def test_jobbus_delivers_published_events():
    async def scenario():
        bus = JobBus()
        stream = bus.stream()
        consume = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0)  # let the subscriber register
        await bus.publish("job.progress", {"id": "j1", "pct": 40})
        event = await asyncio.wait_for(consume, timeout=1)
        await stream.aclose()
        return event

    event = asyncio.run(scenario())
    assert event["event"] == "job.progress"
    assert '"pct": 40' in event["data"]


def test_jobbus_close_ends_active_streams():
    async def scenario():
        bus = JobBus()
        stream = bus.stream()
        consume = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0)
        bus.close()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(consume, timeout=1)
        with pytest.raises(StopAsyncIteration):
            await anext(bus.stream())

    asyncio.run(scenario())


def test_events_endpoint_streams_sse():
    class OneShotBus(JobBus):
        async def stream(self):
            yield {"event": "job.done", "data": '{"id": "j1"}'}

    client = TestClient(create_app(bus=OneShotBus()))
    with client.stream("GET", "/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert "event: job.done" in body
    assert 'data: {"id": "j1"}' in body


def test_shutdown_sets_intent_then_triggers():
    app = create_app()
    order = []
    app.state.shutdown.bind(
        lambda: order.append(("trigger", app.state.shutdown.intentional))
    )
    client = TestClient(app)
    response = client.post("/shutdown")
    assert response.status_code == 202
    # intent flag was already True when the stop trigger fired (6.6 handshake)
    assert order == [("trigger", True)]


def test_permanent_service_does_not_expose_oauth_callback():
    client = TestClient(create_app())
    assert client.get("/callback?code=x").status_code == 404


def _callback_request(listener, query, *, host="localhost:8765"):
    request = urllib.request.Request(
        f"http://127.0.0.1:{listener.port}/callback?{query}",
        headers={"Host": host},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, response.read().decode(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), exc.headers


def test_temporary_callback_rejects_forgery_then_closes_after_success():
    seen = []

    def oauth_callback(params):
        seen.append(params)
        if params.get("state") != "right":
            return {"ok": False, "error": "state_mismatch"}
        return {"ok": True}

    listener = OAuthCallbackListener(port=0)
    listener.start(oauth_callback, timeout=5)
    assert listener.active
    assert listener._server.config.access_log is False
    assert listener._server.config.proxy_headers is False

    status, body, headers = _callback_request(listener, "code=abc&state=wrong")
    assert status == 400
    assert '"error":"state_mismatch"' in body
    assert headers["Cache-Control"] == "no-store"
    assert listener.active  # forged callbacks must not cancel the real attempt

    # Host is deliberately ignored; the redirect URI is never derived from it.
    status, body, headers = _callback_request(listener, "code=abc&state=right")
    assert status == 200
    assert "close this window" in body
    assert headers["Cache-Control"] == "no-store"
    listener.wait_closed()
    assert not listener.active
    assert seen == [
        {"code": "abc", "state": "wrong"},
        {"code": "abc", "state": "right"},
    ]


def test_temporary_callback_closes_after_terminal_denial_and_timeout():
    denied = OAuthCallbackListener(port=0)
    denied.start(
        lambda params: {"ok": False, "error": "access_denied"}, timeout=5
    )
    assert _callback_request(denied, "error=access_denied&state=right")[0] == 400
    denied.wait_closed()
    assert not denied.active

    expired = OAuthCallbackListener(port=0)
    expired.start(lambda params: {"ok": True}, timeout=0.05)
    expired.wait_closed()
    assert not expired.active


def test_slow_callback_uses_threadpool_and_shared_lock_without_blocking_shutdown():
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    callback_response = []

    def slow_callback(params):
        assert lock.locked()
        started.set()
        assert release.wait(timeout=3)
        return {"ok": True}

    listener = OAuthCallbackListener(port=0)
    listener.start(slow_callback, oauth_lock=lock, timeout=5)
    app = create_app()
    with TestClient(app) as client:
        worker = threading.Thread(
            target=lambda: callback_response.append(
                _callback_request(listener, "code=abc&state=s1")
            )
        )
        worker.start()
        assert started.wait(timeout=1)
        timer = threading.Timer(2, release.set)
        timer.start()
        t0 = time.perf_counter()
        response = client.post("/shutdown")
        elapsed = time.perf_counter() - t0
        release.set()
        worker.join(timeout=3)
        timer.cancel()

    assert response.status_code == 202
    assert elapsed < 1
    listener.wait_closed()
    assert callback_response[0][0] == 200


def test_temporary_callback_collision_preserves_foreign_listener():
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    listener = OAuthCallbackListener(port=blocker.getsockname()[1])
    try:
        with pytest.raises(OAuthCallbackPortInUseError) as info:
            listener.start(lambda params: {"ok": True})
        assert "already in use" in str(info.value)
        assert blocker.getsockname()[1] == listener.port
    finally:
        blocker.close()


def test_port_collision_fails_clean_with_actionable_message():
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    port = blocker.getsockname()[1]
    try:
        with pytest.raises(PortInUseError) as info:
            ensure_port_free("127.0.0.1", port)
        assert "already in use" in str(info.value)
        assert "relaunch" in str(info.value)
    finally:
        blocker.close()
    ensure_port_free("127.0.0.1", port)  # freed -> no raise


def test_no_gzip_middleware_anywhere():
    # sse-starlette breaks under GZipMiddleware; the app must not add one.
    app = create_app()
    names = [m.cls.__name__ for m in app.user_middleware]
    assert "GZipMiddleware" not in names
