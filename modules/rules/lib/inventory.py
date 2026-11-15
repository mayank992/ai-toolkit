"""Everything that shapes Claude Code's behaviour in a project, layer by layer.

For each project Claude Code knows about, collect:
  instructions  ~/.claude/CLAUDE.md, <project>/CLAUDE.md, <project>/CLAUDE.local.md
  memory        ~/.claude/projects/<key>/memory/*.md and its MEMORY.md index
  hooks         user, project and local settings, with the hook-fire log
  lessons       hindsight lessons scoped to this repo, its languages or global
and check them: an instructions file git would commit by accident, index entries without files,
memory files missing from the index, hook scripts that don't exist, and rules saying the same thing
in two layers. Read-only; stdlib only (python 3.9).
"""
import glob
import json
import os
import re
import subprocess
import time

STOP = set("a an and are as at be before but by do does don't for from if in into is it its never no not of on "
           "only or so than that the their them then there these this to use when with without you your".split())


def home(*p):
    return os.path.join(os.path.expanduser("~"), *p)


def claude_dir(*p):
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or home(".claude"), *p)


def state_dir(*p):
    base = os.environ.get("XDG_STATE_HOME") or home(".local", "state")
    return os.path.join(base, "ai-toolkit", "rules", *p)


def project_key(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def load_json(path):
    text = read(path)
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        return {}


def mtime(path):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(path)))
    except OSError:
        return ""


