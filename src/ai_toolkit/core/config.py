"""One config file for every feature: ~/.config/ai-toolkit/config.json.

  {
    "hindsight": {"enabled": true, "stores": [...], ...},
    "rules":     {"enabled": true},
    "setup":     {"enabled": true, "snapshot_dir": "~/code/ai-setup", "memory": true}
  }

Each feature reads only its own section and supplies its defaults. A section that is missing falls
back to the pre-0.2 per-feature file (hindsight.json, setup.json) in the same folder, so upgrading
needs no manual step; the next save writes the section into config.json and leaves the old file alone.
AI_TOOLKIT_CONFIG points at a different config.json (tests, experiments).
"""
import copy
import os

from . import paths
from .jsonio import read_json, write_json_atomic

LEGACY_FILES = {"hindsight": "hindsight.json", "setup": "setup.json"}


def path():
    return os.path.expanduser(os.environ.get("AI_TOOLKIT_CONFIG") or paths.config_dir("config.json"))


def _all():
    data = read_json(path(), {})
    return data if isinstance(data, dict) else {}


def section_source(name):
    """The file a feature's settings currently come from (for status output)."""
    if name in _all():
        return path()
    legacy = LEGACY_FILES.get(name)
    if legacy and os.path.exists(os.path.join(os.path.dirname(path()), legacy)):
        return os.path.join(os.path.dirname(path()), legacy)
    return path()


def load(name, defaults=None):
    """defaults, overlaid with the feature's saved section. Always has an "enabled" key."""
    out = copy.deepcopy(defaults or {})
    out.setdefault("enabled", True)
    data = _all()
    saved = data.get(name)
    if saved is None and name in LEGACY_FILES:
        saved = read_json(os.path.join(os.path.dirname(path()), LEGACY_FILES[name]), None)
    if isinstance(saved, dict):
        out.update(saved)
    return out


def save(name, section):
    data = _all()
    data[name] = section
    write_json_atomic(path(), data)


def enabled(name):
    return bool(load(name).get("enabled", True))
