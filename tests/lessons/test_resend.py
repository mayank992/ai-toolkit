"""Resend: a request sent again with something added is captured as that addition, and the tool calls
rejected on the way are not pushbacks."""
import os
import unittest

from support.lessons_env import ORG_REMOTE, Env
from support.transcripts import assistant, text, tool, tool_result, user, write_transcript

REJECTED = "The user doesn't want to proceed with this tool use. The tool use was rejected."
FIRST = "Check the open comments on the merge request and fix them"
AGAIN = FIRST + ". Do not commit the changes"


class TestAddedOnResend(unittest.TestCase):
    def added(self, prev, cur):
        from ai_toolkit.lessons.turn import added_on_resend
        return added_on_resend(prev, cur)

    def test_appended_constraint(self):
        self.assertEqual(self.added(FIRST, AGAIN), "Do not commit the changes")

    def test_punctuation_and_case_do_not_hide_a_resend(self):
        self.assertEqual(self.added("Pushed the changes. Make the comments as resolved",
                                    "pushed the changes. Make the comments as resolved. Every comment needs a reply"),
                         "Every comment needs a reply")

    def test_inserted_in_the_middle(self):
        self.assertEqual(self.added("Move the credentials table to the shared components folder now",
                                    "Move the credentials table and its modal to the shared components folder now"),
                         "and its modal")

    def test_not_a_resend(self):
        self.assertEqual(self.added(FIRST, FIRST), "", "the same prompt again adds nothing")
        self.assertEqual(self.added(FIRST, FIRST + " please"), "", "a word or two is a typo fix, not a constraint")
        self.assertEqual(self.added("yes do that", "yes do that and also run the tests afterwards"), "", "too short to compare")
        self.assertEqual(self.added("Should we common out the traffic split field keys?",
                                    "Should we common out the whole layout builder instead of the keys?"), "")


class TestResendCapture(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])
        self.path = os.path.join(self.e.home, "t.jsonl")
        self.call = tool("Bash", command="git commit -am wip")

    def tearDown(self):
        self.e.cleanup()

    def payload(self, prompt=None):
        d = {"session_id": "s1", "cwd": self.org, "transcript_path": self.path}
        if prompt is not None:
            d["prompt"] = prompt
        return d

    def interrupted(self, feedback=""):
        result = REJECTED + ((" To tell you how to proceed, the user said:\n%s" % feedback) if feedback else "")
        return [user(FIRST), assistant(text("On it."), self.call), tool_result(self.call["id"], result, is_error=True),
                user("[Request interrupted by user for tool use]")]

    def test_addition_is_queued_and_the_rejection_is_not(self):
        write_transcript(self.path, self.interrupted())
        self.e.hook("capture_prompt", self.payload(AGAIN))
        self.e.hook("capture_transcript", self.payload())  # Stop, after the re-sent request was handled
        q = self.e.queued()
        self.assertEqual([(m["kind"], m["clause"]) for m in q], [("prompt", "Do not commit the changes")])
        self.assertEqual(q[0]["signals"], ["resend"])
        self.assertTrue(q[0]["resend"])
        self.assertEqual(q[0]["context"]["request"], FIRST)
        self.assertNotIn(FIRST, q[0]["clause"], "only the addition is kept, never the whole prompt")

    def test_rejection_already_queued_is_dropped(self):
        write_transcript(self.path, self.interrupted())
        self.e.hook("capture_transcript", self.payload())
        self.assertEqual([m["kind"] for m in self.e.queued()], ["rejected_tool"])
        self.e.hook("capture_prompt", self.payload(AGAIN))
        self.assertEqual([m["kind"] for m in self.e.queued()], ["prompt"])

    def test_rejection_with_a_typed_reason_stays(self):
        write_transcript(self.path, self.interrupted(feedback="never commit without asking"))
        self.e.hook("capture_prompt", self.payload(AGAIN))
        self.e.hook("capture_transcript", self.payload())
        self.assertEqual(sorted(m["kind"] for m in self.e.queued()), ["prompt", "rejected_tool"])

    def test_a_new_request_still_goes_through_the_detector(self):
        write_transcript(self.path, self.interrupted())
        self.e.hook("capture_prompt", self.payload("no, use pnpm instead of npm in this repo"))
        self.e.hook("capture_transcript", self.payload())
        q = self.e.queued()
        self.assertEqual(sorted(m["kind"] for m in q), ["prompt", "rejected_tool"])
        self.assertFalse(any(m.get("resend") for m in q))

    def test_backfill_keeps_a_resend_moment(self):
        write_transcript(self.path, self.interrupted())
        self.e.hook("capture_prompt", self.payload(AGAIN))
        self.e.hs("backfill")
        self.assertEqual([m["clause"] for m in self.e.queued()], ["Do not commit the changes"])


if __name__ == "__main__":
    unittest.main()
