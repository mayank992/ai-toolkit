"""`ait migrate-legacy`: removes only what a 0.1 install.sh wrote, keeps everything else, backs settings up."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from support.lessons_env import AIT, REPO, clean_env

OTHER_HOOK = {"type": "command", "command": "/usr/local/bin/cc-status"}
OURS = {"type": "command", "command": '"$HOME/.claude/ai-toolkit/modules/hindsight/hooks/capture_prompt.py"'}


class TestMigrateLegacy(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="legacy-test-")
        self.env = clean_env(HOME=self.home)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(os.path.join(self.claude, "commands"))
        os.makedirs(os.path.join(self.home, ".local", "bin"))
        self.settings = os.path.join(self.claude, "settings.json")
        with open(self.settings, "w") as f:
            json.dump({"model": "opus", "enabledPlugins": {"ai-toolkit@ai-toolkit": True}, "hooks": {
                "UserPromptSubmit": [{"hooks": [OTHER_HOOK, OURS]}],
                "SessionStart": [{"hooks": [dict(OURS, command=OURS["command"].replace("capture_prompt", "session_start"))]}]}}, f)
        os.symlink(REPO, os.path.join(self.claude, "ai-toolkit"))
        os.symlink(os.path.join(self.claude, "ai-toolkit", "modules", "hindsight", "bin", "hs"),
                   os.path.join(self.home, ".local", "bin", "hs"))
        os.symlink("/opt/elsewhere/tool", os.path.join(self.home, ".local", "bin", "tool"))
        os.symlink(os.path.join(self.claude, "ai-toolkit", "modules", "hindsight", "commands", "lesson.md"),
                   os.path.join(self.claude, "commands", "lesson.md"))

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def ait(self, *args):
        return subprocess.run([sys.executable, AIT, "migrate-legacy"] + list(args), env=self.env,
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def test_dry_run_changes_nothing(self):
        before = open(self.settings).read()
        out = self.ait("--dry-run").stdout
        self.assertIn("2 hook entries", out)
        self.assertEqual(open(self.settings).read(), before)
        self.assertTrue(os.path.islink(os.path.join(self.home, ".local", "bin", "hs")))

    def test_removes_only_ours_and_backs_up(self):
        r = self.ait("--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.load(open(self.settings))
        self.assertEqual(s["hooks"], {"UserPromptSubmit": [{"hooks": [OTHER_HOOK]}]})
        self.assertEqual(s["model"], "opus")
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".local", "bin", "hs")))
        self.assertFalse(os.path.lexists(os.path.join(self.claude, "commands", "lesson.md")))
        self.assertFalse(os.path.lexists(os.path.join(self.claude, "ai-toolkit")))
        self.assertTrue(os.path.islink(os.path.join(self.home, ".local", "bin", "tool")), "unrelated link kept")
        self.assertEqual(len([f for f in os.listdir(self.claude) if f.endswith(".bak")]), 1)
        self.assertIn("nothing to remove", self.ait("--yes").stdout)

    def test_refuses_without_the_plugin(self):
        s = json.load(open(self.settings))
        s.pop("enabledPlugins")
        json.dump(s, open(self.settings, "w"))
        r = self.ait("--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("isn't enabled", r.stderr)


if __name__ == "__main__":
    unittest.main()
