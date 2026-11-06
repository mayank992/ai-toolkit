"""Local read-only HTTP server for `hs ui`: /api/snapshot plus the built React app."""
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import snapshot
from common import MODULE_ROOT, load_config

DIST = os.path.join(MODULE_ROOT, "ui", "dist")
ALLOWED_HOSTS = ("127.0.0.1", "localhost")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # The queue holds redacted prompt snippets; refuse DNS-rebinding requests from other origins.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            return self._send(403, b"forbidden host", "text/plain")
        path = self.path.split("?", 1)[0]
        if path == "/api/snapshot":
            body = snapshot.to_json(snapshot.build(load_config())).encode()
            return self._send(200, body, "application/json")
        rel = os.path.normpath(path.lstrip("/")) if path != "/" else "index.html"
        f = os.path.join(DIST, rel)
        if rel.startswith("..") or not os.path.isfile(f):
            f = os.path.join(DIST, "index.html")
        with open(f, "rb") as fh:
            body = fh.read()
        self._send(200, body, mimetypes.guess_type(f)[0] or "application/octet-stream")


def serve(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
