"""Everything that shapes Claude Code's behaviour in a project, layer by layer.

For each project Claude Code knows about, collect:
  instructions  ~/.claude/CLAUDE.md, <project>/CLAUDE.md, <project>/CLAUDE.local.md
  memory        ~/.claude/projects/<key>/memory/*.md and its MEMORY.md index
  hooks         user, project and local settings, with the hook-fire log
  lessons       hindsight lessons scoped to this repo, its languages or global
and check them: an instructions file git would commit by accident, index entries without files,
memory files missing from the index, hook scripts that don't exist, and rules saying the same thing
in two layers (see checks.py). Read-only; stdlib only (python 3.9).
"""
import glob
import json
import os
import re
import time

from ..core import paths
from ..core.gitutil import git, languages, normalize_remote
from ..core.paths import claude_dir, home, project_key
from . import checks


def state_dir(*p):
    return paths.state_dir("rules", *p)


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


# ---------- discovery ----------

def canonical(path):
    """The spelling Claude Code uses for this folder (its memory and transcript keys depend on it)."""
    real = os.path.realpath(path)
    for p in (load_json(paths.claude_json()).get("projects") or {}):
        if p != path and os.path.realpath(p) == real:
            return p
    return path


def projects():
    """[path] of existing project folders Claude Code has a record of, most recently used first."""
    seen = {}
    for p in (load_json(paths.claude_json()).get("projects") or {}):
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


IMPORT_RX = re.compile(r"(?:^|(?<=\s))@((?:~/|\.{1,2}/|/)?[\w.-][\w./-]*)")
MAX_IMPORT_DEPTH = 5  # the depth Claude Code follows


def imported_paths(text, base_dir):
    """Files a CLAUDE.md pulls in with `@path` (relative to the file, absolute, or ~/...), in order.
    `@` inside code fences or code spans is not an import, and neither is anything that isn't a file."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    out = []
    for m in IMPORT_RX.finditer(text):
        ref = m.group(1).rstrip(".,;:")
        p = home(ref[2:]) if ref.startswith("~/") else os.path.join(base_dir, ref)
        p = os.path.normpath(p)
        if os.path.isfile(p) and p not in out:
            out.append(p)
    return out


def instruction_files(project):
    """CLAUDE.md files in load order, each followed by the files it imports with `@path` (AGENTS.md is
    usually reached this way). An imported file carries its importer's scope and `imported_from`."""
    out, seen = [], set()

    def add(scope, path, parent, depth):
        text = read(path)
        if text is None or path in seen:
            return
        seen.add(path)
        out.append({"scope": scope, "path": path, "lines": len(text.splitlines()), "modified": mtime(path),
                    "sections": headings(text), "rules": bullets(text),
                    "git": git_visibility(project, path) if path.startswith(project.rstrip("/") + "/") else "n/a",
                    "shared": scope == "project", "imported_from": parent})
        if depth < MAX_IMPORT_DEPTH:
            for p in imported_paths(text, os.path.dirname(path)):
                add(scope, p, path, depth + 1)

    for scope, path in (("user", claude_dir("CLAUDE.md")), ("project", os.path.join(project, "CLAUDE.md")),
                        ("local", os.path.join(project, "CLAUDE.local.md"))):
        add(scope, path, "", 0)
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
        t = t.replace("${CLAUDE_PLUGIN_ROOT}", "{plugin}").replace("$CLAUDE_PLUGIN_ROOT", "{plugin}")
        t = t.replace("${HOME}", home()).replace("$HOME", home())
        if t.startswith("~/"):
            t = home(t[2:])
        if t.startswith(("/", "{project}", "{plugin}")):
            return t
    return ""


def hook_target(command, script):
    """The argument after the script when it names what runs, e.g. `run.py hindsight.capture_prompt`."""
    m = re.search(re.escape(os.path.basename(script)) + r"[\"']?\s+([A-Za-z_][\w.:-]*)\s*$", command) if script else None
    return m.group(1) if m else ""


