"""Distill queued correction moments into candidate lessons, then curate.

Runs detached from the SessionEnd hook (or `hs distill`). Safe to run concurrently:
a non-blocking lock makes extra runs exit immediately.
"""
import fcntl
import os
import re

import events as E
import llm
from common import (iso, load_config, locked, log, now_ts, queue_path, read_jsonl, state_dir)
from curate import curate, remember_hashes
from lessons_md import Lesson, jaccard, load_store, save_store, tokens
from store import commit, init_store, is_initialized

MERGE_THRESHOLD = 0.6
MIN_CONFIDENCE = 0.5
FOLLOWUP_WINDOW_S = 600

SYSTEM = """You turn a developer's corrections of an AI coding assistant into durable lessons.

Input: `moments` (corrections captured in one repo) and `existing` lessons for that repo/scope.
Moment kinds: "prompt" (a correction sentence the developer typed), "rejected_tool" (developer rejected
an Edit/Write/Bash call; `clause` is their typed reason, may be empty), "explicit" (developer stated a
lesson directly).

For EVERY moment decide:
- noise=true if it is not actually correcting the assistant's behaviour (e.g. the developer is
  describing their own code, asking a question, or correcting a fact unique to this one task).
- match = id of an existing lesson that this moment repeats (same underlying rule), else null.
- new = key of a new lesson you propose (several moments may share one key), else null.
A rejected_tool with an empty clause usually has match=null,new=null,noise=false.

New lessons must be: one imperative sentence <=120 chars; general enough to apply in future sessions
of this repo; specific enough to act on; contain no secrets, names, emails, file contents or one-off
task details. Prefer scope "repo"; use "global" only for clearly personal style preferences that
apply everywhere; use "lang:<language>" for language-specific conventions (languages: see `langs`).
keywords: 1-5 lowercase words that signal when it applies. files: optional globs (e.g. "package.json").
confidence: 0..1 that this is a real, reusable preference.

Output ONLY JSON:
{"moments":[{"id":"...","noise":false,"match":null,"new":"k1"}],
 "lessons":[{"key":"k1","text":"...","scope":"repo","keywords":["..."],"files":[],"confidence":0.9}]}"""

_LEAD = re.compile(r"^\s*(no|nope|nah|wrong|stop|actually|wait)\b[\s,.!:;—-]*", re.I)
_USE_INSTEAD_OF = re.compile(r"\b(use|prefer|go with|switch to)\s+(.{1,40}?)\s+instead\s+of\s+(.{1,40}?)(?:[.,;!?]|$)", re.I)
_USE_INSTEAD = re.compile(r"\b(use|prefer|go with|switch to)\s+(.{1,40}?)\s+instead\b", re.I)
_DONT = re.compile(r"\b(don'?t|do not|never|stop)\s+(.{3,100}?)(?:[.;!?]|$)", re.I)


def rule_lesson(m):
    """Heuristic fallback: return lesson text or None."""
    c = (m.get("clause") or "").strip()
    if not c:
        return None
    if m["kind"] == "explicit":
        text = c
    else:
        mm = _USE_INSTEAD_OF.search(c)
        if mm:
            text = "Use %s instead of %s" % (mm.group(2).strip(), mm.group(3).strip())
        else:
            mm = _USE_INSTEAD.search(c)
            if mm:
                text = "Use %s" % mm.group(2).strip()
            else:
                mm = _DONT.search(c)
                if not mm:
                    return None
                verb = mm.group(1).lower()
                text = ("Never " if verb == "never" else "Don't ") + mm.group(2).strip()
    text = _LEAD.sub("", text).strip().rstrip(".")
    return (text[:1].upper() + text[1:])[:120] if text else None


