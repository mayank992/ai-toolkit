"""Read-only view of the whole pipeline for `hs ui`: one JSON snapshot, rebuilt per request."""
import json
import os

import events as E
import measure
from common import MODULE_ROOT, iso, log_path, now_ts, queue_path, read_json, read_jsonl
from lessons_md import load_store
from store import is_initialized

STALL_AFTER_S = 24 * 3600
MAX_EVENTS = 300
MAX_LOG_LINES = 120
MAX_PROCESSED = 200
MAX_CONTEXT_REPOS = 6

# Pipeline order and the hook events each stage depends on.
STAGES = (
    ("capture", "Capture", ("UserPromptSubmit", "Stop")),
    ("queue", "Queue", ()),
    ("distill", "Distill", ("SessionEnd",)),
    ("curate", "Curate", ("SessionEnd",)),
    ("store", "Store", ()),
    ("inject", "Inject", ("SessionStart",)),
)


def settings_path():
    return os.path.expanduser("~/.claude/settings.json")


def hook_registrations():
    """[{step, event, script, registered}] for every hook in module.json, checked against settings.json."""
    settings = read_json(settings_path(), {})
    cmds = [h.get("command", "") for evs in (settings.get("hooks") or {}).values()
            for g in evs for h in g.get("hooks", [])]
    manifest = read_json(os.path.join(MODULE_ROOT, "module.json"), {})
    out = []
    for h in manifest.get("hooks", []):
        script = os.path.basename(h["script"])
        out.append({"step": h["step"], "event": h["event"], "script": script,
                    "registered": any(script in c for c in cmds)})
    return out


def _log_lines():
    p = log_path()
    if not os.path.exists(p):
        return []
    with open(p, errors="replace") as f:
        return [l.rstrip("\n") for l in f.readlines()[-2000:]]


def _last_log(lines, needle):
    for l in reversed(lines):
        if needle in l:
            return l.split(" ", 1)[0]
    return None


def _age_s(ts, now):
    if not ts:
        return None
    from stats import parse_ts
    return now - parse_ts(ts)


def _processed(evs, lessons_by_id):
    """Distilled moments, newest first, each with the lesson it fed (merges followed) or noise."""
    resolve = E.alias_map(evs)
    out = []
    for e in reversed(evs):
        if e["t"] != "moment":
            continue
        lid = resolve(e["lesson"]) if e.get("lesson") else None
        l = lessons_by_id.get(lid) if lid else None
        out.append({"ts": e["ts"], "store": e["_store"], "session_id": e.get("session_id", ""),
                    "repo": e.get("repo", ""), "kind": e.get("kind", ""), "signals": e.get("signals") or [],
                    "tool": e.get("tool", ""), "noise": bool(e.get("noise")), "lesson": lid,
                    "lesson_text": l["text"] if l else "", "lesson_status": l["status"] if l else ""})
        if len(out) >= MAX_PROCESSED:
            break
    return out


def _in_context(cfg, evs, queue):
    """What SessionStart would inject right now for each recently seen repo, and when it last did."""
    from curate import rank_cache_path
    from inject import render, select
    repos = {}
    for r in [(m["repo"], m.get("langs") or [], m["ts"]) for m in queue] + \
             [(e.get("repo", ""), e.get("langs") or [], e["ts"]) for e in evs if e["t"] == "session"]:
        if r[0] and (r[0] not in repos or r[2] > repos[r[0]][1]):
            repos[r[0]] = (r[1], r[2])
    last_inject = {}
    for e in evs:
        if e["t"] == "inject":
            last_inject[e.get("repo", "")] = {"ts": e["ts"], "ids": e.get("ids") or []}
    out = []
    for repo, (langs, seen) in sorted(repos.items(), key=lambda kv: kv[1][1], reverse=True)[:MAX_CONTEXT_REPOS]:
        remote = "" if repo.startswith("local:") else repo
        sel = select(cfg, {"repo": repo, "root": "", "remote": remote, "langs": langs}, is_initialized,
                     rank_cache_path())
        out.append({"repo": repo, "langs": langs, "last_seen": seen,
                    "lessons": [{"id": l.id, "text": l.text, "scope": l.scope, "store": st} for st, l, _ in sel],
                    "rendered": render(sel), "last_inject": last_inject.get(repo)})
    return out


