"""Derive per-lesson and per-session statistics by replaying events."""
from datetime import datetime, timezone

import events as ev_mod

EFFICACY_MIN_SESSIONS = 5


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def relevant(scope, sess):
    if scope == "global":
        return True
    if scope.startswith("repo:"):
        return sess.get("repo") == scope[5:]
    if scope.startswith("lang:"):
        return scope[5:] in (sess.get("langs") or [])
    return False


def sessions(evs):
    """session_id -> {repo, langs, ts, moments, injected:set}"""
    out = {}
    for e in evs:
        sid = e.get("session_id")
        if e["t"] not in ("session", "inject", "moment") or not sid:
            continue
        s = out.setdefault(sid, {"repo": e.get("repo", ""), "langs": e.get("langs") or [], "ts": e["ts"],
                                 "moments": 0, "injected": set()})
        if e.get("langs"):
            s["langs"] = e["langs"]
        if e.get("repo"):
            s["repo"] = e["repo"]
        s["ts"] = min(s["ts"], e["ts"])
        if e["t"] == "inject":
            s["injected"].update(e.get("ids") or [])
        if e["t"] == "moment" and not e.get("noise"):
            s["moments"] += 1
    return out


def lesson_stats(evs, lessons):
    """Return {lesson_id: stats dict} for the given Lesson objects."""
    resolve = ev_mod.alias_map(evs)
    sess = sessions(evs)
    for s in sess.values():
        s["injected"] = {resolve(i) for i in s["injected"]}
    st = {}
    for l in lessons:
        st[l.id] = {"hit_sessions": set(), "last_hit": "", "injected": set(), "last_inject": "",
                    "activated": "", "moments": []}
    for e in evs:
        t = e["t"]
        if t == "moment" and e.get("lesson") and not e.get("noise"):
            lid = resolve(e["lesson"])
            if lid in st:
                st[lid]["hit_sessions"].add(e.get("session_id") or e["ts"])
                st[lid]["last_hit"] = max(st[lid]["last_hit"], e["ts"])
                st[lid]["moments"].append(e)
        elif t == "inject":
            for i in e.get("ids") or []:
                lid = resolve(i)
                if lid in st:
                    st[lid]["injected"].add(e.get("session_id"))
                    st[lid]["last_inject"] = max(st[lid]["last_inject"], e["ts"])
        elif t == "promote" or (t == "create" and e.get("status") == "active"):
            lid = resolve(e["lesson"])
            if lid in st:
                st[lid]["activated"] = e["ts"]
        elif t == "restore":
            lid = resolve(e["lesson"])
            if lid in st:
                if e.get("status", "active") == "active":
                    st[lid]["activated"] = e["ts"]
                else:
                    # Back to candidate: it must earn promotion again from new pushbacks.
                    st[lid]["hit_sessions"] = set()
    out = {}
    for l in lessons:
        s = st[l.id]
        repeats = sum(1 for m in s["moments"] if l.id in sess.get(m.get("session_id"), {}).get("injected", ()))
        before_n = after_n = before_m = after_m = 0
        act = s["activated"]
        hit_by_sess = {}
        for m in s["moments"]:
            hit_by_sess[m.get("session_id")] = hit_by_sess.get(m.get("session_id"), 0) + 1
        for sid, se in sess.items():
            if not relevant(l.scope, se):
                continue
            if act and se["ts"] >= act:
                after_n += 1
                after_m += hit_by_sess.get(sid, 0)
            else:
                before_n += 1
                before_m += hit_by_sess.get(sid, 0)
        before_rate = before_m / float(before_n) if before_n else 0.0
        after_rate = after_m / float(after_n) if after_n else 0.0
        n_inj = len(s["injected"])
        flagged = bool(act) and n_inj >= EFFICACY_MIN_SESSIONS and before_rate > 0 and after_rate >= before_rate
        out[l.id] = {
            "hits": len(s["hit_sessions"]),
            "last_hit": s["last_hit"],
            "sessions_injected": n_inj,
            "last_inject": s["last_inject"],
            "activated": act,
            "repeats_while_injected": repeats,
            "before": {"sessions": before_n, "pushbacks": before_m, "rate": round(before_rate, 3)},
            "after": {"sessions": after_n, "pushbacks": after_m, "rate": round(after_rate, 3)},
            "prevented": round(max(0.0, before_rate - after_rate) * after_n, 1) if act else 0.0,
            "flagged_ineffective": flagged,
        }
    return out