def git(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def normalize_remote(url):
    u = (url or "").strip()
    u = re.sub(r"^[a-z+]+://", "", u)
    u = re.sub(r"^[^@/]+@", "", u)
    u = re.sub(r"^([^/:]+):(\d+)/", r"\1/", u)
    u = re.sub(r"^([^/:]+):", r"\1/", u)
    u = re.sub(r"\.git/?$", "", u)
    return u.lower().rstrip("/")


LANG_MARKERS = {"package.json": "js", "tsconfig.json": "ts", "pyproject.toml": "python", "setup.py": "python",
                "go.mod": "go", "Cargo.toml": "rust", "pom.xml": "java", "build.gradle": "java"}


def words(text):
    return {w for w in re.findall(r"[a-z][a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 2}


def similarity(a, b):
    """Overlap coefficient on content words; needs at least 4 shared words to count."""
    wa, wb = words(a), words(b)
    shared = wa & wb
    if len(shared) < 4:
        return 0.0
    return len(shared) / float(min(len(wa), len(wb)))


# ---------- discovery ----------

def canonical(path):
    """The spelling Claude Code uses for this folder (its memory and transcript keys depend on it)."""
    real = os.path.realpath(path)
    for p in (load_json(home(".claude.json")).get("projects") or {}):
        if p != path and os.path.realpath(p) == real:
            return p
    return path


def projects():
    """[path] of existing project folders Claude Code has a record of, most recently used first."""
    seen = {}
    for p in (load_json(home(".claude.json")).get("projects") or {}):
        if os.path.isdir(p):
            seen[p] = 0.0
    for d in glob.glob(claude_dir("projects", "*")):
        key = os.path.basename(d)
        for p in list(seen):
            if project_key(p) == key:
                seen[p] = max(seen[p], os.path.getmtime(d))
    keep = []
    for p, t in seen.items():
        if re.search(r"/scratchpad(/|$)|/claude-\d+/|/\.claude/worktrees/", p):
            continue
        has = any(os.path.exists(os.path.join(p, f)) for f in ("CLAUDE.md", "CLAUDE.local.md", ".claude"))
        if has or os.path.isdir(claude_dir("projects", project_key(p), "memory")):
            keep.append((t, p))
    return [p for _, p in sorted(keep, reverse=True)]


# ---------- layers ----------

def headings(text):
    return [l.lstrip("#").strip() for l in text.splitlines() if l.startswith("## ")]


def bullets(text):
    out = []
    for l in text.splitlines():
        s = l.strip()
        if re.match(r"^([-*]|\d+\.)\s+\S", s):
            out.append(re.sub(r"^([-*]|\d+\.)\s+", "", s))
    return out


def git_visibility(project, path):
    """tracked | ignored | untracked (would show in git status) | n/a"""
    if not os.path.isdir(os.path.join(project, ".git")) and git(project, "rev-parse", "--git-dir")[0]:
        return "n/a"
    rel = os.path.relpath(path, project)
    if git(project, "ls-files", "--error-unmatch", rel)[0] == 0:
        return "tracked"
    if git(project, "check-ignore", "-q", rel)[0] == 0:
        return "ignored"
    return "untracked"


def instruction_files(project):
    out = []
    for scope, path in (("user", claude_dir("CLAUDE.md")), ("project", os.path.join(project, "CLAUDE.md")),
                        ("local", os.path.join(project, "CLAUDE.local.md"))):
        text = read(path)
        if text is None:
            continue
        out.append({"scope": scope, "path": path, "lines": len(text.splitlines()), "modified": mtime(path),
                    "sections": headings(text), "rules": bullets(text),
                    "git": git_visibility(project, path) if scope != "user" else "n/a",
                    "shared": scope == "project"})
    return out


def parse_frontmatter(text):
    meta, body = {}, text
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            mm = re.match(r"^\s*([A-Za-z_]+):\s*(.*)$", line)
            if mm and mm.group(2):
                meta.setdefault(mm.group(1), mm.group(2).strip().strip('"'))
    return meta, body


def memory(project):
    mdir = claude_dir("projects", project_key(project), "memory")
    index_text = read(os.path.join(mdir, "MEMORY.md")) or ""
    indexed = set(re.findall(r"\]\(([^)]+\.md)\)", index_text))
    notes = []
    for f in sorted(glob.glob(os.path.join(mdir, "*.md"))):
        name = os.path.basename(f)
        if name == "MEMORY.md":
            continue
        meta, body = parse_frontmatter(read(f) or "")
        why = re.search(r"\*\*Why:\*\*\s*(.+?)(?:\n\n|\*\*How to apply|$)", body, re.S)
        how = re.search(r"\*\*How to apply:\*\*\s*(.+?)(?:\n\n|$)", body, re.S)
        notes.append({"file": name, "path": f, "name": meta.get("name", name[:-3]), "type": meta.get("type", ""),
                      "description": meta.get("description", ""), "modified": meta.get("modified") or mtime(f),
                      "body": body.strip(), "why": (why.group(1).strip() if why else ""),
                      "how": (how.group(1).strip() if how else ""), "indexed": name in indexed,
                      "links": sorted(set(re.findall(r"\[\[([a-z0-9-]+)\]\]", body)))})
    missing = sorted(f for f in indexed if not os.path.exists(os.path.join(mdir, f)))
    return {"dir": mdir, "notes": notes, "index_missing_files": missing}


def fires(window_days=30):
    """{hook name: {count, last, decisions}} from the hook-fire log hooks append to."""
    out, cutoff = {}, time.time() - window_days * 86400
    for line in (read(state_dir("fires.jsonl")) or "").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("t", 0) < cutoff:
            continue
        s = out.setdefault(e.get("hook", "?"), {"count": 0, "last": 0, "decisions": {}, "projects": {}})
        s["count"] += 1
        s["last"] = max(s["last"], e.get("t", 0))
        d = e.get("decision", "?")
        s["decisions"][d] = s["decisions"].get(d, 0) + 1
        p = e.get("project", "")
        s["projects"][p] = s["projects"].get(p, 0) + 1
    for s in out.values():
        s["last"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s["last"])) if s["last"] else ""
    return out


INTERPRETERS = {"python", "python3", "bash", "sh", "zsh", "node", "env", "/usr/bin/env", "/bin/bash", "/bin/sh",
                "/usr/bin/python3", "uv", "run", "npx", "-u"}


def script_of(command):
    for tok in re.split(r"\s+", command.replace('"', " ").replace("'", " ").strip()):
        if not tok or tok in INTERPRETERS or tok.startswith("-"):
            continue
        t = tok.replace("${CLAUDE_PROJECT_DIR}", "{project}").replace("$CLAUDE_PROJECT_DIR", "{project}")
        t = t.replace("${HOME}", home()).replace("$HOME", home())
        if t.startswith("~/"):
            t = home(t[2:])
        if t.startswith(("/", "{project}")):
            return t
    return ""


def hooks(project, fire_stats):
    out = []
    layers = (("user", claude_dir("settings.json")), ("project", os.path.join(project, ".claude", "settings.json")),
              ("local", os.path.join(project, ".claude", "settings.local.json")))
    for scope, path in layers:
        for event, groups in (load_json(path).get("hooks") or {}).items():
            for g in groups or []:
                for h in g.get("hooks") or []:
                    cmd = h.get("command", "")
                    script = script_of(cmd).replace("{project}", project)
                    name = os.path.splitext(os.path.basename(script))[0] if script else cmd[:40]
                    st = fire_stats.get(name)
                    out.append({"scope": scope, "settings": path, "event": event, "matcher": g.get("matcher", ""),
                                "command": cmd, "script": script, "name": name,
                                "exists": (os.path.exists(script) if script else True),
                                "shared": scope == "project", "logged": st is not None or writes_fire_log(script),
                                "fires": st or {"count": 0, "last": "", "decisions": {}, "projects": {}},
                                "doc": hook_doc(script)})
    return out


def writes_fire_log(script):
    text = read(script) if script else None
    return bool(text) and ("fires.jsonl" in text or "ai-rules fire" in text)


def hook_doc(script):
    text = read(script) if script else None
    if not text:
        return ""
    m = re.search(r'^\s*(?:"""|\'\'\')(.+?)(?:"""|\'\'\')', text, re.S | re.M) or re.search(r"^#\s+(?!!)(.+)$", text, re.M)
    return m.group(1).strip().splitlines()[0] if m else ""


def repo_info(project):
    _, url = git(project, "remote", "get-url", "origin")
    langs = sorted({l for marker, l in LANG_MARKERS.items() if os.path.exists(os.path.join(project, marker))})
    return normalize_remote(url), langs


def lessons(project, repo, langs):
    cfg = load_json(home(".config", "ai-toolkit", "hindsight.json"))
    scopes = {"global"} | ({"repo:" + repo} if repo else set()) | {"lang:" + l for l in langs}
    out = []
    for store in cfg.get("stores") or []:
        root = os.path.expanduser(store.get("path", ""))
        for f in glob.glob(os.path.join(root, "lessons", "active", "*.md")) + \
                [os.path.join(root, "lessons", "candidates.md")]:
            text = read(f) or ""
            for block in re.split(r"\n(?=## L-)", text):
                m = re.match(r"## (L-[0-9a-f]+) — (.+)", block.strip())
                if not m:
                    continue
                field = lambda k: (re.search(r"^- %s:\s*(.+)$" % k, block, re.M) or [None, ""])[1]
                scope = field("scope")
                if scope not in scopes:
                    continue
                out.append({"id": m.group(1), "text": m.group(2).strip(), "scope": scope, "store": store.get("name"),
                            "status": field("status") or ("candidate" if f.endswith("candidates.md") else "active"),
                            "why": field("why"), "issue": field("issue"), "created": field("created")})
    return out


def retros(project):
    out = []
    for line in (read(state_dir("retros.jsonl")) or "").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("project") == project:
            out.append(e)
    return sorted(out, key=lambda e: e.get("at", ""), reverse=True)


# ---------- checks ----------

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


def project_view(project, fire_stats=None):
    fire_stats = fires() if fire_stats is None else fire_stats
    repo, langs = repo_info(project)
    instr = instruction_files(project)
    mem = memory(project)
    hks = hooks(project, fire_stats)
    less = lessons(project, repo, langs)
    return {"path": project, "name": os.path.basename(project.rstrip("/")), "repo": repo, "langs": langs,
            "instructions": instr, "memory": mem, "hooks": hks, "lessons": less, "retros": retros(project),
            "overlaps": overlaps(rule_units(instr, mem, less)), "problems": problems(project, instr, mem, hks)}


def snapshot(limit=12):
    fs = fires()
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "fire_log": state_dir("fires.jsonl"),
            "projects": [project_view(p, fs) for p in projects()[:limit]]}
