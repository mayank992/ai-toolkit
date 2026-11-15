"""Gather the evidence for a post-merge retro of one MR/PR, for /mr-retro to turn into rule changes.

  merge   which commits the MR added, using the merge commit (2 parents) or the squash commit
  share   how many new lines trace to Claude Code: an added line counts as Claude's when a transcript
          wrote it (Edit/Write/Bash) before the merge. Lines already in the repo at the base are skipped
          as boilerplate. It's an upper bound: Bash scripts that quote old code count too.
  push    the developer's corrective prompts in the sessions that worked on the branch
  review  MR notes, classed as human / self / ai-review / bot
  rules   the current rule stack, so proposals can say update / new / already covered

Writes one JSON file under the rules state dir and returns its path. Read-only on the repo.
"""
import collections
import glob
import json
import os
import re
import subprocess
import time

import inventory as inv

PUSHBACK = re.compile(
    r"(^|\b)(no[,. ]|nope|don'?t|do not|never|why (did|do|are|is)|why not|revert|undo|instead|wrong|again|"
    r"i told you|i said|not required|remove (this|it|the)|keep (it|changes) minimal|nothing else|"
    r"should (be|have|not)|we should|can we not|isn'?t|unnecessary|over ?engineer|too complex)", re.I)
TRIVIAL = re.compile(r"^[\s)\]}(\[{;,<>/=:.'\"`-]*$")
AI_MARK = re.compile(r"cfm-mr-review|^\*\*(suggestion|nit|blocking|question|issue)\b|^## Code review:", re.I | re.M)


def run(cmd, cwd, timeout=60):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def norm(line):
    return re.sub(r"\s+", " ", line.strip())


def significant(line):
    n = norm(line)
    return len(n) >= 6 and not TRIVIAL.match(n)


# ---------- forge (GitLab via glab, GitHub via gh) ----------

def forge(project):
    _, url = inv.git(project, "remote", "get-url", "origin")
    return "github" if "github.com" in url else "gitlab"


def mr_meta(project, number):
    if forge(project) == "github":
        rc, out = run(["gh", "pr", "view", str(number), "--json",
                       "title,headRefName,mergedAt,createdAt,mergeCommit,author,url,state"], project)
        if rc:
            raise SystemExit("gh pr view failed: %s" % out.strip())
        d = json.loads(out)
        return {"title": d["title"], "branch": d["headRefName"], "merged_at": d.get("mergedAt") or "",
                "created_at": d["createdAt"], "merge_sha": (d.get("mergeCommit") or {}).get("oid", ""),
                "author": (d.get("author") or {}).get("login", ""), "url": d.get("url", ""), "state": d.get("state", "")}
    rc, out = run([os.environ.get("AI_RULES_GLAB", "glab"), "mr", "view", str(number), "--output", "json"], project)
    if rc:
        raise SystemExit("glab mr view failed: %s" % out.strip())
    d = json.loads(out)
    return {"title": d["title"], "branch": d["source_branch"], "merged_at": d.get("merged_at") or "",
            "created_at": d["created_at"], "merge_sha": d.get("merge_commit_sha") or d.get("squash_commit_sha") or "",
            "author": (d.get("author") or {}).get("username", ""), "url": d.get("web_url", ""), "state": d.get("state", "")}


def mr_notes(project, number, author):
    notes = []
    if forge(project) == "github":
        rc, out = run(["gh", "api", "repos/{owner}/{repo}/pulls/%s/comments" % number, "--paginate"], project)
        raw = json.loads(out) if rc == 0 and out.strip() else []
        for c in raw:
            notes.append({"author": c["user"]["login"], "body": c["body"], "path": c.get("path", ""),
                          "line": c.get("line"), "resolved": None, "at": c.get("created_at", "")})
    else:
        page = 1
        while page < 20:
            rc, out = run([os.environ.get("AI_RULES_GLAB", "glab"), "api",
                           "projects/:id/merge_requests/%s/discussions?per_page=100&page=%d" % (number, page)], project)
            batch = json.loads(out) if rc == 0 and out.strip().startswith("[") else []
            if not batch:
                break
            for t in batch:
                first = True
                for n in t.get("notes") or []:
                    if n.get("system"):
                        continue
                    pos = n.get("position") or {}
                    notes.append({"author": n["author"]["username"], "body": n["body"], "path": pos.get("new_path", ""),
                                  "line": pos.get("new_line"), "resolved": n.get("resolved"), "at": n.get("created_at", ""),
                                  "thread_start": first})
                    first = False
            page += 1
    for n in notes:
        if "bot" in n["author"].lower():
            n["kind"] = "bot"
        elif AI_MARK.search(n["body"] or ""):
            n["kind"] = "ai-review"
        elif n["author"] == author:
            n["kind"] = "self"
        else:
            n["kind"] = "human"
        n["body"] = (n["body"] or "")[:600]
    return notes


