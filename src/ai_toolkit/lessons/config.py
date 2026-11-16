"""The lessons feature's settings, local state paths and store routing.

Settings are the "lessons" section of ~/.config/ai-toolkit/config.json (see core.config).
Local state (queue, transcript offsets, caches, log) lives in ~/.local/state/ai-toolkit/lessons.
The feature was called hindsight until 0.3: its old config section, state folder and HINDSIGHT_*
variables are still read (see state_dir, env and core.config.LEGACY_SECTIONS).
Python 3.9-compatible, stdlib only (hooks may run under /usr/bin/python3 on macOS).
"""
import fnmatch
import hashlib
import os
import re

from ..core import config as core_config
from ..core import hookrun, paths

FEATURE = "lessons"
OLD_FEATURE = "hindsight"  # the feature's name before 0.3
LEGACY_STATE_DIR = "~/.local/state/hindsight"  # before 0.2; moved on first use

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


# ---------- environment / paths ----------

def disabled():
    """True when hooks must no-op (e.g. inside distill's own `claude -p`)."""
    return hookrun.disabled()


def config_path():
    return core_config.section_source(FEATURE)


def env(name):
    """AI_TOOLKIT_<name>, or the HINDSIGHT_<name> it was called before 0.3."""
    return os.environ.get("AI_TOOLKIT_" + name) or os.environ.get("HINDSIGHT_" + name)


def state_dir():
    new = os.path.join(paths.state_root(), FEATURE)
    olds = [os.path.join(paths.state_root(), OLD_FEATURE)]
    if not os.environ.get("XDG_STATE_HOME"):
        olds.append(os.path.expanduser(LEGACY_STATE_DIR))
    for old in olds:
        if os.path.isdir(old):
            _adopt_state(old, new)
    return paths.state_dir(FEATURE)


def _adopt_state(old, new):
    """Bring a state folder from an older version to `new`. The first time that is a rename. After
    that, an older copy of the plugin (Claude Code keeps running its own copy until it is updated) may
    still be queueing pushbacks in the old folder, so its queue is appended to the new one."""
    try:
        if not os.path.exists(new):
            os.makedirs(os.path.dirname(new), exist_ok=True)
            os.rename(old, new)
            old_log = os.path.join(new, "%s.log" % OLD_FEATURE)
            if os.path.exists(old_log):
                os.rename(old_log, os.path.join(new, "%s.log" % FEATURE))
            return
        q = os.path.join(old, "queue.jsonl")
        if os.path.exists(q) and os.path.getsize(q):
            taken = q + ".adopting"
            os.rename(q, taken)  # atomic: a hook appending right now creates a fresh queue file
            with open(taken) as src, open(os.path.join(new, "queue.jsonl"), "a") as dst:
                dst.write(src.read())
            os.remove(taken)
    except OSError:
        pass


def queue_path():
    return os.path.join(state_dir(), "queue.jsonl")


def offsets_path():
    return os.path.join(state_dir(), "offsets.json")


def log_path():
    return os.path.join(state_dir(), "%s.log" % FEATURE)


def log(msg):
    hookrun.log(FEATURE, msg)


# ---------- settings ----------

def load_config():
    cfg = core_config.load(FEATURE, DEFAULT_CONFIG)
    for s in cfg["stores"]:
        s["path"] = os.path.expanduser(s["path"])
    return cfg


def save_config(cfg):
    out = {k: v for k, v in cfg.items()}
    out["stores"] = [dict(s, path=paths.tilde(s["path"])) for s in cfg["stores"]]
    core_config.save(FEATURE, out)


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


# ---------- identifiers ----------

def short_hash(*parts):
    h = hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()
    return h[:10]


def hostname():
    import socket  # lazy: costs ~15ms, and only store writes need it
    return re.sub(r"[^A-Za-z0-9_.-]", "_", socket.gethostname().split(".")[0]) or "host"
