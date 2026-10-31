"""Step 2 — Distill: queue -> candidate lessons (LLM + rule fallback), privacy, queue handling."""
import json
import os
import unittest

from helpers import ORG_REMOTE, ORG_REPO, Env

REJ = ("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, "
       "the new_string was NOT written to the file). STOP what you are doing.\n\nNote: ...")


class TestDistill(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])

    def tearDown(self):
        self.e.cleanup()

    def prompt(self, sid, text, cwd=None):
        self.e.now += 30
        self.e.hook("capture_prompt.py", {"session_id": sid, "cwd": cwd or self.org, "prompt": text})

    def test_llm_distill_creates_candidate_and_empties_queue(self):
        self.prompt("s1", "Here's context about billing. No, use pnpm instead of npm.")
        self.prompt("s1", "no, that's wrong NOISE I meant my own variable")
        r = self.e.hs("distill")
        self.assertIn("Use pnpm, never npm, in this repo", r.stdout)
        self.assertEqual(self.e.queued(), [])
        ls = self.e.lessons("org")
        self.assertEqual(len(ls), 1)
        l = list(ls.values())[0]
        self.assertEqual((l.status, l.scope), ("candidate", "repo:" + ORG_REPO))
        self.assertEqual(l.files, ["package.json"])
        self.assertIn(l.id, self.e.read("org", "candidates.md"))
        moments = [e for e in self.e.events("org") if e["t"] == "moment"]
        self.assertEqual(sorted(m["noise"] for m in moments), [False, True])
        self.assertIn("distill", self.e.git_log("org"))
        # Nothing landed in the personal store.
        self.assertEqual(self.e.lessons("personal"), {})

    def test_store_never_contains_raw_clauses(self):
        self.prompt("s1", "no, use pnpm instead of npm because billing-secret-project-x")
        self.e.hs("distill")
        txt = self.e.all_store_text("org")
        self.assertNotIn("billing-secret-project-x", txt)
        self.assertNotIn("instead of npm because", txt)

    def test_rule_fallback_when_llm_unavailable(self):
        self.prompt("s1", "no, use vitest instead of jest")
        r = self.e.hs("distill", extra_env={"FAKE_LLM_MODE": "fail"})
        self.assertIn("via rules", r.stdout)
        lid = list(self.e.lessons("org"))[0]
        # garbage output -> rules again; same correction in a new session is a hit on the same lesson
        self.prompt("s2", "no, use vitest instead of jest")
        r = self.e.hs("distill", extra_env={"FAKE_LLM_MODE": "garbage"})
        self.assertIn("hits: " + lid, r.stdout)
        ls = list(self.e.lessons("org").values())
        self.assertEqual([l.text for l in ls], ["Use vitest instead of jest"])

    def test_rule_templates(self):
        from distill import rule_lesson
        cases = {
            "no, use pnpm instead of npm": "Use pnpm instead of npm",
            "don't add type hints everywhere.": "Don't add type hints everywhere",
            "No. Never commit directly to main": "Never commit directly to main",
            "why did you change the API?": None,
        }
        for clause, want in cases.items():
            self.assertEqual(rule_lesson({"kind": "prompt", "clause": clause}), want, clause)

    def test_explicit_goes_straight_to_active(self):
        self.e.hs("capture", stdin="Run make lint before committing\n", cwd=self.org)
        self.e.hs("distill")
        l = list(self.e.lessons("org").values())[0]
        self.assertEqual(l.status, "active")
        self.assertTrue(self.e.read("org", "active/repo-gitlab.example-corp.com__team__web.md"))

    def test_rejection_followed_by_prompt_counts_once(self):
        t = os.path.join(self.e.home, "t.jsonl")
        with open(t, "w") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "u1", "name": "Bash", "input": {"command": "npm i"}}]}}) + "\n")
            f.write(json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "u1", "content": REJ, "is_error": True}]}}) + "\n")
        self.e.hook("capture_transcript.py", {"session_id": "s1", "cwd": self.org, "transcript_path": t})
        self.prompt("s1", "no, use pnpm instead of npm")
        self.assertEqual(len(self.e.queued()), 2)
        self.e.hs("distill")
        moments = [e for e in self.e.events("org") if e["t"] == "moment"]
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0]["kind"], "prompt")

    def test_dry_run_writes_nothing(self):
        self.prompt("s1", "no, use pnpm instead of npm")
        r = self.e.hs("distill", "--dry-run")
        self.assertIn("[dry-run]", r.stdout)
        self.assertEqual(len(self.e.queued()), 1)
        self.assertEqual(self.e.lessons("org"), {})

    def test_moments_arriving_during_distill_are_kept(self):
        # Simulate: distill processes a snapshot; a moment appended afterwards must survive.
        self.prompt("s1", "no, use pnpm instead of npm")
        import distill as D
        orig = D._plan_group

        def plan_and_capture(*a, **k):
            self.prompt("s2", "don't add docstrings to private helpers")
            return orig(*a, **k)
        D._plan_group = plan_and_capture
        old_env = dict(os.environ)
        try:
            os.environ.update(self.e._env())
            D.distill(cfg=None)
        finally:
            D._plan_group = orig
            os.environ.clear()
            os.environ.update(old_env)
        q = self.e.queued()
        self.assertEqual(len(q), 1)
        self.assertIn("docstrings", q[0]["clause"])

    def test_session_end_hook_records_session(self):
        self.e.hook("session_end.py", {"session_id": "s9", "cwd": self.org, "reason": "exit"})
        ev = [e for e in self.e.events("org") if e["t"] == "session"]
        self.assertEqual((ev[0]["phase"], ev[0]["repo"]), ("end", ORG_REPO))


if __name__ == "__main__":
    unittest.main()