def _premerge(moments):
    """A rejected tool use with no typed reason, followed by a correction prompt in the same
    session shortly after, is ONE pushback: drop the rejection, flag the prompt."""
    out = []
    for i, m in enumerate(moments):
        if m["kind"] == "rejected_tool" and not m.get("clause"):
            nxt = [n for n in moments[i + 1:] if n.get("session_id") == m.get("session_id")]
            if nxt and nxt[0]["kind"] == "prompt":
                try:
                    from stats import parse_ts
                    if parse_ts(nxt[0]["ts"]) - parse_ts(m["ts"]) <= FOLLOWUP_WINDOW_S:
                        nxt[0]["after_rejection"] = m.get("tool")
                        continue
                except ValueError:
                    pass
        out.append(m)
    return out


def _relevant_existing(lessons, repo, langs):
    scopes = {"global"} | ({"repo:" + repo} if repo else set()) | {"lang:" + l for l in langs}
    return [l for l in lessons.values() if l.status in ("candidate", "active") and l.scope in scopes]


def _norm_scope(scope, repo, langs):
    scope = (scope or "repo").strip()
    if scope == "repo" or scope.startswith("repo:"):
        return "repo:" + repo if repo else "global"
    if scope.startswith("lang:"):
        lang = scope[5:].strip().lower()
        return "lang:" + lang if lang else ("repo:" + repo if repo else "global")
    return "global"


def _plan_group(store, moments, lessons, repo, langs, cfg, use_llm):
    """Return list of decisions: (moment, noise, lesson_id_or_None, new_lesson_or_None, source)."""
    existing = _relevant_existing(lessons, repo, langs)
    res = None
    if use_llm:
        payload = {
            "repo": repo or "(no repo)", "langs": langs,
            "moments": [{k: m.get(k) for k in ("id", "kind", "clause", "tool", "file_ext", "signals", "after_rejection")
                         if m.get(k) not in (None, "", [])} for m in moments],
            "existing": [{"id": l.id, "scope": l.scope, "status": l.status, "text": l.text} for l in existing],
        }
        res = llm.call(SYSTEM, payload, model=cfg.get("distill_model", "haiku"))
    decisions = []
    if isinstance(res, dict) and isinstance(res.get("moments"), list):
        new_by_key = {}
        for nl in res.get("lessons") or []:
            if not isinstance(nl, dict) or not isinstance(nl.get("text"), str) or not nl.get("key"):
                continue
            text = nl["text"].strip()[:160]
            try:
                conf = float(nl.get("confidence", 1))
            except (TypeError, ValueError):
                conf = 0.0
            if not text or conf < MIN_CONFIDENCE:
                continue
            new_by_key[nl["key"]] = {"text": text, "scope": nl.get("scope"),
                                     "keywords": [str(k).lower()[:30] for k in (nl.get("keywords") or [])][:5],
                                     "files": [str(f)[:60] for f in (nl.get("files") or [])][:5]}
        by_id = {d.get("id"): d for d in res["moments"] if isinstance(d, dict)}
        valid_ids = {l.id for l in existing}
        for m in moments:
            d = by_id.get(m["id"], {})
            match = d.get("match") if d.get("match") in valid_ids else None
            new = new_by_key.get(d.get("new")) if not match else None
            if m["kind"] == "explicit" and not match and not new:
                new = {"text": m["clause"][:120], "scope": "repo", "keywords": [], "files": []}
            decisions.append((m, bool(d.get("noise")) and m["kind"] != "explicit", match, new, "llm"))
        return decisions
    if use_llm:
        log("distill: LLM unavailable, using rules for %d moment(s)" % len(moments))
    for m in moments:
        text = rule_lesson(m)
        new = {"text": text, "scope": "repo", "keywords": sorted(tokens(text))[:4], "files": []} if text else None
        decisions.append((m, False, None, new, "rules"))
    return decisions


def distill(dry_run=False, use_llm=True, queue_file=None, cfg=None):
    """Process the queue. Returns dict(summary) for display/tests."""
    cfg = cfg or load_config()
    lock_f = open(os.path.join(state_dir(), "distill.run.lock"), "a")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return {"skipped": "another distill is running"}
    try:
        return _distill(cfg, dry_run, use_llm, queue_file)
    finally:
        fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()


