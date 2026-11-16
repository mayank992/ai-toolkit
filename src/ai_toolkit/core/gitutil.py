"""Git helpers and repo identity: the one place that turns a folder into a stable repo id."""
import os
import re

from .proc import run

LANG_MARKERS = {
    "package.json": "js",
    "tsconfig.json": "ts",
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "kotlin",
    "Gemfile": "ruby",
    "composer.json": "php",
    "Package.swift": "swift",
}


def git(cwd, *args, timeout=10):
    """(returncode, stripped stdout) of `git -C cwd args...`."""
    rc, out, _ = run(["git", "-C", cwd] + list(args), timeout=timeout)
    return rc, out.strip()


def git_out(cwd, *args, timeout=10):
    """Stripped stdout, or "" when git fails."""
    rc, out = git(cwd, *args, timeout=timeout)
    return out if rc == 0 else ""


def normalize_remote(url):
    """git@host:a/b.git | https://u:p@host/a/b.git | ssh://git@host:22/a/b -> host/a/b"""
    if not url:
        return ""
    u = url.strip()
    u = re.sub(r"^[a-z+]+://", "", u)          # scheme
    u = re.sub(r"^[^@/]+@", "", u)              # user[:pass]@
    u = re.sub(r"^([^/:]+):(\d+)/", r"\1/", u)  # host:port/
    u = re.sub(r"^([^/:]+):", r"\1/", u)        # scp-style host:path
    u = re.sub(r"\.git/?$", "", u)
    return u.lower().rstrip("/")


def languages(folder):
    return sorted({lang for marker, lang in LANG_MARKERS.items() if os.path.exists(os.path.join(folder, marker))})


def repo_info(cwd):
    """dict(repo, root, remote, langs). `repo` is a stable id used to scope lessons and rules.

    A repo with an origin remote is identified by its normalized remote, so every clone shares lessons;
    a repo without one by its path ("local:~/code/x"); a folder outside git by "".
    """
    cwd = cwd or os.getcwd()
    root = git_out(cwd, "rev-parse", "--show-toplevel", timeout=2)
    remote = normalize_remote(git_out(cwd, "remote", "get-url", "origin", timeout=2)) if root else ""
    if remote:
        repo = remote
    elif root:
        home = os.path.expanduser("~")
        repo = "local:" + (("~" + root[len(home):]) if root.startswith(home) else root)
    else:
        repo = ""
    return {"repo": repo, "root": root, "remote": remote, "langs": languages(root or cwd)}
