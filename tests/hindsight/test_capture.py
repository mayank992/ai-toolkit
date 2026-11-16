"""Capture: detector, redaction, remote normalization, the capture hooks and the store CLI. Offline."""
import json
import os
import unittest

from support import hindsight_env

from ai_toolkit.hindsight.detect import detect
from ai_toolkit.hindsight.redact import redact, scan
from ai_toolkit.core.gitutil import normalize_remote

FAKE_SECRET = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

class Env(hindsight_env.Env):
    """Isolated HOME with an org store and a personal default store, not yet initialized."""

    def __init__(self):
        super().__init__(init_stores=False)

    def hs(self, *args, **kw):
        kw.setdefault("check", False)
        return super().hs(*args, **kw)


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
                    {"AI_TOOLKIT_DISABLE": "1"})
        self.assertEqual(self.e.queued(), [])

    def test_garbage_input_never_fails(self):
        r = self.e.hook("capture_prompt", {}, stdin="not json")
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


if __name__ == "__main__":
    unittest.main()
