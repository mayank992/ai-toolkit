"""hs ui: the read-only snapshot server that backs the React dashboard."""
import json
import os
import socket
import subprocess
import unittest
import urllib.error
import urllib.request

from helpers import DAY, MOD, ORG_REMOTE, Env


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestUi(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])
        self.server = None

    def tearDown(self):
        self.stop()
        self.e.cleanup()

    def stop(self):
        if self.server:
            self.server.terminate()
            self.server.wait(10)
            self.server.stdout.close()
            self.server = None

    def register(self, *events):
        with open(os.path.join(MOD, "module.json")) as f:
            manifest = json.load(f)
        hooks = {}
        for h in manifest["hooks"]:
            if h["event"] in events:
                cmd = '"$HOME/.claude/ai-toolkit/modules/hindsight/%s"' % h["script"]
                hooks.setdefault(h["event"], []).append({"hooks": [{"type": "command", "command": cmd}]})
        os.makedirs(os.path.join(self.e.home, ".claude"), exist_ok=True)
        with open(os.path.join(self.e.home, ".claude", "settings.json"), "w") as f:
            json.dump({"hooks": hooks}, f)

    def start(self):
        self.stop()
        self.port = free_port()
        self.server = subprocess.Popen([os.path.join(MOD, "bin", "hs"), "ui", "--api-only", "--port", str(self.port)],
                                       env=self.e._env(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.assertIn("hindsight ui", self.server.stdout.readline())

    def get(self, host="127.0.0.1"):
        req = urllib.request.Request("http://127.0.0.1:%d/api/snapshot" % self.port, headers={"Host": host})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def health(self, snap):
        return {s["id"]: s["health"] for s in snap["stages"]}

    def test_capture_only_install_shows_stalled_queue_and_off_stages(self):
        self.register("UserPromptSubmit", "Stop")
        self.e.hook("capture_prompt.py", {"session_id": "s1", "cwd": self.org, "prompt": "no, use pnpm instead of npm"})
        self.start()
        snap = self.get()
        self.assertEqual(len(snap["queue"]), 1)
        self.assertEqual(snap["queue"][0]["clause"], "no, use pnpm instead of npm")
        self.assertEqual(self.health(snap), {"capture": "ok", "queue": "waiting", "distill": "off",
                                             "curate": "off", "store": "ok", "inject": "off"})

        self.e.now += 2 * DAY
        self.start()
        self.assertEqual(self.health(self.get())["queue"], "stalled")

    def test_full_loop_lands_lessons_events_and_report(self):
        self.register("UserPromptSubmit", "Stop", "SessionEnd", "SessionStart")
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        self.e.session("s2", self.org, ["no, use pnpm instead of npm"])
        self.e.session("s3", self.org)
        self.start()
        snap = self.get()
        self.assertEqual(snap["queue"], [])
        self.assertTrue(all(h == "ok" for h in self.health(snap).values()), snap["stages"])
        org = next(s for s in snap["stores"] if s["name"] == "org")
        self.assertEqual([l["status"] for l in org["lessons"]], ["active"])
        self.assertIn("moment", {e["t"] for e in snap["events"]})
        self.assertEqual(snap["report"]["totals"]["sessions"], 3)
        lesson = org["lessons"][0]
        self.assertEqual({(p["lesson"], p["lesson_text"]) for p in snap["processed"]}, {(lesson["id"], lesson["text"])})
        ctx = next(r for r in snap["in_context"] if r["repo"] == "gitlab.example-corp.com/team/web")
        self.assertEqual([l["id"] for l in ctx["lessons"]], [lesson["id"]])
        self.assertIn(lesson["text"], ctx["rendered"])
        self.assertEqual(ctx["last_inject"]["ids"], [lesson["id"]])

    def test_rejects_foreign_host_header(self):
        self.start()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get(host="attacker.example")
        self.assertEqual(cm.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
