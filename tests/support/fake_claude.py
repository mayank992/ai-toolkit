#!/usr/bin/env python3
"""Stand-in for the `claude` CLI: records each call and edits ~/.claude.json / plugin state like the real one."""
import json
import os
import sys

H = os.path.expanduser("~")
args = sys.argv[1:]
with open(os.path.join(H, "claude-calls.jsonl"), "a") as f:
    f.write(json.dumps({"argv": args, "cwd": os.getcwd()}) + "\n")


def rw(path, fn, default):
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = default
    fn(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f)


cj = os.path.join(H, ".claude.json")
plug = os.path.join(H, ".claude", "plugins")
if args[:2] == ["mcp", "add-json"]:
    scope, name, cfg = args[3], args[4], json.loads(args[5])

    def add(d):
        target = d.setdefault("mcpServers", {}) if scope == "user" else \
            d.setdefault("projects", {}).setdefault(os.getcwd(), {}).setdefault("mcpServers", {})
        target[name] = cfg
    rw(cj, add, {})
elif args[:2] == ["mcp", "remove"]:
    scope, name = args[3], args[4]
    rw(cj, lambda d: (d.get("mcpServers", {}) if scope == "user" else
                      d.get("projects", {}).get(os.getcwd(), {}).get("mcpServers", {})).pop(name, None), {})
elif args[:3] == ["plugin", "marketplace", "add"]:
    ref = args[3]
    rw(os.path.join(plug, "known_marketplaces.json"),
       lambda d: d.__setitem__(ref.split("/")[-1], {"source": {"source": "github", "repo": ref}}), {})
elif args[:2] == ["plugin", "install"]:
    rw(os.path.join(plug, "installed_plugins.json"),
       lambda d: d.setdefault("plugins", {}).__setitem__(args[2], [{"scope": "user"}]), {"version": 2})
else:
    sys.exit("fake claude: unsupported %r" % args)
