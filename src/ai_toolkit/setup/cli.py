"""`ait setup ...`: see your AI tool setup and replicate it on another machine.

  ait setup init DIR [--remote URL] [--no-memory]   choose where snapshots live (a private git repo)
  ait setup show [--json]                           inventory and health of this machine's setup
  ait setup status                                  what changed since the last export
  ait setup export [DIR] [--no-memory] [--push]     write the snapshot (secrets become placeholders)
  ait setup apply [DIR] [--dry-run] [--yes]         make this machine match a snapshot (with backups)
"""
import getpass
import json
import os
import sys

from . import ops
from . import snapshot_tree as stree

MARK = {"ok": " ", "info": "·", "warn": "!", "error": "x"}


def snapshot_dir(a, cfg):
    d = os.path.abspath(os.path.expanduser(a.dir)) if getattr(a, "dir", None) else cfg.get("snapshot_dir")
    if not d:
        sys.exit("no snapshot folder. Run: ait setup init ~/code/ai-setup  (or pass DIR)")
    return d


def memory_on(a, cfg):
    return False if getattr(a, "no_memory", False) else cfg.get("memory", True)


def cmd_init(a):
    d = os.path.abspath(os.path.expanduser(a.dir))
    os.makedirs(d, exist_ok=True)
    if not os.path.isdir(os.path.join(d, ".git")):
        ok, out = stree.git(d, "init", "-q")
        if not ok:
            sys.exit(out)
    if a.remote:
        stree.git(d, "remote", "remove", "origin")
        stree.git(d, "remote", "add", "origin", a.remote)
    cfg = stree.load_config()
    cfg["snapshot_dir"] = d
    cfg["memory"] = not a.no_memory
    stree.save_config(cfg)
    print("snapshot folder: %s%s\nmemory: %s\nconfig: %s" % (
        d, " (origin %s)" % a.remote if a.remote else "", "included" if cfg["memory"] else "excluded", stree.config_path()))
    print("next: ait setup export")


def cmd_show(a):
    if a.json:
        print(json.dumps([{"id": t.ID, "sections": t.inventory()} for t in ops.tools()], indent=2))
        return
    for t in ops.tools():
        print("== %s" % t.TITLE)
        for s in t.inventory():
            print("\n%s (%d)" % (s["title"], len(s["items"])))
            for i in s["items"]:
                line = "  %s %-34s %s" % (MARK.get(i["status"], " "), i["name"][:34], i["detail"][:70])
                if i["tag"]:
                    line += "  [%s]" % i["tag"]
                print(line)
                if i["note"]:
                    print("      %s" % i["note"])


def cmd_status(a):
    cfg = stree.load_config()
    d = snapshot_dir(a, cfg)
    snap = ops.snapshot(dict(cfg, snapshot_dir=d))
    print("snapshot: %s (last export %s from %s)" % (snap["snapshot_dir"], snap["last_export_at"] or "never",
                                                     snap["last_export_host"] or "-"))
    for t in snap["tools"]:
        if not t["detected"]:
            continue
        drift = t["export"]["drift"]
        print("%s: %s" % (t["title"], "%d file(s) differ" % len(drift) if drift else "up to date"))
        for c in drift:
            print("  %-8s %s" % (c["change"], c["path"]))
        for b in t["export"]["blocked"]:
            print("  BLOCKED  %s contains %s" % (b["path"], ", ".join(b["kinds"])))


