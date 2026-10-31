"""Step 5 — Measure: efficacy before/after activation, ineffective flagging, weekly report."""
import json
import os
import unittest

from helpers import DAY, ORG_REMOTE, ORG_REPO, T0, Env


def ts(t):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class TestMeasure(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])

    def tearDown(self):
        self.e.cleanup()

    def seed(self, lesson_id, before, after, injected=True):
        """before/after: lists of pushback counts per session (before / after activation)."""
        lines = []
        t = T0
        repo = ORG_REPO
        lines.append({"t": "create", "ts": ts(t), "lesson": lesson_id, "scope": "repo:" + repo, "status": "candidate"})
        for i, n in enumerate(before):
            t += DAY
            sid = "b%d" % i
            lines.append({"t": "session", "ts": ts(t), "session_id": sid, "repo": repo, "langs": [], "phase": "start"})
            for _ in range(n):
                lines.append({"t": "moment", "ts": ts(t + 60), "session_id": sid, "repo": repo, "kind": "prompt",
                              "signals": ["lead_no"], "noise": False, "lesson": lesson_id})
        t += DAY
        lines.append({"t": "promote", "ts": ts(t), "lesson": lesson_id, "by": "auto"})
        for i, n in enumerate(after):
            t += DAY
            sid = "a%d" % i
            lines.append({"t": "session", "ts": ts(t), "session_id": sid, "repo": repo, "langs": [], "phase": "start"})
            if injected:
                lines.append({"t": "inject", "ts": ts(t), "session_id": sid, "repo": repo, "ids": [lesson_id]})
            for _ in range(n):
                lines.append({"t": "moment", "ts": ts(t + 60), "session_id": sid, "repo": repo, "kind": "prompt",
                              "signals": ["i_said"], "noise": False, "lesson": lesson_id})
        # one noise moment for detector precision
        lines.append({"t": "moment", "ts": ts(t + 120), "session_id": "a0", "repo": repo, "kind": "prompt",
                      "signals": ["lead_no"], "noise": True, "lesson": None})
        p = os.path.join(self.e.store_path("org"), "events", "seed.jsonl")
        with open(p, "a") as f:
            for l in lines:
                f.write(json.dumps(l) + "\n")
        self.e.now = t + DAY

    def lesson(self, id, text):
        self.e.write("org", "active/repo-gitlab.example-corp.com__team__web.md",
                     "# A\n\n## %s — %s\n- scope: repo:%s\n- status: active\n- created: 2026-10-01\n" % (id, text, ORG_REPO))

    def report(self):
        return json.loads(self.e.hs("report", "--json").stdout)

    def test_effective_lesson(self):
        self.lesson("L-00000a", "Use pnpm")
        self.seed("L-00000a", before=[2, 1, 1, 2], after=[0, 1, 0, 0, 0, 0])
        r = self.report()
        l = next(x for x in r["lessons"] if x["id"] == "L-00000a")
        self.assertEqual(l["before"], {"sessions": 4, "pushbacks": 6, "rate": 1.5})
        self.assertEqual(l["after"], {"sessions": 6, "pushbacks": 1, "rate": 0.167})
        self.assertEqual(l["repeats_while_injected"], 1)
        self.assertEqual(l["sessions_injected"], 6)
        self.assertAlmostEqual(l["prevented"], 8.0, places=0)
        self.assertFalse(l["flagged_ineffective"])
        self.assertEqual(r["totals"]["sessions"], 10)
        self.assertEqual(r["totals"]["pushbacks"], 7)
        self.assertEqual(r["precision"]["lead_no"]["n"], 7)
        self.assertEqual(r["precision"]["i_said"]["precision"], 1.0)
        text = self.e.hs("report").stdout
        self.assertIn("Pushbacks per session", text)
        self.assertIn("1.50->0.17", text)

    def test_ineffective_lesson_flagged_and_retired(self):
        self.lesson("L-00000b", "Use pnpm")
        self.seed("L-00000b", before=[1, 1], after=[1, 1, 2, 1, 1])
        l = next(x for x in self.report()["lessons"] if x["id"] == "L-00000b")
        self.assertTrue(l["flagged_ineffective"])
        self.assertIn("ineffective", self.e.hs("report").stdout)
        r = self.e.hs("curate", "--store", "org")
        self.assertIn("ineffective", r.stdout)
        self.assertEqual(self.e.lessons("org")["L-00000b"].status, "retired")

    def test_weekly_buckets(self):
        self.lesson("L-00000c", "Use pnpm")
        self.seed("L-00000c", before=[3] * 7, after=[0] * 14)
        w = self.report()["weekly"]
        self.assertGreaterEqual(len(w), 3)
        self.assertGreater(w[0]["rate"], w[-1]["rate"])
        self.assertIn("trend: ↓", self.e.hs("report").stdout)


if __name__ == "__main__":
    unittest.main()
