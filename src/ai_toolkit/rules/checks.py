"""Checks on a project's rule stack: each returns findings the CLI and dashboard show as problems."""
import os
import re

STOP = set("a an and are as at be before but by do does don't for from if in into is it its never no not of on "
           "only or so than that the their them then there these this to use when with without you your".split())


def words(text):
    return {w for w in re.findall(r"[a-z][a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 2}


def similarity(a, b):
    """Overlap coefficient on content words; needs at least 4 shared words to count."""
    wa, wb = words(a), words(b)
    shared = wa & wb
    if len(shared) < 4:
        return 0.0
    return len(shared) / float(min(len(wa), len(wb)))


def rule_units(instr, mem, less):
    units = []
    for f in instr:
        for r in f["rules"]:
            units.append(("%s CLAUDE" % f["scope"], r[:90], r))
    for n in mem["notes"]:
        units.append(("memory", n["name"], n["description"] + " " + n["how"]))
    for l in less:
        units.append(("lesson", l["id"], l["text"] + " " + l["why"]))
    return units


def overlaps(units, threshold=0.45):
    out = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            a, b = units[i], units[j]
            if a[0] == b[0]:
                continue
            s = similarity(a[2], b[2])
            if s >= threshold:
                out.append({"a": {"layer": a[0], "name": a[1]}, "b": {"layer": b[0], "name": b[1]}, "score": round(s, 2)})
    return sorted(out, key=lambda o: -o["score"])[:40]


def problems(project, instr, mem, hks):
    out = []
    for f in instr:
        if f["scope"] == "local" and f["git"] == "untracked":
            out.append({"level": "error", "where": f["path"],
                        "text": "CLAUDE.local.md is not ignored by git, so it shows in git status and could be committed.",
                        "fix": "echo /CLAUDE.local.md >> .git/info/exclude"})
        if f["lines"] > 300:
            out.append({"level": "warn", "where": f["path"], "text": "%d lines; long instruction files dilute each rule." % f["lines"], "fix": ""})
    for n in mem["notes"]:
        if not n["indexed"]:
            out.append({"level": "warn", "where": n["path"], "text": "Memory note is not listed in MEMORY.md, so it is never loaded.",
                        "fix": "add a line to MEMORY.md"})
        if n["type"] in ("feedback", "project") and not n["why"]:
            out.append({"level": "info", "where": n["path"], "text": "Feedback note has no **Why:** line.", "fix": ""})
    for f in mem["index_missing_files"]:
        out.append({"level": "warn", "where": os.path.join(mem["dir"], "MEMORY.md"), "text": "Index points at missing %s." % f, "fix": ""})
    for h in hks:
        if h["script"] and not h["exists"]:
            out.append({"level": "error", "where": h["settings"], "text": "Hook script missing: %s" % h["script"], "fix": ""})
        elif h["logged"] is False and h["scope"] == "local":
            out.append({"level": "info", "where": h["settings"],
                        "text": "%s doesn't write to the fire log, so its usefulness can't be measured." % h["name"], "fix": ""})
    return out


