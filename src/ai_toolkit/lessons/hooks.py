"""lessons's Claude Code hooks. hooks/hooks.json runs each as `hooks/run.py lessons.<name>`.

core.hookrun supplies the payload, the disable switches, error logging and the always-exit-0 rule,
so each function here only does its job.

  capture_prompt      UserPromptSubmit  queue prompts that look like corrections
  capture_transcript  Stop              queue tool uses the developer rejected
  session_end         SessionEnd        record the session, start distill in the background
  session_start       SessionStart      inject the lessons relevant to this repo
"""
import json
import os
import re
import subprocess
import sys

from . import events as E
from .config import env as _env
from .config import load_config, log, offsets_path, queue_path, route_store, state_dir
from ..core.clock import now_ts
from ..core.gitutil import repo_info
from ..core.jsonio import locked, read_json, read_jsonl, write_json_atomic
from .store import is_initialized

FEEDBACK_RX = re.compile(r"the user said:\s*(.*?)(?:\n\s*\nNote:|\Z)", re.S | re.I)
WATCHED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}
MAX_FEEDBACK = 200
MIN_RESEND_CHARS = 20  # shorter prompts ("yes", "continue") are never a request sent again
MAX_EDITED = 500


# ---------- UserPromptSubmit ----------

def capture_prompt(data):
    """Store the redacted correction clause (never the whole prompt) plus, unless `capture_context` is
    off, a short redacted summary of the agent turn being corrected (local queue only). Feedback right
    after the agent edited files is captured at a lower detector threshold."""
    from .queue import enqueue
    from .turn import load_entries, resend, turn_context
    from .detect import FOLLOWUP_THRESHOLD, THRESHOLD, detect
    prompt = data.get("prompt", "")
    path = data.get("transcript_path") or ""
    entries = None
    if len(prompt) >= MIN_RESEND_CHARS and not prompt.lstrip().startswith("/") and os.path.exists(path):
        entries = load_entries(path)
        edit = resend(entries, prompt)
        if edit:
            return _capture_resend(data, prompt, entries, edit)
    hit = detect(prompt, threshold=FOLLOWUP_THRESHOLD)
    if not hit:
        return
    if entries is None and os.path.exists(path):
        entries = load_entries(path)
    ctx = turn_context(entries, prompt) if entries else None
    after_edit = bool(ctx and ctx["edited"])
    if hit["score"] < THRESHOLD and not after_edit:
        return
    extra = {"signals": hit["signals"], "score": hit["score"], "after_edit": after_edit}
    if ctx and load_config().get("capture_context", True):
        extra["context"] = ctx
    rec = enqueue("prompt", data.get("session_id"), data.get("cwd"), hit["clause"], **extra)
    if rec:
        log("captured prompt %s signals=%s after_edit=%s" % (rec["id"], ",".join(hit["signals"]), after_edit))


def _capture_resend(data, prompt, entries, edit):
    """The developer sent their last request again with something added. Queue the addition, and
    forget the tool calls they rejected on the way: stopping the agent to rephrase isn't a pushback."""
    from .queue import enqueue
    from .turn import turn_context
    extra = {"signals": ["resend"], "resend": True}
    ctx = turn_context(entries, prompt)
    if ctx and load_config().get("capture_context", True):
        extra["context"] = ctx
    rec = enqueue("prompt", data.get("session_id"), data.get("cwd"), edit["added"], **extra)
    dropped = _forget_rejections(edit["rejected_ids"])
    if rec:
        log("captured prompt %s signals=resend rejections_dropped=%d" % (rec["id"], dropped))


def _edited_path():
    return os.path.join(state_dir(), "edited_rejections.json")


def _forget_rejections(ids):
    """Remember tool-call ids so the Stop hook skips them, and drop any it already queued."""
    if not ids:
        return 0
    ep = _edited_path()
    with locked(ep):
        known = read_json(ep, [])
        write_json_atomic(ep, (known + [i for i in ids if i not in known])[-MAX_EDITED:])
    from .distill import _drop_from_queue
    queued = [m["id"] for m in read_jsonl(queue_path())
              if m.get("kind") == "rejected_tool" and not m.get("clause") and m.get("tool_use_id") in ids]
    if queued:
        _drop_from_queue(queue_path(), set(queued))
    return len(queued)


# ---------- Stop ----------

def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def scan_rejections(path, start):
    """([(tool_use_id, tool_name, file_ext, summary, feedback)], new_offset) for rejections after `start`.

    Reads only whole lines, so a line still being written is picked up next time."""
    from .turn import REJECT_PREFIX, action_summary
    tool_uses = {}
    found = []
    with open(path, "rb") as f:
        f.seek(start)
        while True:
            line = f.readline()
            if not line or not line.endswith(b"\n"):
                break
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