def build(cfg):
    now = now_ts()
    hooks = hook_registrations()
    on = {}
    for h in hooks:
        on[h["event"]] = on.get(h["event"], True) and h["registered"]

    queue = read_jsonl(queue_path()) if os.path.exists(queue_path()) else []
    queue.sort(key=lambda m: m.get("ts", ""), reverse=True)
    stores_live = [s for s in cfg["stores"] if is_initialized(s)]
    evs = E.load_all(stores_live)
    lines = _log_lines()

    stores = []
    counts = {"candidate": 0, "active": 0, "retired": 0, "dismissed": 0}
    for s in cfg["stores"]:
        lessons = []
        if is_initialized(s):
            for l in load_store(s).values():
                d = l.to_dict()
                d["store"] = s["name"]
                d["file"] = getattr(l, "source_file", "")
                lessons.append(d)
                counts[l.status] = counts.get(l.status, 0) + 1
        stores.append({"name": s["name"], "path": s["path"], "remote": s.get("remote", ""),
                       "match": s.get("match", []), "default": bool(s.get("default")),
                       "initialized": is_initialized(s), "lessons": lessons})

    oldest = queue[-1]["ts"] if queue else None
    last = {
        "capture": queue[0]["ts"] if queue else _last_log(lines, " captured "),
        "queue": oldest,
        "distill": _last_log(lines, " distill done"),
        "curate": _last_log(lines, " curate "),
        "store": next((e["ts"] for e in reversed(evs) if e["t"] == "create"), None),
        "inject": next((e["ts"] for e in reversed(evs) if e["t"] == "inject"), None),
    }
    metric = {
        "capture": "%d captured" % (sum(1 for e in evs if e["t"] == "moment") + len(queue)),
        "queue": "%d waiting" % len(queue),
        "distill": "%d moments processed" % sum(1 for e in evs if e["t"] == "moment"),
        "curate": "%d promoted · %d retired" % (sum(1 for e in evs if e["t"] == "promote"),
                                               sum(1 for e in evs if e["t"] == "retire")),
        "store": "%d active · %d candidate" % (counts["active"], counts["candidate"]),
        "inject": "%d sessions" % len({e.get("session_id") for e in evs if e["t"] == "inject"}),
    }
    stalled = bool(queue) and (_age_s(oldest, now) or 0) > STALL_AFTER_S

    stages = []
    for sid, label, needs in STAGES:
        missing = [ev for ev in needs if not on.get(ev, False)]
        if missing:
            health, note = "off", "hook not registered: %s (run ./install.sh)" % ", ".join(missing)
        elif sid in ("queue", "distill") and stalled:
            health, note = "stalled", "oldest moment waiting more than 24h"
        elif sid in ("queue", "distill") and queue:
            health, note = "waiting", "runs at the next SessionEnd"
        else:
            health, note = "ok", ""
        stages.append({"id": sid, "label": label, "health": health, "note": note,
                       "metric": metric[sid], "last_at": last[sid]})

    lessons_by_id = {l["id"]: l for s in stores for l in s["lessons"]}
    return {
        "generated_at": iso(now),
        "stages": stages,
        "hooks": hooks,
        "queue": queue,
        "processed": _processed(evs, lessons_by_id),
        "in_context": _in_context(cfg, evs, queue),
        "stores": stores,
        "events": list(reversed(evs[-MAX_EVENTS:])),
        "report": measure.build(cfg),
        "log": lines[-MAX_LOG_LINES:],
    }


def to_json(snap):
    return json.dumps(snap, default=list)
