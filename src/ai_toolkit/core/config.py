"""One config file for every feature: ~/.config/ai-toolkit/config.json.

  {
    "lessons":   {"enabled": true, "stores": [...], ...},
    "rules":     {"enabled": true},
    "setup":     {"enabled": true, "snapshot_dir": "~/code/ai-setup", "memory": true}
  }

Each feature reads only its own section and supplies its defaults. A section that is missing falls
back to the name it had before (the "hindsight" section until 0.3) and then to the pre-0.2 per-feature
file (hindsight.json, setup.json) in the same folder, so upgrading needs no manual step; the next save
writes the section into config.json under its current name and leaves the old file alone.
AI_TOOLKIT_CONFIG points at a different config.json (tests, experiments).
"""
import copy
import os

from . import paths
from .jsonio import read_json, write_json_atomic

LEGACY_FILES = {"lessons": "hindsight.json", "setup": "setup.json"}
LEGACY_SECTIONS = {"lessons": "hindsight"}  # the lessons feature was called hindsight until 0.3


def path():
    return os.path.expanduser(os.environ.get("AI_TOOLKIT_CONFIG") or paths.config_dir("config.json"))


def _all():
    data = read_json(path(), {})
    return data if isinstance(data, dict) else {}


def section_source(name):
    """The file a feature's settings currently come from (for status output)."""
    if name in _all() or LEGACY_SECTIONS.get(name) in _all():
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
    if saved is None:
        saved = data.get(LEGACY_SECTIONS.get(name))
    if saved is None and name in LEGACY_FILES:
        saved = read_json(os.path.join(os.path.dirname(path()), LEGACY_FILES[name]), None)
    if isinstance(saved, dict):
        out.update(saved)
    return out


def save(name, section):
    data = _all()
    data[name] = section
    data.pop(LEGACY_SECTIONS.get(name), None)  # one section per feature: the old name is replaced, not kept beside it
    write_json_atomic(path(), data)


def enabled(name):
    return bool(load(name).get("enabled", True))
