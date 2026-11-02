"""Lessons as human-editable Markdown.

A store holds:
  lessons/candidates.md          status: candidate
  lessons/active/<scope>.md      status: active   (one file per scope)
  lessons/archive.md             status: retired | dismissed

Each lesson is a section:

    ## L-3f9a1c — Use pnpm, never npm, in this repo
    - scope: repo:github.com/me/web
    - trigger: keywords=npm,install; files=package.json
    - why: the repo is a pnpm workspace; npm breaks the lockfile   (the reason behind the rule)
    - issue: ran npm install after adding a dependency            (the mistake that taught it)
    - status: active
    - created: 2026-10-31
    - pinned: true
    - reason: ...            (archive only)
    - merged: L-aaaaaa, ...  (ids folded into this one)
    free-form notes lines are preserved

The `status` field is the source of truth: change it by hand and the next
curate run moves the section to the right file.
"""
import hashlib
import os
import re

from common import iso, short_hash

STATUSES = ("candidate", "active", "retired", "dismissed")
_HEAD = re.compile(r"^##\s+(L-[0-9a-f]{4,12})\s*[—–-]+\s*(.*?)\s*$")
_FIELD = re.compile(r"^-\s*([a-z_]+)\s*:\s*(.*?)\s*$")

HEADERS = {
    "candidates": "# Candidate lessons\n\n<!-- Distilled from pushback; promoted after repeated hits. Edit freely. -->\n",
    "archive": "# Archived lessons\n\n<!-- Retired or dismissed lessons, kept for audit. -->\n",
    "active": "# Active lessons — {scope}\n\n<!-- Injected at SessionStart. Edit or delete freely; set `status:` to move a lesson. -->\n",
}


class Lesson(object):
    FIELDS = ("scope", "trigger", "why", "issue", "status", "created", "pinned", "reason", "merged")

    def __init__(self, id, text, scope="global", keywords=None, files=None, status="candidate",
                 created=None, pinned=False, reason="", merged=None, notes=None, why="", issue=""):
        self.id = id
        self.text = text.strip()
        self.scope = scope
        self.keywords = list(keywords or [])
        self.files = list(files or [])
        self.status = status
        self.created = created or iso()[:10]
        self.pinned = bool(pinned)
        self.reason = reason or ""
        self.merged = list(merged or [])
        self.notes = list(notes or [])
        self.why = why or ""
        self.issue = issue or ""

    @staticmethod
    def new_id(store_name, text, scope):
        return "L-" + short_hash(store_name, scope, text.lower().strip())[:6]

    def trigger_str(self):
        parts = []
        if self.keywords:
            parts.append("keywords=" + ",".join(self.keywords))
        if self.files:
            parts.append("files=" + ",".join(self.files))
        return "; ".join(parts)

    def content_hash(self):
        """Hash of human-meaningful content; differs => the developer edited it."""
        parts = [self.text, self.scope, self.trigger_str(), self.status, "\n".join(self.notes)]
        if self.why or self.issue:  # only when set, so lessons from before these fields keep their hash
            parts += [self.why, self.issue]
        s = "\x1f".join(parts)
        return hashlib.sha1(s.encode()).hexdigest()[:12]

    def to_md(self):
        lines = ["## %s — %s" % (self.id, self.text), "- scope: %s" % self.scope]
        if self.keywords or self.files:
            lines.append("- trigger: %s" % self.trigger_str())
        if self.why:
            lines.append("- why: %s" % self.why)
        if self.issue:
            lines.append("- issue: %s" % self.issue)
        lines.append("- status: %s" % self.status)
        lines.append("- created: %s" % self.created)
        if self.pinned:
            lines.append("- pinned: true")
        if self.reason:
            lines.append("- reason: %s" % self.reason)
        if self.merged:
            lines.append("- merged: %s" % ", ".join(self.merged))
        lines.extend(self.notes)
        return "\n".join(lines) + "\n"

    def to_dict(self):
        return {"id": self.id, "text": self.text, "scope": self.scope, "keywords": self.keywords,
                "files": self.files, "status": self.status, "created": self.created, "pinned": self.pinned,
                "reason": self.reason, "merged": self.merged, "why": self.why, "issue": self.issue}


def _parse_trigger(v):
    kw, files = [], []
    for part in v.split(";"):
        if "=" not in part:
            continue
        k, val = part.split("=", 1)
        items = [x.strip() for x in val.split(",") if x.strip()]
        if k.strip() == "keywords":
            kw = items
        elif k.strip() == "files":
            files = items
    return kw, files


