"""core: config sections and the pre-0.2 fallback, Claude Code paths, the hook runner's contract,
hindsight's one-time state move. Each test runs in its own throwaway HOME."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager

from support.hindsight_env import RUN, clean_env

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
            self.assertTrue(config.enabled("hindsight"))
            config.save("hindsight", {"enabled": False})
            self.assertFalse(config.enabled("hindsight"))


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
            for target in ("", "nope", "nope.hook", "hindsight.no_such_hook"):
                self.assertEqual(self.run_hook(home, target).returncode, 0, target)
            log = open(os.path.join(home, ".local", "state", "ai-toolkit", "hindsight", "hindsight.log")).read()
            self.assertIn("no_such_hook error", log)

    def test_legacy_disable_variable_still_works(self):
        with home_env() as home:
            r = self.run_hook(home, "hindsight.no_such_hook", HINDSIGHT_DISABLE="1")
            self.assertEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(home, ".local", "state", "ai-toolkit", "hindsight", "hindsight.log")))


class TestStateMove(unittest.TestCase):
    def test_pre_02_state_folder_moves_once(self):
        with home_env() as home:
            old = os.path.join(home, ".local", "state", "hindsight")
            write(os.path.join(old, "offsets.json"), {"t": 1})
            from ai_toolkit.hindsight.config import state_dir
            new = state_dir()
            self.assertEqual(new, os.path.join(home, ".local", "state", "ai-toolkit", "hindsight"))
            self.assertEqual(json.load(open(os.path.join(new, "offsets.json"))), {"t": 1})
            self.assertFalse(os.path.exists(old))


class TestInstalledCopy(unittest.TestCase):
    def test_reports_files_that_differ_from_the_checkout(self):
        # Regression: docs said a local plugin loads in place; Claude Code runs a copy, which went stale unnoticed.
        from ai_toolkit.core import install
        with home_env() as home:
            self.assertEqual(install.copy_behind(), (None, []), "plugin not installed")
            copy = os.path.join(home, ".claude", "plugins", "cache", "ai-toolkit", "ai-toolkit", "0.2.0")
            for d in install.RUNTIME_DIRS:
                shutil.copytree(os.path.join(install.REPO_ROOT, d), os.path.join(copy, d),
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
            write(os.path.join(home, ".claude", "settings.json"), {"enabledPlugins": {"ai-toolkit@ai-toolkit": True}})
            write(os.path.join(home, ".claude", "plugins", "installed_plugins.json"),
                  {"version": 2, "plugins": {"ai-toolkit@ai-toolkit": [{"scope": "user", "installPath": copy}]}})
            self.assertEqual(install.copy_behind(), (copy, []), "an identical copy is not behind")
            with open(os.path.join(copy, "hooks", "run.py"), "a") as f:
                f.write("# older\n")
            os.remove(os.path.join(copy, "src", "ai_toolkit", "cli.py"))
            self.assertEqual(install.copy_behind(), (copy, [os.path.join("hooks", "run.py"),
                                                            os.path.join("src", "ai_toolkit", "cli.py")]))


if __name__ == "__main__":
    unittest.main()
