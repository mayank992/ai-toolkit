"""Claude Code adapter: inventory, export and apply for ~/.claude, ~/.claude.json and the files they reference.

Exported tree (under <snapshot>/claude-code/):
  settings.json            user settings; ai-toolkit's own hooks removed (install.sh re-adds them)
  CLAUDE.md, agents/, commands/, skills/, output-styles/, keybindings.json
  mcp.json                 {"user": {...}, "projects": {"{{HOME}}/path": {...}}}; secrets as ${secret:id}
  plugins.json             marketplaces and installed plugin ids
  files/<path under ~>     scripts that hooks or the status line call from outside ~/.claude
  memory/~<project>/       auto-memory per project, keyed relative to $HOME (only with memory on)
"""
import copy
import json
import os
import re
import shlex
import shutil

import core

ID = "claude-code"
TITLE = "Claude Code"
TOOLKIT_TAG = "/.claude/ai-toolkit/"  # in hook commands that ai-toolkit's settings_merge.py wrote
SKIP_SKILLS = {"synced"}  # managed by Claude Code itself (skills synced from claude.ai)
COPY_DIRS = ("agents", "commands", "skills", "output-styles")
MAX_FILE = 2 * 1024 * 1024


def claude_dir():
    return os.path.join(core.home(), ".claude")


def claude_json_path():
    return os.path.join(core.home(), ".claude.json")


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def detected():
    return os.path.isdir(claude_dir())


def ours(cmd):
    return TOOLKIT_TAG in cmd


def toolkit_link(p):
    """Links that ai-toolkit's install.sh creates (e.g. /lesson); it re-creates them on the new machine."""
    return os.path.islink(p) and "/ai-toolkit/" in os.readlink(p)


def project_label(key_suffix):
    """Readable ~/path for a project memory folder, using Claude Code's own list of project paths."""
    key = core.encode_project(core.home()) + key_suffix
    for p in (read_json(claude_json_path(), {}).get("projects") or {}):
        if core.encode_project(p) == key:
            return short(p)
    return "~" + key_suffix


def iter_hooks(settings):
    for event, groups in (settings.get("hooks") or {}).items():
        for g in groups or []:
            for h in g.get("hooks") or []:
                yield event, g.get("matcher", ""), h