def cmd_export(a):
    cfg = stree.load_config()
    d = snapshot_dir(a, cfg)
    try:
        changes, rendered = ops.export(d, memory_on(a, cfg))
    except ValueError as e:
        sys.exit(str(e))
    for tid, (tree, rep) in rendered.items():
        print("%s: %d files, %d secret placeholder(s), %d change(s)" % (
            tid, len(tree), len(rep["placeholders"]), sum(1 for c in changes if c["tool"] == tid)))
        for s in rep["skipped"]:
            print("  skipped %s (%s)" % (s["path"], s["reason"]))
    for c in changes:
        print("  %-8s %s/%s" % (c["change"], c["tool"], c["path"]))
    if os.path.isdir(os.path.join(d, ".git")) and not a.no_commit:
        stree.git(d, "add", "-A")
        ok, _ = stree.git(d, "diff", "--cached", "--quiet")
        if not ok:
            stree.git(d, "commit", "-q", "-m", "ai-toolkit setup: snapshot from %s" % ops.socket.gethostname())
            print("committed in %s" % d)
        if a.push:
            ok, out = stree.git(d, "push", "-u", "origin", "HEAD")
            print("pushed" if ok else "push failed: %s" % out)
    print("wrote %s" % d)


def prompt_secret(sid):
    if not sys.stdin.isatty():
        return ""
    return getpass.getpass("value for %s (empty to skip): " % sid)


def cmd_apply(a):
    cfg = stree.load_config()
    d = snapshot_dir(a, cfg)
    if not os.path.isfile(os.path.join(d, stree.MANIFEST)):
        sys.exit("%s is not a setup snapshot (no %s)" % (d, stree.MANIFEST))
    prompt = None if a.dry_run or a.yes else prompt_secret
    acts = ops.plan(d, prompt, memory_on(a, cfg))
    todo = [x for _, x in acts if x.change != "same"]
    same = len(acts) - len(todo)
    for x in todo:
        flag = "BLOCKED" if x.blocked else x.change
        tail = x.blocked or x.summary
        print("  %-8s %-11s %s%s" % (flag, x.kind, stree.to_template(x.target).replace(stree.HOME_TOKEN, "~"),
                                    "  (%s)" % tail if tail else ""))
    print("%d change(s), %d already in place, %d blocked" % (
        len([x for x in todo if not x.blocked]), same, len([x for x in todo if x.blocked])))
    runnable = [x for x in todo if not x.blocked and x.run]
    if a.dry_run or not runnable:
        return
    if not a.yes and input("apply %d change(s)? [y/N] " % len(runnable)).lower() != "y":
        sys.exit("aborted")
    failed = 0
    for x in runnable:
        try:
            x.run()
        except Exception as e:  # keep going; report every failure at the end
            failed += 1
            print("  failed  %s: %s" % (x.target, e))
    bdir = os.path.join(stree.state_dir(), "backups")
    print("applied %d change(s)%s. Backups of overwritten files: %s" % (
        len(runnable) - failed, ", %d failed" % failed if failed else "", bdir))
    if failed:
        sys.exit(1)


def register(parent):
    """Add `setup` and its subcommands to the root `ait` parser."""
    p = parent.add_parser("setup", help="inventory your Claude Code setup and replicate it on another machine",
                          description=__doc__.split("\n")[0].strip("`"))
    sub = p.add_subparsers(dest="setup_cmd", metavar="COMMAND", required=True)
    i = sub.add_parser("init", help="choose the snapshot folder (git repo)")
    i.add_argument("dir")
    i.add_argument("--remote", help="git remote for the snapshot repo (keep it private)")
    i.add_argument("--no-memory", action="store_true", help="leave memory files out of exports")
    i.set_defaults(fn=cmd_init)
    s = sub.add_parser("show", help="inventory and health of this machine's setup")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_show)
    st = sub.add_parser("status", help="what changed since the last export")
    st.add_argument("dir", nargs="?")
    st.set_defaults(fn=cmd_status)
    e = sub.add_parser("export", help="write the snapshot")
    e.add_argument("dir", nargs="?")
    e.add_argument("--no-memory", action="store_true")
    e.add_argument("--no-commit", action="store_true")
    e.add_argument("--push", action="store_true")
    e.set_defaults(fn=cmd_export)
    ap = sub.add_parser("apply", help="make this machine match a snapshot")
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-y", "--yes", action="store_true", help="no confirmation; secrets only from config/env")
    ap.add_argument("--no-memory", action="store_true")
    ap.set_defaults(fn=cmd_apply)
