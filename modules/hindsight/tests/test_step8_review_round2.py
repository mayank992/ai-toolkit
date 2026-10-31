"""Regression tests for the second code review round (2026-11-01)."""
import json
import os
import sys
import unittest

from helpers import MOD, ORG_REMOTE, Env

sys.path.insert(0, os.path.join(MOD, "lib"))

DAY = 86400


class TestReviewRound2(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])

    def tearDown(self):
        self.e.cleanup()

    def pnpm(self):
        return next(l for l in self.e.lessons("org").values() if "pnpm" in l.text)

    # 1. a lesson the developer retired is not brought back by distill
    def test_user_retired_lesson_stays_retired(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        lid = self.pnpm().id
        self.e.hs("retire", lid, "--reason", "no longer relevant")
        self.e.session("s2", self.org, ["no, use pnpm"])
        self.assertEqual(self.e.lessons("org")[lid].status, "retired")
        self.assertFalse(any(e["t"] == "restore" and e.get("by") == "auto" for e in self.e.events("org")))

    def test_user_dismissed_by_hand_edit_stays_dismissed(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        lid = self.pnpm().id
        self.e.hs("dismiss", lid, "--reason", "one-off")
        self.e.session("s2", self.org, ["no, use pnpm"])
        self.assertEqual(self.e.lessons("org")[lid].status, "dismissed")

    # 2. a revived lesson starts its hit count over: no instant re-promotion
    def test_revived_lesson_must_earn_promotion_again(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        self.e.session("s2", self.org, ["no, use pnpm instead of npm"])
        lid = self.pnpm().id
        self.assertEqual(self.e.lessons("org")[lid].status, "active")
        self.e.now += 61 * DAY
        self.e.hs("curate")
        self.assertEqual(self.e.lessons("org")[lid].status, "retired")
        self.e.session("s3", self.org, ["no, use pnpm"])
        self.assertEqual(self.e.lessons("org")[lid].status, "candidate", "2 old hits must not count")
        self.e.session("s4", self.org, ["no, use pnpm"])
        self.assertEqual(self.e.lessons("org")[lid].status, "active")

    # 3. dry-run sees its own in-memory merges when deciding promotions
    def test_curate_dry_run_reports_promotion_after_merge(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        self.e.session("s2", self.org, ["no, indent with tabs"])
        # Two near-duplicate candidates in one scope, one hit session each.
        a = self.pnpm()
        b_id = "L-b0b0b0"
        text = self.e.read("org", "candidates.md")
        text += "\n## %s — Use pnpm, never npm, in this repo please\n- scope: %s\n- status: candidate\n" \
                "- created: 2099-01-01\n" % (b_id, a.scope)
        self.e.write("org", "candidates.md", text)
        with open(os.path.join(self.e.store_path("org"), "events", "seed.jsonl"), "a") as f:
            f.write(json.dumps({"t": "moment", "ts": "2099-01-01T00:00:00Z", "session_id": "sx", "repo": "",
                                "lesson": b_id, "noise": False, "kind": "prompt"}) + "\n")
        dry = self.e.hs("curate", "--dry-run").stdout
        self.assertIn("merge %s -> %s" % (b_id, a.id), dry)
        self.assertIn("promote %s" % a.id, dry)
        self.assertEqual(self.e.lessons("org")[a.id].status, "candidate", "dry run wrote nothing")

    # 4. redaction: single-case + digit tokens are caught, paths still are not
    def test_redaction_single_case_tokens(self):
        from redact import redact
        for tok in ("abcdefghijklmnopqrstuvwxyz0123456789abcdefgh", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGH"):
            self.assertNotIn(tok, redact("token %s here" % tok))
        path = "frontend/src/components/dashboard/widgets/RevenueChart.tsx"
        self.assertIn(path, redact("edit %s" % path))
        self.assertIn("thisIsAVeryLongCamelCaseIdentifierWithoutDigits", redact(
            "rename thisIsAVeryLongCamelCaseIdentifierWithoutDigits"))

    # 5. softened lead words don't leak into the clause
    def test_softener_sentence_not_in_clause(self):
        from detect import detect
        d = detect("No worries. Revert that change.")
        self.assertEqual(d["clause"], "Revert that change.")
        self.assertIsNone(detect("No problem, thanks!"))
        self.assertEqual(detect("Thanks. No, use pnpm instead.")["clause"], "No, use pnpm instead.")

    # 6. scope casing / synonyms from the LLM
    def test_scope_normalization(self):
        from distill import _norm_scope
        repo = "github.com/me/x"
        self.assertEqual(_norm_scope("Global", repo, []), "global")
        self.assertEqual(_norm_scope("all", repo, []), "global")
        self.assertEqual(_norm_scope("LANG:Python", repo, ["python"]), "lang:python")
        self.assertEqual(_norm_scope("lang:rust", repo, ["python"]), "repo:" + repo)
        self.assertEqual(_norm_scope("repo", repo, []), "repo:" + repo)

    # 7. a catch-all glob on a non-default store can't swallow every repo
    def test_route_ignores_catch_all_on_non_default(self):
        from common import route_store
        cfg = {"stores": [{"name": "work", "match": ["*"]},
                          {"name": "org", "match": ["*example-corp.com/*"]},
                          {"name": "personal", "match": ["*"], "default": True}]}
        self.assertEqual(route_store(cfg, "github.com/me/side")["name"], "personal")
        self.assertEqual(route_store(cfg, "gitlab.example-corp.com/team/web")["name"], "org")
        cfg_path = os.path.join(self.e.home, ".config", "ai-toolkit", "hindsight.json")
        with open(cfg_path) as f:
            cfg = json.load(f)
        cfg["stores"].insert(0, {"name": "work", "path": "~/.ai-memory/work", "match": ["*"]})
        with open(cfg_path, "w") as f:
            json.dump(cfg, f)
        out = self.e.hs("doctor", check=False).stdout
        self.assertIn("catch-all match", out)

    # 8. a failed save writes no events and keeps the moments queued
    def test_save_failure_writes_no_events(self):
        import distill as D
        self.e.hook("capture_prompt.py", {"session_id": "s1", "cwd": self.org, "prompt": "no, use pnpm instead of npm"})
        orig = D.save_store

        def boom(*a, **k):
            raise OSError("disk full")
        D.save_store = boom
        old_env = dict(os.environ)
        try:
            os.environ.update(self.e._env())
            with self.assertRaises(OSError):
                D.distill(cfg=None)
        finally:
            D.save_store = orig
            os.environ.clear()
            os.environ.update(old_env)
        self.assertEqual([e for e in self.e.events("org") if e["t"] == "moment"], [])
        self.assertEqual(len(self.e.queued()), 1)
        self.e.hs("distill")
        self.assertEqual(len([e for e in self.e.events("org") if e["t"] == "moment"]), 1)


if __name__ == "__main__":
    unittest.main()
