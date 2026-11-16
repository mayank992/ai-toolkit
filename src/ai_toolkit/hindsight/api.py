"""hindsight's public surface. Other features and the dashboard import this module, never the internals."""
from .config import load_config
from .lessons import load_store
from .store import is_initialized

LIVE = ("candidate", "active")


def snapshot():
    """The dashboard's JSON-ready view of the whole pipeline."""
    from . import snapshot as snap
    return snap.build(load_config())


def lessons_for(repo, langs):
    """Live lessons (candidate or active) that apply to a repo: scoped global, to its languages or to it.

    [{id, text, scope, store, status, why, issue, created}], across every initialized store.
    """
    scopes = {"global"} | ({"repo:" + repo} if repo else set()) | {"lang:" + l for l in langs}
    out = []
    for store in load_config()["stores"]:
        if not is_initialized(store):
            continue
        for l in load_store(store).values():
            if l.status in LIVE and l.scope in scopes:
                out.append({"id": l.id, "text": l.text, "scope": l.scope, "store": store["name"],
                            "status": l.status, "why": l.why or "", "issue": l.issue or "",
                            "created": l.created or ""})
    return out
