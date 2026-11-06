"""Tool-agnostic parts of ai-setup: home templating, secret handling, snapshot trees, backups, config.

An adapter (one per AI tool) turns the live config into a *rendered tree* ({relpath: bytes}) that is
safe to commit, and turns a stored tree back into a list of *actions* that apply it. Everything in
this file is shared by every adapter.
"""
import json
import os
import re
import shutil
import subprocess
import time

HOME_TOKEN = "{{HOME}}"
MANIFEST = "manifest.json"


def home():
    return os.path.expanduser("~")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(os.environ.get("AI_SETUP_NOW") or time.time())))


# ---------------------------------------------------------------- config

def config_path():
    return os.path.join(home(), ".config", "ai-toolkit", "setup.json")


def load_config():
    cfg = {"snapshot_dir": "", "memory": True}
    try:
        with open(config_path()) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg["snapshot_dir"]:
        cfg["snapshot_dir"] = os.path.expanduser(cfg["snapshot_dir"])
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(config_path()), exist_ok=True)
    out = dict(cfg)
    if out.get("snapshot_dir", "").startswith(home() + os.sep):
        out["snapshot_dir"] = "~" + out["snapshot_dir"][len(home()):]
    with open(config_path(), "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------- home templating

def to_template(text, h=None):
    """Machine paths -> {{HOME}} so a snapshot works under any user name."""
    h = h or home()
    return text.replace(h, HOME_TOKEN)


def from_template(text, h=None):
    return text.replace(HOME_TOKEN, h or home())


def map_strings(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [map_strings(x, fn) for x in obj]
    if isinstance(obj, dict):
        return {k: map_strings(v, fn) for k, v in obj.items()}
    return obj


def encode_project(path):
    """Claude Code's project folder name for a path: every non-alphanumeric char becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


# ---------------------------------------------------------------- secrets

SECRET_NAME = re.compile(r"token|secret|passw|api[_-]?key|apikey|private[_-]?key|credential|auth|cookie|session", re.I)
TOKEN_SHAPES = [
    ("github token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("gitlab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("anthropic/openai key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}")),
]


def placeholder(secret_id):
    return "${secret:%s}" % secret_id


PLACEHOLDER = re.compile(r"\$\{secret:([^}]+)\}")


def is_unset(value):
    return not value or "${" in value


def token_hits(text):
    return [name for name, rx in TOKEN_SHAPES if rx.search(text)]


class Secrets(object):
    """Collects placeholders while an adapter redacts values; never stores the values themselves."""

    def __init__(self):
        self.ids = []

    def take(self, secret_id):
        if secret_id not in self.ids:
            self.ids.append(secret_id)
        return placeholder(secret_id)

    def mapping(self, d, prefix):
        """Redact values of secret-looking keys (env vars, headers)."""
        out = {}
        for k, v in (d or {}).items():
            if isinstance(v, str) and SECRET_NAME.search(k) and not is_unset(v):
                out[k] = self.take("%s.%s" % (prefix, k))
            else:
                out[k] = self.string(v, "%s.%s" % (prefix, k)) if isinstance(v, str) else v
        return out

    def args(self, args, prefix):
        """Redact `--token X`, `KEY=value` and token-shaped values in a command line."""
        out, redact_next = [], False
        for i, a in enumerate(args):
            if not isinstance(a, str):
                out.append(a)
                continue
            if redact_next:
                out.append(self.take("%s.arg%d" % (prefix, i)))
                redact_next = False
                continue
            m = re.match(r"^(-{1,2}[\w-]+|[A-Za-z_][A-Za-z0-9_]*)=(.+)$", a)
            if m and SECRET_NAME.search(m.group(1)) and not is_unset(m.group(2)):
                out.append("%s=%s" % (m.group(1), self.take("%s.%s" % (prefix, m.group(1).lstrip("-")))))
                continue
            if a.startswith("-") and SECRET_NAME.search(a) and "=" not in a and i + 1 < len(args):
                redact_next = True
            out.append(self.string(a, "%s.arg%d" % (prefix, i)))
        return out

    def string(self, s, secret_id):
        """Whole-value replacement when a free-form string carries a token shape or secret query param."""
        if token_hits(s):
            return self.take(secret_id)
        return re.sub(r"([?&](?:[\w-]*(?:token|key|secret|auth)[\w-]*)=)([^&#\s]+)",
                      lambda m: m.group(1) + self.take(secret_id + "." + m.group(1).strip("?&=")) if not is_unset(m.group(2))
                      else m.group(0), s, flags=re.I)


def fill_placeholders(obj, values):
    """Replace ${secret:id} with values[id]; returns (obj, missing ids)."""
    missing = []

    def fn(s):
        def sub(m):
            if m.group(1) in values:
                return values[m.group(1)]
            missing.append(m.group(1))
            return m.group(0)
        return PLACEHOLDER.sub(sub, s)
    return map_strings(obj, fn), missing


def env_secret_name(secret_id):
    return "AI_SETUP_SECRET_" + re.sub(r"[^A-Za-z0-9]", "_", secret_id).upper()


# ---------------------------------------------------------------- trees

def read_tree(root):
    """{relpath: bytes} for every file under root (missing root -> {})."""
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = fh.read()
    return out


def diff_trees(new, old):
    """[{path, change}] where change is added | changed | removed, sorted by path."""
    out = []
    for p in sorted(set(new) | set(old)):
        if p not in old:
            out.append({"path": p, "change": "added"})
        elif p not in new:
            out.append({"path": p, "change": "removed"})
        elif new[p] != old[p]:
            out.append({"path": p, "change": "changed"})
    return out


def write_tree(tree, root, modes=None):
    """Make root hold exactly `tree` (files not in it are deleted)."""
    for p in diff_trees(tree, read_tree(root)):
        full = os.path.join(root, p["path"])
        if p["change"] == "removed":
            os.remove(full)
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(tree[p["path"]])
    for p, mode in (modes or {}).items():
        if os.path.exists(os.path.join(root, p)):
            os.chmod(os.path.join(root, p), mode)
    for d, dirs, files in os.walk(root, topdown=False):
        if d != root and not dirs and not files and ".git" not in d.split(os.sep):
            os.rmdir(d)


# ---------------------------------------------------------------- applying

def state_dir():
    return os.path.join(home(), ".local", "state", "ai-toolkit", "setup")


class Backup(object):
    """Copies each file once, before its first write, into a timestamped folder."""

    def __init__(self):
        self.root = os.path.join(state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"))
        self.saved = set()

    def save(self, path):
        if path in self.saved or not os.path.isfile(path):
            return
        rel = os.path.relpath(path, home()) if path.startswith(home() + os.sep) else path.lstrip(os.sep)
        dest = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
        self.saved.add(path)


def write_file(path, data, backup, mode=None):
    backup.save(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".ai-setup.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    if mode:
        os.chmod(path, mode)


def tool_cmd(name):
    """argv prefix for an external CLI; tests swap it via AI_SETUP_<NAME>_CMD."""
    override = os.environ.get("AI_SETUP_%s_CMD" % name.upper())
    return override.split() if override else [name]


def run(argv, cwd=None, timeout=180):
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def git(root, *args):
    return run(["git", "-C", root] + list(args), timeout=60)


def snapshot_git(root):
    """Small git status for the dashboard: remote, uncommitted changes, last commit time."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return None
    ok, remote = git(root, "remote", "get-url", "origin")
    _, porcelain = git(root, "status", "--porcelain")
    ok2, last = git(root, "log", "-1", "--format=%cI")
    return {"remote": remote if ok else "", "dirty": bool(porcelain.strip()), "last_commit_at": last if ok2 else None}
