"""Step 1 — Capture. Runs fully offline in a throwaway HOME."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(MOD))
sys.path.insert(0, os.path.join(MOD, "lib"))

from detect import detect  # noqa: E402
from redact import redact, scan  # noqa: E402
from common import normalize_remote  # noqa: E402

FAKE_SECRET = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


class Env:
    """Isolated HOME + config with an org store and a personal default store."""

    def __init__(self):
        self.home = tempfile.mkdtemp(prefix="hs-test-")
        self.env = dict(os.environ, HOME=self.home)
        for k in ("HINDSIGHT_DISABLE", "HINDSIGHT_CONFIG", "HINDSIGHT_STATE_DIR"):
            self.env.pop(k, None)
        cfg_dir = os.path.join(self.home, ".config", "ai-toolkit")
        os.makedirs(cfg_dir)
        with open(os.path.join(cfg_dir, "hindsight.json"), "w") as f:
            json.dump({"stores": [
                {"name": "org", "path": "~/.ai-memory/org", "remote": "", "match": ["*example-corp.com/*"]},
                {"name": "personal", "path": "~/.ai-memory/personal", "remote": "", "match": ["*"], "default": True},
            ]}, f)
        self.queue = os.path.join(self.home, ".local", "state", "hindsight", "queue.jsonl")

    def repo(self, name, remote=None, markers=()):
        d = os.path.join(self.home, "code", name)
        os.makedirs(d)
        subprocess.run(["git", "init", "-q", d], check=True, env=self.env)
        if remote:
            subprocess.run(["git", "-C", d, "remote", "add", "origin", remote], check=True, env=self.env)
        for m in markers:
            open(os.path.join(d, m), "w").close()
        return d

    def hook(self, script, payload, extra_env=None):
        env = dict(self.env, **(extra_env or {}))
        r = subprocess.run([os.path.join(MOD, "hooks", script)], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, r.stderr
        return r

    def hs(self, *args, stdin=None, cwd=None):
        return subprocess.run([os.path.join(MOD, "bin", "hs")] + list(args), input=stdin, cwd=cwd,
                              capture_output=True, text=True, env=self.env, timeout=20)

    def queued(self):
        if not os.path.exists(self.queue):
            return []
        return [json.loads(l) for l in open(self.queue) if l.strip()]

    def cleanup(self):
        shutil.rmtree(self.home, ignore_errors=True)


class TestDetector(unittest.TestCase):
    POSITIVE = [
        "no, use pnpm instead of npm",
        "No. Don't add comments to every line.",
        "I said not to touch the tests",
        "why did you change the API signature?",
        "revert that, it was fine before",
        "stop adding try/except everywhere",
        "that's wrong, the endpoint is /v2/users",
        "use vitest instead",
        "you forgot to update the types again",
        "don't mock the database in these tests",
        "Not like that — keep the function pure",
    ]
    NEGATIVE = [
        "add a no-op handler for the close event",
        "I don't know why the build fails, can you check?",
        "no problem, thanks!",
        "write a function that returns true if the list is not empty",
        "refactor the auth module into smaller files",
        "/lesson use pnpm",
        "can you explain how hooks work?",
        "never mind",
    ]

    def test_positives(self):
        for p in self.POSITIVE:
            self.assertIsNotNone(detect(p), "missed: %r" % p)

    def test_negatives(self):
        for p in self.NEGATIVE:
            self.assertIsNone(detect(p), "false positive: %r -> %r" % (p, detect(p)))

    def test_clause_is_only_correction_sentences(self):
        prompt = "Here is a lot of context about the module. It handles billing. No, use pnpm instead of npm."
        hit = detect(prompt)
        self.assertIn("pnpm", hit["clause"])
        self.assertNotIn("billing", hit["clause"])

    def test_clause_capped(self):
        hit = detect("no, " + "use the other approach " * 30)
        self.assertLessEqual(len(hit["clause"]), 200)


class TestRedaction(unittest.TestCase):
    def test_secrets(self):
        cases = [FAKE_SECRET, "sk-ant-api03-abcdefghijklmnopqrstuv", "glpat-abcdefghijklmnopqrst",
                 "AKIAABCDEFGHIJKLMNOP", "password=hunter2hunter2", "me@example.com",
                 "https://user:pa55word@host.com/repo", "Bearer abcdefghijklmnopqrstuvwxyz123456",
                 "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"]
        for c in cases:
            out = redact("don't use %s here" % c)
            self.assertIn("[REDACTED", out, c)
            self.assertEqual(scan(out), [], "scanner still flags %r -> %r" % (c, out))

    def test_plain_text_untouched(self):
        s = "don't use the auth token flow, use the session cookie instead"
        self.assertEqual(redact(s), s)

    def test_home_path(self):
        self.assertEqual(redact(os.path.expanduser("~/code/x.py")), "~/code/x.py")


class TestNormalizeRemote(unittest.TestCase):
    def test_forms(self):
        exp = "gitlab.example-corp.com/team/web"
        for u in ["git@gitlab.example-corp.com:team/web.git",
                  "https://user:tok@gitlab.example-corp.com/team/web.git",
                  "ssh://git@gitlab.example-corp.com:2222/team/web"]:
            self.assertEqual(normalize_remote(u), exp, u)


class TestCaptureHooks(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        self.e.cleanup()

    def test_prompt_routing_and_privacy(self):
        org = self.e.repo("web", "git@gitlab.example-corp.com:team/web.git", ["package.json"])
        mine = self.e.repo("side", "git@github.com:me/side.git", ["pyproject.toml"])
        prompt = "Context: billing service secret token=%s. No, use pnpm instead of npm." % FAKE_SECRET
        self.e.hook("capture_prompt.py", {"session_id": "s1", "cwd": org, "prompt": prompt})
        self.e.hook("capture_prompt.py", {"session_id": "s2", "cwd": mine, "prompt": "don't add type hints everywhere"})
        self.e.hook("capture_prompt.py", {"session_id": "s3", "cwd": self.e.home, "prompt": "wrong, I said use tabs"})
        self.e.hook("capture_prompt.py", {"session_id": "s4", "cwd": mine, "prompt": "please add a README"})
        q = self.e.queued()
        self.assertEqual([r["store"] for r in q], ["org", "personal", "personal"])
        self.assertEqual(q[0]["repo"], "gitlab.example-corp.com/team/web")
        self.assertEqual(q[0]["langs"], ["js"])
        self.assertEqual(q[1]["langs"], ["python"])
        self.assertEqual(q[2]["repo"], "")
        raw = open(self.e.queue).read()
        self.assertNotIn(FAKE_SECRET, raw)
        self.assertNotIn("billing", raw, "non-correction sentences must not be stored")
        self.assertNotIn("prompt\": \"", raw)

    def test_duplicate_not_requeued(self):
        d = self.e.repo("x", "git@github.com:me/x.git")
        for _ in range(2):
            self.e.hook("capture_prompt.py", {"session_id": "s", "cwd": d, "prompt": "no, use pnpm"})
        self.assertEqual(len(self.e.queued()), 1)

    def test_disabled_env_noop(self):
        d = self.e.repo("x", "git@github.com:me/x.git")
        self.e.hook("capture_prompt.py", {"session_id": "s", "cwd": d, "prompt": "no, use pnpm"},
                    {"HINDSIGHT_DISABLE": "1"})
        self.assertEqual(self.e.queued(), [])

    def test_garbage_input_never_fails(self):
        r = subprocess.run([os.path.join(MOD, "hooks", "capture_prompt.py")], input="not json",
                           capture_output=True, text=True, env=self.e.env)
        self.assertEqual(r.returncode, 0)

    def _transcript(self, path, entries, mode="w"):
        with open(path, mode) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    @staticmethod
    def _use(tid, name, fp=None):
        inp = {"file_path": fp, "old_string": "SECRET_DIFF_CONTENT"} if fp else {"command": "rm -rf build"}
        return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}

    @staticmethod
    def _result(tid, text):
        return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": True}]}}

    REJ = ("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file "
           "edit, the new_string was NOT written to the file). STOP what you are doing and wait for the user to "
           "tell you how to proceed.\n\nNote: The user's next message may contain a correction or preference.")
    REJ_FB = ("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file "
              "edit, the new_string was NOT written to the file). To tell you how to proceed, the user said:\n"
              "keep the old name, contact me@example.com\n\nNote: The user's next message may contain a correction.")

    def test_transcript_rejections_incremental(self):
        d = self.e.repo("web", "git@gitlab.example-corp.com:team/web.git")
        t = os.path.join(self.e.home, "t.jsonl")
        self._transcript(t, [
            self._use("u1", "Edit", d + "/src/App.tsx"), self._result("u1", self.REJ_FB),
            self._use("u2", "Bash"), self._result("u2", self.REJ),
            self._use("u3", "Read", d + "/a.py"), self._result("u3", "file contents"),
        ])
        payload = {"session_id": "s1", "cwd": d, "transcript_path": t}
        self.e.hook("capture_transcript.py", payload)
        q = self.e.queued()
        self.assertEqual([(r["tool"], r["file_ext"]) for r in q], [("Edit", "tsx"), ("Bash", "")])
        self.assertEqual(q[0]["clause"], "keep the old name, contact [REDACTED:email]")
        self.assertEqual(q[1]["clause"], "")
        self.assertEqual([r["rejected"] for r in q], ["Edit App.tsx", "Bash: rm -rf build"])
        raw = open(self.e.queue).read()
        self.assertNotIn("SECRET_DIFF_CONTENT", raw)
        # Re-run: nothing new.
        self.e.hook("capture_transcript.py", payload)
        self.assertEqual(len(self.e.queued()), 2)
        # Append a new rejection: only that one is added.
        self._transcript(t, [self._use("u4", "Write", d + "/b.py"), self._result("u4", self.REJ)], mode="a")
        self.e.hook("capture_transcript.py", payload)
        q = self.e.queued()
        self.assertEqual(len(q), 3)
        self.assertEqual((q[2]["tool"], q[2]["file_ext"], q[2]["store"]), ("Write", "py", "org"))

    def test_marker_in_successful_output_is_not_a_rejection(self):
        d = self.e.repo("web", "git@github.com:me/web.git")
        t = os.path.join(self.e.home, "t.jsonl")
        ok = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u1",
                                                       "content": 'REJECT = "%s"' % self.REJ, "is_error": False}]}}
        quoted = self._result("u2", "grep hit: " + self.REJ)
        self._transcript(t, [self._use("u1", "Bash"), ok, self._use("u2", "Bash"), quoted])
        self.e.hook("capture_transcript.py", {"session_id": "s", "cwd": d, "transcript_path": t})
        self.assertEqual(self.e.queued(), [])

    def test_partial_last_line_is_retried(self):
        d = self.e.repo("x", "git@github.com:me/x.git")
        t = os.path.join(self.e.home, "t.jsonl")
        self._transcript(t, [self._use("u1", "Edit", d + "/a.go")])
        with open(t, "a") as f:
            f.write(json.dumps(self._result("u1", self.REJ))[:40])  # half-written line
        payload = {"session_id": "s", "cwd": d, "transcript_path": t}
        self.e.hook("capture_transcript.py", payload)
        self.assertEqual(self.e.queued(), [])
        with open(t, "w") as f:  # complete it
            f.write(json.dumps(self._use("u1", "Edit", d + "/a.go")) + "\n" + json.dumps(self._result("u1", self.REJ)) + "\n")
        self.e.hook("capture_transcript.py", payload)
        self.assertEqual(len(self.e.queued()), 1)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        self.e.cleanup()

    def test_explicit_capture_and_status(self):
        d = self.e.repo("web", "git@gitlab.example-corp.com:team/web.git")
        r = self.e.hs("capture", stdin="Use pnpm, never npm, in this repo\n", cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        q = self.e.queued()
        self.assertEqual((q[0]["kind"], q[0]["store"]), ("explicit", "org"))
        r = self.e.hs("status", cwd=d)
        self.assertIn("store=org", r.stdout)
        self.assertIn("explicit=1", r.stdout)

    def test_store_init(self):
        r = self.e.hs("store", "init")
        self.assertEqual(r.returncode, 0, r.stderr)
        for s in ("org", "personal"):
            p = os.path.join(self.e.home, ".ai-memory", s)
            self.assertTrue(os.path.isdir(os.path.join(p, ".git")))
            self.assertTrue(os.path.exists(os.path.join(p, "lessons", "candidates.md")))
        self.assertIn("already set up", self.e.hs("store", "init").stdout)


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        os.remove(os.path.join(self.e.home, ".config", "ai-toolkit", "hindsight.json"))
        os.makedirs(os.path.join(self.e.home, ".claude"))
        self.settings = os.path.join(self.e.home, ".claude", "settings.json")
        self.original = {"model": "opus", "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "/usr/local/bin/cc-status"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "/usr/local/bin/cc-status"}]}]}}
        json.dump(self.original, open(self.settings, "w"))

    def tearDown(self):
        self.e.cleanup()

    def run_sh(self, *args):
        r = subprocess.run(list(args), capture_output=True, text=True, env=self.e.env, cwd=REPO, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_install_idempotent_and_uninstall_restores(self):
        self.run_sh("./install.sh", "--steps", "1")
        self.run_sh("./install.sh", "--steps", "1")
        s = json.load(open(self.settings))
        cmds = [h["command"] for ev in s["hooks"].values() for g in ev for h in g["hooks"]]
        self.assertEqual(sum("capture_prompt.py" in c for c in cmds), 1)
        self.assertEqual(sum("capture_transcript.py" in c for c in cmds), 1)
        self.assertEqual(sum("cc-status" in c for c in cmds), 2, "existing hooks preserved")
        self.assertEqual(s["model"], "opus")
        self.assertTrue(os.path.islink(os.path.join(self.e.home, ".claude", "ai-toolkit")))
        self.assertTrue(os.path.exists(os.path.join(self.e.home, ".local", "bin", "hs")))
        self.assertTrue(os.path.exists(os.path.join(self.e.home, ".claude", "commands", "lesson.md")))
        self.assertTrue(os.path.isdir(os.path.join(self.e.home, ".ai-memory", "personal", ".git")))
        # Hook command as registered actually runs (uses $HOME symlink path).
        cmd = [c for c in cmds if "capture_prompt.py" in c][0]
        r = subprocess.run(["bash", "-c", cmd], input=json.dumps({"session_id": "s", "cwd": self.e.home, "prompt": "no, use pnpm"}),
                           capture_output=True, text=True, env=self.e.env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.e.queued()), 1)
        self.run_sh("./uninstall.sh")
        self.assertEqual(json.load(open(self.settings)), self.original)
        self.assertFalse(os.path.exists(os.path.join(self.e.home, ".local", "bin", "hs")))


if __name__ == "__main__":
    unittest.main()
