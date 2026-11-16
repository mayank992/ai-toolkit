"""Local read-only HTTP server for the ai-toolkit dashboard.

  GET /api/modules              enabled features: [{name, title, tagline}]
  GET /api/m/<name>/snapshot    that feature's api.snapshot() as JSON
  everything else               the built web app (ui/dist), with index.html as the fallback

Snapshots are built in-process, each on its own thread with a timeout: a slow or broken feature
answers 504/502 for its own card and never takes the others down. The server binds to 127.0.0.1,
rejects any Host header that isn't local (DNS rebinding) and has no endpoint that writes.
"""
import importlib
import json
import mimetypes
import os
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..core import config
from .registry import FEATURES

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DIST = os.path.join(REPO, "ui", "dist")
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
SNAPSHOT_TIMEOUT_S = 30
SNAPSHOT_PATH = re.compile(r"^/api/m/([A-Za-z0-9_-]+)/snapshot$")


def discover():
    """Registered features that are enabled in config."""
    return [f for f in FEATURES if config.enabled(f["name"])]


def run_snapshot(feature, timeout=SNAPSHOT_TIMEOUT_S):
    """(status, body bytes, content type)."""
    result = {}

    def work():
        try:
            snap = importlib.import_module(feature["api"]).snapshot()
            result["body"] = json.dumps(snap, default=list).encode()
        except BaseException:  # SystemExit from a feature must not kill the server thread silently
            result["error"] = traceback.format_exc().strip().splitlines()[-15:]

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return 504, ("%s snapshot timed out after %ds" % (feature["name"], timeout)).encode(), "text/plain"
    if "error" in result:
        return 502, ("%s snapshot failed\n%s" % (feature["name"], "\n".join(result["error"]))).encode(), "text/plain"
    return 200, result["body"], "application/json"


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
        # Snapshots hold redacted prompt snippets and local config; refuse DNS-rebinding requests.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            return self._send(403, b"forbidden host", "text/plain")
        path = self.path.split("?", 1)[0]
        if path == "/api/modules":
            mods = [{k: f[k] for k in ("name", "title", "tagline")} for f in discover()]
            return self._send(200, json.dumps(mods).encode(), "application/json")
        m = SNAPSHOT_PATH.match(path)
        if m:
            feature = next((f for f in discover() if f["name"] == m.group(1)), None)
            if not feature:
                return self._send(404, ("no feature %r with a dashboard" % m.group(1)).encode(), "text/plain")
            return self._send(*run_snapshot(feature))
        if path.startswith("/api/"):
            return self._send(404, b"unknown endpoint", "text/plain")
        rel = os.path.normpath(path.lstrip("/")) if path != "/" else "index.html"
        f = os.path.join(DIST, rel)
        if rel.startswith("..") or not os.path.isfile(f):
            if rel.startswith("assets" + os.sep):  # a stale page asking for an old build; HTML here would fail silently
                return self._send(404, b"not in this build; reload the page", "text/plain")
            f = os.path.join(DIST, "index.html")
        with open(f, "rb") as fh:
            body = fh.read()
        self._send(200, body, mimetypes.guess_type(f)[0] or "application/octet-stream")


def serve(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
