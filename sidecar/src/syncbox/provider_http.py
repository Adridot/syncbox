"""Small bounded HTTPS transport for catalogue metadata and provider share links."""

import http.client
import ipaddress
import socket
import ssl
import time
import queue
import threading
from urllib.parse import urljoin, urlsplit

import certifi

# System DNS has no Python socket timeout. Limit both waiting and outstanding lookups.
_DNS_SLOTS = threading.BoundedSemaphore(2)


def _addresses(address, timeout):
    deadline = time.monotonic() + timeout
    if not _DNS_SLOTS.acquire(timeout=timeout):
        raise TimeoutError("provider_timeout")
    result = queue.Queue(maxsize=1)
    def resolve():
        try:
            result.put((socket.getaddrinfo(*address, type=socket.SOCK_STREAM), None))
        except Exception as error:
            result.put((None, error))
        finally:
            _DNS_SLOTS.release()
    threading.Thread(target=resolve, daemon=True, name="provider-dns").start()
    try:
        addresses, error = result.get(timeout=max(0, deadline - time.monotonic()))
    except queue.Empty:
        raise TimeoutError("provider_timeout") from None
    if error:
        raise error
    return addresses


def validate_url(url, hosts):
    try:
        parsed = urlsplit(url)
        if len(url) > 8192 or parsed.scheme != "https" or parsed.hostname not in hosts or parsed.port not in (None, 443) or parsed.username or parsed.password:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise ValueError("unsupported_network_destination") from None


def public_connection(address, timeout=15, source_address=None):
    last_error = None
    deadline = time.monotonic() + timeout
    for family, kind, proto, _, sockaddr in _addresses(address, timeout):
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global or (ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global):
            raise ValueError("private_network_destination")
        sock = socket.socket(family, kind, proto)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("provider_timeout")
            sock.settimeout(remaining)
            sock.connect(sockaddr)
            sock.settimeout(max(.001, deadline - time.monotonic()))
            return sock
        except OSError as error:
            last_error = error
            sock.close()
    raise last_error or OSError("provider_address_unavailable")


def request(url, *, hosts, headers=None, data=None, method="GET", headers_only=False, max_bytes=4 * 1024 * 1024, timeout=15):
    deadline = time.monotonic() + 30
    origin = urlsplit(url).hostname
    for _ in range(6):
        parsed = validate_url(url, hosts)
        if headers and any(key.lower() == "authorization" for key in headers) and parsed.hostname != origin:
            raise ValueError("credential_redirect_refused")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("provider_timeout")
        conn = http.client.HTTPSConnection(parsed.hostname, timeout=min(timeout, remaining), context=ssl.create_default_context(cafile=certifi.where()))
        conn._create_connection = public_connection
        try:
            conn.request(method, parsed.path + ("?" + parsed.query if parsed.query else ""), body=data,
                         headers={**(headers or {}), "Accept-Encoding": "identity"})
            transport_socket = getattr(conn, "sock", None)
            if transport_socket:
                transport_socket.settimeout(max(.001, deadline - time.monotonic()))
            response = conn.getresponse()
            response_headers = dict(response.getheaders())
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("invalid_provider_redirect")
                url = urljoin(url, location)
                if method != "GET":
                    raise ValueError("provider_post_redirect_refused")
                continue
            if headers_only:
                return response.status, response_headers, b"", url
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("compressed_network_response_refused")
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("provider_timeout")
                if transport_socket:
                    transport_socket.settimeout(max(.001, min(timeout, deadline - time.monotonic())))
                chunk = response.read1(min(65536, max_bytes + 1 - size))
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("network_byte_limit")
                if not chunk:
                    return response.status, response_headers, b"".join(chunks), url
                chunks.append(chunk)
        finally:
            conn.close()
    raise ValueError("provider_redirect_limit")
