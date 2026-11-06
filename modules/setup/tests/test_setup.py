"""ai-setup end to end: export from one machine, apply on another with a different home path."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(MOD, "bin", "ai-setup")
FAKE = os.path.join(MOD, "tests", "fake_claude.py")
sys.path.insert(0, os.path.join(MOD, "lib"))
import core  # noqa: E402

MCP_TOKEN = "s3cr3t-user-token-value"
PROJ_TOKEN = "glpat-abcdefghijklmnopqrstu"
ARG_KEY = "argkey-9f8e7d6c5b4a"


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text if isinstance(text, str) else json.dumps(text, indent=2))
    if mode:
        os.chmod(path, mode)


def read(path):
    with open(path) as f:
        return f.read()


class Machine(object):
    def __init__(self, root, user):
        self.home = os.path.join(root, "Users", user)
        os.makedirs(self.home)
        self.env = dict(os.environ, HOME=self.home, AI_SETUP_CLAUDE_CMD="%s %s" % (sys.executable, FAKE),
                        AI_SETUP_NOW="1793000000")

    def p(self, *parts):
        return os.path.join(self.home, *parts)

    def cli(self, *args, ok=True, env=None):
        r = subprocess.run([sys.executable, CLI] + list(args), env=dict(self.env, **(env or {})),
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if ok and r.returncode != 0:
            raise AssertionError("ai-setup %s failed:\n%s%s" % (" ".join(args), r.stdout, r.stderr))
        return r

    def calls(self):
        if not os.path.exists(self.p("claude-calls.jsonl")):
            return []
        return [json.loads(l)["argv"] for l in read(self.p("claude-calls.jsonl")).splitlines()]


def populate(m):
    h = m.home
    write(m.p(".config", "notify", "ping.sh"), "#!/bin/sh\necho ping\n", 0o755)
    write(m.p(".claude", "settings.json"), {
        "model": "opus",
        "env": {"MY_API_KEY": "settings-env-secret", "PLAIN": "kept"},
        "enabledPlugins": {"tool@mk-repo": True},
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "%s/.config/notify/ping.sh" % h}]},
                     {"hooks": [{"type": "command", "command": '"$HOME/.claude/ai-toolkit/modules/hindsight/hooks/x.py"'}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "%s/.config/notify/gone.sh" % h}]}],
        },
    })
    write(m.p(".claude", "CLAUDE.md"), "# global\nsee %s/notes\n" % h)
    write(m.p(".claude", "agents", "reviewer.md"), "agent\n")
    write(m.p(".claude", "skills", "mine", "SKILL.md"), "skill\n")
    write(m.p(".claude", "skills", "synced", "abc", "SKILL.md"), "managed by claude\n")
    os.makedirs(m.p(".claude", "commands"))
    os.symlink(m.p(".claude", "ai-toolkit", "modules", "hindsight", "commands", "lesson.md"), m.p(".claude", "commands", "lesson.md"))
    write(m.p(".claude.json"), {
        "oauthAccount": {"email": "x"},
        "mcpServers": {"tools": {"command": "/bin/sh", "args": ["-c", "true", "--api-key", ARG_KEY],
                                 "env": {"SERVICE_TOKEN": MCP_TOKEN, "REGION": "eu"}}},
        "projects": {m.p("code", "proj"): {"mcpServers": {"gl": {"command": "npx", "args": ["-y", "gl"],
                                                                 "env": {"GITLAB_PERSONAL_ACCESS_TOKEN": PROJ_TOKEN}}}}},
    })
    write(m.p(".claude", "plugins", "known_marketplaces.json"), {"mk-repo": {"source": {"source": "github", "repo": "org/mk-repo"}}})
    write(m.p(".claude", "plugins", "installed_plugins.json"), {"version": 2, "plugins": {"tool@mk-repo": [{"scope": "user"}]}})
    mem = m.p(".claude", "projects", core.encode_project(m.p("code", "proj")), "memory")
    write(os.path.join(mem, "MEMORY.md"), "- [Use pnpm](use-pnpm.md) — in %s/code/proj\n" % h)
    write(os.path.join(mem, "use-pnpm.md"), "use pnpm\n")


os.environ["AI_SETUP_NOW"] = "1793000000"


class TestSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ai-setup-test-")
        self.a = Machine(self.tmp, "alice.one")
        self.b = Machine(self.tmp, "bob")
        populate(self.a)
        self.snap = os.path.join(self.tmp, "snapshot")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def exported(self):
        return {os.path.relpath(os.path.join(d, f), self.snap): read(os.path.join(d, f))
                for d, _, fs in os.walk(self.snap) for f in fs if ".git" not in d}

    def test_export_is_portable_and_secret_free(self):
        self.a.cli("export", self.snap)
        files = self.exported()
        blob = "".join(files.values())
        for secret in (MCP_TOKEN, PROJ_TOKEN, ARG_KEY, "settings-env-secret"):
            self.assertNotIn(secret, blob)
        self.assertNotIn(self.a.home, blob)
        self.assertIn("{{HOME}}/.config/notify/ping.sh", files["claude-code/settings.json"])
        self.assertNotIn("ai-toolkit", files["claude-code/settings.json"])
        self.assertIn('"PLAIN": "kept"', files["claude-code/settings.json"])
        self.assertIn("claude-code/files/.config/notify/ping.sh", files)
        self.assertIn("claude-code/skills/mine/SKILL.md", files)
        self.assertFalse([p for p in files if "synced" in p or "lesson.md" in p])
        self.assertIn("claude-code/memory/~-code-proj/use-pnpm.md", files)
        self.assertNotIn("oauthAccount", files["claude-code/mcp.json"])
        mcp = json.loads(files["claude-code/mcp.json"])
        self.assertEqual(mcp["user"]["tools"]["env"]["REGION"], "eu")
        self.assertEqual(mcp["user"]["tools"]["args"][3], "${secret:mcp.user.tools.args.arg3}")
        self.assertIn("{{HOME}}/code/proj", mcp["projects"])
        self.assertEqual(len(json.loads(files["manifest.json"])["tools"]["claude-code"]["placeholders"]), 4)

        shutil.rmtree(self.snap)
        self.a.cli("export", self.snap, "--no-memory")
        self.assertFalse([p for p in self.exported() if "/memory/" in p])

    def test_export_refuses_files_with_secrets(self):
        mem = self.a.p(".claude", "projects", core.encode_project(self.a.p("code", "proj")), "memory")
        write(os.path.join(mem, "oops.md"), "token ghp_" + "a" * 36 + "\n")
        r = self.a.cli("export", self.snap, ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("oops.md", r.stderr)
        self.assertFalse(os.path.exists(self.snap))

    def test_apply_on_a_new_machine_then_idempotent(self):
        self.a.cli("export", self.snap)
        secrets = {core.env_secret_name("mcp.user.tools.env.SERVICE_TOKEN"): "new-token",
                   core.env_secret_name("mcp.user.tools.args.arg3"): "new-arg-key",
                   core.env_secret_name("settings.env.MY_API_KEY"): "new-settings-secret"}
        dry = self.b.cli("apply", self.snap, "--dry-run", env=secrets)
        self.assertFalse(os.path.exists(self.b.p(".claude")))
        self.assertIn("BLOCKED", dry.stdout)  # project folder ~/code/proj doesn't exist on bob's machine

        self.b.cli("apply", self.snap, "--yes", env=secrets)
        s = json.loads(read(self.b.p(".claude", "settings.json")))
        self.assertEqual(s["hooks"]["Stop"][0]["hooks"][0]["command"], self.b.p(".config", "notify", "ping.sh"))
        self.assertEqual(s["env"], {"MY_API_KEY": "new-settings-secret", "PLAIN": "kept"})
        script = self.b.p(".config", "notify", "ping.sh")
        self.assertTrue(os.stat(script).st_mode & stat.S_IXUSR)
        self.assertIn(self.b.home + "/notes", read(self.b.p(".claude", "CLAUDE.md")))
        mem = self.b.p(".claude", "projects", core.encode_project(self.b.p("code", "proj")), "memory", "MEMORY.md")
        self.assertIn(self.b.home + "/code/proj", read(mem))
        cj = json.loads(read(self.b.p(".claude.json")))
        self.assertEqual(cj["mcpServers"]["tools"]["env"]["SERVICE_TOKEN"], "new-token")
        self.assertEqual(cj["mcpServers"]["tools"]["args"][3], "new-arg-key")
        self.assertIn(["plugin", "marketplace", "add", "org/mk-repo"], self.b.calls())
        self.assertIn(["plugin", "install", "tool@mk-repo"], self.b.calls())

        again = self.b.cli("apply", self.snap, "--dry-run")
        self.assertIn("0 change(s)", again.stdout)  # secrets now come from bob's own config
        self.assertIn("1 blocked", again.stdout)

    def test_apply_merges_into_existing_settings_and_backs_up(self):
        self.a.cli("export", self.snap, "--no-memory")
        write(self.b.p(".claude", "settings.json"), {"theme": "light", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}})
        self.b.cli("apply", self.snap, "--yes", env={core.env_secret_name("settings.env.MY_API_KEY"): "v"})
        s = json.loads(read(self.b.p(".claude", "settings.json")))
        self.assertEqual(s["theme"], "light")
        self.assertEqual([h["hooks"][0]["command"] for h in s["hooks"]["Stop"]], ["mine.sh", self.b.p(".config", "notify", "ping.sh")])
        backups = [os.path.join(d, f) for d, _, fs in os.walk(self.b.p(".local", "state", "ai-toolkit", "setup", "backups")) for f in fs]
        self.assertTrue(any(b.endswith(".claude/settings.json") for b in backups))

    def test_dashboard_snapshot_reports_health_and_drift(self):
        self.a.cli("init", self.snap)
        self.a.cli("export")
        snap = json.loads(self.a.cli("snapshot").stdout)
        tool = snap["tools"][0]
        self.assertEqual(tool["export"]["drift"], [])
        self.assertEqual(snap["last_export_at"], core.now_iso())  # AI_SETUP_NOW pins the clock
        hooks = next(s for s in tool["sections"] if s["id"] == "hooks")["items"]
        self.assertTrue(any(i["status"] == "error" and "gone.sh" in i["note"] for i in hooks))
        self.assertTrue(any(i["tag"] == "ai-toolkit" for i in hooks))
        write(self.a.p(".claude", "CLAUDE.md"), "# changed\n")
        tool = json.loads(self.a.cli("snapshot").stdout)["tools"][0]
        self.assertEqual(tool["export"]["drift"], [{"path": "CLAUDE.md", "change": "changed"}])


if __name__ == "__main__":
    unittest.main()
