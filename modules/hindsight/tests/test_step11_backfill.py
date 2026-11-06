"""hs backfill: refine queued moments from their transcripts with the current capture rules."""
import json
import os
import unittest

from helpers import ORG_REMOTE, Env
from test_step9_context import assistant, text, tool, tool_result, user, write_transcript

REJ = "The user doesn't want to proceed with this tool use. The tool use was rejected."


def read(path):
    with open(path) as f:
        return f.read()


class TestBackfill(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])
        proj = os.path.join(self.e.home, ".claude", "projects", "-code-web")
        os.makedirs(proj)
        write_transcript(os.path.join(proj, "s1.jsonl"), [
            user("add lodash"),
            assistant(dict(tool("Bash", command="cat hooks/capture_transcript.py"), id="cat")),
            tool_result("cat", 'REJECT_PREFIX = "%s"' % REJ),
            assistant(text("reading done"), tool("Read", file_path="/x/a.py"),
                      dict(tool("Bash", command="npm install lodash"), id="npm")),
            tool_result("npm", REJ, is_error=True),
            user([{"type": "text", "text": "[Request interrupted by user for tool use]"}]),
            user("no, use pnpm instead of npm"),
        ])
        old_ctx = {"request": "[Request interrupted by user for tool use]", "actions": [], "reply": "", "edited": False}
        self.moments = [
            {"id": "fp", "kind": "rejected_tool", "session_id": "s1", "tool_use_id": "cat", "tool": "Bash",
             "clause": "", "ts": "2026-10-27T10:00:00Z", "repo": "r", "store": "org", "langs": []},
            {"id": "rej", "kind": "rejected_tool", "session_id": "s1", "tool_use_id": "npm", "tool": "Bash",
             "clause": "", "ts": "2026-10-27T10:01:00Z", "repo": "r", "store": "org", "langs": [], "context": old_ctx},
            {"id": "pr", "kind": "prompt", "session_id": "s1", "clause": "no, use pnpm instead of npm",
             "ts": "2026-10-27T10:02:00Z", "repo": "r", "store": "org", "langs": [], "signals": ["lead_no"],
             "context": old_ctx},
            {"id": "gone", "kind": "prompt", "session_id": "nope", "clause": "don't do that",
             "ts": "2026-10-27T10:03:00Z", "repo": "r", "store": "org", "langs": []},
        ]
        os.makedirs(self.e.state, exist_ok=True)
        with open(self.e.queue, "w") as f:
            f.write("".join(json.dumps(m) + "\n" for m in self.moments))

    def tearDown(self):
        self.e.cleanup()

    def test_dry_run_reports_and_writes_nothing(self):
        before = read(self.e.queue)
        r = self.e.hs("backfill", "--dry-run")
        self.assertIn("1 drop, 1 keep, 2 update", r.stdout)
        self.assertEqual(read(self.e.queue), before)

    def test_refines_queue_and_is_idempotent(self):
        self.e.hs("backfill")
        q = {m["id"]: m for m in self.e.queued()}
        self.assertNotIn("fp", q, "successful output quoting the rejection message is not a rejection")
        self.assertEqual(q["rej"]["rejected"], "Bash: npm install lodash")
        self.assertEqual(q["rej"]["context"]["request"], "add lodash")
        self.assertEqual(q["rej"]["context"]["actions"][-1], "Bash: npm install lodash")
        self.assertEqual(q["pr"]["context"]["request"], "add lodash",
                         "the interrupt marker is not the turn the developer corrected")
        self.assertEqual(q["gone"], self.moments[3])

        after = read(self.e.queue)
        r = self.e.hs("backfill")
        self.assertIn("2 same", r.stdout)
        self.assertEqual(read(self.e.queue), after)

    def test_waits_for_a_running_distill(self):
        import fcntl
        before = read(self.e.queue)
        with open(os.path.join(self.e.state, "distill.run.lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.e.hs("backfill", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("distill is running", r.stderr)
        self.assertEqual(read(self.e.queue), before)


if __name__ == "__main__":
    unittest.main()
