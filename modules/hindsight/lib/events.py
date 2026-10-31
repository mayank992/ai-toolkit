"""Append-only per-host event log inside each store (events/<host>.jsonl).

Per-host files never conflict on git merge; every statistic is derived by
replaying the union of all hosts' events.

Event types (field `t`):
  session   {session_id, repo, langs, phase: start|end}
  inject    {session_id, repo, ids: [...]}
  moment    {session_id, repo, kind, signals, noise: bool, lesson: id|null}
  create    {lesson, scope, source: llm|rules|explicit}
  promote   {lesson, by: auto|user}
  retire    {lesson, reason}
  dismiss   {lesson, reason}
  restore   {lesson}
  merge     {lesson (from), into}
  delete    {lesson}
  review    {lesson, decision}
  edit      {lesson}
"""
import glob
import os

from common import append_jsonl, iso, now_ts, read_jsonl
from store import events_path


def emit(store, t, **fields):
    rec = {"t": t, "ts": iso(now_ts())}
    rec.update(fields)
    p = events_path(store)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    append_jsonl(p, rec)
    return rec


def load(store):
    evs = []
    for p in sorted(glob.glob(os.path.join(store["path"], "events", "*.jsonl"))):
        evs.extend(read_jsonl(p))
    evs.sort(key=lambda e: e.get("ts", ""))
    return evs


def load_all(stores):
    evs = []
    for s in stores:
        for e in load(s):
            e["_store"] = s["name"]
            evs.append(e)
    evs.sort(key=lambda e: e.get("ts", ""))
    return evs


def alias_map(evs):
    """Follow merge chains: old id -> surviving id."""
    m = {}
    for e in evs:
        if e["t"] == "merge":
            m[e["lesson"]] = e["into"]

    def resolve(i):
        seen = set()
        while i in m and i not in seen:
            seen.add(i)
            i = m[i]
        return i
    return resolve
