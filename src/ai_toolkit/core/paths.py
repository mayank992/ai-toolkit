"""Where things live on disk. The only module that knows these locations.

  config   $XDG_CONFIG_HOME/ai-toolkit/          (default ~/.config/ai-toolkit)
  state    $XDG_STATE_HOME/ai-toolkit/<feature>/ (default ~/.local/state/ai-toolkit/<feature>)
  claude   $CLAUDE_CONFIG_DIR                    (default ~/.claude), plus ~/.claude.json

Memory stores (hindsight) and setup snapshots are git repos whose paths come from config.
"""
import os
import re


def home(*parts):
    return os.path.join(os.path.expanduser("~"), *parts)


def config_dir(*parts):
    base = os.environ.get("XDG_CONFIG_HOME") or home(".config")
    return os.path.join(base, "ai-toolkit", *parts)


def state_root():
    base = os.environ.get("XDG_STATE_HOME") or home(".local", "state")
    return os.path.join(base, "ai-toolkit")


def state_dir(feature, *parts):
    """Machine-local state for one feature. Created on first use."""
    d = os.path.join(state_root(), feature)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, *parts)


def claude_dir(*parts):
    """Claude Code's config folder, honouring CLAUDE_CONFIG_DIR like Claude Code does."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or home(".claude")
    return os.path.join(base, *parts)


def claude_json():
    """Claude Code's global state file (projects, MCP servers)."""
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return os.path.join(os.environ["CLAUDE_CONFIG_DIR"], ".claude.json")
    return home(".claude.json")


def project_key(path):
    """Claude Code's folder name for a project under claude_dir('projects'): non-alphanumerics become '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def tilde(path):
    """Replace $HOME with ~ for display and for paths written to config."""
    h = home()
    return "~" + path[len(h):] if path == h or path.startswith(h + os.sep) else path
