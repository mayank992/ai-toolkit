"""Step 4 — Inject: SessionStart picks only relevant lessons, within budget, and logs injections."""
import time
import unittest

from helpers import MOD, ORG_REMOTE, ORG_REPO, Env


def lesson_md(id, text, scope, files=""):
    return "## %s — %s\n- scope: %s\n%s- status: active\n- created: 2026-10-01\n\n" % (
        id, text, scope, ("- trigger: files=%s\n" % files) if files else "")


class TestInject(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])
        self.side = self.e.repo("side", "git@github.com:me/side.git", ["pyproject.toml"])
        w = self.e.write
        w("org", "active/repo-gitlab.example-corp.com__team__web.md",
          "# Active\n\n" + lesson_md("L-000001", "Use pnpm, never npm", "repo:" + ORG_REPO, "package.json"))
        w("org", "active/repo-gitlab.example-corp.com__team__other.md",
          "# Active\n\n" + lesson_md("L-000002", "Other repo rule", "repo:gitlab.example-corp.com/team/other"))
        w("org", "active/global.md", "# Active\n\n" + lesson_md("L-000003", "Org-learned global: no emojis", "global"))
        w("personal", "active/global.md", "# Active\n\n" + lesson_md("L-000004", "Keep answers short", "global"))
        w("personal", "active/lang-python.md", "# Active\n\n" + lesson_md("L-000005", "Use pytest, not unittest", "lang:python"))
        w("personal", "active/lang-js.md", "# Active\n\n" + lesson_md("L-000006", "Prefer const over let", "lang:js"))

    def tearDown(self):
        self.e.cleanup()

    def start(self, sid, cwd):
        import json
        out = self.e.hook("session_start.py", {"session_id": sid, "cwd": cwd, "source": "startup"}).stdout
        return json.loads(out) if out.strip() else None

    def test_org_repo_gets_repo_lang_and_global(self):
        out = self.start("s1", self.org)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        for want in ("L-000001", "L-000003", "L-000004", "L-000006"):
            self.assertIn(want, ctx)
        for not_want in ("L-000002", "L-000005"):
            self.assertNotIn(not_want, ctx)
        self.assertTrue(ctx.index("L-000001") < ctx.index("L-000004"), "repo lessons rank first")
        self.assertIn("4 lessons loaded", out["systemMessage"])
        inj = [e for e in self.e.events("org") if e["t"] == "inject"]
        self.assertEqual(sorted(inj[0]["ids"]), ["L-000001", "L-000003", "L-000004", "L-000006"])
        self.assertEqual(self.e.events("personal"), [], "org session events stay in the org store")

    def test_personal_repo(self):
        ctx = self.start("s2", self.side)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("L-000005", ctx)
        self.assertNotIn("L-000001", ctx)
        self.assertNotIn("L-000006", ctx)
        self.assertTrue(any(e["t"] == "inject" for e in self.e.events("personal")))

    def test_budget(self):
        self.e.set_config(inject_budget_lines=2)
        ctx = self.start("s3", self.org)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(ctx.count("- [L-"), 2)

    def test_nothing_to_inject_prints_nothing(self):
        bare = self.e.repo("bare", "git@github.com:me/bare.git")
        self.e.write("personal", "active/global.md", "# Active\n")
        self.e.write("org", "active/global.md", "# Active\n")
        self.assertIsNone(self.start("s4", bare))
        self.assertTrue(any(e["t"] == "session" for e in self.e.events("personal")))

    def test_disabled(self):
        r = self.e.hook("session_start.py", {"session_id": "s", "cwd": self.org}, {"HINDSIGHT_DISABLE": "1"})
        self.assertEqual(r.stdout, "")

    def test_preview_cli(self):
        r = self.e.hs("inject", "--cwd", self.org)
        self.assertIn("Use pnpm, never npm", r.stdout)

    def test_fast(self):
        t = time.time()
        for i in range(5):
            self.start("p%d" % i, self.org)
        self.assertLess((time.time() - t) / 5, 0.5)


if __name__ == "__main__":
    unittest.main()
