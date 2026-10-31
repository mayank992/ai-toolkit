"""Write correction moments to the local queue (never synced, emptied by distill)."""
from common import (append_jsonl, iso, load_config, now_ts, queue_path, read_jsonl,
                    repo_info, route_store, short_hash)
from redact import redact

KINDS = ("prompt", "rejected_tool", "explicit")


def enqueue(kind, session_id, cwd, clause="", **extra):
    """Redact, route and append one moment. Returns the record, or None if duplicate."""
    assert kind in KINDS
    cfg = load_config()
    info = repo_info(cwd)
    store = route_store(cfg, info["remote"])
    clause = redact(clause or "")
    rec = {
        "id": short_hash(kind, session_id, clause, extra.get("tool_use_id", "")),
        "ts": iso(now_ts()),
        "kind": kind,
        "session_id": session_id or "",
        "repo": info["repo"],
        "langs": info["langs"],
        "store": store["name"],
        "clause": clause,
    }
    for k, v in extra.items():
        rec[k] = redact(v) if isinstance(v, str) else v
    if any(r.get("id") == rec["id"] for r in read_jsonl(queue_path())):
        return None
    append_jsonl(queue_path(), rec)
    return rec
