"""Controlled DNS/socket fixtures; no requests to third-party targets."""
import socket
import threading
import time

import pytest
from syncbox import provider_http


def test_all_address_attempts_share_one_connection_deadline(monkeypatch):
    clock = [0]
    attempts = []
    monkeypatch.setattr(provider_http.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(provider_http, '_addresses', lambda *a: [(socket.AF_INET, socket.SOCK_STREAM, 0, '', (f'93.184.216.{i}', 443)) for i in range(10)])
    class Socket:
        def settimeout(self, timeout):
            self.timeout = timeout
        def connect(self, address):
            attempts.append(address)
            clock[0] += self.timeout
            raise TimeoutError('fixture connection timed out')
        def close(self):
            pass
    monkeypatch.setattr(provider_http.socket, 'socket', lambda *a: Socket())
    with pytest.raises(TimeoutError):
        provider_http.public_connection(('example.com', 443), timeout=15)
    assert len(attempts) == 1 and clock[0] == 15


def test_dns_wait_is_bounded_and_private_addresses_never_connect(monkeypatch):
    release = threading.Event()
    def resolve(*a, **kw):
        release.wait(1)
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('127.0.0.1', 443))]
    monkeypatch.setattr(provider_http.socket, 'getaddrinfo', resolve)
    before = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='provider_timeout'):
            provider_http.public_connection(('example.com', 443), timeout=.05)
        assert time.monotonic() - before < .5
    finally:
        release.set()
    monkeypatch.setattr(provider_http, '_addresses', lambda *a: resolve())
    monkeypatch.setattr(provider_http.socket, 'socket', lambda *a: pytest.fail('private address must not be fetched'))
    with pytest.raises(ValueError, match='private_network_destination'):
        provider_http.public_connection(('example.com', 443))
