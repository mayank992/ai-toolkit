"""Shared test harness: isolated HOME, fake LLM, helpers to drive hooks and the CLI."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(MOD))
FAKE_LLM = os.path.join(MOD, "tests", "fake_llm.py")
sys.path.insert(0, os.path.join(MOD, "lib"))

ORG_REMOTE = "git@gitlab.example-corp.com:team/web.git"
ORG_REPO = "gitlab.example-corp.com/team/web"
DAY = 86400
T0 = 1793000000  # fixed clock (2026-10-27)


class Env(object):
    def __init__(self, **cfg_overrides):
        self.home = tempfile.mkdtemp(prefix="hs-test-")
        self.now = T0
        self.env = dict(os.environ, HOME=self.home, HINDSIGHT_LLM_CMD="%s %s" % (sys.executable, FAKE_LLM),
                        HINDSIGHT_NO_BACKGROUND="1")
        for k in ("HINDSIGHT_DISABLE", "HINDSIGHT_CONFIG", "HINDSIGHT_STATE_DIR", "HINDSIGHT_NO_LLM", "FAKE_LLM_MODE"):
            self.env.pop(k, None)
        cfg = {"stores": [
            {"name": "org", "path": "~/.ai-memory/org", "remote": "", "match": ["*example-corp.com/*"]},
            {"name": "personal", "path": "~/.ai-memory/personal", "remote": "", "match": ["*"], "default": True},
        ]}
        cfg.update(cfg_overrides)
        d = os.path.join(self.home, ".config", "ai-toolkit")
        os.makedirs(d)
        with open(os.path.join(d, "hindsight.json"), "w") as f:
            json.dump(cfg, f)
        self.state = os.path.join(self.home, ".local", "state", "hindsight")
        self.queue = os.path.join(self.state, "queue.jsonl")
        self.hs("store", "init")

    # ----- fixtures -----
    def repo(self, name, remote=None, markers=()):
        d = os.path.join(self.home, "code", name)
        os.makedirs(d)
        subprocess.run(["git", "init", "-q", d], check=True, env=self.env)
        if remote:
            subprocess.run(["git", "-C", d, "remote", "add", "origin", remote], check=True, env=self.env)
        for m in markers:
            open(os.path.join(d, m), "w").close()
        return d

    def store_path(self, name):
        return os.path.join(self.home, ".ai-memory", name)

    # ----- runners -----
    def _env(self, extra=None):
        e = dict(self.env, HINDSIGHT_NOW=str(self.now))
        e.update(extra or {})
        return e

    def hook(self, script, payload, extra_env=None):
        r = subprocess.run([os.path.join(MOD, "hooks", script)], input=json.dumps(payload),
                           capture_output=True, text=True, env=self._env(extra_env), timeout=30)
        assert r.returncode == 0, r.stderr
        return r

    def hs(self, *args, stdin=None, cwd=None, extra_env=None, check=True):
        r = subprocess.run([os.path.join(MOD, "bin", "hs")] + list(args), input=stdin, cwd=cwd,
                           capture_output=True, text=True, env=self._env(extra_env), timeout=60)
        if check:
            assert r.returncode == 0, "hs %s failed:\n%s\n%s" % (" ".join(args), r.stdout, r.stderr)
        return r

    # ----- a whole simulated session -----
    def session(self, sid, cwd, prompts=(), advance=DAY):
        """SessionStart -> prompts -> SessionEnd -> distill. Returns the SessionStart output (dict or None)."""
        out = self.hook("session_start.py", {"session_id": sid, "cwd": cwd, "source": "startup"}).stdout.strip()
        for p in prompts:
            self.now += 60
            self.hook("capture_prompt.py", {"session_id": sid, "cwd": cwd, "prompt": p})
        self.now += 60
        self.hook("session_end.py", {"session_id": sid, "cwd": cwd, "reason": "exit"})
        self.hs("distill")
        self.now += advance
        return json.loads(out) if out else None

    # ----- inspection -----
    def queued(self):
        if not os.path.exists(self.queue):
            return []
        with open(self.queue) as f:
            return [json.loads(l) for l in f if l.strip()]

    def events(self, store):
        out = []
        for p in sorted(glob.glob(os.path.join(self.store_path(store), "events", "*.jsonl"))):
            with open(p) as f:
                out.extend(json.loads(l) for l in f if l.strip())
        return out

    def lessons(self, store):
        from lessons_md import load_store
        return load_store({"name": store, "path": self.store_path(store)})

    def read(self, store, rel):
        p = os.path.join(self.store_path(store), "lessons", rel)
        if not os.path.exists(p):
            return ""
        with open(p) as f:
            return f.read()

    def write(self, store, rel, text):
        with open(os.path.join(self.store_path(store), "lessons", rel), "w") as f:
            f.write(text)

    def all_store_text(self, store):
        buf = []
        for root, _, files in os.walk(self.store_path(store)):
            if "/.git" in root:
                continue
            for fn in files:
                with open(os.path.join(root, fn), errors="ignore") as f:
                    buf.append(f.read())
        return "\n".join(buf)

    def git_log(self, store):
        return subprocess.run(["git", "-C", self.store_path(store), "log", "--oneline"], capture_output=True,
                              text=True).stdout

    def set_config(self, **kv):
        p = os.path.join(self.home, ".config", "ai-toolkit", "hindsight.json")
        with open(p) as f:
            cfg = json.load(f)
        cfg.update(kv)
        with open(p, "w") as f:
            json.dump(cfg, f)

    def cleanup(self):
        shutil.rmtree(self.home, ignore_errors=True)