def parse(text, default_status="candidate"):
    lessons = []
    cur = None
    for raw in text.splitlines():
        m = _HEAD.match(raw)
        if m:
            cur = Lesson(m.group(1), m.group(2), status=default_status)
            lessons.append(cur)
            continue
        if cur is None:
            continue
        line = raw.rstrip()
        if line.startswith("# ") or line.startswith("## "):
            cur = None  # a non-lesson heading ends the section
            continue
        f = _FIELD.match(line)
        if f and f.group(1) in Lesson.FIELDS:
            k, v = f.group(1), f.group(2)
            if k == "trigger":
                cur.keywords, cur.files = _parse_trigger(v)
            elif k == "pinned":
                cur.pinned = v.lower() in ("true", "yes", "1")
            elif k == "merged":
                cur.merged = [x.strip() for x in v.split(",") if x.strip()]
            elif k == "status":
                cur.status = v.lower() if v.lower() in STATUSES else default_status
            else:
                setattr(cur, k, v)
        elif line.strip() and not line.strip().startswith("<!--"):
            cur.notes.append(line)
    return lessons


# ---------- store-level IO ----------

def _safe_name(s, sep):
    """A single path component: no separators, never "." or ".." (scopes may come from the LLM)."""
    return re.sub(r"[^A-Za-z0-9._-]+", sep, s).strip("_.") or "_"


def scope_file(scope):
    if scope == "global":
        name = "global"
    elif scope.startswith("lang:"):
        name = "lang-" + _safe_name(scope[5:], "_")
    elif scope.startswith("repo:"):
        name = "repo-" + _safe_name(scope[5:], "__")
    else:
        name = _safe_name(scope, "_")
    return os.path.join("active", name + ".md")


def file_for(lesson):
    if lesson.status == "candidate":
        return "candidates.md"
    if lesson.status == "active":
        return scope_file(lesson.scope)
    return "archive.md"


def lessons_dir(store):
    return os.path.join(store["path"], "lessons")


def _all_files(store):
    d = lessons_dir(store)
    out = []
    for rel in ("candidates.md", "archive.md"):
        if os.path.exists(os.path.join(d, rel)):
            out.append(rel)
    ad = os.path.join(d, "active")
    if os.path.isdir(ad):
        out.extend(os.path.join("active", f) for f in sorted(os.listdir(ad)) if f.endswith(".md"))
    return out


def load_store(store):
    """Return {id: Lesson} for every lesson in the store. Later duplicates of an id are dropped."""
    d = lessons_dir(store)
    out = {}
    for rel in _all_files(store):
        default = "candidate" if rel == "candidates.md" else ("retired" if rel == "archive.md" else "active")
        with open(os.path.join(d, rel)) as f:
            for l in parse(f.read(), default):
                l.source_file = rel
                out.setdefault(l.id, l)
    return out


def load_active_files(store, rels):
    """Fast path for SessionStart: parse only the given active/* files."""
    d = lessons_dir(store)
    out = []
    for rel in rels:
        p = os.path.join(d, rel)
        if os.path.exists(p):
            with open(p) as f:
                out.extend(l for l in parse(f.read(), "active") if l.status == "active")
    return out


def save_store(store, lessons):
    """Rewrite every lesson file from `lessons` (iterable of Lesson). Removes emptied active files."""
    d = lessons_dir(store)
    groups = {}
    for l in sorted(lessons, key=lambda x: (x.created, x.id)):
        groups.setdefault(file_for(l), []).append(l)
    groups.setdefault("candidates.md", [])
    groups.setdefault("archive.md", [])
    written = set()
    for rel, ls in groups.items():
        if rel == "candidates.md":
            head = HEADERS["candidates"]
        elif rel == "archive.md":
            head = HEADERS["archive"]
        else:
            head = HEADERS["active"].format(scope=ls[0].scope if ls else rel)
        body = head + "".join("\n" + l.to_md() for l in ls)
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        old = None
        if os.path.exists(p):
            with open(p) as f:
                old = f.read()
        if old != body:
            with open(p, "w") as f:
                f.write(body)
        written.add(rel)
    for rel in _all_files(store):
        if rel.startswith("active") and rel not in written:
            os.remove(os.path.join(d, rel))


# ---------- similarity ----------

_STOP = set("a an the in on of to for and or is are be it this that with use using never always do don't dont not "
            "instead when should must please you your our repo code".split())


def tokens(s):
    return {w for w in re.findall(r"[a-z0-9_.+#-]+", s.lower()) if w not in _STOP and len(w) > 1}


def jaccard(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))
