"""Tool-agnostic parts of setup: home templating, secret handling, snapshot trees, backups, config.

An adapter (one per AI tool) turns the live config into a *rendered tree* ({relpath: bytes}) that is
safe to commit, and turns a stored tree back into a list of *actions* that apply it. Everything in
this file is shared by every adapter.
"""
import os
import re
import shutil
import time

from ..core import clock, paths, proc
from ..core import config as core_config
from ..core.secrets import SECRET_NAME, token_hits  # noqa: F401  (used by adapters as stree.*)

HOME_TOKEN = "{{HOME}}"
MANIFEST = "manifest.json"


def home():
    return paths.home()


def now_iso():
    return clock.iso(int(clock.now_ts()))


# ---------------------------------------------------------------- config

FEATURE = "setup"
DEFAULTS = {"snapshot_dir": "", "memory": True}


def config_path():
    return core_config.section_source(FEATURE)


def load_config():
    cfg = core_config.load(FEATURE, DEFAULTS)
    if cfg["snapshot_dir"]:
        cfg["snapshot_dir"] = os.path.expanduser(cfg["snapshot_dir"])
    return cfg


def save_config(cfg):
    out = dict(cfg)
    if out.get("snapshot_dir"):
        out["snapshot_dir"] = paths.tilde(out["snapshot_dir"])
    core_config.save(FEATURE, out)


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

def placeholder(secret_id):
    return "${secret:%s}" % secret_id


PLACEHOLDER = re.compile(r"\$\{secret:([^}]+)\}")


def is_unset(value):
    return not value or "${" in value


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
    return "AI_TOOLKIT_SECRET_" + re.sub(r"[^A-Za-z0-9]", "_", secret_id).upper()


def env_secret(secret_id):
    """A secret's value from the environment; AI_SETUP_SECRET_* is the pre-0.2 spelling."""
    name = env_secret_name(secret_id)
    return os.environ.get(name) or os.environ.get(name.replace("AI_TOOLKIT_", "AI_SETUP_", 1)) or ""


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
    return paths.state_dir(FEATURE)


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
    tmp = path + ".ai-toolkit.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    if mode:
        os.chmod(path, mode)


def tool_cmd(name):
    """argv prefix for an external CLI; tests swap it via AI_TOOLKIT_<NAME>_CMD."""
    return proc.tool_cmd(name)


def run(argv, cwd=None, timeout=180):
    """(ok, combined output)."""
    rc, out, err = proc.run(argv, cwd=cwd, timeout=timeout)
    return rc == 0, (out + err).strip()


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
