"""core: config sections and the pre-0.2 fallback, Claude Code paths, the hook runner's contract,
the lessons feature's state moves from older versions. Each test runs in its own throwaway HOME."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager

from support.lessons_env import RUN, clean_env

from ai_toolkit.core import config, paths


@contextmanager
def home_env(**extra):
    home = tempfile.mkdtemp(prefix="core-test-")
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(clean_env(HOME=home, **extra))
    try:
        yield home
    finally:
        os.environ.clear()
        os.environ.update(old)
        shutil.rmtree(home, ignore_errors=True)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


class TestConfig(unittest.TestCase):
    def test_defaults_then_saved_section(self):
        with home_env():
            self.assertEqual(config.load("x", {"a": 1}), {"a": 1, "enabled": True})
            config.save("x", {"a": 2})
            config.save("y", {"b": 3})
            self.assertEqual(config.load("x", {"a": 1})["a"], 2)
            self.assertEqual(json.load(open(config.path())), {"x": {"a": 2}, "y": {"b": 3}})

    def test_legacy_file_used_until_first_save(self):
        with home_env() as home:
            legacy = os.path.join(home, ".config", "ai-toolkit", "setup.json")
            write(legacy, {"snapshot_dir": "~/snap"})
            self.assertEqual(config.load("setup")["snapshot_dir"], "~/snap")
            self.assertEqual(config.section_source("setup"), legacy)
            config.save("setup", {"snapshot_dir": "~/other"})
            self.assertEqual(config.load("setup")["snapshot_dir"], "~/other")
            self.assertTrue(os.path.exists(legacy), "the old file is left in place")

    def test_enabled_flag(self):
        with home_env():
            self.assertTrue(config.enabled("lessons"))
            config.save("lessons", {"enabled": False})
            self.assertFalse(config.enabled("lessons"))

    def test_section_under_its_old_name_is_read_until_saved(self):
        # The lessons feature was called hindsight until 0.3; a config written then must keep working.
        with home_env():
            write(config.path(), {"hindsight": {"enabled": False, "promote_at": 3}, "rules": {}})
            self.assertFalse(config.enabled("lessons"))
            self.assertEqual(config.load("lessons", {"promote_at": 2})["promote_at"], 3)
            self.assertEqual(config.section_source("lessons"), config.path())
            config.save("lessons", {"promote_at": 4})
            self.assertEqual(json.load(open(config.path())), {"lessons": {"promote_at": 4}, "rules": {}})


class TestPaths(unittest.TestCase):
    def test_claude_config_dir_is_honoured(self):
        with home_env(CLAUDE_CONFIG_DIR="/tmp/cc") as home:
            self.assertEqual(paths.claude_dir("settings.json"), "/tmp/cc/settings.json")
            self.assertEqual(paths.claude_json(), "/tmp/cc/.claude.json")
        with home_env() as home:
            self.assertEqual(paths.claude_dir(), os.path.join(home, ".claude"))
            self.assertEqual(paths.claude_json(), os.path.join(home, ".claude.json"))

    def test_xdg_state_and_tilde(self):
        with home_env(XDG_STATE_HOME="/tmp/xdg-state-test") as home:
            self.assertEqual(paths.state_dir("rules", "f"), "/tmp/xdg-state-test/ai-toolkit/rules/f")
            self.assertEqual(paths.tilde(os.path.join(home, "a")), "~/a")
            self.assertEqual(paths.tilde(home + "x/a"), home + "x/a")
        shutil.rmtree("/tmp/xdg-state-test", ignore_errors=True)


class TestHookRunner(unittest.TestCase):
    def run_hook(self, home, target, stdin="{}", **env):
        return subprocess.run([sys.executable, RUN, target], input=stdin, capture_output=True, text=True,
                              env=clean_env(HOME=home, **env), timeout=30)

    def test_always_exits_zero_and_logs_errors(self):
        with home_env() as home:
            for target in ("", "nope", "nope.hook", "lessons.no_such_hook", "hindsight.old_name_hook"):
                self.assertEqual(self.run_hook(home, target).returncode, 0, target)
            log = open(os.path.join(home, ".local", "state", "ai-toolkit", "lessons", "lessons.log")).read()
            self.assertIn("no_such_hook error", log)
            self.assertIn("old_name_hook error", log, "a hook target written before 0.3 runs the lessons feature")

    def test_legacy_disable_variable_still_works(self):
        with home_env() as home:
            r = self.run_hook(home, "lessons.no_such_hook", HINDSIGHT_DISABLE="1")
            self.assertEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(home, ".local", "state", "ai-toolkit", "lessons", "lessons.log")))


class TestStateMove(unittest.TestCase):
    def test_pre_02_state_folder_moves_once(self):
        with home_env() as home:
            old = os.path.join(home, ".local", "state", "hindsight")
            write(os.path.join(old, "offsets.json"), {"t": 1})
            from ai_toolkit.lessons.config import state_dir
            new = state_dir()
            self.assertEqual(new, os.path.join(home, ".local", "state", "ai-toolkit", "lessons"))
            self.assertEqual(json.load(open(os.path.join(new, "offsets.json"))), {"t": 1})
            self.assertFalse(os.path.exists(old))

    def test_hindsight_state_folder_moves_and_a_late_queue_is_adopted(self):
        with home_env() as home:
            from ai_toolkit.lessons.config import log_path, queue_path, state_dir
            old = os.path.join(home, ".local", "state", "ai-toolkit", "hindsight")
            write(os.path.join(old, "offsets.json"), {"t": 1})
            with open(os.path.join(old, "queue.jsonl"), "w") as f:
                f.write('{"id": "a"}\n')
            with open(os.path.join(old, "hindsight.log"), "w") as f:
                f.write("old line\n")
            new = state_dir()
            self.assertEqual(new, os.path.join(home, ".local", "state", "ai-toolkit", "lessons"))
            self.assertFalse(os.path.exists(old))
            self.assertEqual(open(log_path()).read(), "old line\n")
            # A plugin copy from before the rename keeps running until it is updated, and queues into the old folder.
            os.makedirs(old)
            with open(os.path.join(old, "queue.jsonl"), "w") as f:
                f.write('{"id": "b"}\n')
            state_dir()
            self.assertEqual(open(queue_path()).read(), '{"id": "a"}\n{"id": "b"}\n')
            self.assertFalse(os.path.exists(os.path.join(old, "queue.jsonl")))
            state_dir()
            self.assertEqual(open(queue_path()).read().count("\n"), 2, "adopted once")


class TestInstalledCopy(unittest.TestCase):
    def test_reports_files_that_differ_from_the_checkout(self):
        # Regression: docs said a local plugin loads in place; Claude Code runs a copy, which went stale unnoticed.
        from ai_toolkit.core import plugin
        with home_env() as home:
            self.assertEqual(plugin.copy_behind(), (None, []), "plugin not installed")
            copy = os.path.join(home, ".claude", "plugins", "cache", "ai-toolkit", "ai-toolkit", "0.2.0")
            for d in plugin.RUNTIME_DIRS:
                shutil.copytree(os.path.join(plugin.REPO_ROOT, d), os.path.join(copy, d),
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
            write(os.path.join(home, ".claude", "settings.json"), {"enabledPlugins": {"ai-toolkit@ai-toolkit": True}})
            write(os.path.join(home, ".claude", "plugins", "installed_plugins.json"),
                  {"version": 2, "plugins": {"ai-toolkit@ai-toolkit": [{"scope": "user", "installPath": copy}]}})
            self.assertEqual(plugin.copy_behind(), (copy, []), "an identical copy is not behind")
            with open(os.path.join(copy, "hooks", "run.py"), "a") as f:
                f.write("# older\n")
            os.remove(os.path.join(copy, "src", "ai_toolkit", "cli.py"))
            self.assertEqual(plugin.copy_behind(), (copy, [os.path.join("hooks", "run.py"),
                                                            os.path.join("src", "ai_toolkit", "cli.py")]))


if __name__ == "__main__":
    unittest.main()
