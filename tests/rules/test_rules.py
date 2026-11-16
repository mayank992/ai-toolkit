"""ait rules end to end in a temporary HOME: inventory, checks, fire log, retro data with a fake glab."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

from support.lessons_env import AIT, clean_env


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text if isinstance(text, str) else json.dumps(text))


def sh(cwd, *args):
    subprocess.run(list(args), cwd=cwd, check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
                            GIT_COMMITTER_EMAIL="t@e", GIT_AUTHOR_DATE="2026-01-01T00:00:00Z",
                            GIT_COMMITTER_DATE="2026-01-01T00:00:00Z"))


FAKE_GLAB = textwrap.dedent('''\
    #!%s
    import json, sys
    a = sys.argv[1:]
    if a[:2] == ["mr", "view"]:
        print(json.dumps({"title": "feat: widget", "source_branch": "feature/w", "merged_at": "2030-01-01T00:00:00Z",
                          "created_at": "2025-01-01T00:00:00Z", "merge_commit_sha": open(sys.argv[0] + ".sha").read().strip(),
                          "author": {"username": "dev"}, "web_url": "u", "state": "merged"}))
    elif a and a[0] == "api":
        if a[1].endswith("&page=1"):
            print(json.dumps([
                {"notes": [{"system": False, "author": {"username": "dev"}, "body": "remove this comment", "position": {"new_path": "src/w.ts", "new_line": 2}, "resolved": True, "created_at": "x"}]},
                {"notes": [{"system": False, "author": {"username": "dev"}, "body": "**suggestion (non-blocking)**: rename", "resolved": True, "created_at": "x"}]},
                {"notes": [{"system": False, "author": {"username": "reviewer"}, "body": "why here?", "resolved": False, "created_at": "x"}]},
                {"notes": [{"system": False, "author": {"username": "gitlab-comment-bot"}, "body": "coverage", "created_at": "x"}]}]))
        else:
            print("[]")
    ''') % sys.executable


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.proj = os.path.join(self.home, "code", "app")
        os.makedirs(self.proj)
        self.env = clean_env(HOME=self.home, XDG_STATE_HOME=os.path.join(self.home, ".state"))
        p = self.proj
        sh(p, "git", "init", "-q", "-b", "main")
        sh(p, "git", "remote", "add", "origin", "git@gitlab.example.com:team/app.git")
        write(os.path.join(p, "src", "base.ts"), "import { a } from 'b';\nexport const keep = 1;\n")
        write(os.path.join(p, "package.json"), "{}")
        sh(p, "git", "add", "-A")
        sh(p, "git", "commit", "-qm", "base")
        write(os.path.join(p, "CLAUDE.local.md"), "# Mine\n\n## Types\n- No loose StringAnyMap types in new code anywhere\n")
        write(os.path.join(p, ".claude", "settings.local.json"), {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "python3 $HOME/.claude/hooks/guard.py"},
            {"type": "command", "command": "python3 $HOME/.claude/hooks/missing.py"}]}]}})
        write(os.path.join(self.home, ".claude", "hooks", "guard.py"), '"""Guard git."""\n# writes fires.jsonl\n')
        write(os.path.join(self.home, ".claude.json"), {"projects": {p: {}}})
        key = "".join(c if c.isalnum() else "-" for c in p)
        self.mem = os.path.join(self.home, ".claude", "projects", key, "memory")
        write(os.path.join(self.mem, "MEMORY.md"), "- [Strict](strict-types.md) — x\n- [Gone](gone.md) — y\n")
        write(os.path.join(self.mem, "strict-types.md"), "---\nname: strict-types\ndescription: No loose StringAnyMap types in new code\nmetadata:\n  type: feedback\n---\n\nUse concrete types.\n\n**Why:** reviews.\n\n**How to apply:** grep the diff for StringAnyMap loose types in new code.\n")
        write(os.path.join(self.mem, "orphan.md"), "---\nname: orphan\ndescription: not indexed\nmetadata:\n  type: feedback\n---\n\nbody\n")
        self.tdir = os.path.dirname(self.mem)

    def cli(self, *args, cwd=None, env=None):
        r = subprocess.run([sys.executable, AIT, "rules"] + list(args), cwd=cwd or self.proj, env=dict(self.env, **(env or {})),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def view(self):
        return json.loads(self.cli("show", "--json"))

    def test_inventory_and_checks(self):
        v = self.view()
        self.assertEqual(v["repo"], "gitlab.example.com/team/app")
        local = [f for f in v["instructions"] if f["scope"] == "local"][0]
        self.assertEqual(local["git"], "untracked")
        self.assertEqual(local["rules"], ["No loose StringAnyMap types in new code anywhere"])
        texts = " | ".join(p["text"] for p in v["problems"])
        self.assertIn("not ignored by git", texts)
        self.assertIn("not listed in MEMORY.md", texts)
        self.assertIn("missing gone.md", texts)
        self.assertIn("Hook script missing", texts)
        guard = [h for h in v["hooks"] if h["name"] == "guard"][0]
        self.assertTrue(guard["logged"])
        self.assertEqual(guard["doc"], "Guard git.")
        self.assertTrue(any(o["b"]["name"] == "strict-types" or o["a"]["name"] == "strict-types" for o in v["overlaps"]))

        with open(os.path.join(self.proj, ".git", "info", "exclude"), "a") as f:
            f.write("/CLAUDE.local.md\n")
        v = self.view()
        self.assertEqual([f for f in v["instructions"] if f["scope"] == "local"][0]["git"], "ignored")
        self.assertNotIn("not ignored by git", " | ".join(p["text"] for p in v["problems"]))

    def test_imported_instruction_files_are_followed(self):
        # Regression: a CLAUDE.md that is only `@AGENTS.md` showed as one line with no rules.
        p = self.proj
        write(os.path.join(p, "CLAUDE.md"), "@AGENTS.md\n\nSee `@not/an/import.md` and mail dev@example.com\n")
        write(os.path.join(p, "AGENTS.md"), "# Agents\n\n## Rules\n- Runtime code is standard library only\n\n@docs/style.md\n@AGENTS.md\n")
        write(os.path.join(p, "docs", "style.md"), "## Style\n- Lines are at most 130 characters\n")
        write(os.path.join(p, "not", "an", "import.md"), "- never listed\n")
        files = [f for f in self.view()["instructions"] if f["scope"] == "project"]
        self.assertEqual([os.path.relpath(f["path"], p) for f in files], ["CLAUDE.md", "AGENTS.md", os.path.join("docs", "style.md")])
        self.assertEqual([os.path.basename(f["imported_from"]) for f in files], ["", "CLAUDE.md", "AGENTS.md"])
        self.assertEqual(files[1]["rules"], ["Runtime code is standard library only"])
        self.assertTrue(all(f["shared"] for f in files))
        self.assertIn("@ ", self.cli("show"))

    def test_hooks_of_enabled_plugins_are_listed(self):
        # Regression: only settings files were read, so a plugin's hooks (ai-toolkit's own included) were invisible.
        root = os.path.join(self.home, ".claude", "plugins", "cache", "mk", "memo", "1.0.0")
        off = os.path.join(self.home, ".claude", "plugins", "cache", "mk", "off", "1.0.0")
        for r in (root, off):
            write(os.path.join(r, "hooks", "hooks.json"), {"hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/run.py" memo.session_start'}]}]}})
        write(os.path.join(root, "hooks", "run.py"), '"""Runs one hook."""\n')
        write(os.path.join(self.home, ".claude", "settings.json"), {"enabledPlugins": {"memo@mk": True, "off@mk": False}})
        write(os.path.join(self.home, ".claude", "plugins", "installed_plugins.json"), {"version": 2, "plugins": {
            "memo@mk": [{"scope": "user", "installPath": root}], "off@mk": [{"scope": "user", "installPath": off}]}})
        v = self.view()
        plugin = [h for h in v["hooks"] if h["scope"] == "plugin"]
        self.assertEqual([(h["plugin"], h["name"], h["event"]) for h in plugin], [("memo", "memo: memo.session_start", "SessionStart")])
        self.assertTrue(plugin[0]["exists"])
        self.assertFalse(plugin[0]["shared"])
        self.assertNotIn("memo", " | ".join(p["text"] for p in v["problems"]), "a plugin's hooks are not the developer's to fix")

    def test_fire_log_counts(self):
        self.cli("fire", "guard", "ask")
        self.cli("fire", "guard", "ask")
        self.cli("fire", "guard", "deny")
        guard = [h for h in self.view()["hooks"] if h["name"] == "guard"][0]
        self.assertEqual(guard["fires"]["count"], 3)
        self.assertEqual(guard["fires"]["decisions"], {"ask": 2, "deny": 1})

    def test_snapshot_lists_project(self):
        r = subprocess.run([sys.executable, AIT, "snapshot", "rules"], cwd=self.proj, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        snap = json.loads(r.stdout)
        self.assertEqual([p["path"] for p in snap["projects"]], [self.proj])

    def test_retro_data_and_log(self):
        p = self.proj
        sh(p, "git", "checkout", "-qb", "feature/w")
        write(os.path.join(p, "src", "w.ts"), "import { a } from 'b';\nexport const widgetValue = computeWidget(a);\nexport const handWritten = somethingElse(a);\n")
        sh(p, "git", "add", "src/w.ts")
        sh(p, "git", "commit", "-qm", "widget")
        sh(p, "git", "checkout", "-q", "main")
        sh(p, "git", "merge", "-q", "--no-ff", "feature/w", "-m", "merge")
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=p, capture_output=True, text=True).stdout.strip()
        glab = os.path.join(self.tmp, "glab")
        write(glab, FAKE_GLAB)
        os.chmod(glab, 0o755)
        write(glab + ".sha", sha)
        lines = [
            {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "gitBranch": "feature/w", "message": {"content": "build the widget"}},
            {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "gitBranch": "feature/w", "message": {"content": [
                {"type": "tool_use", "name": "Write", "input": {"file_path": "src/w.ts", "content": "export const widgetValue = computeWidget(a);\n"}}]}},
            {"type": "user", "timestamp": "2026-01-01T00:02:00Z", "gitBranch": "feature/w", "message": {"content": "no, don't add comments again"}},
            {"type": "user", "timestamp": "2026-01-01T00:03:00Z", "gitBranch": "main", "message": {"content": "unrelated"}},
        ]
        write(os.path.join(self.tdir, "abcdef12-0000.jsonl"), "\n".join(json.dumps(l) for l in lines) + "\n")
        out = self.cli("retro", "collect", "7", env={"AI_TOOLKIT_GLAB_CMD": glab})
        path = out.splitlines()[0]
        d = json.load(open(path))
        self.assertEqual(d["share"]["new_lines"], 2)
        self.assertEqual(d["share"]["cc_lines"], 1)
        self.assertEqual(d["share"]["by_session"], {"abcdef12": 1})
        self.assertEqual(len(d["sessions"]), 1)
        self.assertEqual([p["text"] for p in d["sessions"][0]["pushback"]], ["no, don't add comments again"])
        self.assertEqual(sorted(n["kind"] for n in d["notes"]), ["ai-review", "bot", "human", "self"])
        self.assertIn("strict-types", [m["name"] for m in d["rules"]["memory"]])
        self.cli("retro", "log", "7", "--proposed", "3", "--applied", "2", "--note", "added comments rule")
        r = self.view()["retros"][0]
        self.assertEqual((r["mr"], r["applied"], r["share"], r["title"]), ("7", 2, 50, "feat: widget"))


if __name__ == "__main__":
    unittest.main()