# ---------- transcripts ----------

def transcripts(project):
    d = inv.claude_dir("projects", inv.project_key(project))
    return glob.glob(os.path.join(d, "*.jsonl")) + glob.glob(os.path.join(d, "*", "subagents", "**", "*.jsonl"), recursive=True)


def user_text(o):
    if o.get("isMeta") or o.get("toolUseResult"):
        return ""
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        t = c
    elif isinstance(c, list):
        if any(isinstance(p, dict) and p.get("type") == "tool_result" for p in c):
            return ""
        t = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    else:
        return ""
    t = t.strip()
    if not t or t.startswith(("<", "Base directory for this skill", "[Request interrupted")):
        return ""
    return re.sub(r"<pasted_content[^>]*>.*?</pasted_content[^>]*>", "[pasted]", t, flags=re.S)


def scan(project, branch, number, until):
    """CC writes (all sessions, up to `until`) and per-session prompts for sessions on `branch`."""
    writes, sessions = [], {}
    needle = str(number)
    for f in transcripts(project):
        sid = os.path.relpath(f, inv.claude_dir("projects", inv.project_key(project))).split(os.sep)[0][:8]
        is_sub = "subagents" in f
        on_branch = False
        prompts = []
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                ts = o.get("timestamp", "")
                if until and ts and ts > until:
                    continue
                if o.get("gitBranch") == branch:
                    on_branch = True
                if o.get("type") == "assistant":
                    for p in (o.get("message") or {}).get("content") or []:
                        if not (isinstance(p, dict) and p.get("type") == "tool_use"):
                            continue
                        i, n = p.get("input") or {}, p.get("name")
                        if n == "Edit":
                            writes.append((ts, sid, i.get("new_string", ""), i.get("old_string", "")))
                        elif n == "MultiEdit":
                            for e in i.get("edits") or []:
                                writes.append((ts, sid, e.get("new_string", ""), e.get("old_string", "")))
                        elif n == "Write":
                            writes.append((ts, sid, i.get("content", ""), ""))
                        elif n == "Bash":
                            writes.append((ts, sid, i.get("command", ""), ""))
                elif o.get("type") == "user" and not is_sub:
                    t = user_text(o)
                    if t:
                        prompts.append({"at": ts, "text": t[:400], "branch": o.get("gitBranch", "")})
                        if needle in t:
                            on_branch = True
        if on_branch and not is_sub:
            s = sessions.setdefault(sid, {"id": sid, "prompts": []})
            s["prompts"] += [p for p in prompts if p["branch"] == branch or needle in p["text"]]
    for s in sessions.values():
        s["prompts"].sort(key=lambda p: p["at"])
        s["start"] = s["prompts"][0]["at"] if s["prompts"] else ""
        s["pushback"] = [p for p in s["prompts"] if PUSHBACK.search(p["text"])]
    return writes, sorted(sessions.values(), key=lambda s: s["start"])


