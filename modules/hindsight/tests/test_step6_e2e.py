"""End-to-end: install -> capture -> distill -> curate -> inject -> measure -> sync -> uninstall.

Every hook is executed through the exact command string install.sh registered in
settings.json (so the wiring itself is under test). Uses the fake LLM.
"""
import json
import os
import subprocess
import unittest

from helpers import DAY, ORG_REMOTE, REPO, Env

REJ_FB = ("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, "
          "the new_string was NOT written to the file). To tell you how to proceed, the user said:\n"
          "use pnpm, npm breaks our lockfile\n\nNote: ...")


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        os.makedirs(os.path.join(self.e.home, ".claude"))
        self.settings = os.path.join(self.e.home, ".claude", "settings.json")
        self.original = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]}, "model": "opus"}
        with open(self.settings, "w") as f:
            json.dump(self.original, f)
        r = subprocess.run(["./install.sh"], cwd=REPO, env=self.e._env(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.settings) as f:
            s = json.load(f)
        self.cmd = {}
        for event, groups in s["hooks"].items():
            for g in groups:
                for h in g["hooks"]:
                    if "ai-toolkit" in h["command"]:
                        self.cmd[event] = h["command"]
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])

    def tearDown(self):
        self.e.cleanup()

    def fire(self, event, payload):
        r = subprocess.run(["bash", "-c", self.cmd[event]], input=json.dumps(dict(payload, hook_event_name=event)),
                           capture_output=True, text=True, env=self.e._env(), timeout=60)
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
        cfg_p = os.path.join(self.e.home, ".config", "ai-toolkit", "hindsight.json")
        with open(cfg_p) as f:
            cfg = json.load(f)
        cfg["stores"][0]["remote"] = bare
        with open(cfg_p, "w") as f:
            json.dump(cfg, f)
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

        # Uninstall restores settings exactly; memory stays.
        subprocess.run(["./uninstall.sh"], cwd=REPO, env=self.e._env(), check=True, capture_output=True)
        with open(self.settings) as f:
            self.assertEqual(json.load(f), self.original)
        self.assertTrue(os.path.isdir(self.e.store_path("org")))


if __name__ == "__main__":
    unittest.main()
