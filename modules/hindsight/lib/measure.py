"""Reporting: pushbacks per session over time, lesson efficacy, detector precision."""
from datetime import datetime, timezone

import events as E
import stats as S
from lessons_md import load_store
from store import is_initialized


def _week(ts):
    d = datetime.fromtimestamp(S.parse_ts(ts), timezone.utc)
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def build(cfg, store_name=None, repo=None, weeks=8):
    stores = [s for s in cfg["stores"] if is_initialized(s) and (not store_name or s["name"] == store_name)]
    evs = E.load_all([s for s in cfg["stores"] if is_initialized(s)])
    sess = S.sessions(evs)
    if store_name:
        sids = {e.get("session_id") for e in evs if e.get("_store") == store_name}
        sess = {k: v for k, v in sess.items() if k in sids}
    if repo:
        sess = {k: v for k, v in sess.items() if v.get("repo") == repo}

    by_week = {}
    for s in sess.values():
        w = by_week.setdefault(_week(s["ts"]), {"sessions": 0, "pushbacks": 0})
        w["sessions"] += 1
        w["pushbacks"] += s["moments"]
    wk = sorted(by_week)[-weeks:]
    weekly = [{"week": w, "sessions": by_week[w]["sessions"], "pushbacks": by_week[w]["pushbacks"],
               "rate": round(by_week[w]["pushbacks"] / float(by_week[w]["sessions"]), 2)} for w in wk]

    lessons = []
    counts = {"candidate": 0, "active": 0, "retired": 0, "dismissed": 0}
    for s in stores:
        ls = load_store(s)
        for l in ls.values():
            counts[l.status] = counts.get(l.status, 0) + 1
        live = [l for l in ls.values() if l.status in ("candidate", "active")]
        if repo:
            live = [l for l in live if l.scope in ("global", "repo:" + repo) or l.scope.startswith("lang:")]
        st = S.lesson_stats(evs, live)
        for l in live:
            d = dict(st[l.id], id=l.id, text=l.text, scope=l.scope, status=l.status, store=s["name"], pinned=l.pinned)
            lessons.append(d)

    # Detector precision: share of captured prompts per signal that distill judged real (non-noise)
    sig = {}
    for e in evs:
        if e["t"] != "moment" or e.get("kind") != "prompt":
            continue
        if store_name and e.get("_store") != store_name:
            continue
        for sgn in e.get("signals") or []:
            d = sig.setdefault(sgn, {"n": 0, "real": 0})
            d["n"] += 1
            d["real"] += 0 if e.get("noise") else 1
    precision = {k: {"n": v["n"], "precision": round(v["real"] / float(v["n"]), 2)} for k, v in sig.items()}
    kinds = {}
    for e in evs:
        if e["t"] == "moment" and not e.get("noise") and (not store_name or e.get("_store") == store_name):
            kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
    dismissed = sum(1 for e in evs if e["t"] == "dismiss" and (not store_name or e.get("_store") == store_name))

    total_s = sum(w["sessions"] for w in weekly)
    total_p = sum(w["pushbacks"] for w in weekly)
    return {
        "weekly": weekly,
        "totals": {"sessions": total_s, "pushbacks": total_p,
                   "rate": round(total_p / float(total_s), 2) if total_s else 0.0},
        "lessons": lessons,
        "counts": counts,
        "precision": precision,
        "pushback_kinds": kinds,
        "dismissed": dismissed,
    }


def render(r, width=30):
    out = []
    t = r["totals"]
    out.append("Pushbacks per session (by week)")
    if not r["weekly"]:
        out.append("  no sessions recorded yet")
    mx = max([w["rate"] for w in r["weekly"]] + [0.01])
    for w in r["weekly"]:
        bar = "█" * int(round(w["rate"] / mx * width))
        out.append("  %s  %-*s %5.2f  (%d pushbacks / %d sessions)" % (w["week"], width, bar, w["rate"],
                                                                      w["pushbacks"], w["sessions"]))
    if len(r["weekly"]) >= 2:
        a, b = r["weekly"][0]["rate"], r["weekly"][-1]["rate"]
        trend = "↓" if b < a else ("↑" if b > a else "→")
        out.append("  trend: %s %.2f -> %.2f" % (trend, a, b))
    out.append("  total: %d pushbacks over %d sessions (%.2f/session)  kinds: %s" % (
        t["pushbacks"], t["sessions"], t["rate"],
        ", ".join("%s=%d" % kv for kv in sorted(r["pushback_kinds"].items())) or "-"))

    c = r["counts"]
    out.append("")
    out.append("Lessons: %d active, %d candidate, %d retired, %d dismissed" % (
        c.get("active", 0), c.get("candidate", 0), c.get("retired", 0), c.get("dismissed", 0)))
    act = [l for l in r["lessons"] if l["status"] == "active"]
    if act:
        out.append("")
        out.append("Active lesson efficacy (pushbacks/session on this topic, before -> after activation)")
        out.append("  %-9s %5s %5s %13s %9s %6s  %s" % ("id", "hits", "inj", "before->after", "repeats", "saved", "lesson"))
        for l in sorted(act, key=lambda x: (-x["prevented"], -x["hits"])):
            flag = "  ⚠ ineffective" if l["flagged_ineffective"] else ""
            out.append("  %-9s %5d %5d %6.2f->%-6.2f %9d %6.1f  %s%s" % (
                l["id"], l["hits"], l["sessions_injected"], l["before"]["rate"], l["after"]["rate"],
                l["repeats_while_injected"], l["prevented"], l["text"][:60], flag))
    cand = [l for l in r["lessons"] if l["status"] == "candidate"]
    if cand:
        out.append("")
        out.append("Candidates (promote at enough hits, or `hs review`)")
        for l in sorted(cand, key=lambda x: -x["hits"])[:10]:
            out.append("  %-9s hits=%d  %s" % (l["id"], l["hits"], l["text"][:80]))
    if r["precision"]:
        out.append("")
        out.append("Detector precision (captured prompts judged real by distill)")
        for k, v in sorted(r["precision"].items(), key=lambda kv: -kv[1]["n"]):
            out.append("  %-14s n=%-4d %3d%%" % (k, v["n"], v["precision"] * 100))
    if r["dismissed"]:
        out.append("  dismissed lessons in review: %d" % r["dismissed"])
    return "\n".join(out)
