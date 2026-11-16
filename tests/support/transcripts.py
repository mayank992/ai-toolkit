"""Builders for Claude Code transcript lines (JSONL), shared by capture/context/backfill tests."""
import json


def user(text, **kw):
    return dict({"type": "user", "message": {"role": "user", "content": text}}, **kw)


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def tool(name, **inp):
    return {"type": "tool_use", "id": "t-%s-%d" % (name, len(inp)), "name": name, "input": inp}


def text(t):
    return {"type": "text", "text": t}


def tool_result(tid, content="ok", is_error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": is_error}]}}


def write_transcript(path, entries):
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path