def capture_transcript(data):
    """Incrementally scan the transcript for rejected tool uses. Keeps a per-transcript byte offset so
    each turn only reads new lines. Records the tool name, file extension, a one-line summary of the
    rejected call and the developer's typed feedback, all redacted. Never the diff."""
    path = data.get("transcript_path") or ""
    if not path or not os.path.exists(path):
        return
    op = offsets_path()
    with locked(op):
        offsets = read_json(op, {})
        start = int(offsets.get(path, 0))
        if start > os.path.getsize(path):
            start = 0  # transcript rewritten
        found, new_off = scan_rejections(path, start)
        offsets[path] = new_off
        if len(offsets) > 200:  # prune transcripts that no longer exist
            offsets = {k: v for k, v in offsets.items() if os.path.exists(k)}
        write_json_atomic(op, offsets)
    found = [x for x in found if not x[1] or x[1] in WATCHED_TOOLS]
    if found:
        edited = set(read_json(_edited_path(), []))  # rejected only so the request could be rephrased
        found = [x for x in found if x[4] or x[0] not in edited]
    if not found:
        return
    from .queue import enqueue
    ctx = None
    with_context = load_config().get("capture_context", True)
    if with_context:
        from .turn import previous_turn
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


# ---------- SessionEnd ----------

def session_end(data):
    """Record the session end, then distill+curate in a detached background process. Returns at once;
    the distill job logs to lessons.log in the state folder."""
    cfg = load_config()
    info = repo_info(data.get("cwd"))
    home = route_store(cfg, info["remote"])
    if is_initialized(home):
        E.emit(home, "session", phase="end", session_id=data.get("session_id", ""), repo=info["repo"],
               langs=info["langs"], reason=data.get("reason", ""))
    if not _distill_due() or _env("NO_BACKGROUND") == "1":
        return
    src = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = dict(os.environ, AI_TOOLKIT_DISABLE="1",
               PYTHONPATH=os.pathsep.join(p for p in (src, os.environ.get("PYTHONPATH", "")) if p))
    out = open(os.path.join(state_dir(), "distill.out"), "a")
    subprocess.Popen([sys.executable, "-m", "ai_toolkit", "lessons", "distill", "--quiet"],
                     stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True, env=env,
                     cwd=state_dir())


IDLE_DISTILL_EVERY = 86400  # with nothing queued, still curate (retire, hand edits) once a day


def _distill_due():
    """True when there are queued moments, or the last background run is more than a day old. Headless
    sessions end by the hundred with an empty queue; starting a process for each one is pure waste."""
    stamp = os.path.join(state_dir(), "distill_started.json")
    qp = queue_path()
    queued = os.path.exists(qp) and os.path.getsize(qp) > 0
    now = now_ts()
    if not queued and now - float(read_json(stamp, {}).get("ts", 0)) < IDLE_DISTILL_EVERY:
        return False
    write_json_atomic(stamp, {"ts": now})
    return True


# ---------- SessionStart ----------

def session_start(data):
    """Inject the lessons relevant to this repo / languages. Emits additionalContext for Claude and a
    one-line systemMessage for the developer, and logs session + inject events for measurement."""
    from .curate import rank_cache_path
    from .inject import render, select
    cfg = load_config()
    info = repo_info(data.get("cwd"))
    selected = select(cfg, info, is_initialized, rank_cache_path())
    sid = data.get("session_id", "")
    home = route_store(cfg, info["remote"])
    if is_initialized(home):
        E.emit(home, "session", phase="start", session_id=sid, repo=info["repo"], langs=info["langs"],
               source=data.get("source", ""))
        if selected:
            E.emit(home, "inject", session_id=sid, repo=info["repo"], langs=info["langs"],
                   ids=[l.id for _, l, _ in selected])
    if not selected:
        return
    n_new = _unreviewed(cfg)
    msg = "ai-toolkit: %d lesson%s loaded" % (len(selected), "" if len(selected) == 1 else "s")
    if n_new:
        msg += " · %d newly promoted — run `hs review`" % n_new
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": render(selected)},
        "systemMessage": msg,
    }))


def _unreviewed(cfg):
    """Active lessons promoted automatically that the developer hasn't reviewed (cheap: reads a cache)."""
    cache = read_json(os.path.join(state_dir(), "unreviewed.json"), {})
    return sum(len(v) for k, v in cache.items() if any(s["name"] == k and is_initialized(s) for s in cfg["stores"]))
