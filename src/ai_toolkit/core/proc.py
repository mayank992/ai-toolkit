"""Running external commands without ever raising."""
import os
import subprocess


def run(argv, cwd=None, timeout=60, env=None):
    """(returncode, stdout, stderr). A command that can't start or times out returns rc 127 / 124."""
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ss: %s" % (timeout, argv[0])
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr


def tool_cmd(name):
    """argv prefix for an external CLI. AI_TOOLKIT_<NAME>_CMD overrides it (tests use fakes)."""
    override = os.environ.get("AI_TOOLKIT_%s_CMD" % name.upper().replace("-", "_"))
    return override.split() if override else [name]
