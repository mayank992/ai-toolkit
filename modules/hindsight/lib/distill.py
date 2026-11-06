"""Distill queued correction moments into candidate lessons, then curate.

Runs detached from the SessionEnd hook (or `hs distill`). Safe to run concurrently:
a non-blocking lock makes extra runs exit immediately.
"""
import contextlib
import fcntl
import json
import os
import re

import events as E
import llm
from common import (default_store, iso, load_config, locked, log, now_ts, queue_path, read_jsonl, state_dir)
from curate import apply_hand_edits, curate, remember_hashes
from lessons_md import Lesson, jaccard, load_store, save_store, tokens
from redact import redact
from stats import parse_ts
from store import commit, init_store, is_initialized

MERGE_THRESHOLD = 0.6
MIN_CONFIDENCE = 0.5
MAX_WHY = 160
FOLLOWUP_WINDOW_S = 600
GLOBAL_ALIASES = ("global", "all", "everywhere", "any", "user", "personal")

SYSTEM = """You turn a developer's corrections of an AI coding assistant into durable lessons.

Input: `moments` (corrections captured in one repo) and `existing` lessons for that repo/scope.
Moment kinds: "prompt" (a correction sentence the developer typed), "rejected_tool" (developer rejected
an Edit/Write/Bash call; `rejected` is that call, `clause` their typed reason, may be empty), "explicit" (developer stated a
lesson directly). A moment may carry `context`: what the assistant had just done when the developer
pushed back — `request` (what it was asked), `actions` (its tool calls), `reply` (what it said last).
`after_edit` = the assistant had just changed files, so the correction is feedback on that work.

For EVERY moment decide:
- noise=true if it is not actually correcting the assistant's behaviour (e.g. a new request, a
  question, the developer describing their own code, or a fact unique to this one task).
- match = id of an existing lesson that this moment repeats (same underlying rule), else null.
- new = key of a new lesson you propose (several moments may share one key), else null.
A rejected_tool with an empty clause and no telling context usually has match=null,new=null,noise=false.

To propose a lesson, reason like a reviewer doing a post-mortem:
1. issue: what the assistant concretely did wrong, judged from `context` against the correction.
2. why: the general cause — the assumption, habit or missing check that led to it, i.e. why the
   developer cares. Look past the one instance: "used npm" -> "ignored the repo's package manager".
3. text: the general rule that would have prevented this whole class of mistake, not a patch for
   this one instance ("Check the lockfile and use the repo's package manager", not "Use pnpm for
   lodash").

New lessons must be: text = one imperative sentence <=120 chars; general enough to apply in future
sessions; specific enough to act on. why and issue: one short sentence each, <=120 chars, abstract
(no code, file contents, secrets, names, emails or one-off task details). Prefer scope "repo"; use
"global" only for clearly personal style preferences that apply everywhere; use "lang:<language>"
for language-specific conventions (languages: see `langs`). keywords: 1-5 lowercase words that
signal when it applies. files: optional globs (e.g. "package.json"). confidence: 0..1 that this is
a real, reusable preference.

Output ONLY JSON:
{"moments":[{"id":"...","noise":false,"match":null,"new":"k1"}],
 "lessons":[{"key":"k1","text":"...","why":"...","issue":"...","scope":"repo","keywords":["..."],
             "files":[],"confidence":0.9}]}"""

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
    """Map the LLM's scope onto one we trust. A language scope must be one detected in the repo
    (it becomes a file name), otherwise the lesson falls back to the repo scope."""
    repo_scope = "repo:" + repo if repo else "global"
    scope = (scope if isinstance(scope, str) else "repo").strip().lower()
    if scope in GLOBAL_ALIASES:
        return "global"
    if scope.startswith("lang:"):
        lang = scope[5:].strip().lower()
        return "lang:" + lang if lang in langs else repo_scope
    return repo_scope


