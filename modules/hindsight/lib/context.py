"""What the agent did right before a pushback: the request, its actions, and its reply.

Read from the tail of the Claude Code transcript so distill can tell *why* the developer pushed
back, not just what they typed. Everything is redacted and truncated, and it only ever goes to
the local queue (never a store): distill turns it into an abstract `issue` / `why` and drops it.
"""
import json
import os

from redact import redact

TAIL_BYTES = 512 * 1024
MAX_REQUEST = 300
MAX_REPLY = 300
MAX_ACTIONS = 8
MAX_CMD = 80
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
REJECT_PREFIX = "The user doesn't want to proceed with this tool use"
# User-role entries that are not something the developer typed.
_NOT_TYPED = ("<task-notification>", "<command-", "<local-command", "<system-reminder>", "Caveat:",
              "[Request interrupted")


def _norm(s):
    return " ".join((s or "").split()).lower()


def _clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def typed_text(entry):
    """The developer's typed text for a user entry, or None if it isn't a typed prompt."""
    if entry.get("isMeta") or entry.get("isSidechain"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    else:
        return None
    text = text.strip()
    if not text or text.startswith(_NOT_TYPED):
        return None
    return text


def action_summary(block):
    name = block.get("name", "") or "?"
    inp = block.get("input") or {}
    path = inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""
    if path:
        return "%s %s" % (name, os.path.basename(path))
    if name == "Bash" and inp.get("command"):
        return "Bash: %s" % _clip(inp["command"], MAX_CMD)
    return name


def load_entries(path, tail_bytes=TAIL_BYTES):
    """User and assistant entries of a transcript; only the last `tail_bytes` unless it is None."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if tail_bytes is not None and size > tail_bytes:
            f.seek(size - tail_bytes)
            f.readline()  # drop the partial first line
        data = f.read()
    out = []
    for line in data.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("type") in ("user", "assistant"):
            out.append(d)
    return out


def _turns(entries):
    """[{request, actions, reply}] — one per typed prompt, with what the agent did after it."""
    turns = []
    for e in entries:
        if e.get("isSidechain"):
            continue
        if e["type"] == "user":
            text = typed_text(e)
            if text is not None:
                turns.append({"request": text, "actions": [], "reply": ""})
            continue
        if not turns:
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                turns[-1]["actions"].append(action_summary(b))
            elif b.get("type") == "text" and b.get("text", "").strip():
                turns[-1]["reply"] = b["text"]  # keep the last thing the agent said
    return turns


def previous_turn(transcript_path, current_prompt=None):
    """Context for the agent turn the developer is reacting to, or None.

    At UserPromptSubmit the current prompt may already be in the transcript; it is skipped so the
    result describes the turn *before* it. At Stop (current_prompt=None) it is the turn just ended.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    return turn_context(load_entries(transcript_path), current_prompt)


def turn_context(entries, current_prompt=None):
    """Context for the last agent turn in `entries` (see previous_turn), or None."""
    turns = _turns(entries)
    if current_prompt:
        cur = _norm(current_prompt)
        while turns and _norm(turns[-1]["request"]) == cur:
            turns.pop()
    if not turns:
        return None
    t = turns[-1]
    actions = t["actions"]
    edited = any(a.split(" ", 1)[0] in EDIT_TOOLS for a in actions)
    if len(actions) > MAX_ACTIONS:  # keep the latest: they are what the developer reacted to
        actions = ["… %d earlier" % (len(actions) - MAX_ACTIONS + 1)] + actions[-(MAX_ACTIONS - 1):]
    return {
        "request": redact(_clip(t["request"], MAX_REQUEST)),
        "actions": [redact(a) for a in actions],
        "reply": redact(_clip(t["reply"], MAX_REPLY)),
        "edited": edited,
    }
