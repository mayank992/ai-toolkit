"""Headless LLM calls via `claude -p` (uses the developer's existing Claude Code auth).

HINDSIGHT_LLM_CMD overrides the command (tests use a fake that echoes canned JSON).
HINDSIGHT_NO_LLM=1 forces the rule-based fallback.
"""
import json
import os
import re
import shlex
import subprocess

from common import log, state_dir


def _claude_cmd(model, system):
    return ["claude", "-p", "--model", model, "--output-format", "json",
            "--tools", "", "--no-session-persistence", "--strict-mcp-config",
            "--disable-slash-commands", "--settings", '{"disableAllHooks": true}',
            "--system-prompt", system]


def extract_json(text):
    """Pull the first JSON object out of model text (handles ```json fences / chatter)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cand = m.group(1) if m else text
    start = cand.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = esc = False
    for i in range(start, len(cand)):
        c = cand[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cand[start:i + 1])
                except ValueError:
                    return None
    return None


def call(system, payload, model="haiku", timeout=180):
    """Send payload (dict) as the user message; return parsed JSON object or None."""
    if os.environ.get("HINDSIGHT_NO_LLM") == "1":
        return None
    user = json.dumps(payload, indent=1)
    env = dict(os.environ, HINDSIGHT_DISABLE="1")
    override = os.environ.get("HINDSIGHT_LLM_CMD")
    cmd = shlex.split(override) if override else _claude_cmd(model, system)
    try:
        r = subprocess.run(cmd, input=user if override is None else json.dumps({"system": system, "input": payload}),
                           capture_output=True, text=True, timeout=timeout, env=env, cwd=state_dir())
    except (OSError, subprocess.SubprocessError) as e:
        log("llm error: %r" % e)
        return None
    if r.returncode != 0:
        log("llm exit %d: %s" % (r.returncode, r.stderr.strip()[:300]))
        return None
    out = r.stdout
    try:
        wrapper = json.loads(out)
    except ValueError:
        wrapper = None
    if isinstance(wrapper, dict):
        is_cli_wrapper = "result" in wrapper or wrapper.get("type") == "result"
        if not is_cli_wrapper:
            return wrapper  # a bare JSON answer
        if wrapper.get("is_error") or not isinstance(wrapper.get("result"), str):
            log("llm error result (%s): %s" % (wrapper.get("subtype", "?"), str(wrapper.get("result", ""))[:300]))
            return None
        out = wrapper["result"]
    obj = extract_json(out)
    if obj is None:
        log("llm unparseable output: %s" % out[:300])
    return obj
