"""Shared helpers: paths, config, repo detection, store routing, queue IO.

Python 3.9-compatible, stdlib only (hooks may run under /usr/bin/python3 on macOS).
"""
import contextlib
import copy
import fcntl
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_CONFIG = {
    "stores": [
        {
            "name": "personal",
            "path": "~/.ai-memory/personal",
            "remote": "",
            "match": ["*"],
            "default": True,
        }
    ],
    "promote_at": 2,
    "cap_per_scope": 50,
    "retire_days": 60,
    "inject_budget_lines": 15,
    "inject_budget_chars": 1500,
    "auto_promote": True,
    "capture_context": True,
    "distill_model": "haiku",
}

LANG_MARKERS = {
    "package.json": "js",
    "tsconfig.json": "ts",
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "kotlin",
    "Gemfile": "ruby",
    "composer.json": "php",
    "Package.swift": "swift",
}


# ---------- environment / paths ----------

def disabled():
    """True when hooks must no-op (e.g. inside distill's own `claude -p`)."""
    return os.environ.get("HINDSIGHT_DISABLE") == "1"


def now_ts():
    """Unix time; overridable with HINDSIGHT_NOW for tests."""
    v = os.environ.get("HINDSIGHT_NOW")
    return float(v) if v else time.time()


def iso(ts=None):
    return datetime.fromtimestamp(now_ts() if ts is None else ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def config_path():
    return os.path.expanduser(os.environ.get("HINDSIGHT_CONFIG", "~/.config/ai-toolkit/hindsight.json"))


def state_dir():
    d = os.path.expanduser(os.environ.get("HINDSIGHT_STATE_DIR", "~/.local/state/hindsight"))
    os.makedirs(d, exist_ok=True)
    return d


def queue_path():
    return os.path.join(state_dir(), "queue.jsonl")


def offsets_path():
    return os.path.join(state_dir(), "offsets.json")


def log_path():
    return os.path.join(state_dir(), "hindsight.log")


def log(msg):
    try:
        with open(log_path(), "a") as f:
            f.write("%s %s\n" % (iso(), msg))
    except OSError:
        pass


# ---------- json helpers ----------

def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(path):
    """Exclusive advisory lock on <path>.lock."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def append_jsonl(path, record):
    with locked(path):
        with open(path, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def read_hook_input():
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}


# ---------- config ----------

def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    user = read_json(config_path(), None)
    if isinstance(user, dict):
        cfg.update(user)
    for s in cfg["stores"]:
        s["path"] = os.path.expanduser(s["path"])
    return cfg


def save_config(cfg):
    out = json.loads(json.dumps(cfg))
    home = os.path.expanduser("~")
    for s in out["stores"]:
        if s["path"].startswith(home):
            s["path"] = "~" + s["path"][len(home):]
    write_json_atomic(config_path(), out)


# ---------- repo detection ----------

def _git(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, timeout=2)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def normalize_remote(url):
    """git@host:a/b.git | https://u:p@host/a/b.git | ssh://git@host:22/a/b -> host/a/b"""
    if not url:
        return ""
    u = url.strip()
    u = re.sub(r"^[a-z+]+://", "", u)          # scheme
    u = re.sub(r"^[^@/]+@", "", u)              # user[:pass]@
    u = re.sub(r"^([^/:]+):(\d+)/", r"\1/", u)  # host:port/
    u = re.sub(r"^([^/:]+):", r"\1/", u)        # scp-style host:path
    u = re.sub(r"\.git/?$", "", u)
    return u.lower().rstrip("/")


def repo_info(cwd):
    """Return dict(repo, root, remote, langs). repo is a stable id for scoping."""
    cwd = cwd or os.getcwd()
    root = _git(cwd, "rev-parse", "--show-toplevel")
    remote = normalize_remote(_git(cwd, "remote", "get-url", "origin")) if root else ""
    base = root or cwd
    langs = sorted({lang for marker, lang in LANG_MARKERS.items() if os.path.exists(os.path.join(base, marker))})
    home = os.path.expanduser("~")
    if remote:
        repo = remote
    elif root:
        repo = "local:" + (("~" + root[len(home):]) if root.startswith(home) else root)
    else:
        repo = ""
    return {"repo": repo, "root": root, "remote": remote, "langs": langs}


# ---------- store routing ----------

def default_store(cfg):
    """The store flagged `default` (else the first one)."""
    return next((s for s in cfg["stores"] if s.get("default")), cfg["stores"][0])


def catch_all_globs(store):
    """Globs that match every remote. On a non-default store they would make the default unreachable."""
    return [p for p in store.get("match", []) if p.strip("*") == ""]


def route_store(cfg, remote):
    """Pick the first non-default store whose `match` globs fit the normalized remote; else default.

    Catch-all globs ("*") on non-default stores are ignored (`hs doctor` warns about them)."""
    if remote:
        for s in cfg["stores"]:
            if s.get("default"):
                continue
            pats = [p for p in s.get("match", []) if p not in catch_all_globs(s)]
            if any(fnmatch.fnmatch(remote, pat) for pat in pats):
                return s
    return default_store(cfg)


def short_hash(*parts):
    h = hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()
    return h[:10]


def hostname():
    import socket
    return re.sub(r"[^A-Za-z0-9_.-]", "_", socket.gethostname().split(".")[0]) or "host"
