"""Regression tests for the 2026-11 code review findings."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager

from helpers import ORG_REMOTE, ORG_REPO, Env

REPO_FILE = "active/repo-gitlab.example-corp.com__team__web.md"


@contextmanager
def environ(env):
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


class TestReviewFixes(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.org = self.e.repo("web", ORG_REMOTE, ["package.json"])

    def tearDown(self):
        self.e.cleanup()

    def pnpm(self):
        return next(l for l in self.e.lessons("org").values() if "pnpm" in l.text)

    # 1. distill must not swallow hand edits by recording hashes before curate looks
    def test_hand_edit_survives_a_distill_run(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        l = self.pnpm()
        self.e.write("org", "candidates.md",
                     self.e.read("org", "candidates.md").replace(l.text, "Always use pnpm, never yarn"))
        self.e.session("s2", self.org, ["no, indent with tabs"])  # queued moment -> distill runs
        l2 = self.e.lessons("org")[l.id]
        self.assertTrue(l2.pinned)
        self.assertEqual(l2.text, "Always use pnpm, never yarn")
        self.assertTrue(any(e["t"] == "edit" and e["lesson"] == l.id for e in self.e.events("org")))

    def test_hand_delete_seen_by_distill(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        l = self.pnpm()
        self.e.write("org", "candidates.md", "# Candidate lessons\n")
        self.e.session("s2", self.org, ["no, indent with tabs"])
        self.assertTrue(any(e["t"] == "delete" and e["lesson"] == l.id for e in self.e.events("org")))

    # 2. curate --dry-run writes nothing
    def test_curate_dry_run_writes_no_events(self):
        self.e.hs("distill", "--no-llm")
        self.e.write("org", "candidates.md",
                     "# Candidate lessons\n\n"
                     "## L-aaaaaa — Use pnpm instead of npm for installs\n- scope: repo:%s\n- status: candidate\n"
                     "- created: 2026-10-01\n\n"
                     "## L-bbbbbb — Use pnpm instead of npm for package installs\n- scope: repo:%s\n"
                     "- status: candidate\n- created: 2026-10-02\n" % (ORG_REPO, ORG_REPO))
        before = self.e.events("org")
        r = self.e.hs("curate", "--store", "org", "--dry-run")
        self.assertIn("merge L-bbbbbb -> L-aaaaaa", r.stdout)
        self.assertEqual(self.e.events("org"), before)
        self.assertEqual(sorted(self.e.lessons("org")), ["L-aaaaaa", "L-bbbbbb"])

    # 3. LLM-chosen scopes can't escape lessons/active/
    def test_scope_file_is_one_path_component(self):
        from distill import _norm_scope
        from lessons_md import scope_file
        for scope in ("lang:../../x", "lang:c/c++", "lang:..", "weird/../../scope"):
            rel = scope_file(scope)
            self.assertEqual(os.path.dirname(rel), "active", rel)
            self.assertEqual(os.path.normpath(os.path.join("lessons", rel)), os.path.join("lessons", rel))
        self.assertEqual(scope_file("lang:js"), "active/lang-js.md")
        self.assertEqual(_norm_scope("lang:../../x", "r", ["js"]), "repo:r")
        self.assertEqual(_norm_scope("lang:JS", "r", ["js"]), "lang:js")
        self.assertEqual(_norm_scope(["bad"], "", []), "global")

    # 4. a curate failure must not make the next run re-count the same moments
    def test_curate_failure_still_drains_queue(self):
        self.e.hook("capture_prompt.py", {"session_id": "s1", "cwd": self.org, "prompt": "no, use pnpm instead of npm"})
        self.assertEqual(len(self.e.queued()), 1)
        import distill as D

        def boom(*a, **k):
            raise RuntimeError("boom")
        with environ(self.e._env()):
            orig, D.curate = D.curate, boom
            try:
                r = D.distill(use_llm=False)
            finally:
                D.curate = orig
        self.assertEqual(self.e.queued(), [])
        self.assertTrue(any("curate failed" in x for x in r["stores"]["org"]["curate"]))
        self.e.hs("distill")
        self.assertEqual(sum(1 for e in self.e.events("org") if e["t"] == "moment"), 1)

    def test_malformed_consolidation_output_is_ignored(self):
        import curate as C
        import llm
        self.e.hs("distill", "--no-llm")
        self.e.write("org", "candidates.md", "# Candidate lessons\n" + "".join(
            "\n## L-%06x — Rule number %d about thing%d\n- scope: global\n- status: candidate\n" % (i, i, i)
            for i in range(35)))
        with environ(self.e._env()):
            orig, llm.call = llm.call, lambda *a, **k: {"groups": [["L-000001", "L-000002"], {"ids": [["x"]]}, 7]}
            try:
                store = {"name": "org", "path": self.e.store_path("org")}
                C.curate(store)  # must not raise
            finally:
                llm.call = orig

    # 5. ordinary paths are not secrets
    def test_redaction_ignores_paths_but_catches_keys(self):
        from redact import redact, scan
        path = "put it in frontend/src/components/dashboard/widgets"
        self.assertEqual(redact(path), path)
        self.assertEqual(scan("repo:github.com/someorganization/someverylongrepositoryname"), [])
        self.assertIn("long_base64", scan("token aB3dEfGhIjKlMnOpQrStUvWxYz0123456789abcdEF"))

    # 6. a store without --match would capture every repo
    def test_store_add_requires_match(self):
        r = self.e.hs("store", "add", "work", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--match", r.stderr)
        self.e.hs("store", "add", "work", "--match", "*example.com/*")
        with open(os.path.join(self.e.home, ".config", "ai-toolkit", "hindsight.json")) as f:
            cfg = json.load(f)
        self.assertEqual(next(s for s in cfg["stores"] if s["name"] == "work")["match"], ["*example.com/*"])

    # 7. sync's secret scan must not skip a store whose path merely contains "/.git"
    def test_sync_scans_store_under_dot_git_prefix_dir(self):
        remote = os.path.join(self.e.home, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        self.e.set_config(stores=[{"name": "personal", "path": "~/.github-memory/personal", "remote": remote,
                                   "match": ["*"], "default": True}])
        self.e.hs("store", "init")
        p = os.path.join(self.e.home, ".github-memory", "personal", "lessons", "candidates.md")
        with open(p, "a") as f:
            f.write("\n## L-cccccc — key ghp_abcdefghijklmnopqrstuvwxyz0123\n- scope: global\n")
        r = self.e.hs("sync", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REFUSING", r.stdout)

    # 8. a lesson curate retired comes back (as a candidate) when the pushback recurs;
    #    one the developer retired stays retired (see test_step8_review_round2)
    def test_retired_lesson_revives_when_pushback_recurs(self):
        self.e.session("s1", self.org, ["no, use pnpm instead of npm"])
        lid = self.pnpm().id
        self.e.now += 61 * 86400
        self.e.hs("curate")
        self.assertEqual(self.e.lessons("org")[lid].status, "retired")
        self.e.session("s2", self.org, ["no, use pnpm"])
        self.assertEqual(self.e.lessons("org")[lid].status, "candidate")
        self.assertTrue(any(e["t"] == "restore" and e["lesson"] == lid and e.get("by") == "auto"
                            for e in self.e.events("org")))

    # 10. one long lesson must not block shorter ones
    def test_inject_skips_lesson_too_long_for_budget(self):
        from inject import select
        self.e.write("org", "active/global.md", "# Active lessons — global\n\n"
                     "## L-000001 — %s\n- scope: global\n- status: active\n\n"
                     "## L-000002 — Use pnpm\n- scope: global\n- status: active\n" % ("x" * 1450))
        cfg = {"stores": [{"name": "org", "path": self.e.store_path("org")}]}
        info = {"repo": "", "root": "", "langs": []}
        ids = [l.id for _, l, _ in select(cfg, info, lambda s: True, "/nonexistent")]
        self.assertEqual(ids, ["L-000002"])


class TestUnits(unittest.TestCase):
    # 9. a `claude -p` error wrapper is a failure, not an answer
    def test_llm_error_wrapper_returns_none(self):
        import llm
        d = tempfile.mkdtemp()
        try:
            body = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True})
            env = dict(os.environ, HINDSIGHT_STATE_DIR=d,
                       HINDSIGHT_LLM_CMD="%s -c 'print(%r)'" % (sys.executable, body))
            env.pop("HINDSIGHT_NO_LLM", None)
            with environ(env):
                self.assertIsNone(llm.call("sys", {"x": 1}))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_thanks_does_not_hide_a_correction(self):
        from detect import detect
        r = detect("Thanks, but dont use npm, use pnpm instead.")
        self.assertIsNotNone(r)
        self.assertIn("pnpm", r["clause"])
        self.assertIsNone(detect("no problem, thanks!"))
        self.assertIsNone(detect("thanks, that works"))


if __name__ == "__main__":
    unittest.main()
