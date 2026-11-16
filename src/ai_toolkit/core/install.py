"""Is ai-toolkit wired into Claude Code on this machine, and how?

Two ways are recognised:
  plugin   "ai-toolkit@<marketplace>" is enabled in a settings file, so hooks/hooks.json is active;
  legacy   hook commands that the pre-0.2 install.sh wrote into ~/.claude/settings.json
           (they contain "/.claude/ai-toolkit/"). Still honoured so an old install keeps reporting.
"""
import os

from . import paths
from .jsonio import read_json

PLUGIN = "ai-toolkit"
LEGACY_TAG = "/.claude/ai-toolkit/"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def plugin_hooks():
    """{event: hook target like "hindsight.capture_prompt"} declared in hooks/hooks.json."""
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
    plugin = plugin_enabled(settings)
    legacy = settings_hook_commands(settings)
    out = []
    for event, targets in sorted(plugin_hooks().items()):
        for t in targets:
            f, _, hook = t.partition(".")
            if f != feature:
                continue
            via = "plugin" if plugin else None
            if not via and any(e == event and LEGACY_TAG in c and hook in c for e, c in legacy):
                via = "legacy"
            out.append({"event": event, "hook": hook, "registered": bool(via), "via": via or ""})
    return out

