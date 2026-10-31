"""Step 3 — Curate: promote on repeat hits, merge duplicates, hand edits, retire, cap, review."""
import unittest

from helpers import DAY, ORG_REMOTE, ORG_REPO, Env

REPO_FILE = "active/repo-gitlab.example-corp.com__team__web.md"


class TestCurate(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])

    def tearDown(self):
        self.e.cleanup()

    def pnpm_lesson(self):
        return next(l for l in self.e.lessons("org").values() if "pnpm" in l.text)

    def test_promote_after_two_sessions_not_two_moments(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm", "I said use pnpm!"])
        self.assertEqual(self.pnpm_lesson().status, "candidate", "two hits in ONE session must not promote")
        self.e.session("s2", self.org, ["no, use pnpm"])
        l = self.pnpm_lesson()
        self.assertEqual(l.status, "active")
        self.assertIn(l.id, self.e.read("org", REPO_FILE))
        self.assertNotIn(l.id, self.e.read("org", "candidates.md"))
        self.assertTrue(any(e["t"] == "promote" and e["by"] == "auto" for e in self.e.events("org")))

    def test_promote_at_three(self):
        self.e.set_config(promote_at=3)
        self.e.session("s1", self.org, ["no, use pnpm"])
        self.e.session("s2", self.org, ["no, use pnpm"])
        self.assertEqual(self.pnpm_lesson().status, "candidate")
        self.e.session("s3", self.org, ["no, use pnpm"])
        self.assertEqual(self.pnpm_lesson().status, "active")

    def test_near_duplicate_candidates_merge(self):
        self.e.hs("distill", "--no-llm")  # no-op, creates nothing
        self.e.write("org", "candidates.md",
                     "# Candidate lessons\n\n"
                     "## L-aaaaaa — Use pnpm instead of npm for installs\n- scope: repo:%s\n- status: candidate\n"
                     "- created: 2026-10-01\n\n"
                     "## L-bbbbbb — Use pnpm instead of npm for package installs\n- scope: repo:%s\n"
                     "- status: candidate\n- created: 2026-10-02\n" % (ORG_REPO, ORG_REPO))
        r = self.e.hs("curate", "--store", "org")
        self.assertIn("merge L-bbbbbb -> L-aaaaaa", r.stdout)
        ls = self.e.lessons("org")
        self.assertEqual(list(ls), ["L-aaaaaa"])
        self.assertEqual(ls["L-aaaaaa"].merged, ["L-bbbbbb"])

    def test_hand_edit_pins_and_status_edit_counts(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        l = self.pnpm_lesson()
        txt = self.e.read("org", "candidates.md")
        txt = txt.replace(l.text, "Always use pnpm (never npm or yarn)").replace("status: candidate", "status: active")
        self.e.write("org", "candidates.md", txt)
        r = self.e.hs("curate", "--store", "org")
        self.assertIn("pinned", r.stdout)
        l2 = self.e.lessons("org")[l.id]
        self.assertEqual((l2.status, l2.pinned, l2.text), ("active", True, "Always use pnpm (never npm or yarn)"))
        self.assertIn(l.id, self.e.read("org", REPO_FILE), "status edit moved the section")
        self.assertTrue(any(e["t"] == "promote" and e.get("by") == "user" for e in self.e.events("org")))

    def test_hand_delete_is_logged(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        l = self.pnpm_lesson()
        self.e.write("org", "candidates.md", "# Candidate lessons\n")
        self.e.hs("curate", "--store", "org")
        self.assertTrue(any(e["t"] == "delete" and e["lesson"] == l.id for e in self.e.events("org")))

    def test_retire_unused_but_not_pinned(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        self.e.hs("capture", stdin="Run make lint before committing\n", cwd=self.org)
        self.e.hs("distill")
        lint = next(l for l in self.e.lessons("org").values() if "lint" in l.text)
        self.e.hs("edit", lint.id, extra_env={"EDITOR": "sed -i '' -e s/committing/every_commit/"})
        self.assertTrue(self.e.lessons("org")[lint.id].pinned)
        self.e.now += 61 * DAY
        r = self.e.hs("curate", "--store", "org")
        self.assertIn("unused for", r.stdout)
        ls = self.e.lessons("org")
        self.assertEqual(self.pnpm_lesson().status, "retired")
        self.assertEqual(ls[lint.id].status, "active", "pinned lessons are never auto-retired")
        self.assertIn("unused for", self.e.read("org", "archive.md"))

    def test_cap_per_scope(self):
        self.e.set_config(cap_per_scope=2)
        for t in ("Run make lint first", "Prefer named exports", "Keep components under 200 lines"):
            self.e.hs("capture", stdin=t, cwd=self.org)
        self.e.hs("distill")
        active = [l for l in self.e.lessons("org").values() if l.status == "active"]
        self.assertEqual(len(active), 2)
        self.assertIn("over cap", self.e.read("org", "archive.md"))

    def test_review_list_and_cli_status_changes(self):
        self.e.session("s1", self.org, ["no, use pnpm"])
        self.e.session("s2", self.org, ["no, use pnpm"])
        l = self.pnpm_lesson()
        r = self.e.hs("review", "--list")
        self.assertIn(l.id, r.stdout)
        # interactive: keep it
        self.e.hs("review", stdin="k\n")
        self.assertNotIn(l.id, self.e.hs("review", "--list").stdout)
        self.e.hs("dismiss", l.id, "--reason", "team switched to bun")
        self.assertEqual(self.e.lessons("org")[l.id].status, "dismissed")
        self.e.hs("restore", l.id)
        self.assertEqual(self.e.lessons("org")[l.id].status, "candidate")
        self.e.hs("rm", l.id, "-y")
        self.assertNotIn(l.id, self.e.lessons("org"))
        self.assertNotIn(l.id, self.e.hs("list", "--status", "all", check=False).stdout)
        self.assertTrue(any(e["t"] == "delete" for e in self.e.events("org")))


if __name__ == "__main__":
    unittest.main()
