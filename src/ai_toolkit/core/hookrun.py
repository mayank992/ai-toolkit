"""Run one Claude Code hook: `hooks/run.py <feature>.<hook>` (see hooks/hooks.json).

The contract every hook gets for free:
  - the hook function receives the parsed stdin payload (dict; {} when stdin isn't JSON);
  - AI_TOOLKIT_DISABLE=1, or "enabled": false in the feature's config section, turns it into a no-op;
  - any exception is logged to the feature's state folder (<feature>.log) and swallowed;
  - the process always exits 0, so a bug here never blocks or breaks a Claude Code session.
"""
import json
import os
import sys

from . import config, paths
from .clock import iso


def disabled():
    # HINDSIGHT_DISABLE is the pre-0.2 name; distill sets the new one for its own `claude -p` call.
    return os.environ.get("AI_TOOLKIT_DISABLE") == "1" or os.environ.get("HINDSIGHT_DISABLE") == "1"


def log(feature, msg):
    try:
        with open(paths.state_dir(feature, "%s.log" % feature), "a") as f:
            f.write("%s %s\n" % (iso(), msg))
    except OSError:
        pass


def read_payload(stream=None):
    try:
        data = json.load(stream or sys.stdin)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def main(argv):
    target = argv[0] if argv else ""
    feature, _, hook = target.partition(".")
    try:
        if not feature or not hook:
            raise ValueError("usage: run.py <feature>.<hook>, got %r" % target)
        if disabled() or not config.enabled(feature):
            return 0
        module = __import__("ai_toolkit.%s.hooks" % feature, fromlist=[hook])  # not importlib: keep startup lean
        fn = getattr(module, hook)
        fn(read_payload())
    except Exception as e:  # never break the user's session
        log(feature or "ai-toolkit", "%s error: %r" % (hook or target, e))
    return 0
