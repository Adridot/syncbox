"""Provider-only transport for the pinned yt-dlp runtime."""

import ipaddress
import socket
import urllib.request
from urllib.parse import urlsplit

from yt_dlp.networking import _urllib
from yt_dlp.networking._helper import create_connection, _socket_connect

PROVIDER_HOSTS = (
    "youtube.com", "youtu.be", "googlevideo.com", "ytimg.com",
    "youtubei.googleapis.com", "soundcloud.com", "sndcdn.com", "snd.sc",
    "soundcloud.app.goo.gl",
    "playback.media-streaming.soundcloud.cloud",
)


class BoundaryError(ValueError):
    pass


def validate_destination(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        valid = (
            len(url) <= 8192 and parsed.scheme == "https"
            and parsed.port in (None, 443) and not parsed.username and not parsed.password
            and any(host == domain or host.endswith("." + domain) for domain in PROVIDER_HOSTS)
        )
    except ValueError:
        valid = False
    if not valid:
        raise BoundaryError("unsupported_network_destination")


def public_socket(address, timeout, source_address):
    # Validate the exact resolved sockaddr used by connect, with no second DNS lookup.
    ip = ipaddress.ip_address(address[4][0])
    if not ip.is_global or (ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global):
        raise BoundaryError("private_network_destination")
    return _socket_connect(address, timeout, source_address)


def public_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    return create_connection(address, timeout, source_address, _create_socket_func=public_socket)


class Budget:
    def __init__(self, max_bytes, max_requests=500):
        self.remaining_bytes = max_bytes
        self.remaining_requests = max_requests


class Boundary(urllib.request.BaseHandler):
    handler_order = 100  # Check each redirect before HTTPHandler connects/decompresses.

    def __init__(self, budget, validator=validate_destination):
        self.budget = budget
        self.validator = validator

    def http_request(self, request):
        self.validator(request.full_url)
        self.budget.remaining_requests -= 1
        if self.budget.remaining_requests < 0:
            raise BoundaryError("network_request_limit")
        request.add_header("Accept-Encoding", "identity")
        return request

    https_request = http_request

    def http_response(self, request, response):
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            response.close()
            raise BoundaryError("compressed_network_response_refused")
        original_read = response.read

        def read(size=-1):
            limit = self.budget.remaining_bytes
            size = min(limit + 1, size) if size is not None and size >= 0 else limit + 1
            data = original_read(size)
            self.budget.remaining_bytes -= len(data)
            if self.budget.remaining_bytes < 0:
                response.close()
                raise BoundaryError("network_byte_limit")
            return data

        response.read = read
        return response

    https_response = http_response


def transport(budget):
    # yt-dlp's private urllib integration is covered by tests and its exact lock.
    # Force this sole handler; other transports must not bypass the boundary.
    _urllib.create_connection = public_connection

    class ProviderUrllibRH(_urllib.UrllibRH):
        _SUPPORTED_URL_SCHEMES = ("https",)
        _SUPPORTED_PROXY_SCHEMES = ()

        def _create_instance(self, *args, **kwargs):
            opener = super()._create_instance(*args, **kwargs)
            opener.add_handler(Boundary(budget))
            return opener

    return ProviderUrllibRH