def command_paths(cmd):
    """Absolute file paths a shell command runs or reads, with $HOME/~ expanded."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = cmd.split()
    out = []
    for p in parts:
        p = p.replace("$HOME", core.home()).replace("${HOME}", core.home())
        if p.startswith("~/"):
            p = core.home() + p[1:]
        if p.startswith("/") and os.path.isfile(p):
            out.append(p)
    return out


def external_files(settings):
    """Scripts under $HOME (but outside ~/.claude) that hooks or the status line call."""
    cmds = [h.get("command", "") for _, _, h in iter_hooks(settings) if not ours(h.get("command", ""))]
    sl = settings.get("statusLine") or {}
    if sl.get("command"):
        cmds.append(sl["command"])
    found = []
    for c in cmds:
        for p in command_paths(c):
            if p.startswith(core.home() + os.sep) and not p.startswith(claude_dir() + os.sep) and p not in found:
                found.append(p)
    return found


def memory_dirs():
    """[(suffix, path)] for each project memory folder under $HOME; suffix is the folder key after $HOME."""
    root = os.path.join(claude_dir(), "projects")
    prefix = core.encode_project(core.home())
    out = []
    for key in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        mem = os.path.join(root, key, "memory")
        if key.startswith(prefix) and os.path.isdir(mem) and any(f.endswith(".md") for f in os.listdir(mem)):
            out.append((key[len(prefix):], mem))
    return out


def mcp_config():
    cj = read_json(claude_json_path(), {})
    projects = {p: v["mcpServers"] for p, v in (cj.get("projects") or {}).items() if (v or {}).get("mcpServers")}
    return cj.get("mcpServers") or {}, projects


# ---------------------------------------------------------------- export

def redact_server(cfg, prefix, secrets):
    out = dict(cfg)
    if "env" in out:
        out["env"] = secrets.mapping(out["env"], prefix + ".env")
    if "headers" in out:
        out["headers"] = secrets.mapping(out["headers"], prefix + ".headers")
    if "args" in out:
        out["args"] = secrets.args(out["args"], prefix + ".args")
    for k in ("url", "command"):
        if isinstance(out.get(k), str):
            out[k] = secrets.string(out[k], "%s.%s" % (prefix, k))
    return out


def export_settings(settings, secrets):
    s = copy.deepcopy(settings)
    hooks = {}
    for event, groups in (s.get("hooks") or {}).items():
        kept = []
        for g in groups or []:
            hs = [h for h in g.get("hooks") or [] if not ours(h.get("command", ""))]
            if hs:
                kept.append(dict(g, hooks=hs))
        if kept:
            hooks[event] = kept
    if hooks:
        s["hooks"] = hooks
    else:
        s.pop("hooks", None)
    if "env" in s:
        s["env"] = secrets.mapping(s["env"], "settings.env")
    return s


def dump(obj):
    return (json.dumps(obj, indent=2, sort_keys=False) + "\n").encode()


def add_dir(tree, src, dest, skipped):
    for d, dirs, files in os.walk(src, followlinks=True):
        rel_d = os.path.relpath(d, src)
        skip = SKIP_SKILLS if dest == "skills" and rel_d == "." else set()
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in skip and not toolkit_link(os.path.join(d, x))]
        for f in files:
            p = os.path.join(d, f)
            if f == ".DS_Store" or toolkit_link(p):
                continue
            if os.path.getsize(p) > MAX_FILE:
                skipped.append({"path": os.path.join(dest, rel_d, f), "reason": "larger than 2 MB"})
                continue
            with open(p, "rb") as fh:
                tree[os.path.normpath(os.path.join(dest, rel_d, f))] = fh.read()


def render(memory=True):
    """(tree, report) where tree is {relpath: bytes} ready to commit and report says what was redacted."""
    secrets = core.Secrets()
    tree, skipped, modes = {}, [], {}
    c = claude_dir()
    settings = read_json(os.path.join(c, "settings.json"), {})
    tree["settings.json"] = dump(export_settings(settings, secrets))
    for name in ("CLAUDE.md", "keybindings.json"):
        p = os.path.join(c, name)
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                tree[name] = fh.read()
    for d in COPY_DIRS:
        if os.path.isdir(os.path.join(c, d)):
            add_dir(tree, os.path.join(c, d), d, skipped)

    user, projects = mcp_config()
    mcp = {"user": {n: redact_server(v, "mcp.user.%s" % n, secrets) for n, v in sorted(user.items())}, "projects": {}}
    for path, servers in sorted(projects.items()):
        if not path.startswith(core.home() + os.sep):
            skipped.append({"path": "mcp.json", "reason": "project outside home: %s" % path})
            continue
        key = os.path.relpath(path, core.home())
        mcp["projects"][path] = {n: redact_server(v, "mcp.project.%s.%s" % (key, n), secrets) for n, v in sorted(servers.items())}
    tree["mcp.json"] = dump(mcp)

    known = read_json(os.path.join(c, "plugins", "known_marketplaces.json"), {})
    installed = (read_json(os.path.join(c, "plugins", "installed_plugins.json"), {}) or {}).get("plugins", {})
    tree["plugins.json"] = dump({
        "marketplaces": {n: (v or {}).get("source", {}) for n, v in sorted(known.items())},
        "plugins": sorted(installed),
    })

    for p in external_files(settings):
        rel = os.path.join("files", os.path.relpath(p, core.home()))
        with open(p, "rb") as fh:
            tree[rel] = fh.read()
        if os.access(p, os.X_OK):
            modes[rel] = 0o755

    if memory:
        for suffix, mem in memory_dirs():
            for f in sorted(os.listdir(mem)):
                if f.endswith(".md") and os.path.isfile(os.path.join(mem, f)):
                    with open(os.path.join(mem, f), "rb") as fh:
                        tree[os.path.join("memory", "~" + suffix, f)] = fh.read()

    blocked = []
    for rel, data in list(tree.items()):
        try:
            text = data.decode()
        except UnicodeDecodeError:
            continue
        hits = core.token_hits(text)
        if hits:
            blocked.append({"path": rel, "kinds": hits})
        tree[rel] = core.to_template(text).encode()
    report = {"placeholders": secrets.ids, "skipped": skipped, "blocked": blocked, "modes": modes}
    return tree, report


# ---------------------------------------------------------------- apply

def merge_settings(cur, snap):
    """Snapshot settings layered over the current ones: scalars win, dicts merge, lists and hooks union."""
    out = copy.deepcopy(cur)
    for k, v in snap.items():
        if k == "hooks":
            hooks = out.setdefault("hooks", {})
            for event, groups in v.items():
                have = {h.get("command") for _, _, h in iter_hooks({"hooks": {event: hooks.get(event, [])}})}
                for g in groups:
                    new = [h for h in g.get("hooks") or [] if h.get("command") not in have]
                    if new:
                        hooks.setdefault(event, []).append(dict(g, hooks=new))
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_settings(out[k], v)
        elif isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + [x for x in v if x not in out[k]]
        else:
            out[k] = copy.deepcopy(v)
    return out


class Action(object):
    def __init__(self, kind, target, change, summary, run=None, blocked=None):
        self.kind, self.target, self.change, self.summary = kind, target, change, summary
        self.run, self.blocked = run, blocked

    def as_dict(self):
        return {"kind": self.kind, "target": self.target, "change": self.change, "summary": self.summary,
                "blocked": self.blocked}


def file_action(kind, target, data, backup_ref, mode=None, label=None):
    if os.path.isfile(target):
        with open(target, "rb") as fh:
            if fh.read() == data:
                return Action(kind, target, "same", label or "")
        change = "update"
    else:
        change = "add"
    return Action(kind, target, change, label or "", run=lambda: core.write_file(target, data, backup_ref[0], mode))


def resolve_secrets(ids, current_values, prompt):
    """Secret values from (1) this machine's existing config, (2) AI_SETUP_SECRET_* env vars, (3) a prompt."""
    values = {}
    for sid in ids:
        if sid in current_values and not core.is_unset(current_values[sid]):
            values[sid] = current_values[sid]
        elif os.environ.get(core.env_secret_name(sid)):
            values[sid] = os.environ[core.env_secret_name(sid)]
        elif prompt:
            v = prompt(sid)
            if v:
                values[sid] = v
    return values


