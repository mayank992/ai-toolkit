#!/usr/bin/env python3
"""Deterministic stand-in for `claude -p` used by tests (HINDSIGHT_LLM_CMD).

Reads {"system", "input"} on stdin. Topic rules:
  clause mentions pnpm   -> lesson "Use pnpm, never npm, in this repo" (matches existing pnpm lesson)
  clause mentions tabs   -> global lesson "Indent with tabs"
  clause mentions NOISE  -> noise
  explicit               -> lesson = clause
  anything else          -> unattributed
FAKE_LLM_MODE=garbage prints non-JSON; FAKE_LLM_MODE=fail exits 1.
"""
import json
import os
import sys

mode = os.environ.get("FAKE_LLM_MODE", "")
if mode == "fail":
    sys.exit(1)
if mode == "garbage":
    print("I'm sorry, I can't produce JSON today")
    sys.exit(0)
req = json.load(sys.stdin)
inp = req["input"]
if "groups" in req["system"]:  # consolidation request
    print(json.dumps({"result": json.dumps({"groups": []})}))
    sys.exit(0)
existing = inp.get("existing", [])
moments, lessons = [], {}
for m in inp["moments"]:
    c = (m.get("clause") or "").lower()
    d = {"id": m["id"], "noise": False, "match": None, "new": None}
    if "noise" in c:
        d["noise"] = True
    elif "pnpm" in c:
        ex = next((e for e in existing if "pnpm" in e["text"].lower()), None)
        if ex:
            d["match"] = ex["id"]
        else:
            d["new"] = "pnpm"
            lessons["pnpm"] = {"key": "pnpm", "text": "Use pnpm, never npm, in this repo", "scope": "repo",
                               "keywords": ["npm", "pnpm", "install"], "files": ["package.json"], "confidence": 0.95}
    elif "tabs" in c:
        ex = next((e for e in existing if "tabs" in e["text"].lower()), None)
        if ex:
            d["match"] = ex["id"]
        else:
            d["new"] = "tabs"
            lessons["tabs"] = {"key": "tabs", "text": "Indent with tabs", "scope": "global",
                               "keywords": ["indent"], "files": [], "confidence": 0.9}
    elif m["kind"] == "explicit":
        d["new"] = "x" + m["id"]
        lessons[d["new"]] = {"key": d["new"], "text": m["clause"], "scope": "repo", "keywords": [], "files": [],
                             "confidence": 1}
    moments.append(d)
# Wrap like `claude -p --output-format json`, with chatter + fence to exercise extraction.
print(json.dumps({"type": "result", "is_error": False,
                  "result": "Here you go:\n```json\n" + json.dumps({"moments": moments, "lessons": list(lessons.values())}) + "\n```"}))
