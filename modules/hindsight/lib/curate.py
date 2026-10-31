"""Curate a store: detect hand edits, merge duplicates, consolidate, promote, retire, cap.

Pinned lessons (hand-edited) are never rewritten, merged away or auto-retired.
"""
import os

import events as E
import llm
import stats as S
from common import iso, load_config, log, now_ts, read_json, state_dir, write_json_atomic
from lessons_md import jaccard, load_store, save_store
from store import commit, is_initialized

MERGE_THRESHOLD = 0.6
CONSOLIDATE_AT = 30
DAY = 86400.0

CONSOLIDATE_SYSTEM = """You consolidate a developer's list of candidate coding-assistant lessons.
Group lessons that express the same rule (same scope only). For each group of 2+ ids output the
best single imperative wording (<=120 chars). Never invent new rules. Output ONLY JSON:
{"groups": [{"ids": ["L-..", "L-.."], "text": "merged lesson"}]}"""


def _hash_path():
    return os.path.join(state_dir(), "lesson_hashes.json")


def rank_cache_path():
    return os.path.join(state_dir(), "rank_cache.json")


def _age_days(ts_iso, now):
    if not ts_iso:
        return None
    try:
        return (now - S.parse_ts(ts_iso if "T" in ts_iso else ts_iso + "T00:00:00Z")) / DAY
    except ValueError:
        return None


class _Recorder:
    """Dry-run stand-in for events.emit: writes nothing, but remembers merges so stats see them."""

    def __init__(self):
        self.events = []

    def __call__(self, store, t, **fields):
        rec = dict(fields, t=t, ts=iso(now_ts()))
        self.events.append(rec)
        return rec


def merge_into(emit, store, src, dst, actions):
    dst.merged = sorted(set(dst.merged + [src.id] + src.merged))
    src.status = "_deleted"
    emit(store, "merge", lesson=src.id, into=dst.id)
    actions.append("merge %s -> %s" % (src.id, dst.id))


def apply_hand_edits(store, lessons, emit=E.emit):
    """Compare lessons as loaded from disk with the hashes recorded after the last tool write.

    Edited lessons become pinned; hand status changes and deletions become events. Must run on
    freshly loaded lessons BEFORE anything else changes them or records new hashes.
    """
    actions = []
    known = read_json(_hash_path(), {}).get(store["name"], {})
    for l in lessons.values():
        prev = known.get(l.id)
        if not prev or prev.get("h") == l.content_hash():
            continue
        l.pinned = True
        emit(store, "edit", lesson=l.id)
        actions.append("pinned %s (edited by you)" % l.id)
        if prev.get("s") != l.status:
            t = {"active": "promote", "retired": "retire", "dismissed": "dismiss", "candidate": "restore"}[l.status]
            extra = {"status": l.status} if t == "restore" else {}
            emit(store, t, lesson=l.id, by="user", reason="status edited by hand", **extra)
            actions.append("%s %s (by hand)" % (t, l.id))
    for lid in sorted(set(known) - set(lessons)):
        emit(store, "delete", lesson=lid)
        actions.append("deleted %s (by you)" % lid)
    return actions