def _short(v):
    """One redacted sentence from the LLM, or ""."""
    if not isinstance(v, str):
        return ""
    v = redact(" ".join(v.split()))
    return v if len(v) <= MAX_WHY else v[: MAX_WHY - 1] + "…"


def _plan_group(moments, lessons, repo, langs, cfg, use_llm):
    """Return list of decisions: (moment, noise, lesson_id_or_None, new_lesson_or_None, source)."""
    existing = _relevant_existing(lessons, repo, langs)
    res = None
    if use_llm:
        payload = {
            "repo": repo or "(no repo)", "langs": langs,
            "moments": [{k: m.get(k) for k in ("id", "kind", "clause", "tool", "rejected", "file_ext", "signals", "after_rejection",
                                               "after_edit", "context")
                         if m.get(k) not in (None, "", [], False)} for m in moments],
            "existing": [{"id": l.id, "scope": l.scope, "status": l.status, "text": l.text} for l in existing],
        }
        res = llm.call(SYSTEM, payload, model=cfg.get("distill_model", "haiku"))
    decisions = []
    if isinstance(res, dict) and isinstance(res.get("moments"), list):
        new_by_key = {}
        for nl in res.get("lessons") or []:
            if not isinstance(nl, dict) or not isinstance(nl.get("text"), str) or not nl.get("key"):
                continue
            text = redact(nl["text"].strip())[:160]
            try:
                conf = float(nl.get("confidence", 1))
            except (TypeError, ValueError):
                conf = 0.0
            if not text or conf < MIN_CONFIDENCE:
                continue
            new_by_key[nl["key"]] = {"text": text, "scope": nl.get("scope"),
                                     "why": _short(nl.get("why")), "issue": _short(nl.get("issue")),
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


def _drop_from_queue(qpath, ids):
    """Remove `ids` from the queue; keep anything that arrived while distill was running."""
    with locked(qpath):
        rest = [m for m in read_jsonl(qpath) if m.get("id") not in ids]
        tmp = qpath + ".tmp"
        with open(tmp, "w") as f:
            for m in rest:
                f.write(json.dumps(m, sort_keys=True) + "\n")
        os.replace(tmp, qpath)


def _retired_by_user(store, lesson_id):
    """True when the developer (not curate) made the lesson's last status change to retired/dismissed."""
    last = None
    for e in E.load(store):
        if e.get("lesson") == lesson_id and e["t"] in ("retire", "dismiss", "restore", "promote"):
            last = e
    return bool(last) and last["t"] in ("retire", "dismiss") and last.get("by") == "user"


def _safe_curate(store, cfg, use_llm):
    try:
        return curate(store, cfg, use_llm=use_llm)
    except Exception as e:  # noqa: BLE001 — curate retries on the next run; distill must finish
        log("curate %s failed: %r" % (store["name"], e))
        return ["curate failed: %r" % e]


@contextlib.contextmanager
def run_lock():
    """Held by every run that rewrites the queue from a snapshot of it. Yields False if taken."""
    with open(os.path.join(state_dir(), "distill.run.lock"), "a") as lock_f:
        try:
            fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def distill(dry_run=False, use_llm=True, queue_file=None, cfg=None):
    """Process the queue. Returns dict(summary) for display/tests."""
    cfg = cfg or load_config()
    with run_lock() as got:
        if not got:
            return {"skipped": "another distill is running"}
        return _distill(cfg, dry_run, use_llm, queue_file)


def _distill(cfg, dry_run, use_llm, queue_file):
    qpath = queue_file or queue_path()
    moments = sorted(read_jsonl(qpath), key=lambda m: m.get("ts", ""))
    summary = {"moments": len(moments), "stores": {}, "dry_run": dry_run}
    stores = {s["name"]: s for s in cfg["stores"]}
    default = default_store(cfg)["name"]
    by_store = {}
    for m in moments:
        by_store.setdefault(m.get("store") if m.get("store") in stores else default, []).append(m)

    for sname, queued in by_store.items():
        store = stores[sname]
        if not is_initialized(store):
            if dry_run:
                continue
            init_store(store)
        ms = _premerge(queued)
        lessons = load_store(store)
        pending = []  # events are written only after the lessons they describe are saved

        def emit(_store, t, **fields):
            pending.append((t, fields))
        out = summary["stores"].setdefault(sname, {"new": [], "hits": [], "noise": 0, "unattributed": 0, "curate": []})
        if not dry_run:
            # Hand edits must be seen against the files as the developer left them, before
            # distill rewrites them and records new hashes.
            out["curate"] = apply_hand_edits(store, lessons, emit)
        groups = {}
        for m in ms:
            groups.setdefault(m.get("repo") or "", []).append(m)
        for repo, gms in groups.items():
            langs = sorted({l for m in gms for l in (m.get("langs") or [])})
            for m, noise, match, new, source in _plan_group(gms, lessons, repo, langs, cfg, use_llm):
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
                        old = lessons.get(lid)
                        if (old and old.status == "retired" and not old.pinned
                                and not _retired_by_user(store, lid)):
                            # Curate retired it (unused / ineffective / cap) but the pushback came back.
                            # It returns as a candidate whose hit count starts over (see stats), so it
                            # must recur in new sessions before it is injected again.
                            old.status, old.reason = "candidate", ""
                            out["new"].append({"id": lid, "text": old.text, "scope": scope, "status": "candidate",
                                               "source": "revived"})
                            emit(store, "restore", lesson=lid, by="auto", status="candidate",
                                 reason="pushback recurred")
                        elif not old:
                            status = "active" if m["kind"] == "explicit" else "candidate"
                            lessons[lid] = Lesson(lid, new["text"], scope, new["keywords"], new["files"], status,
                                                  why=new.get("why", ""), issue=new.get("issue", ""))
                            out["new"].append({"id": lid, "text": new["text"], "scope": scope, "status": status,
                                               "source": source})
                            emit(store, "create", lesson=lid, scope=scope, status=status,
                                 source="explicit" if m["kind"] == "explicit" else source)
                if lid and not noise and m["kind"] == "explicit" and lessons[lid].status == "candidate":
                    lessons[lid].status = "active"  # stating it explicitly is a promotion
                    emit(store, "promote", lesson=lid, by="explicit")
                if noise:
                    out["noise"] += 1
                elif lid:
                    out["hits"].append(lid)
                else:
                    out["unattributed"] += 1
                emit(store, "moment", session_id=m.get("session_id", ""), repo=m.get("repo", ""),
                     langs=m.get("langs") or [], kind=m["kind"], signals=m.get("signals") or [],
                     tool=m.get("tool", ""), noise=noise, lesson=None if noise else lid,
                     moment_ts=m.get("ts"))
        if dry_run:
            continue
        # Order matters for crash safety: if saving fails, no events exist yet and the moments stay
        # queued for a clean retry. The remaining window (crash between writing events and dropping
        # the queue) is a few local file writes wide.
        save_store(store, lessons.values())
        remember_hashes(store, lessons.values())
        for t, fields in pending:
            E.emit(store, t, **fields)
        commit(store, "hindsight: distill %d moment(s)" % len(ms))
        if queue_file is None:  # drop right after the commit: keeps the double-count window minimal
            _drop_from_queue(qpath, {m["id"] for m in queued})
        out["curate"] += _safe_curate(store, cfg, use_llm)
    # Curate stores that had no new moments too (time-based retirement)
    if not dry_run:
        for s in cfg["stores"]:
            if s["name"] not in by_store and is_initialized(s):
                summary["stores"].setdefault(s["name"], {})["curate"] = _safe_curate(s, cfg, use_llm)
    log("distill done: %s" % {k: (v if k != "stores" else {n: {kk: (len(vv) if isinstance(vv, list) else vv)
                                                                  for kk, vv in d.items()} for n, d in v.items()})
                              for k, v in summary.items()})
    summary["at"] = iso(now_ts())
    return summary
