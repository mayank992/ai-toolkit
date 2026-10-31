#!/usr/bin/env python3
"""Add/remove ai-toolkit hook entries in Claude Code settings.json.

Only entries whose command contains TAG are ever touched; other hooks are preserved
exactly. Writes a timestamped backup before every change.

usage:
  settings_merge.py add    <settings.json> <module_dir> [--max-step N]
  settings_merge.py remove <settings.json> [--module NAME]
  settings_merge.py list   <settings.json>
"""
import json
import os
import shutil
import sys
import time

TAG = "/.claude/ai-toolkit/"


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save(path, data):
    if os.path.exists(path):
        bak = "%s.bak-ai-toolkit-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(path, bak)
        print("  backup: %s" % bak)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def ours(cmd, module=None):
    if TAG not in cmd:
        return False
    return module is None or ("/modules/%s/" % module) in cmd


def command_for(module_name, script):
    return '"$HOME/.claude/ai-toolkit/modules/%s/%s"' % (module_name, script)


def add(settings_path, module_dir, max_step=None):
    manifest = load(os.path.join(module_dir, "module.json"))
    name = manifest["name"]
    data = load(settings_path)
    hooks = data.setdefault("hooks", {})
    wanted = [h for h in manifest.get("hooks", []) if max_step is None or h.get("step", 1) <= max_step]
    changed = False
    # Drop this module's entries that are no longer wanted (e.g. lower --max-step).
    wanted_cmds = {(h["event"], command_for(name, h["script"])) for h in wanted}
    for event, groups in list(hooks.items()):
        for g in groups:
            before = len(g.get("hooks", []))
            g["hooks"] = [h for h in g.get("hooks", [])
                          if not ours(h.get("command", ""), name) or (event, h["command"]) in wanted_cmds]
            changed |= len(g["hooks"]) != before
        hooks[event] = [g for g in groups if g.get("hooks")]
        if not hooks[event]:
            del hooks[event]
    for h in wanted:
        cmd = command_for(name, h["script"])
        groups = hooks.setdefault(h["event"], [])
        if any(x.get("command") == cmd for g in groups for x in g.get("hooks", [])):
            print("  = %-17s %s" % (h["event"], h["script"]))
            continue
        entry = {"type": "command", "command": cmd}
        if h.get("timeout"):
            entry["timeout"] = h["timeout"]
        group = {"hooks": [entry]}
        if h.get("matcher"):
            group["matcher"] = h["matcher"]
        groups.append(group)
        changed = True
        print("  + %-17s %s" % (h["event"], h["script"]))
    if changed:
        save(settings_path, data)
    return changed


def remove(settings_path, module=None):
    data = load(settings_path)
    hooks = data.get("hooks", {})
    removed = 0
    for event, groups in list(hooks.items()):
        for g in groups:
            before = len(g.get("hooks", []))
            g["hooks"] = [h for h in g.get("hooks", []) if not ours(h.get("command", ""), module)]
            removed += before - len(g["hooks"])
        hooks[event] = [g for g in groups if g.get("hooks")]
        if not hooks[event]:
            del hooks[event]
    if removed:
        save(settings_path, data)
    print("  removed %d hook entr%s" % (removed, "y" if removed == 1 else "ies"))
    return removed


def list_ours(settings_path):
    for event, groups in load(settings_path).get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                if ours(h.get("command", "")):
                    print("%-17s %s" % (event, h["command"]))


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    op, path = argv[1], os.path.expanduser(argv[2])
    if op == "add":
        max_step = None
        if "--max-step" in argv:
            max_step = int(argv[argv.index("--max-step") + 1])
        add(path, argv[3], max_step)
    elif op == "remove":
        mod = argv[argv.index("--module") + 1] if "--module" in argv else None
        remove(path, mod)
    elif op == "list":
        list_ours(path)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