def current_secret_values(snap_server, live_server):
    """Map placeholder ids in a snapshot server to the values the same fields hold on this machine."""
    out = {}

    def walk(s, l):
        if isinstance(s, str) and isinstance(l, str):
            ids = core.PLACEHOLDER.findall(s)
            if len(ids) == 1:
                pre, post = s.split(core.placeholder(ids[0]))
                if l.startswith(pre) and l.endswith(post) and len(l) >= len(pre) + len(post):
                    out[ids[0]] = l[len(pre):len(l) - len(post)]
        elif isinstance(s, dict) and isinstance(l, dict):
            for k in s:
                walk(s[k], l.get(k))
        elif isinstance(s, list) and isinstance(l, list):
            for a, b in zip(s, l):
                walk(a, b)
    walk(snap_server, live_server or {})
    return out


def mcp_actions(snap, prompt, backup_ref):
    user, projects = mcp_config()
    actions = []
    claude = core.tool_cmd("claude")
    groups = [("user", None, snap.get("user") or {}, user)]
    for path, servers in (snap.get("projects") or {}).items():
        groups.append(("local", path, servers, projects.get(path, {})))
    for scope, path, servers, live in groups:
        for name, cfg in sorted(servers.items()):
            target = "mcp %s%s" % (name, " (%s)" % path.replace(core.home(), "~") if path else "")
            ids = sorted(set(core.PLACEHOLDER.findall(json.dumps(cfg))))
            values = resolve_secrets(ids, current_secret_values(cfg, live.get(name)), prompt)
            want, missing = core.fill_placeholders(cfg, values)
            if live.get(name) == want:
                actions.append(Action("mcp", target, "same", ""))
                continue
            if missing:
                actions.append(Action("mcp", target, "add" if name not in live else "update", "",
                                      blocked="needs %s (set %s)" % (", ".join(missing), core.env_secret_name(missing[0]))))
                continue
            if path and not os.path.isdir(path):
                actions.append(Action("mcp", target, "add", "", blocked="project folder does not exist on this machine"))
                continue

            def go(name=name, want=want, scope=scope, path=path, exists=name in live):
                if exists:
                    core.run(claude + ["mcp", "remove", "-s", scope, name], cwd=path)
                ok, out = core.run(claude + ["mcp", "add-json", "-s", scope, name, json.dumps(want)], cwd=path)
                if not ok:
                    raise RuntimeError("claude mcp add-json %s failed: %s" % (name, out))
            summary = "%d secret(s) filled" % len(ids) if ids else ""
            actions.append(Action("mcp", target, "update" if name in live else "add", summary, run=go))
    return actions


