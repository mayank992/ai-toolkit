"""Re-derive queued moments from their transcripts with the current capture rules (`hs backfill`).

Idempotent: a moment already matching what capture would record today is left alone. Moments whose
transcript is gone are kept as they are. Only rejections that aren't real rejections are dropped;
repeats across sessions stay, since distill promotes on them.
"""
import glob
import json
import os

from common import load_config, locked, queue_path, read_jsonl
from context import REJECT_PREFIX, action_summary, load_entries, turn_context, typed_text
from redact import redact


def find_transcript(session_id, projects_dir=None):
    root = projects_dir or os.path.expanduser("~/.claude/projects")
    hits = glob.glob(os.path.join(root, "*", "%s.jsonl" % session_id)) if session_id else []
    return hits[0] if hits else None


def _blocks(entry):
    content = (entry.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _result_text(block):
    c = block.get("content")
    if isinstance(c, list):
        c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict))
    return (c or "").lstrip() if isinstance(c, str) else ""


def _refine_rejection(m, entries, with_context):
    tid = m.get("tool_use_id")
    use, result_at = None, None
    for i, e in enumerate(entries):
        for b in _blocks(e):
            if b.get("type") == "tool_use" and b.get("id") == tid:
                use = b
            elif b.get("type") == "tool_result" and b.get("tool_use_id") == tid:
                result_at = (i, b)
    if result_at is None:
        return "keep", m, "tool call not in transcript"
    i, res = result_at
    if not (res.get("is_error") and _result_text(res).startswith(REJECT_PREFIX)):
        return "drop", None, "not a rejection (tool output quoting the rejection message)"
    out = dict(m)
    if with_context:
        if use:
            out["rejected"] = redact(action_summary(use))
        ctx = turn_context(entries[: i + 1])
        if ctx:
            out["context"] = ctx
    return ("update" if out != m else "same"), out, ""


def _refine_prompt(m, entries, with_context):
    from detect import FOLLOWUP_THRESHOLD, detect
    at = None
    for i, e in enumerate(entries):
        if e.get("type") != "user":
            continue
        text = typed_text(e)
        hit = detect(text, threshold=FOLLOWUP_THRESHOLD) if text else None
        if hit and redact(hit["clause"]) == m.get("clause"):
            at = i
    if at is None:
        return "keep", m, "prompt not found in transcript"
    out = dict(m)
    ctx = turn_context(entries[:at])
    if ctx and with_context:
        out["context"] = ctx
    out["after_edit"] = bool(ctx and ctx["edited"])
    return ("update" if out != m else "same"), out, ""


def refine(m, entries, with_context=True):
    """(action, moment_or_None, reason) for one queued moment; action is same|update|keep|drop."""
    if m.get("kind") == "rejected_tool":
        return _refine_rejection(m, entries, with_context)
    if m.get("kind") == "prompt":
        return _refine_prompt(m, entries, with_context)
    return "same", m, ""


class Busy(Exception):
    pass


def backfill(dry_run=False, projects_dir=None):
    """Refine every queued moment. Returns [(moment_before, action, moment_after, reason)].

    Holds distill's run lock: a distill already working from a snapshot of the queue would
    otherwise distill the unrefined moments and then drop the refined ones by id."""
    from distill import run_lock
    with run_lock() as got:
        if not got:
            raise Busy("distill is running; try again when it finishes")
        return _backfill(dry_run, projects_dir)


def _backfill(dry_run, projects_dir):
    with_context = load_config().get("capture_context", True)
    qpath = queue_path()
    cache = {}
    plan = []
    for m in read_jsonl(qpath):
        sid = m.get("session_id", "")
        if sid not in cache:
            p = find_transcript(sid, projects_dir)
            cache[sid] = load_entries(p, tail_bytes=None) if p else None
        if cache[sid] is None:
            plan.append((m, "keep", m, "transcript not found"))
            continue
        action, new, reason = refine(m, cache[sid], with_context)
        plan.append((m, action, new, reason))
    if dry_run:
        return plan
    by_id = {m["id"]: (action, new) for m, action, new, _ in plan}
    with locked(qpath):
        rest = []
        for m in read_jsonl(qpath):
            action, new = by_id.get(m.get("id"), ("same", m))
            if action != "drop":
                rest.append(new if action == "update" else m)
        tmp = qpath + ".tmp"
        with open(tmp, "w") as f:
            for m in rest:
                f.write(json.dumps(m, sort_keys=True) + "\n")
        os.replace(tmp, qpath)
    return plan
