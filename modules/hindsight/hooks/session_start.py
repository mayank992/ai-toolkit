#!/usr/bin/env python3
"""SessionStart hook: inject the lessons relevant to this repo / languages.

Emits additionalContext for Claude and a one-line systemMessage for the developer.
Logs session + inject events for measurement. Always exits 0.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))


def main():
    from common import disabled, load_config, read_hook_input, repo_info, route_store
    if disabled():
        return
    data = read_hook_input()
    cfg = load_config()
    info = repo_info(data.get("cwd"))
    from store import is_initialized
    from curate import rank_cache_path
    from inject import render, select
    selected = select(cfg, info, is_initialized, rank_cache_path())
    sid = data.get("session_id", "")
    home = route_store(cfg, info["remote"])
    if is_initialized(home):
        import events as E
        E.emit(home, "session", phase="start", session_id=sid, repo=info["repo"], langs=info["langs"],
               source=data.get("source", ""))
        if selected:
            E.emit(home, "inject", session_id=sid, repo=info["repo"], langs=info["langs"],
                   ids=[l.id for _, l, _ in selected])
    if not selected:
        return
    n_new = _unreviewed(cfg, is_initialized)
    msg = "hindsight: %d lesson%s loaded" % (len(selected), "" if len(selected) == 1 else "s")
    if n_new:
        msg += " · %d newly promoted — run `hs review`" % n_new
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": render(selected)},
        "systemMessage": msg,
    }))


def _unreviewed(cfg, is_initialized):
    """Active lessons promoted automatically that the developer hasn't reviewed (cheap: reads a cache)."""
    from common import read_json, state_dir
    cache = read_json(os.path.join(state_dir(), "unreviewed.json"), {})
    return sum(len(v) for k, v in cache.items() if any(s["name"] == k and is_initialized(s) for s in cfg["stores"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            from common import log
            log("session_start error: %r" % e)
        except Exception:
            pass
    sys.exit(0)