def share(project, merge_sha, writes):
    rc, parents = inv.git(project, "rev-list", "--parents", "-n", "1", merge_sha)
    ps = parents.split()[1:]
    base = ps[0] if ps else merge_sha + "^"
    _, diff = inv.git(project, "diff", "--unified=0", "-M", base, merge_sha)
    existing = set()
    files = [l[6:] for l in diff.splitlines() if l.startswith("+++ b/")]
    dirs = sorted({"/".join(f.split("/")[:3]) if f.count("/") >= 3 else f.rsplit("/", 1)[0] if "/" in f else "." for f in files})
    rc, grep = run(["git", "grep", "-h", "-I", "-e", ".", base, "--"] + dirs, project, timeout=300)
    if rc == 0:
        existing = {norm(l.split(":", 1)[1] if l.startswith(base) else l) for l in grep.splitlines()}
    first = {}
    for ts, sid, new, old in sorted(writes):
        olds = {norm(x) for x in old.split("\n")}
        for x in new.replace("\\n", "\n").split("\n"):
            for n in {norm(x), norm(x).strip("\"'").rstrip(",").strip("\"'")}:
                if n and n not in olds:
                    first.setdefault(n, sid)
    per_file = collections.OrderedDict()
    cur = None
    for l in diff.splitlines():
        if l.startswith("+++ "):
            cur = None if l == "+++ /dev/null" else l[6:]
        elif l.startswith("+") and not l.startswith("+++") and cur and significant(l[1:]):
            n = norm(l[1:])
            if n in existing:
                continue
            c = per_file.setdefault(cur, {"cc": 0, "other": 0, "sessions": collections.Counter()})
            sid = first.get(n) or first.get(n.strip("\"'"))
            if sid:
                c["cc"] += 1
                c["sessions"][sid] += 1
            else:
                c["other"] += 1
    test = re.compile(r"(__tests__|\.spec\.|\.test\.|__mocks__)")
    tot = collections.Counter()
    by_session = collections.Counter()
    for f, c in per_file.items():
        k = "test" if test.search(f) else "src"
        tot[k + "_cc"] += c["cc"]
        tot[k + "_other"] += c["other"]
        by_session.update(c["sessions"])
    rows = sorted(({"file": f, "cc": c["cc"], "other": c["other"]} for f, c in per_file.items()),
                  key=lambda r: -r["other"])
    allc = tot["src_cc"] + tot["test_cc"]
    allt = allc + tot["src_other"] + tot["test_other"]
    pct = lambda a, b: round(100.0 * a / b) if b else None
    return {"base": base, "files": len(per_file), "new_lines": allt, "cc_lines": allc, "cc_pct": pct(allc, allt),
            "src_pct": pct(tot["src_cc"], tot["src_cc"] + tot["src_other"]),
            "test_pct": pct(tot["test_cc"], tot["test_cc"] + tot["test_other"]),
            "by_session": dict(by_session.most_common(12)), "least_cc_files": rows[:15]}


def rules_now(project):
    v = inv.project_view(project)
    return {"instructions": [{"path": f["path"], "sections": f["sections"], "rules": f["rules"]} for f in v["instructions"]],
            "memory": [{"file": n["file"], "name": n["name"], "description": n["description"]} for n in v["memory"]["notes"]],
            "lessons": [{"id": l["id"], "text": l["text"], "status": l["status"]} for l in v["lessons"]]}


def gather(project, number):
    meta = mr_meta(project, number)
    until = meta["merged_at"] or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    writes, sessions = scan(project, meta["branch"], number, until)
    out = {"project": project, "mr": str(number), "meta": meta, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "sessions": sessions, "notes": mr_notes(project, number, meta["author"]), "rules": rules_now(project)}
    if meta["merge_sha"] and inv.git(project, "cat-file", "-e", meta["merge_sha"])[0] == 0:
        out["share"] = share(project, meta["merge_sha"], writes)
    else:
        out["share"] = None
        out["share_note"] = "merge commit not available locally (not merged yet, or run git fetch)"
    kinds = collections.Counter(n["kind"] for n in out["notes"] if n.get("thread_start", True))
    out["summary"] = {"sessions": len(sessions), "prompts": sum(len(s["prompts"]) for s in sessions),
                      "pushback": sum(len(s["pushback"]) for s in sessions), "threads": dict(kinds)}
    os.makedirs(inv.state_dir("retro"), exist_ok=True)
    path = inv.state_dir("retro", "%s-%s.json" % (os.path.basename(project.rstrip("/")), number))
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    return path, out


def log(project, number, proposed, applied, note=""):
    os.makedirs(inv.state_dir(), exist_ok=True)
    e = {"project": project, "mr": str(number), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "proposed": proposed, "applied": applied, "note": note[:300]}
    path = inv.state_dir("retro", "%s-%s.json" % (os.path.basename(project.rstrip("/")), number))
    d = inv.load_json(path)
    if d:
        e["share"] = (d.get("share") or {}).get("cc_pct")
        e["summary"] = d.get("summary")
        e["title"] = d.get("meta", {}).get("title", "")
    with open(inv.state_dir("retros.jsonl"), "a") as f:
        f.write(json.dumps(e) + "\n")
    return e
