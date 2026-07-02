"""POC #4 - tiny results endpoint (127.0.0.1:8898). The WKWebView page POSTs progress
markers and the final result here; every request's Origin header is recorded verbatim.
POST /marker -> appended to build/events.jsonl (orchestrator polls it)
POST /result -> build/result.json (final payload) + appended to events.jsonl
Answers CORS (echo) so the cross-origin page can POST; measurement-only, see sidecar_cors.py.
"""

import json
import socketserver
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

BUILD = sys.argv[1]


class LoopbackHTTPServer(HTTPServer):
    """Stock HTTPServer.server_bind calls socket.getfqdn(), which hangs in sandboxed/
    DNS-less environments BEFORE listen() is reached (bound port, no listener, connects
    time out). Loopback-only server needs no fqdn -> skip it. (Measured on this machine:
    getfqdn('127.0.0.1') hung > 3 s.)"""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw)
        except Exception:
            body = {"unparsed": raw.decode("utf-8", "replace")}
        rec = {
            "t_epoch": time.time(),
            "path": self.path,
            "origin": self.headers.get("Origin"),
            "body": body,
        }
        with open(BUILD + "/events.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        if self.path == "/result":
            with open(BUILD + "/result.json", "w") as f:
                json.dump(rec, f, indent=2)
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    LoopbackHTTPServer(("127.0.0.1", 8898), H).serve_forever()
