#!/usr/bin/env python3
"""UserPromptSubmit hook: queue prompts that look like corrections.

Stores only the redacted correction clause, never the prompt. Always exits 0.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))


def main():
    from common import disabled, log, read_hook_input
    if disabled():
        return
    data = read_hook_input()
    from detect import detect
    hit = detect(data.get("prompt", ""))
    if not hit:
        return
    from capture import enqueue
    rec = enqueue("prompt", data.get("session_id"), data.get("cwd"), hit["clause"],
                  signals=hit["signals"], score=hit["score"])
    if rec:
        log("captured prompt %s signals=%s" % (rec["id"], ",".join(hit["signals"])))


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