def _distill(cfg, dry_run, use_llm, queue_file):
    qpath = queue_file or queue_path()
    moments = sorted(read_jsonl(qpath), key=lambda m: m.get("ts", ""))
    summary = {"moments": len(moments), "stores": {}, "dry_run": dry_run}
    stores = {s["name"]: s for s in cfg["stores"]}
    processed = set(m["id"] for m in moments)
    moments = _premerge(moments)
    by_store = {}
    for m in moments:
        by_store.setdefault(m.get("store") if m.get("store") in stores else
                            next(s["name"] for s in cfg["stores"] if s.get("default")), []).append(m)

    for sname, ms in by_store.items():
        store = stores[sname]
        if not is_initialized(store):
            if dry_run:
                continue
            init_store(store)
        lessons = load_store(store)
        out = summary["stores"].setdefault(sname, {"new": [], "hits": [], "noise": 0, "unattributed": 0, "curate": []})
        groups = {}
        for m in ms:
            groups.setdefault(m.get("repo") or "", []).append(m)
        for repo, gms in groups.items():
            langs = sorted({l for m in gms for l in (m.get("langs") or [])})
            for m, noise, match, new, source in _plan_group(store, gms, lessons, repo, langs, cfg, use_llm):
                lid = match
                if not noise and not lid and new:
                    scope = _norm_scope(new["scope"], repo, langs)
                    # local dedupe against anything live in the same scope
                    dup = next((l for l in lessons.values() if l.status in ("candidate", "active")
                                and l.scope == scope and jaccard(l.text, new["text"]) >= MERGE_THRESHOLD), None)
                    if dup:
                        lid = dup.id
                    else:
                        lid = Lesson.new_id(sname, new["text"], scope)
                        if lid not in lessons:
                            status = "active" if m["kind"] == "explicit" else "candidate"
                            lessons[lid] = Lesson(lid, new["text"], scope, new["keywords"], new["files"], status)
                            out["new"].append({"id": lid, "text": new["text"], "scope": scope, "status": status,
                                               "source": source})
                            if not dry_run:
                                E.emit(store, "create", lesson=lid, scope=scope, status=status,
                                       source="explicit" if m["kind"] == "explicit" else source)
                if lid and not noise and m["kind"] == "explicit" and lessons[lid].status == "candidate":
                    lessons[lid].status = "active"  # stating it explicitly is a promotion
                    if not dry_run:
                        E.emit(store, "promote", lesson=lid, by="explicit")
                if noise:
                    out["noise"] += 1
                elif lid:
                    out["hits"].append(lid)
                else:
                    out["unattributed"] += 1
                if not dry_run:
                    E.emit(store, "moment", session_id=m.get("session_id", ""), repo=m.get("repo", ""),
                           langs=m.get("langs") or [], kind=m["kind"], signals=m.get("signals") or [],
                           tool=m.get("tool", ""), noise=noise, lesson=None if noise else lid,
                           moment_ts=m.get("ts"))
        if dry_run:
            continue
        save_store(store, lessons.values())
        remember_hashes(store, lessons.values())
        commit(store, "hindsight: distill %d moment(s)" % len(ms))
        out["curate"] = curate(store, cfg, use_llm=use_llm)

    if not dry_run and queue_file is None:
        # Drop processed moments; keep any that arrived while we were working.
        with locked(qpath):
            rest = [m for m in read_jsonl(qpath) if m.get("id") not in processed]
            tmp = qpath + ".tmp"
            with open(tmp, "w") as f:
                import json
                for m in rest:
                    f.write(json.dumps(m, sort_keys=True) + "\n")
            os.replace(tmp, qpath)
    # Curate stores that had no new moments too (time-based retirement)
    if not dry_run:
        for s in cfg["stores"]:
            if s["name"] not in by_store and is_initialized(s):
                summary["stores"].setdefault(s["name"], {})["curate"] = curate(s, cfg, use_llm=use_llm)
    log("distill done: %s" % {k: (v if k != "stores" else {n: {kk: (len(vv) if isinstance(vv, list) else vv)
                                                                  for kk, vv in d.items()} for n, d in v.items()})
                              for k, v in summary.items()})
    summary["at"] = iso(now_ts())
    return summary
