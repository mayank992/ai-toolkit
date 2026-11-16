"""Is the ai-toolkit plugin enabled on this machine, and which hooks does that register?

The hooks are registered when "ai-toolkit@<marketplace>" is enabled in settings.json, which activates
hooks/hooks.json. Hook entries left in settings.json by a 0.1 install.sh no longer run (their targets are
gone); `ait doctor` points at `ait migrate-legacy` to remove them.
"""
import os

from . import paths
from .jsonio import read_json

PLUGIN = "ai-toolkit"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def plugin_hooks():
    """{event: hook target like "lessons.capture_prompt"} declared in hooks/hooks.json."""
    data = read_json(os.path.join(REPO_ROOT, "hooks", "hooks.json"), {})
    out = {}
    for event, groups in (data.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                out.setdefault(event, []).append(h.get("command", "").rsplit(" ", 1)[-1])
    return out


def user_settings():
    return read_json(paths.claude_dir("settings.json"), {})


def plugin_enabled(settings=None):
    """The enabledPlugins key that turns this plugin on, or None."""
    settings = user_settings() if settings is None else settings
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):  # running inside the plugin itself (incl. --plugin-dir)
        return "%s@running" % PLUGIN
    for key, on in (settings.get("enabledPlugins") or {}).items():
        if on and key.split("@", 1)[0] == PLUGIN:
            return key
    return None


def settings_hook_commands(settings=None):
    settings = user_settings() if settings is None else settings
    return [(event, h.get("command", "")) for event, groups in (settings.get("hooks") or {}).items()
            for g in groups for h in g.get("hooks", [])]


def hook_status(feature):
    """[{event, hook, registered, via}] for each hook the plugin declares for `feature`."""
    settings = user_settings()
    via = "plugin" if plugin_enabled(settings) else ""
    out = []
    for event, targets in sorted(plugin_hooks().items()):
        for t in targets:
            f, _, hook = t.partition(".")
            if f != feature:
                continue
            out.append({"event": event, "hook": hook, "registered": bool(via), "via": via})
    return out



RUNTIME_DIRS = ("src", "hooks", "skills", "bin", ".claude-plugin")


def installed_copy(settings=None):
    """The folder Claude Code runs the plugin from (a copy it made at install time), or None."""
    key = plugin_enabled(settings)
    plugins = (read_json(paths.claude_dir("plugins", "installed_plugins.json"), {}) or {}).get("plugins") or {}
    entries = [e for e in plugins.get(key) or [] if isinstance(e, dict) and e.get("installPath")]
    return entries[-1]["installPath"] if entries else None


def _runtime_files(root):
    out = {}
    for d in RUNTIME_DIRS:
        for base, dirs, files in os.walk(os.path.join(root, d)):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for f in files:
                if f.endswith(".pyc") or f == ".DS_Store":
                    continue
                p = os.path.join(base, f)
                try:
                    with open(p, "rb") as fh:
                        out[os.path.relpath(p, root)] = fh.read()
                except OSError:
                    pass
    return out


def copy_behind():
    """(installed copy, [files that differ from this checkout]) when hooks run from a different folder
    than this code; (None, []) when they are the same folder or the plugin isn't installed."""
    copy = installed_copy()
    if not copy or not os.path.isdir(copy) or os.path.realpath(copy) == os.path.realpath(REPO_ROOT):
        return None, []
    here, there = _runtime_files(REPO_ROOT), _runtime_files(copy)
    return copy, sorted(f for f in set(here) | set(there) if here.get(f) != there.get(f))
