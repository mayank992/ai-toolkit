"""export / apply / snapshot across every adapter. Adapters are modules with ID, TITLE, detected(),
inventory(), render(memory) and plan(src, prompt, memory); add one to ADAPTERS to support a new tool."""
import json
import os
import socket

from . import snapshot_tree as stree
from .adapters import claude_code

ADAPTERS = [claude_code]

README = """# AI tool setup snapshot

Written by `ait setup export` from [ai-toolkit](https://github.com/mayank992/ai-toolkit). Keep this repo **private**:
it can hold your memory files. Secrets are never stored; they appear as `${secret:id}` placeholders.

Replicate on a new machine:

```bash
# install ai-toolkit first (see its docs/getting-started.md), then:
git clone <this repo> ~/code/ai-setup
ait setup apply ~/code/ai-setup --dry-run   # see what would change
ait setup apply ~/code/ai-setup             # backs up anything it overwrites
```

Secrets are taken from the existing config, then `AI_TOOLKIT_SECRET_<ID>` env vars, then a prompt.
"""


def tools():
    return [a for a in ADAPTERS if a.detected()]


def render_all(memory):
    return {a.ID: a.render(memory) for a in tools()}


def blocked_files(rendered):
    return [dict(b, tool=t) for t, (_, rep) in rendered.items() for b in rep["blocked"]]


def read_manifest(root):
    try:
        with open(os.path.join(root, stree.MANIFEST)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def export(root, memory):
    """Write the snapshot; returns (changes, rendered). Raises ValueError if any file holds a secret."""
    rendered = render_all(memory)
    blocked = blocked_files(rendered)
    if blocked:
        raise ValueError("refusing to export; these files contain secrets:\n" + "\n".join(
            "  %s/%s: %s" % (b["tool"], b["path"], ", ".join(b["kinds"])) for b in blocked))
    os.makedirs(root, exist_ok=True)
    changes = []
    for tid, (tree, rep) in rendered.items():
        changes += [dict(c, tool=tid) for c in stree.diff_trees(tree, stree.read_tree(os.path.join(root, tid)))]
        stree.write_tree(tree, os.path.join(root, tid), rep["modes"])
    manifest = {"exported_at": stree.now_iso(), "host": socket.gethostname(), "memory": memory,
                "tools": {t: {"files": len(tree), "placeholders": rep["placeholders"], "skipped": rep["skipped"],
                              "modes": {p: m for p, m in rep["modes"].items()}}
                          for t, (tree, rep) in rendered.items()}}
    with open(os.path.join(root, stree.MANIFEST), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    if not os.path.exists(os.path.join(root, "README.md")):
        with open(os.path.join(root, "README.md"), "w") as f:
            f.write(README)
    return changes, rendered


def plan(root, prompt, memory):
    return [(a, act) for a in ADAPTERS for act in a.plan(root, prompt=prompt, memory=memory)]


def snapshot(cfg):
    """Everything the dashboard shows, as one JSON-able dict."""
    root = cfg.get("snapshot_dir") or ""
    memory = cfg.get("memory", True)
    rendered = render_all(memory)
    out_tools = []
    for a in ADAPTERS:
        if not a.detected():
            out_tools.append({"id": a.ID, "title": a.TITLE, "detected": False, "sections": []})
            continue
        tree, rep = rendered[a.ID]
        on_disk = stree.read_tree(os.path.join(root, a.ID)) if root else {}
        drift = stree.diff_trees(tree, on_disk) if root and os.path.isdir(root) else []
        out_tools.append({
            "id": a.ID, "title": a.TITLE, "detected": True, "sections": a.inventory(),
            "export": {
                "files": [{"path": p, "bytes": len(b)} for p, b in sorted(tree.items())],
                "placeholders": rep["placeholders"], "skipped": rep["skipped"], "blocked": rep["blocked"],
                "drift": drift,
            },
        })
    manifest = read_manifest(root) if root else {}
    return {
        "generated_at": stree.now_iso(),
        "snapshot_dir": stree.to_template(root).replace(stree.HOME_TOKEN, "~") if root else "",
        "snapshot_exists": bool(root) and os.path.isdir(root),
        "memory": memory,
        "last_export_at": manifest.get("exported_at"),
        "last_export_host": manifest.get("host"),
        "git": stree.snapshot_git(root) if root else None,
        "tools": out_tools,
    }
