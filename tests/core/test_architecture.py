"""The import rule that keeps features independent (see docs/architecture.md):

  - core imports no feature;
  - a feature imports another feature only through that feature's api.py;
  - nothing under src/ edits sys.path (only bin/ and hooks/run.py do, once each).
"""
import ast
import os
import unittest

from support.hindsight_env import SRC

PKG = os.path.join(SRC, "ai_toolkit")
FEATURES = {"hindsight", "rules", "setup"}


def modules():
    for root, _, files in os.walk(PKG):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                rel = os.path.relpath(path, SRC)[:-3].replace(os.sep, ".")
                yield path, rel[:-9] if rel.endswith(".__init__") else rel


def imports(path, modname):
    """Absolute module names imported by a file, with relative imports resolved."""
    pkg = modname.split(".") if path.endswith("__init__.py") else modname.split(".")[:-1]
    out = []
    for node in ast.walk(ast.parse(open(path).read())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = pkg[:len(pkg) - node.level + 1] if node.level else []
            mod = ".".join(base + ([node.module] if node.module else []))
            out += [mod + "." + a.name for a in node.names] if not node.module else [mod]
    return out


class TestImportRule(unittest.TestCase):
    def test_core_imports_no_feature(self):
        for path, mod in modules():
            if mod.startswith("ai_toolkit.core"):
                bad = [i for i in imports(path, mod) if i.split(".")[1:2] and i.split(".")[1] in FEATURES
                       and i.startswith("ai_toolkit.")]
                self.assertEqual(bad, [], mod)

    def test_features_meet_only_through_api(self):
        for path, mod in modules():
            parts = mod.split(".")
            if len(parts) < 2 or parts[1] not in FEATURES:
                continue
            for i in imports(path, mod):
                ip = i.split(".")
                if i.startswith("ai_toolkit.") and len(ip) > 1 and ip[1] in FEATURES and ip[1] != parts[1]:
                    self.assertEqual(ip[2:3], ["api"], "%s imports %s" % (mod, i))

    def test_no_sys_path_edits_in_src(self):
        for path, mod in modules():
            self.assertNotIn("sys.path", open(path).read(), mod)


if __name__ == "__main__":
    unittest.main()
