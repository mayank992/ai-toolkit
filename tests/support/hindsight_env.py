"""Isolated machine for hindsight tests: throwaway HOME, fixed clock, fake LLM, helpers to drive the
hooks (through hooks/run.py, exactly as hooks/hooks.json does) and the CLI (bin/hs)."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
RUN = os.path.join(REPO, "hooks", "run.py")
HS = os.path.join(REPO, "bin", "hs")
AIT = os.path.join(REPO, "bin", "ait")
FAKE_LLM = os.path.join(REPO, "tests", "support", "fake_llm.py")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

ORG_REMOTE = "git@gitlab.example-corp.com:team/web.git"
ORG_REPO = "gitlab.example-corp.com/team/web"
DAY = 86400
T0 = 1793000000  # fixed clock (2026-10-27)

# Variables from the developer's own shell that would leak into a test machine.
LEAKY_ENV = ("AI_TOOLKIT_DISABLE", "AI_TOOLKIT_CONFIG", "AI_TOOLKIT_NOW", "HINDSIGHT_DISABLE", "HINDSIGHT_NO_LLM",
             "FAKE_LLM_MODE", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_ROOT")

DEFAULT_STORES = [
    {"name": "org", "path": "~/.ai-memory/org", "remote": "", "match": ["*example-corp.com/*"]},
    {"name": "personal", "path": "~/.ai-memory/personal", "remote": "", "match": ["*"], "default": True},
]


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in LEAKY_ENV}
    env.update(extra)
    return env


class Env(object):
    """One machine. `init_stores=False` leaves the stores for the test to create."""

    def __init__(self, init_stores=True, **cfg_overrides):
        self.home = tempfile.mkdtemp(prefix="hs-test-")
        self.now = T0
        self.env = clean_env(HOME=self.home, HINDSIGHT_LLM_CMD="%s %s" % (sys.executable, FAKE_LLM),
                             HINDSIGHT_NO_BACKGROUND="1")
        cfg = {"stores": [dict(s) for s in DEFAULT_STORES]}
        cfg.update(cfg_overrides)
        self.config_file = os.path.join(self.home, ".config", "ai-toolkit", "config.json")
        self._write_config({"hindsight": cfg})
        self.state = os.path.join(self.home, ".local", "state", "ai-toolkit", "hindsight")
        self.queue = os.path.join(self.state, "queue.jsonl")
        if init_stores:
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
        e = dict(self.env, AI_TOOLKIT_NOW=str(self.now))
        e.update(extra or {})
        return e

    def hook(self, name, payload, extra_env=None, stdin=None):
        """Run hindsight.<name> the way hooks/hooks.json does. `name` may carry the old ".py" suffix."""
        target = "hindsight." + name[:-3] if name.endswith(".py") else "hindsight." + name
        r = subprocess.run([sys.executable, RUN, target], input=stdin if stdin is not None else json.dumps(payload),
                           capture_output=True, text=True, env=self._env(extra_env), timeout=30)
        assert r.returncode == 0, r.stderr
        return r

    def hs(self, *args, stdin=None, cwd=None, extra_env=None, check=True):
        r = subprocess.run([sys.executable, HS] + list(args), input=stdin, cwd=cwd,
                           capture_output=True, text=True, env=self._env(extra_env), timeout=60)
        if check:
            assert r.returncode == 0, "hs %s failed:\n%s\n%s" % (" ".join(args), r.stdout, r.stderr)
        return r

    # ----- a whole simulated session -----
    def session(self, sid, cwd, prompts=(), advance=DAY):
        """SessionStart -> prompts -> SessionEnd -> distill. Returns the SessionStart output (dict or None)."""
        out = self.hook("session_start", {"session_id": sid, "cwd": cwd, "source": "startup"}).stdout.strip()
        for p in prompts:
            self.now += 60
            self.hook("capture_prompt", {"session_id": sid, "cwd": cwd, "prompt": p})
        self.now += 60
        self.hook("session_end", {"session_id": sid, "cwd": cwd, "reason": "exit"})
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
        from ai_toolkit.hindsight.lessons import load_store
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

    # ----- config -----
    def _write_config(self, data):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(data, f)

    def config(self):
        with open(self.config_file) as f:
            return json.load(f)["hindsight"]

    def set_config(self, **kv):
        cfg = self.config()
        cfg.update(kv)
        data = json.load(open(self.config_file))
        data["hindsight"] = cfg
        self._write_config(data)

    def cleanup(self):
        shutil.rmtree(self.home, ignore_errors=True)