def plugin_actions(snap):
    c = claude_dir()
    known = read_json(os.path.join(c, "plugins", "known_marketplaces.json"), {})
    installed = (read_json(os.path.join(c, "plugins", "installed_plugins.json"), {}) or {}).get("plugins", {})
    claude = core.tool_cmd("claude")
    actions = []
    for name, src in sorted((snap.get("marketplaces") or {}).items()):
        if name in known:
            actions.append(Action("marketplace", name, "same", ""))
            continue
        ref = src.get("repo") or src.get("url") or src.get("path")
        if not ref:
            actions.append(Action("marketplace", name, "add", "", blocked="unknown source %r" % src))
            continue

        def go(ref=ref):
            ok, out = core.run(claude + ["plugin", "marketplace", "add", ref])
            if not ok:
                raise RuntimeError("marketplace add %s failed: %s" % (ref, out))
        actions.append(Action("marketplace", name, "add", ref, run=go))
    for pid in snap.get("plugins") or []:
        if pid in installed:
            actions.append(Action("plugin", pid, "same", ""))
            continue

        def go(pid=pid):
            ok, out = core.run(claude + ["plugin", "install", pid])
            if not ok:
                raise RuntimeError("plugin install %s failed: %s" % (pid, out))
        actions.append(Action("plugin", pid, "add", "", run=go))
    return actions


def plan(src, prompt=None, memory=True):
    """Actions that make this machine match the snapshot at <src>/claude-code."""
    root = os.path.join(src, ID)
    if not os.path.isdir(root):
        return []
    tree = core.read_tree(root)
    manifest = read_json(os.path.join(src, core.MANIFEST), {})
    modes = (manifest.get("tools", {}).get(ID) or {}).get("modes", {})
    backup_ref = [core.Backup()]
    c = claude_dir()
    actions = []

    def text(rel):
        return core.from_template(tree[rel].decode())

    if "settings.json" in tree:
        target = os.path.join(c, "settings.json")
        cur = read_json(target, {})
        snap = json.loads(text("settings.json"))
        ids = sorted(set(core.PLACEHOLDER.findall(json.dumps(snap.get("env", {})))))
        values = resolve_secrets(ids, current_secret_values(snap.get("env", {}), cur.get("env", {})), prompt)
        snap, missing = core.fill_placeholders(snap, values)
        merged = merge_settings(cur, snap)
        if missing:
            actions.append(Action("settings", target, "update", "", blocked="needs " + ", ".join(missing)))
        elif merged == cur:
            actions.append(Action("settings", target, "same", ""))
        else:
            changed = sorted(k for k in merged if merged.get(k) != cur.get(k))
            actions.append(file_action("settings", target, dump(merged), backup_ref, label="keys: " + ", ".join(changed)))

    for rel in sorted(tree):
        top = rel.split(os.sep)[0]
        if rel in ("settings.json", "mcp.json", "plugins.json"):
            continue
        data = text(rel).encode() if _is_text(tree[rel]) else tree[rel]
        if top == "files":
            target = os.path.join(core.home(), os.path.relpath(rel, "files"))
            actions.append(file_action("file", target, data, backup_ref, modes.get(rel)))
        elif top == "memory":
            if not memory:
                continue
            parts = rel.split(os.sep)
            key = core.encode_project(core.home()) + parts[1][1:]
            target = os.path.join(c, "projects", key, "memory", *parts[2:])
            actions.append(file_action("memory", target, data, backup_ref))
        else:
            actions.append(file_action(top if top in COPY_DIRS else "file", os.path.join(c, rel), data, backup_ref))

    if "mcp.json" in tree:
        actions += mcp_actions(json.loads(text("mcp.json")), prompt, backup_ref)
    if "plugins.json" in tree:
        actions += plugin_actions(json.loads(text("plugins.json")))
    return actions


