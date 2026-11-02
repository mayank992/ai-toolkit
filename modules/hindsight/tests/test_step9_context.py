"""Step 9 — Context: capture what the agent did before a pushback, distill the issue and why."""
import hashlib
import json
import os
import tempfile
import unittest

from helpers import ORG_REMOTE, Env

REPO_FILE = "active/repo-prod-gitlab-ui.sprinklr.com__team__web.md"
SECRET = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def user(text, **kw):
    return dict({"type": "user", "message": {"role": "user", "content": text}}, **kw)


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def tool(name, **inp):
    return {"type": "tool_use", "id": "t-%s-%d" % (name, len(inp)), "name": name, "input": inp}


def text(t):
    return {"type": "text", "text": t}


def tool_result(tid, content="ok"):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": content}]}}


def write_transcript(path, entries):
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


IMPLEMENTATION = [
    user("refactor the old settings page"),
    assistant(text("Done.")),
    user("add lodash to the web app"),
    assistant(text("I'll install it."), tool("Bash", command="npm install lodash --token=%s" % SECRET)),
    tool_result("t-Bash-1"),
    user("<task-notification>background job finished</task-notification>"),
    user("Base directory for this skill: ...", isMeta=True),
    assistant(tool("Edit", file_path="/Users/me/code/web/package.json", old_string="a", new_string="b")),
    tool_result("t-Edit-3"),
    assistant(text("Installed lodash and added it to package.json.")),
]


class TestPreviousTurn(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "t.jsonl")

    def test_extracts_request_actions_reply(self):
        from context import previous_turn
        write_transcript(self.path, IMPLEMENTATION + [user("no, use pnpm instead of npm")])
        ctx = previous_turn(self.path, "no, use pnpm instead of npm")
        self.assertEqual(ctx["request"], "add lodash to the web app")
        self.assertEqual(ctx["actions"][1], "Edit package.json")
        self.assertTrue(ctx["actions"][0].startswith("Bash: npm install lodash"))
        self.assertNotIn(SECRET, json.dumps(ctx), "context must be redacted")
        self.assertEqual(ctx["reply"], "Installed lodash and added it to package.json.")
        self.assertTrue(ctx["edited"])

    def test_current_prompt_not_yet_written(self):
        from context import previous_turn
        write_transcript(self.path, IMPLEMENTATION)
        self.assertEqual(previous_turn(self.path, "no, use pnpm")["request"], "add lodash to the web app")

    def test_no_edit_turn(self):
        from context import previous_turn
        write_transcript(self.path, [user("explain hooks"), assistant(text("Hooks are..."))])
        ctx = previous_turn(self.path, "that's wrong")
        self.assertFalse(ctx["edited"])
        self.assertEqual(ctx["actions"], [])

    def test_missing_or_empty_transcript(self):
        from context import previous_turn
        self.assertIsNone(previous_turn(os.path.join(self.dir, "nope.jsonl")))
        write_transcript(self.path, [])
        self.assertIsNone(previous_turn(self.path))

    def test_many_actions_are_capped(self):
        from context import MAX_ACTIONS, previous_turn
        write_transcript(self.path, [user("do it")] +
                         [assistant(tool("Read", file_path="/x/f%d.py" % i)) for i in range(20)])
        ctx = previous_turn(self.path)
        self.assertEqual(len(ctx["actions"]), MAX_ACTIONS)
        self.assertIn("more", ctx["actions"][-1])


class TestLessonHashCompat(unittest.TestCase):
    def test_hash_unchanged_for_lessons_without_why(self):
        from lessons_md import Lesson
        l = Lesson("L-aaaaaa", "Use pnpm", "global", ["npm"], [], "active")
        old = hashlib.sha1("\x1f".join([l.text, l.scope, l.trigger_str(), l.status, ""]).encode()).hexdigest()[:12]
        self.assertEqual(l.content_hash(), old, "adding fields must not make old lessons look hand-edited")
        l.why = "the repo uses pnpm"
        self.assertNotEqual(l.content_hash(), old)

    def test_why_issue_round_trip(self):
        from lessons_md import Lesson, parse
        l = Lesson("L-bbbbbb", "Use pnpm", "global", why="lockfile is pnpm", issue="ran npm install")
        back = parse(l.to_md())[0]
        self.assertEqual((back.why, back.issue), ("lockfile is pnpm", "ran npm install"))


class TestContextCapture(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])
        self.tpath = os.path.join(self.e.home, "transcript.jsonl")

    def tearDown(self):
        self.e.cleanup()

    def prompt(self, p, sid="s1"):
        self.e.hook("capture_prompt.py", {"session_id": sid, "cwd": self.org, "prompt": p,
                                          "transcript_path": self.tpath})

    def test_soft_feedback_after_edit_is_captured_with_context(self):
        write_transcript(self.tpath, IMPLEMENTATION)
        self.prompt("the import is broken now, it should be a named import")
        q = self.e.queued()
        self.assertEqual(len(q), 1)
        self.assertTrue(q[0]["after_edit"])
        self.assertEqual(q[0]["context"]["request"], "add lodash to the web app")

    def test_soft_feedback_without_edit_is_ignored(self):
        write_transcript(self.tpath, [user("explain the import"), assistant(text("It is a default import."))])
        self.prompt("the import is broken now")
        self.assertEqual(self.e.queued(), [])

    def test_capture_context_off_keeps_detection_but_drops_context(self):
        self.e.set_config(capture_context=False)
        write_transcript(self.tpath, IMPLEMENTATION)
        self.prompt("the import is broken now")
        q = self.e.queued()
        self.assertEqual(len(q), 1)
        self.assertNotIn("context", q[0])

    def test_rejected_tool_gets_context(self):
        write_transcript(self.tpath, [
            user("add lodash"),
            assistant(tool("Bash", command="npm install lodash")),
            tool_result("t-Bash-1", "The user doesn't want to proceed with this tool use. "
                                    "the user said:\nuse pnpm\n\nNote: ..."),
        ])
        self.e.hook("capture_transcript.py", {"session_id": "s1", "cwd": self.org, "transcript_path": self.tpath})
        q = self.e.queued()
        self.assertEqual(q[0]["kind"], "rejected_tool")
        self.assertEqual(q[0]["context"]["actions"], ["Bash: npm install lodash"])

    def test_distill_records_issue_and_why_and_inject_shows_why(self):
        write_transcript(self.tpath, IMPLEMENTATION)
        self.e.hook("session_start.py", {"session_id": "s1", "cwd": self.org, "source": "startup"})
        self.prompt("no, use pnpm instead of npm")
        self.e.hs("distill")
        l = next(x for x in self.e.lessons("org").values() if "pnpm" in x.text)
        self.assertIn("lockfile", l.why)
        self.assertIn("npm install lodash", l.issue)
        self.assertNotIn(SECRET, self.e.all_store_text("org"))
        self.assertNotIn("add lodash to the web app", self.e.all_store_text("org"),
                         "the raw request stays in the local queue, never the store")
        self.e.hs("promote", l.id)
        out = self.e.hs("inject", "--cwd", self.org).stdout
        self.assertIn("(why: The repo is a pnpm workspace", out)


if __name__ == "__main__":
    unittest.main()
