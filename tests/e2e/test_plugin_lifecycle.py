"""End-to-end: plugin hooks -> capture -> distill -> curate -> inject -> measure -> sync -> disable.

Every hook is executed through the exact command string in hooks/hooks.json, with CLAUDE_PLUGIN_ROOT
set the way Claude Code sets it for a plugin (so the wiring itself is under test). Uses the fake LLM.
"""
import json
import os
import subprocess
import unittest

from support.lessons_env import DAY, ORG_REMOTE, REPO, Env

REJ_FB = ("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, "
          "the new_string was NOT written to the file). To tell you how to proceed, the user said:\n"
          "use pnpm, npm breaks our lockfile\n\nNote: ...")


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        with open(os.path.join(REPO, "hooks", "hooks.json")) as f:
            declared = json.load(f)["hooks"]
        self.cmd = {event: groups[0]["hooks"][0]["command"] for event, groups in declared.items()}
        self.assertEqual(sorted(self.cmd), ["SessionEnd", "SessionStart", "Stop", "UserPromptSubmit"])
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])

    def tearDown(self):
        self.e.cleanup()

    def fire(self, event, payload):
        r = subprocess.run(["bash", "-c", self.cmd[event]], input=json.dumps(dict(payload, hook_event_name=event)),
                           capture_output=True, text=True, env=self.e._env({"CLAUDE_PLUGIN_ROOT": REPO}), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def run_session(self, sid, prompts=(), rejection=False):
        out = self.fire("SessionStart", {"session_id": sid, "cwd": self.org, "source": "startup"})
        t = os.path.join(self.e.home, "%s.jsonl" % sid)
        open(t, "w").close()
        for p in prompts:
            self.e.now += 60
            self.fire("UserPromptSubmit", {"session_id": sid, "cwd": self.org, "prompt": p, "transcript_path": t})
            self.fire("Stop", {"session_id": sid, "cwd": self.org, "transcript_path": t})
        if rejection:
            with open(t, "a") as f:
                f.write(json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "tu-" + sid, "name": "Edit",
                     "input": {"file_path": self.org + "/package.json", "old_string": "x", "new_string": "y"}}]}}) + "\n")
                f.write(json.dumps({"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "tu-" + sid, "content": REJ_FB, "is_error": True}]}}) + "\n")
            self.fire("Stop", {"session_id": sid, "cwd": self.org, "transcript_path": t})
        self.e.now += 60
        self.fire("SessionEnd", {"session_id": sid, "cwd": self.org, "reason": "exit"})
        self.e.hs("distill")  # what the SessionEnd hook launches in the background
        self.e.now += DAY
        return json.loads(out) if out else None

    def test_full_lifecycle(self):
        self.assertEqual(set(self.cmd), {"UserPromptSubmit", "Stop", "SessionEnd", "SessionStart"})

        # Week 1: Claude keeps using npm; developer pushes back in two separate sessions.
        self.assertIsNone(self.run_session("s1", ["Add lodash to the project", "no, use pnpm instead of npm"]))
        ls = self.e.lessons("org")
        self.assertEqual([l.status for l in ls.values()], ["candidate"])
        self.assertIsNone(self.run_session("s2", rejection=True))  # rejected edit with typed feedback
        lesson = list(self.e.lessons("org").values())[0]
        self.assertEqual(lesson.status, "active", "promoted after 2nd session with the same pushback")

        # From now on the lesson is injected and Claude complies: no more pushback.
        for i in range(3, 9):
            out = self.run_session("s%d" % i, ["Add zod for validation"])
            self.assertIn(lesson.id, out["hookSpecificOutput"]["additionalContext"])
            self.assertIn("newly promoted", out["systemMessage"]) if i == 3 else None

        # Developer reviews the auto-promoted lesson -> nudge disappears.
        self.e.hs("review", stdin="k\n")
        out = self.run_session("s9")
        self.assertNotIn("newly promoted", out["systemMessage"])

        # Measure
        r = json.loads(self.e.hs("report", "--json").stdout)
        st = next(l for l in r["lessons"] if l["id"] == lesson.id)
        self.assertEqual(st["hits"], 2)
        self.assertEqual(st["before"]["pushbacks"], 2)
        self.assertEqual(st["after"]["pushbacks"], 0)
        self.assertEqual(st["repeats_while_injected"], 0)
        self.assertGreater(st["prevented"], 0)
        self.assertEqual(r["totals"]["sessions"], 9)
        self.assertEqual(r["totals"]["pushbacks"], 2)
        print("\n" + self.e.hs("report").stdout)

        # Privacy: nothing raw anywhere in the store or local state.
        blob = self.e.all_store_text("org") + self.e.all_store_text("personal")
        for raw in ("Add lodash", "Add zod", "npm breaks our lockfile", "old_string"):
            self.assertNotIn(raw, blob)
        self.assertEqual(self.e.queued(), [])

        # Sync org store to a private bare remote; personal store gets nothing org-related.
        bare = os.path.join(self.e.home, "remote-org.git")
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        stores = self.e.config()["stores"]
        stores[0]["remote"] = bare
        self.e.set_config(stores=stores)
        self.assertIn("org: synced", self.e.hs("sync", "org").stdout)
        clone = os.path.join(self.e.home, "clone")
        subprocess.run(["git", "clone", "-q", bare, clone], check=True)
        with open(os.path.join(clone, "lessons", "active", "repo-gitlab.example-corp.com__team__web.md")) as f:
            self.assertIn(lesson.text, f.read())
        self.assertNotIn("example-corp", self.e.all_store_text("personal"))

        # A secret pasted into a lesson by hand blocks the push.
        p = os.path.join(self.e.store_path("org"), "lessons", "candidates.md")
        with open(p, "a") as f:
            f.write("\n## L-dead00 — token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n- scope: global\n")
        r = self.e.hs("sync", "org", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REFUSING", r.stdout)

        # Turning lessons off in config makes every hook a no-op; memory stays.
        self.e.set_config(enabled=False)
        self.fire("UserPromptSubmit", {"session_id": "off", "cwd": self.org, "prompt": "no, use pnpm instead"})
        self.assertEqual(self.e.queued(), [])
        self.assertTrue(os.path.isdir(self.e.store_path("org")))

if __name__ == "__main__":
    unittest.main()
