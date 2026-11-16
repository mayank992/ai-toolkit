"""Status edge cases: what the developer decided by hand stays decided; scope and store routing rules."""
import json
import os
import unittest

from support.hindsight_env import ORG_REMOTE, Env


DAY = 86400


def _iso(t):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class TestStatusEdgeCases(unittest.TestCase):
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
        from ai_toolkit.hindsight.redact import redact
        for tok in ("abcdefghijklmnopqrstuvwxyz0123456789abcdefgh", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGH"):
            self.assertNotIn(tok, redact("token %s here" % tok))
        path = "frontend/src/components/dashboard/widgets/RevenueChart.tsx"
        self.assertIn(path, redact("edit %s" % path))
        self.assertIn("thisIsAVeryLongCamelCaseIdentifierWithoutDigits", redact(
            "rename thisIsAVeryLongCamelCaseIdentifierWithoutDigits"))

    # 5. softened lead words don't leak into the clause
    def test_softener_sentence_not_in_clause(self):
        from ai_toolkit.hindsight.detect import detect
        d = detect("No worries. Revert that change.")
        self.assertEqual(d["clause"], "Revert that change.")
        self.assertIsNone(detect("No problem, thanks!"))
        self.assertEqual(detect("Thanks. No, use pnpm instead.")["clause"], "No, use pnpm instead.")

    # 6. scope casing / synonyms from the LLM
    def test_scope_normalization(self):
        from ai_toolkit.hindsight.distill import _norm_scope
        repo = "github.com/me/x"
        self.assertEqual(_norm_scope("Global", repo, []), "global")
        self.assertEqual(_norm_scope("all", repo, []), "global")
        self.assertEqual(_norm_scope("LANG:Python", repo, ["python"]), "lang:python")
        self.assertEqual(_norm_scope("lang:rust", repo, ["python"]), "repo:" + repo)
        self.assertEqual(_norm_scope("repo", repo, []), "repo:" + repo)

    # 7. a catch-all glob on a non-default store can't swallow every repo
    def test_route_ignores_catch_all_on_non_default(self):
        from ai_toolkit.hindsight.config import route_store
        cfg = {"stores": [{"name": "work", "match": ["*"]},
                          {"name": "org", "match": ["*example-corp.com/*"]},
                          {"name": "personal", "match": ["*"], "default": True}]}
        self.assertEqual(route_store(cfg, "github.com/me/side")["name"], "personal")
        self.assertEqual(route_store(cfg, "gitlab.example-corp.com/team/web")["name"], "org")
        stores = self.e.config()["stores"]
        stores.insert(0, {"name": "work", "path": "~/.ai-memory/work", "match": ["*"]})
        self.e.set_config(stores=stores)
        out = self.e.hs("doctor", check=False).stdout
        self.assertIn("catch-all match", out)

    # 8. a failed save writes no events and keeps the moments queued
    def test_save_failure_writes_no_events(self):
        from ai_toolkit.hindsight import distill as D
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

    # 9. doctor only fails on errors from the last week
    def test_doctor_ignores_old_log_errors(self):
        # Regression: one disk-full error made `ait doctor` exit 1 for good.
        from support.hindsight_env import DAY
        os.makedirs(self.e.state, exist_ok=True)
        log = os.path.join(self.e.state, "hindsight.log")
        with open(log, "w") as f:
            f.write("%s capture_transcript error: OSError(28, 'No space left on device')\n" % _iso(self.e.now - 30 * DAY))
        self.assertIn("ok   no errors in log", self.e.hs("doctor", check=False).stdout)
        with open(log, "a") as f:
            f.write("%s capture_prompt error: ValueError('x')\n" % _iso(self.e.now - DAY))
        out = self.e.hs("doctor", check=False).stdout
        self.assertIn("FAIL no errors in log", out)
        self.assertNotIn("No space left", out)

    # 10. SessionEnd starts distill only when there is something to do
    def test_session_end_skips_distill_when_idle(self):
        # Regression: every headless session spawned a distill process that found an empty queue.
        stamp = os.path.join(self.e.state, "distill_started.json")
        started = lambda: json.load(open(stamp))["ts"]
        end = lambda: self.e.hook("session_end", {"session_id": "s", "cwd": self.org, "reason": "other"})
        end()
        first = started()
        self.e.now += 3600
        end()
        self.assertEqual(started(), first, "nothing queued and distill ran within the day")
        self.e.hook("capture_prompt", {"session_id": "s", "cwd": self.org, "prompt": "no, use pnpm instead of npm"})
        end()
        self.assertEqual(started(), self.e.now, "a queued moment is a reason to run")
        self.e.hs("distill")
        self.e.now += 2 * 86400
        end()
        self.assertEqual(started(), self.e.now, "idle for a day: run once so curate still retires and pins")


if __name__ == "__main__":
    unittest.main()