def _is_text(data):
    try:
        data.decode()
        return True
    except UnicodeDecodeError:
        return False


# ---------------------------------------------------------------- inventory

def item(name, detail="", status="ok", note="", tag=""):
    return {"name": name, "detail": detail, "status": status, "note": note, "tag": tag}


def short(p):
    return p.replace(core.home(), "~")


def inventory():
    """Sections of items describing this machine's Claude Code setup, with health checks."""
    c = claude_dir()
    settings = read_json(os.path.join(c, "settings.json"), {})
    sections = []

    # settings
    items = []
    for src in ("settings.json", "settings.local.json"):
        p = os.path.join(c, src)
        if os.path.isfile(p):
            data = read_json(p, None)
            items.append(item(src, short(p), "ok" if data is not None else "error",
                              "" if data is not None else "not valid JSON", tag="file"))
    for k in ("model", "effortLevel", "theme", "outputStyle", "autoMemoryEnabled", "voiceEnabled"):
        if k in settings:
            items.append(item(k, json.dumps(settings[k]), tag="setting"))
    for k in ("permissions", "env", "statusLine", "autoMode"):
        if k in settings:
            n = len(settings[k]) if isinstance(settings[k], (dict, list)) else 1
            items.append(item(k, "%d entr%s" % (n, "y" if n == 1 else "ies"), tag="setting"))
    managed = "/Library/Application Support/ClaudeCode/managed-settings.json"
    if os.path.isfile(managed):
        items.append(item("managed-settings.json", managed, "ok", "set by your organization; not exported", tag="file"))
    sections.append({"id": "settings", "title": "Settings", "items": items})

    # hooks
    items = []
    for event, matcher, h in iter_hooks(settings):
        cmd = h.get("command", "")
        status, note = "ok", ""
        try:
            first = (shlex.split(cmd)[:1] or [""])[0].replace("$HOME", core.home())
        except ValueError:
            first = ""
        if first.startswith("/") and not os.path.exists(first):
            status, note = "error", "script missing: %s" % short(first)
        elif first.startswith("/") and not os.access(first, os.X_OK):
            status, note = "warn", "script is not executable"
        elif not first.startswith("/") and first and not shutil.which(first):
            status, note = "warn", "%s not on PATH" % first
        items.append(item(event + (" [%s]" % matcher if matcher else ""), short(cmd), status, note,
                          tag="ai-toolkit" if ours(cmd) else "yours"))
    sections.append({"id": "hooks", "title": "Hooks", "items": items})

    # mcp
    user, projects = mcp_config()
    items = []
    for scope, servers in [("user", user)] + [("project %s" % os.path.basename(p), s) for p, s in sorted(projects.items())]:
        for name, cfg in sorted(servers.items()):
            items.append(mcp_item(name, cfg, scope))
    sections.append({"id": "mcp", "title": "MCP servers", "items": items})

    # plugins
    known = read_json(os.path.join(c, "plugins", "known_marketplaces.json"), {})
    installed = (read_json(os.path.join(c, "plugins", "installed_plugins.json"), {}) or {}).get("plugins", {})
    enabled = settings.get("enabledPlugins") or {}
    items = []
    for pid in sorted(set(installed) | set(enabled)):
        on = enabled.get(pid)
        if pid not in installed:
            items.append(item(pid, "enabled but not installed", "error", "run: claude plugin install %s" % pid, tag="plugin"))
        else:
            items.append(item(pid, "enabled" if on else "installed, disabled", "ok" if on else "info", tag="plugin"))
    for name, v in sorted(known.items()):
        src = (v or {}).get("source", {})
        items.append(item(name, src.get("repo") or src.get("url") or src.get("path") or "", tag="marketplace"))
    for name in sorted(settings.get("extraKnownMarketplaces") or {}):
        if name not in known:
            items.append(item(name, "declared in settings, not added", "warn", tag="marketplace"))
    sections.append({"id": "plugins", "title": "Plugins", "items": items})

    # skills, agents, commands
    items = []
    for d, tag in (("skills", "skill"), ("agents", "agent"), ("commands", "command"), ("output-styles", "output style")):
        base = os.path.join(c, d)
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            if name.startswith("."):
                continue
            p = os.path.join(base, name)
            if d == "skills" and name in SKIP_SKILLS:
                items.append(item(name, "synced by Claude Code", "info", "not exported", tag=tag))
                continue
            if os.path.islink(p) and not os.path.exists(p):
                items.append(item(name, short(os.readlink(p)), "error", "broken symlink", tag=tag))
                continue
            if d == "skills" and not os.path.isfile(os.path.join(p, "SKILL.md")):
                items.append(item(name, short(p), "warn", "no SKILL.md", tag=tag))
                continue
            owner = "ai-toolkit" if toolkit_link(p) else ""
            items.append(item(os.path.splitext(name)[0] if d != "skills" else name, short(p), note=owner and "installed by ai-toolkit", tag=tag))
    p = os.path.join(c, "CLAUDE.md")
    if os.path.isfile(p):
        items.insert(0, item("CLAUDE.md", short(p), tag="instructions"))
    sections.append({"id": "extensions", "title": "Skills, agents, commands", "items": items})

    # memory
    items = []
    for suffix, mem in memory_dirs():
        files = [f for f in os.listdir(mem) if f.endswith(".md")]
        idx = os.path.join(mem, "MEMORY.md")
        status, note = "ok", ""
        if os.path.isfile(idx):
            with open(idx) as fh:
                links = re.findall(r"\]\(([^)]+\.md)\)", fh.read())
            broken = [l for l in links if not os.path.isfile(os.path.join(mem, l))]
            if broken:
                status, note = "warn", "MEMORY.md links to missing: " + ", ".join(broken[:3])
        items.append(item(project_label(suffix), "%d file(s)" % len(files), status, note, tag="memory"))
    sections.append({"id": "memory", "title": "Memory", "items": items})

    for s in external_files(settings):
        sections[1]["items"].append(item(os.path.basename(s), short(s), "ok", "copied into exports", tag="script"))
    return sections


