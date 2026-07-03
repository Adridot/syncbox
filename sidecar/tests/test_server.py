"""Tests for the loopback HTTP+SSE service (SPEC-UNIFIED 6.3/6.6/6.10 + the
2026-07-02 CORS amendment, POC #4)."""

import asyncio
import socket

import pytest
from starlette.testclient import TestClient

from syncbox import server
from syncbox.server import JobBus, PortInUseError, create_app, ensure_port_free

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


def test_callback_unconfigured_returns_503():
    client = TestClient(create_app())
    assert client.get("/callback?code=x").status_code == 503


def test_callback_works_regardless_of_host_header():
    seen = []

    def oauth_callback(params):
        seen.append(params)
        return {"ok": True}

    client = TestClient(create_app(oauth_callback=oauth_callback))
    # Browser rewrote 127.0.0.1 -> localhost: the route must still answer.
    response = client.get(
        "/callback?code=abc&state=s1", headers={"Host": "localhost:8765"}
    )
    assert response.status_code == 200
    assert "close this window" in response.text
    assert seen == [{"code": "abc", "state": "s1"}]


def test_callback_error_returns_400():
    client = TestClient(
        create_app(oauth_callback=lambda params: {"ok": False, "error": "state_mismatch"})
    )
    response = client.get("/callback?code=abc&state=wrong")
    assert response.status_code == 400
    assert response.json()["error"] == "state_mismatch"


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
