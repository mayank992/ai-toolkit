"""Local read-only HTTP server for the ai-toolkit dashboard.

  GET /api/modules              modules whose module.json has a "ui" block
  GET /api/m/<name>/snapshot    runs that module's snapshot command and returns its JSON
  everything else               the built shell app (ui/dist), with index.html as the fallback

Each module produces its own snapshot in a subprocess, so modules never share an interpreter
(no import clashes between their lib/ folders) and a broken module can't take the others down.
"""
import json
import mimetypes
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = os.path.join(REPO, "modules")
DIST = os.path.join(REPO, "ui", "dist")
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
SNAPSHOT_TIMEOUT_S = 30
SNAPSHOT_PATH = re.compile(r"^/api/m/([A-Za-z0-9_-]+)/snapshot$")


def discover():
    """[{name, title, tagline, dir, snapshot}] for each module that opts into the dashboard."""
    out = []
    for name in sorted(os.listdir(MODULES)) if os.path.isdir(MODULES) else []:
        try:
            with open(os.path.join(MODULES, name, "module.json")) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            continue
        ui = manifest.get("ui")
        if not ui or not ui.get("snapshot"):
            continue
        out.append({"name": name, "title": ui.get("title") or name,
                    "tagline": ui.get("tagline") or manifest.get("description", ""),
                    "dir": os.path.join(MODULES, name), "snapshot": ui["snapshot"]})
    return out


def run_snapshot(mod):
    """(status, body bytes, content type) from the module's snapshot command."""
    cmd = [os.path.join(mod["dir"], mod["snapshot"][0])] + list(mod["snapshot"][1:])
    try:
        p = subprocess.run(cmd, cwd=mod["dir"], capture_output=True, timeout=SNAPSHOT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 504, ("%s snapshot timed out after %ds" % (mod["name"], SNAPSHOT_TIMEOUT_S)).encode(), "text/plain"
    except OSError as e:
        return 502, ("%s snapshot could not start: %s" % (mod["name"], e)).encode(), "text/plain"
    if p.returncode != 0:
        tail = p.stderr.decode(errors="replace").strip().splitlines()[-15:]
        return 502, ("%s snapshot exited %d\n%s" % (mod["name"], p.returncode, "\n".join(tail))).encode(), "text/plain"
    try:
        json.loads(p.stdout)
    except ValueError:
        return 502, ("%s snapshot did not print JSON" % mod["name"]).encode(), "text/plain"
    return 200, p.stdout, "application/json"


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
            mods = [{k: m[k] for k in ("name", "title", "tagline")} for m in discover()]
            return self._send(200, json.dumps(mods).encode(), "application/json")
        m = SNAPSHOT_PATH.match(path)
        if m:
            mod = next((x for x in discover() if x["name"] == m.group(1)), None)
            if not mod:
                return self._send(404, ("no module %r with a dashboard" % m.group(1)).encode(), "text/plain")
            return self._send(*run_snapshot(mod))
        if path.startswith("/api/"):
            return self._send(404, b"unknown endpoint", "text/plain")
        rel = os.path.normpath(path.lstrip("/")) if path != "/" else "index.html"
        f = os.path.join(DIST, rel)
        if rel.startswith("..") or not os.path.isfile(f):
            f = os.path.join(DIST, "index.html")
        with open(f, "rb") as fh:
            body = fh.read()
        self._send(200, body, mimetypes.guess_type(f)[0] or "application/octet-stream")


def serve(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