def mcp_item(name, cfg, scope):
    kind = cfg.get("type") or ("http" if cfg.get("url") else "stdio")
    status, notes = "ok", []
    if cfg.get("url"):
        detail = cfg["url"]
        notes.append("connection not checked here; run: claude mcp list")
    else:
        cmd = cfg.get("command", "")
        detail = " ".join([short(cmd)] + [short(a) for a in (cfg.get("args") or [])[:4]]) + (" …" if len(cfg.get("args") or []) > 4 else "")
        if cmd and not (os.path.isfile(cmd) if cmd.startswith("/") else shutil.which(cmd)):
            status, notes = "error", ["command not found: %s" % cmd]
        args = cfg.get("args") or []
        for i, a in enumerate(args):
            if a in ("--directory", "--env-file", "--cwd") and i + 1 < len(args):
                p = os.path.expanduser(args[i + 1])
                if not os.path.exists(p):
                    status = "error"
                    notes.append("%s missing: %s" % (a.lstrip("-"), short(p)))
    secrets = [k for k in (cfg.get("env") or {}) if core.SECRET_NAME.search(k)]
    if secrets:
        notes.append("secrets: " + ", ".join(secrets))
    return item(name, detail, status, "; ".join(notes), tag="%s · %s" % (kind, scope))
