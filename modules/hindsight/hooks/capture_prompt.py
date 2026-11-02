#!/usr/bin/env python3
"""UserPromptSubmit hook: queue prompts that look like corrections.

Stores the redacted correction clause (never the whole prompt) plus, unless `capture_context` is
off, a short redacted summary of the agent turn being corrected (local queue only). Feedback right
after the agent edited files is captured at a lower detector threshold. Always exits 0.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))


def main():
    from common import disabled, log, read_hook_input
    if disabled():
        return
    data = read_hook_input()
    prompt = data.get("prompt", "")
    from detect import FOLLOWUP_THRESHOLD, THRESHOLD, detect
    hit = detect(prompt, threshold=FOLLOWUP_THRESHOLD)
    if not hit:
        return
    from context import previous_turn
    ctx = previous_turn(data.get("transcript_path"), prompt)
    after_edit = bool(ctx and ctx["edited"])
    if hit["score"] < THRESHOLD and not after_edit:
        return
    from capture import enqueue
    from common import load_config
    extra = {"signals": hit["signals"], "score": hit["score"], "after_edit": after_edit}
    if ctx and load_config().get("capture_context", True):
        extra["context"] = ctx
    rec = enqueue("prompt", data.get("session_id"), data.get("cwd"), hit["clause"], **extra)
    if rec:
        log("captured prompt %s signals=%s after_edit=%s" % (rec["id"], ",".join(hit["signals"]), after_edit))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the user's session
        try:
            from common import log
            log("capture_prompt error: %r" % e)
        except Exception:
            pass
    sys.exit(0)
