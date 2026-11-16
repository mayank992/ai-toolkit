"""`ait rules ...`: every rule that shapes Claude Code in a project, and the post-merge retro.

  ait rules show [PROJECT] [--json]              the rule stack: instructions, memory, hooks, lessons, problems
  ait rules projects                             projects with any rules, most recent first
  ait rules retro collect MR [--project DIR]     gather MR evidence for /mr-retro; prints the JSON path
  ait rules retro log MR --proposed N --applied N [--note TEXT] [--project DIR]
  ait rules fire HOOK DECISION [--project DIR]   append to the hook-fire log (for your own hook scripts)
"""
import argparse
import json
import os
import time

from . import inventory as inv


def project_arg(p):
    """The project folder for a path: its git top level, spelled the way Claude Code knows it."""
    d = os.path.abspath(os.path.expanduser(p or os.getcwd()))
    rc, top = inv.git(d, "rev-parse", "--show-toplevel")
    if rc != 0 or not top:
        return inv.canonical(d)
    up = os.path.relpath(os.path.realpath(d), os.path.realpath(top))
    if up == "." or up.startswith(".."):
        return inv.canonical(d if up == "." else top)
    return inv.canonical(os.path.normpath(os.path.join(d, *[".."] * len(up.split(os.sep)))))


def cmd_show(a):
    v = inv.project_view(project_arg(a.project))
    if a.json:
        print(json.dumps(v, indent=2))
        return
    print("%s  %s" % (v["path"], v["repo"] or ""))
    print("\nInstructions")
    for f in v["instructions"]:
        print("  %-8s %-55s %3d lines  git:%s" % (f["scope"], f["path"].replace(inv.home(), "~"), f["lines"], f["git"]))
    print("\nMemory (%d)" % len(v["memory"]["notes"]))
    for n in v["memory"]["notes"]:
        print("  %s %-38s %s" % (" " if n["indexed"] else "!", n["name"][:38], n["description"][:80]))
    print("\nHooks (%d)" % len(v["hooks"]))
    for h in v["hooks"]:
        f = h["fires"]["count"]
        print("  %-7s %-16s %-6s %-24s %s" % (h["scope"], h["event"], h["matcher"] or "*", h["name"][:24],
                                              ("%d fires" % f) if h["logged"] else "not logged"))
    print("\nLessons (%d)" % len(v["lessons"]))
    for l in v["lessons"]:
        print("  %s %-9s %s" % (l["id"], l["status"], l["text"][:90]))
    if v["problems"]:
        print("\nProblems")
        for p in v["problems"]:
            print("  [%s] %s  (%s)" % (p["level"], p["text"], p["where"].replace(inv.home(), "~")))
    if v["overlaps"]:
        print("\nPossible overlaps")
        for o in v["overlaps"][:10]:
            print("  %.2f  %s: %s  <->  %s: %s" % (o["score"], o["a"]["layer"], o["a"]["name"][:40],
                                                  o["b"]["layer"], o["b"]["name"][:40]))


def cmd_projects(a):
    for p in inv.projects():
        print(p)


def cmd_retro_collect(a):
    from . import retro
    path, out = retro.gather(project_arg(a.project), a.mr)
    s, sh = out["summary"], out.get("share") or {}
    print(path)
    print("%s: %d sessions, %d prompts (%d pushback), threads %s, CC share %s%% (src %s%%, tests %s%%)" % (
        out["meta"]["title"], s["sessions"], s["prompts"], s["pushback"], s["threads"],
        sh.get("cc_pct"), sh.get("src_pct"), sh.get("test_pct")))


def cmd_retro_log(a):
    from . import retro
    e = retro.log(project_arg(a.project), a.mr, a.proposed, a.applied, a.note or "")
    print(json.dumps(e))


def cmd_fire(a):
    with open(inv.state_dir("fires.jsonl"), "a") as f:
        f.write(json.dumps({"t": int(time.time()), "hook": a.hook, "decision": a.decision,
                            "project": project_arg(a.project)}) + "\n")


def register(parent):
    """Add `rules` and its subcommands to the root `ait` parser."""
    r = parent.add_parser("rules", help="see and check every rule Claude follows in a project",
                          description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = r.add_subparsers(dest="rules_cmd", metavar="COMMAND", required=True)
    p = sub.add_parser("show", help="the rule stack of a project and its problems")
    p.add_argument("project", nargs="?")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_show)
    sub.add_parser("projects", help="projects with any rules, most recent first").set_defaults(fn=cmd_projects)

    retro = sub.add_parser("retro", help="post-merge retro steps used by /mr-retro")
    rsub = retro.add_subparsers(dest="retro_cmd", metavar="STEP", required=True)
    p = rsub.add_parser("collect", help="gather one MR's evidence; prints the JSON path")
    p.add_argument("mr")
    p.add_argument("--project")
    p.set_defaults(fn=cmd_retro_collect)
    p = rsub.add_parser("log", help="record what a retro proposed and applied")
    p.add_argument("mr")
    p.add_argument("--project")
    p.add_argument("--proposed", type=int, default=0)
    p.add_argument("--applied", type=int, default=0)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_retro_log)

    p = sub.add_parser("fire", help="append one decision to the hook-fire log (call it from your hooks)")
    p.add_argument("hook")
    p.add_argument("decision")
    p.add_argument("--project")
    p.set_defaults(fn=cmd_fire)
