"""Memory stores: private git repos that hold lessons + append-only events."""
import os
import subprocess

from common import hostname

README = """# ai-memory ({name})

Private memory store for [ai-toolkit](https://github.com/) / hindsight.
Lessons are human-editable Markdown; edit or delete freely, `hs` picks changes up.

- `lessons/candidates.md`  — distilled, not yet trusted
- `lessons/active/*.md`    — promoted lessons, injected at SessionStart
- `lessons/archive.md`     — retired / dismissed (kept for audit)
- `events/<host>.jsonl`    — append-only per-machine events (hits, injections, sessions)

Never contains raw prompts. Sync manually with `hs sync {name}`.
"""

SEED_FILES = {
    "lessons/candidates.md": "# Candidate lessons\n\n<!-- Distilled from pushback; promoted after repeated hits. -->\n",
    "lessons/archive.md": "# Archived lessons\n\n<!-- Retired or dismissed lessons, kept for audit. -->\n",
    "lessons/active/.gitkeep": "",
    "events/.gitkeep": "",
}


def git(path, *args, check=False):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True, check=check)


def is_initialized(store):
    return os.path.isdir(os.path.join(store["path"], ".git"))


def init_store(store):
    """Create directory layout + git repo. Idempotent. Returns list of created files."""
    p = store["path"]
    os.makedirs(p, exist_ok=True)
    created = []
    files = dict(SEED_FILES)
    files["README.md"] = README.format(name=store["name"])
    for rel, content in files.items():
        fp = os.path.join(p, rel)
        if not os.path.exists(fp):
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w") as f:
                f.write(content)
            created.append(rel)
    if not is_initialized(store):
        git(p, "init", "-q", "-b", "main", check=True)
    if store.get("remote"):
        if git(p, "remote", "get-url", "origin").returncode == 0:
            git(p, "remote", "set-url", "origin", store["remote"])
        else:
            git(p, "remote", "add", "origin", store["remote"])
    if created:
        commit(store, "hindsight: initialize store")
    return created


def commit(store, message):
    p = store["path"]
    git(p, "add", "-A")
    ident = []
    if not git(p, "config", "user.email").stdout.strip():
        ident = ["-c", "user.name=hindsight", "-c", "user.email=hindsight@localhost"]
    r = git(p, *(ident + ["commit", "-q", "-m", message]))
    return r.returncode == 0


def events_path(store):
    return os.path.join(store["path"], "events", "%s.jsonl" % hostname())
