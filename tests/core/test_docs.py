"""The reference docs match the code: every command has a section in docs/reference/cli.md (run `make docs`),
and every config default and every hook is documented."""
import os
import re
import unittest

from support.hindsight_env import REPO

from ai_toolkit.cli import build_parser


def read(*p):
    with open(os.path.join(REPO, *p)) as f:
        return f.read()


def command_paths(parser, words):
    import argparse
    out = [" ".join(words)]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                out += command_paths(sub, words + [name])
    return out


class TestReferenceDocs(unittest.TestCase):
    def test_cli_reference_lists_every_command(self):
        documented = set(re.findall(r"^## `([^`]+)`$", read("docs", "reference", "cli.md"), re.M))
        self.assertEqual(documented, set(command_paths(build_parser(), ["ait"])), "run `make docs`")

    def test_config_reference_lists_every_default(self):
        from ai_toolkit.hindsight.config import DEFAULT_CONFIG
        from ai_toolkit.setup.snapshot_tree import DEFAULTS
        doc = read("docs", "reference", "config.md")
        for key in list(DEFAULT_CONFIG) + list(DEFAULTS) + ["enabled"]:
            self.assertIn("| `%s` |" % key, doc)


if __name__ == "__main__":
    unittest.main()