def enabled_plugins(project):
    """[(name, install path)] of plugins enabled for this project (user, project or local settings)."""
    on = {}
    for path in (claude_dir("settings.json"), os.path.join(project, ".claude", "settings.json"),
                 os.path.join(project, ".claude", "settings.local.json")):
        on.update(load_json(path).get("enabledPlugins") or {})
    installed = load_json(claude_dir("plugins", "installed_plugins.json")).get("plugins") or {}
    out = []
    for key in sorted(k for k, v in on.items() if v):
        entries = [e for e in installed.get(key) or [] if isinstance(e, dict) and e.get("installPath")]
        # a plugin installed for one project only is listed with that project's path
        mine = [e for e in entries if not e.get("projectPath") or e["projectPath"] == project]
        if mine:
            out.append((key.split("@", 1)[0], mine[-1]["installPath"]))
    return out


def hooks(project, fire_stats):
    out = []
    layers = [("user", claude_dir("settings.json"), "", ""),
              ("project", os.path.join(project, ".claude", "settings.json"), "", ""),
              ("local", os.path.join(project, ".claude", "settings.local.json"), "", "")]
    layers += [("plugin", os.path.join(root, "hooks", "hooks.json"), name, root) for name, root in enabled_plugins(project)]
    for scope, path, plugin, root in layers:
        for event, groups in (load_json(path).get("hooks") or {}).items():
            for g in groups or []:
                for h in g.get("hooks") or []:
                    cmd = h.get("command", "")
                    script = script_of(cmd).replace("{project}", project).replace("{plugin}", root)
                    name = os.path.splitext(os.path.basename(script))[0] if script else cmd[:40]
                    if plugin:  # every hook of a plugin often shares one runner script, so name what it runs
                        name = "%s: %s" % (plugin, hook_target(cmd, script) or name)
                    st = fire_stats.get(name)
                    out.append({"scope": scope, "plugin": plugin, "settings": path, "event": event,
                                "matcher": g.get("matcher", ""),
                                "command": cmd, "script": script, "name": name,
                                "exists": (os.path.exists(script) if script else True),
                                "shared": scope == "project", "logged": st is not None or writes_fire_log(script),
                                "fires": st or {"count": 0, "last": "", "decisions": {}, "projects": {}},
                                "doc": hook_doc(script)})
    return out


def writes_fire_log(script):
    text = read(script) if script else None
    return bool(text) and any(m in text for m in ("fires.jsonl", "ait rules fire", "ai-rules fire"))


def hook_doc(script):
    text = read(script) if script else None
    if not text:
        return ""
    m = re.search(r'^\s*(?:"""|\'\'\')(.+?)(?:"""|\'\'\')', text, re.S | re.M) or re.search(r"^#\s+(?!!)(.+)$", text, re.M)
    return m.group(1).strip().splitlines()[0] if m else ""


def repo_info(project):
    _, url = git(project, "remote", "get-url", "origin")
    return normalize_remote(url), languages(project)


def lessons(project, repo, langs):
    """hindsight lessons that apply here, through hindsight's public API (empty if it can't load)."""
    try:
        from ..hindsight.api import lessons_for
        return lessons_for(repo, langs)
    except Exception:
        return []


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


def project_view(project, fire_stats=None):
    fire_stats = fires() if fire_stats is None else fire_stats
    repo, langs = repo_info(project)
    instr = instruction_files(project)
    mem = memory(project)
    hks = hooks(project, fire_stats)
    less = lessons(project, repo, langs)
    return {"path": project, "name": os.path.basename(project.rstrip("/")), "repo": repo, "langs": langs,
            "instructions": instr, "memory": mem, "hooks": hks, "lessons": less, "retros": retros(project),
            "overlaps": checks.overlaps(checks.rule_units(instr, mem, less)),
            "problems": checks.problems(project, instr, mem, hks)}


def snapshot(limit=12):
    fs = fires()
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "fire_log": state_dir("fires.jsonl"),
            "projects": [project_view(p, fs) for p in projects()[:limit]]}
