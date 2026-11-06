#!/usr/bin/env python3
"""Stop hook: incrementally scan the transcript for rejected tool uses.

Keeps a per-transcript byte offset so each turn only reads new lines.
Records the tool name, file extension, a one-line summary of the rejected call (file basename or
the command cut to 80 chars, as in the agent-turn context) and the developer's typed feedback, all
redacted. Never the diff. Always exits 0.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

FEEDBACK_RX = re.compile(r"the user said:\s*(.*?)(?:\n\s*\nNote:|\Z)", re.S | re.I)
WATCHED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}
MAX_FEEDBACK = 200


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def scan(path, start):
    """Return ([(tool_use_id, tool_name, file_ext, summary, feedback)], new_offset) for rejections after `start`."""
    from context import REJECT_PREFIX, action_summary
    tool_uses = {}
    found = []
    with open(path, "rb") as f:
        f.seek(start)
        while True:
            line = f.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                break  # partial line still being written; re-read next time
            start = f.tell()
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            if d.get("type") == "assistant":
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        fp = inp.get("file_path") or inp.get("notebook_path") or ""
                        tool_uses[b.get("id")] = (b.get("name", ""), os.path.splitext(fp)[1].lstrip(".").lower(),
                                                  action_summary(b))
            elif d.get("type") == "user":
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error")):
                        continue
                    # A successful result can contain the marker too, e.g. when the agent reads this file.
                    txt = _text(b.get("content")).lstrip()
                    if not txt.startswith(REJECT_PREFIX):
                        continue
                    tid = b.get("tool_use_id", "")
                    name, ext, summary = tool_uses.get(tid, ("", "", ""))
                    m = FEEDBACK_RX.search(txt)
                    fb = m.group(1).strip()[:MAX_FEEDBACK] if m else ""
                    found.append((tid, name, ext, summary, fb))
    return found, start


def main():
    from common import disabled, locked, log, offsets_path, read_hook_input, read_json, write_json_atomic
    if disabled():
        return
    data = read_hook_input()
    path = data.get("transcript_path") or ""
    if not path or not os.path.exists(path):
        return
    op = offsets_path()
    with locked(op):
        offsets = read_json(op, {})
        start = int(offsets.get(path, 0))
        if start > os.path.getsize(path):
            start = 0  # transcript rewritten
        found, new_off = scan(path, start)
        offsets[path] = new_off
        if len(offsets) > 200:  # prune transcripts that no longer exist
            offsets = {k: v for k, v in offsets.items() if os.path.exists(k)}
        write_json_atomic(op, offsets)
    found = [x for x in found if not x[1] or x[1] in WATCHED_TOOLS]
    if not found:
        return
    from capture import enqueue
    from common import load_config
    ctx = None
    with_context = load_config().get("capture_context", True)
    if with_context:
        from context import previous_turn
        ctx = previous_turn(path)
    for tid, name, ext, summary, fb in found:
        extra = {"tool": name or "unknown", "file_ext": ext, "tool_use_id": tid}
        if with_context:
            extra["rejected"] = summary
        if ctx:
            extra["context"] = ctx
        rec = enqueue("rejected_tool", data.get("session_id"), data.get("cwd"), fb, **extra)
        if rec:
            log("captured rejected_tool %s tool=%s feedback=%s" % (rec["id"], name, bool(fb)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            from common import log
            log("capture_transcript error: %r" % e)
        except Exception:
            pass
    sys.exit(0)
