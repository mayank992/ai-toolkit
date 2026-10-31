#!/usr/bin/env python3
"""SessionEnd hook: record the session end, then distill+curate in a detached background process.

Returns immediately; the distill job logs to ~/.local/state/hindsight/hindsight.log.
"""
import os
import subprocess
import sys

MODULE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MODULE, "lib"))


def main():
    from common import disabled, load_config, read_hook_input, repo_info, route_store, state_dir
    if disabled():
        return
    data = read_hook_input()
    cfg = load_config()
    info = repo_info(data.get("cwd"))
    from store import is_initialized
    home = route_store(cfg, info["remote"])
    if is_initialized(home):
        import events as E
        E.emit(home, "session", phase="end", session_id=data.get("session_id", ""), repo=info["repo"],
               langs=info["langs"], reason=data.get("reason", ""))
    if os.environ.get("HINDSIGHT_NO_BACKGROUND") == "1":
        return
    log = open(os.path.join(state_dir(), "distill.out"), "a")
    subprocess.Popen([sys.executable, os.path.join(MODULE, "bin", "hs"), "distill", "--quiet"],
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                     env=dict(os.environ, HINDSIGHT_DISABLE="1"), cwd=state_dir())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            from common import log
            log("session_end error: %r" % e)
        except Exception:
            pass
    sys.exit(0)