def curate(store, cfg=None, use_llm=True, dry_run=False):
    """Run all curation passes on one store. Returns list of human-readable actions.

    dry_run computes the same actions but writes nothing: no events, no files, no caches.
    """
    cfg = cfg or load_config()
    if not is_initialized(store):
        return []
    emit = _Recorder() if dry_run else E.emit
    now = now_ts()
    lessons = load_store(store)

    # 1. Hand edits -> pinned (+ status changes made by hand become real events)
    actions = apply_hand_edits(store, lessons, emit)

    live = [l for l in lessons.values() if l.status in ("candidate", "active")]

    # 2. Local near-duplicate merge (candidates fold into older/active lessons in the same scope)
    by_age = sorted(live, key=lambda x: (x.status != "active", x.created, x.id))
    for i, a in enumerate(by_age):
        if a.status == "_deleted":
            continue
        for b in by_age[i + 1:]:
            if b.status != "candidate" or b.pinned or b.scope != a.scope:
                continue
            if jaccard(a.text, b.text) >= MERGE_THRESHOLD:
                merge_into(emit, store, b, a, actions)

    # 3. LLM consolidation when the candidate log grows large
    cands = [l for l in lessons.values() if l.status == "candidate"]
    if use_llm and len(cands) > CONSOLIDATE_AT:
        res = llm.call(CONSOLIDATE_SYSTEM, {"lessons": [{"id": l.id, "scope": l.scope, "text": l.text} for l in cands]},
                       model=cfg.get("distill_model", "haiku"))
        groups = res.get("groups") if isinstance(res, dict) else None
        for g in groups if isinstance(groups, list) else []:
            if not isinstance(g, dict) or not isinstance(g.get("ids"), list):
                continue
            ids = [i for i in g["ids"] if isinstance(i, str) and i in lessons and lessons[i].status == "candidate"]
            group = [lessons[i] for i in ids if not lessons[i].pinned]
            if len(group) < 2 or len({x.scope for x in group}) != 1:
                continue
            group.sort(key=lambda x: (x.created, x.id))
            keep = group[0]
            if isinstance(g.get("text"), str) and 0 < len(g["text"]) <= 160:
                keep.text = g["text"].strip()
            for other in group[1:]:
                merge_into(emit, store, other, keep, actions)

    # Stats need merge events applied
    evs = E.load_all([s for s in cfg["stores"] if is_initialized(s)])
    if dry_run:  # merges were only recorded in memory
        evs += [e for e in emit.events if e["t"] == "merge"]
    live = [l for l in lessons.values() if l.status in ("candidate", "active")]
    st = S.lesson_stats(evs, live)

    # 4. Promote
    if cfg.get("auto_promote", True):
        for l in live:
            if l.status == "candidate" and st[l.id]["hits"] >= int(cfg.get("promote_at", 2)):
                l.status = "active"
                emit(store, "promote", lesson=l.id, by="auto", hits=st[l.id]["hits"])
                actions.append("promote %s (%d hits): %s" % (l.id, st[l.id]["hits"], l.text))

    # 5. Retire
    retire_days = float(cfg.get("retire_days", 60))
    for l in live:
        if l.pinned or l.status not in ("candidate", "active"):
            continue
        s = st[l.id]
        last = max(s["last_hit"], s["last_inject"], s["activated"], l.created + "T00:00:00Z")
        age = _age_days(last, now)
        reason = None
        if s["flagged_ineffective"]:
            reason = "ineffective: %.2f -> %.2f pushbacks/session after %d injected sessions" % (
                s["before"]["rate"], s["after"]["rate"], s["sessions_injected"])
        elif age is not None and age > retire_days:
            reason = "unused for %d days" % age
        if reason:
            l.status = "retired"
            l.reason = reason
            emit(store, "retire", lesson=l.id, reason=reason)
            actions.append("retire %s (%s)" % (l.id, reason))

    # 6. Cap per scope
    cap = int(cfg.get("cap_per_scope", 50))
    scopes = {}
    for l in lessons.values():
        if l.status == "active":
            scopes.setdefault(l.scope, []).append(l)
    for scope, ls in scopes.items():
        if len(ls) <= cap:
            continue
        evictable = sorted([l for l in ls if not l.pinned],
                           key=lambda x: (st.get(x.id, {}).get("hits", 0), st.get(x.id, {}).get("last_hit", "")))
        for l in evictable[: len(ls) - cap]:
            l.status = "retired"
            l.reason = "over cap of %d in %s" % (cap, scope)
            emit(store, "retire", lesson=l.id, reason=l.reason)
            actions.append("retire %s (cap)" % l.id)

    final = [l for l in lessons.values() if l.status != "_deleted"]
    if dry_run:
        return actions
    save_store(store, final)

    # Remember content hashes to detect future hand edits; refresh ranking cache for SessionStart.
    remember_hashes(store, final)
    rc = read_json(rank_cache_path(), {})
    rc[store["name"]] = {l.id: st.get(l.id, {}).get("hits", 0) for l in final if l.status == "active"}
    write_json_atomic(rank_cache_path(), rc)
    refresh_unreviewed(store, final)

    if actions:
        log("curate %s: %s" % (store["name"], "; ".join(actions)))
    commit(store, "hindsight: curate (%d change%s)" % (len(actions), "" if len(actions) == 1 else "s")
           if actions else "hindsight: record events")
    return actions


def unreviewed_ids(evs, active_ids):
    """Auto-promoted active lessons the developer hasn't looked at since promotion."""
    pending = {}
    for e in evs:
        lid = e.get("lesson")
        if e["t"] == "promote" and e.get("by") == "auto":
            pending[lid] = True
        elif e["t"] in ("review", "edit", "dismiss", "retire", "delete") or (e["t"] == "promote" and e.get("by") != "auto"):
            pending.pop(lid, None)
    return sorted(i for i in pending if i in active_ids)


def refresh_unreviewed(store, lessons=None):
    lessons = lessons if lessons is not None else load_store(store).values()
    active = {l.id for l in lessons if l.status == "active"}
    path = os.path.join(state_dir(), "unreviewed.json")
    cache = read_json(path, {})
    cache[store["name"]] = unreviewed_ids(E.load(store), active)
    write_json_atomic(path, cache)
    return cache[store["name"]]


def remember_hashes(store, lessons):
    """After a tool-driven write (distill, CLI), record hashes so it isn't mistaken for a hand edit."""
    hashes = read_json(_hash_path(), {})
    hashes[store["name"]] = {l.id: {"h": l.content_hash(), "s": l.status} for l in lessons}
    write_json_atomic(_hash_path(), hashes)


def set_status(store, lesson_id, status, reason="", by="user"):
    """CLI helper: change a lesson's status, emit the event, save, commit."""
    lessons = load_store(store)
    l = lessons.get(lesson_id)
    if not l:
        return None
    old = l.status
    l.status = status
    l.reason = reason if status in ("retired", "dismissed") else ""
    t = {"active": "promote" if old == "candidate" else "restore", "retired": "retire",
         "dismissed": "dismiss", "candidate": "restore"}[status]
    extra = {"status": status} if t == "restore" else {}
    E.emit(store, t, lesson=l.id, by=by, reason=reason, **extra)
    save_store(store, lessons.values())
    remember_hashes(store, lessons.values())
    commit(store, "hindsight: %s %s" % (t, l.id))
    refresh_unreviewed(store, lessons.values())
    return l

