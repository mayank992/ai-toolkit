"""Select the lessons to inject for a session (SessionStart). Must stay fast: no event replay."""
import fnmatch
import glob
import os

from common import read_json
from lessons_md import load_active_files, scope_file

HEADER = ("## Lessons from past corrections (hindsight)\n"
          "The developer corrected these before. Follow them unless told otherwise in this session.\n")


def _files_match(root, globs):
    if not root or not globs:
        return False
    try:
        names = os.listdir(root)
    except OSError:
        return False
    for g in globs:
        if "/" in g or "**" in g:
            if glob.glob(os.path.join(root, g)):
                return True
        elif any(fnmatch.fnmatch(n, g) for n in names):
            return True
    return False


def select(cfg, info, initialized, rank_cache_path):
    """Return list of (store_name, Lesson, score) to inject, best first, within budget."""
    hits = read_json(rank_cache_path, {})
    rels = [scope_file("global")]
    if info["repo"]:
        rels.append(scope_file("repo:" + info["repo"]))
    rels += [scope_file("lang:" + l) for l in info["langs"]]
    picked = []
    seen_text = set()
    for s in cfg["stores"]:
        if not initialized(s):
            continue
        for l in load_active_files(s, rels):
            key = l.text.lower()
            if key in seen_text:
                continue
            seen_text.add(key)
            score = float(hits.get(s["name"], {}).get(l.id, 0))
            if l.scope.startswith("repo:"):
                score += 3
            elif l.scope.startswith("lang:"):
                score += 1
            if _files_match(info["root"], l.files):
                score += 2
            if l.pinned:
                score += 1
            picked.append((s["name"], l, score))
    picked.sort(key=lambda x: (-x[2], x[1].id))
    budget_lines = int(cfg.get("inject_budget_lines", 15))
    budget_chars = int(cfg.get("inject_budget_chars", 1500))
    out, used = [], len(HEADER)
    for p in picked:
        if len(out) >= budget_lines:
            break
        line_len = len(p[1].text) + 14
        if used + line_len > budget_chars:
            continue  # too long for what is left; a shorter, lower-ranked lesson may still fit
        out.append(p)
        used += line_len
    return out


def render(selected):
    if not selected:
        return ""
    return HEADER + "".join("- [%s] %s\n" % (l.id, l.text) for _, l, _ in selected)
