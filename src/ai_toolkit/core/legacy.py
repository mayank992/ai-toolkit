"""Remove what a 0.1 `install.sh` put on this machine, once the plugin replaces it (`ait migrate-legacy`).

0.1 wrote three kinds of things outside the repo:
  - hook entries in ~/.claude/settings.json whose command contains "/.claude/ai-toolkit/";
  - symlinks into the clone: ~/.local/bin/{ai-toolkit,hs,ai-rules,ai-setup}, ~/.claude/commands/{lesson,mr-retro}.md;
  - the ~/.claude/ai-toolkit symlink to the clone itself.
Only those are touched. settings.json is backed up first and every other key and hook is kept as is.
Memory stores, config and state are never touched.
"""
import json
import os
import shutil
import time

from . import paths
from .jsonio import read_json

LEGACY_TAG = "/.claude/ai-toolkit/"  # in every hook command 0.1 wrote
LINK_DIRS = (paths.home(".local", "bin"), paths.claude_dir("commands"))


def _strip_hooks(settings):
    """(new settings, number of hook entries removed)."""
    hooks = settings.get("hooks") or {}
    removed = 0
    out = {}
    for event, groups in hooks.items():
        kept_groups = []
        for g in groups:
            kept = [h for h in g.get("hooks", []) if LEGACY_TAG not in h.get("command", "")]
            removed += len(g.get("hooks", [])) - len(kept)
            if kept:
                kept_groups.append(dict(g, hooks=kept))
        if kept_groups:
            out[event] = kept_groups
    new = dict(settings)
    if out:
        new["hooks"] = out
    else:
        new.pop("hooks", None)
    return new, removed


def _ours(link):
    target = os.readlink(link)
    return "/.claude/ai-toolkit/" in target or target.rstrip("/").endswith("/ai-toolkit")


def plan():
    """[(kind, path, detail)] of what migrate would remove."""
    todo = []
    settings_path = paths.claude_dir("settings.json")
    _, n = _strip_hooks(read_json(settings_path, {}))
    if n:
        todo.append(("hooks", settings_path, "%d hook entr%s" % (n, "y" if n == 1 else "ies")))
    for d in LINK_DIRS:
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            p = os.path.join(d, name)
            if os.path.islink(p) and _ours(p):
                todo.append(("link", p, os.readlink(p)))
    root = paths.claude_dir("ai-toolkit")
    if os.path.islink(root):
        todo.append(("link", root, os.readlink(root)))
    return todo


def apply(todo):
    """Carry out a plan(). Returns the settings backup path, if settings.json was rewritten."""
    backup = None
    for kind, path, _ in todo:
        if kind == "hooks":
            backup = "%s.pre-plugin-%s.bak" % (path, time.strftime("%Y%m%d-%H%M%S"))
            shutil.copy2(path, backup)
            new, _ = _strip_hooks(read_json(path, {}))
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(new, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        elif kind == "link":
            os.remove(path)
    return backup
