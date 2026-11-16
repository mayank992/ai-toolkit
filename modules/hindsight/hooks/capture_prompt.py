#!/usr/bin/env python3
"""Transitional shim: pre-0.2 install.sh registered this path in ~/.claude/settings.json.

It forwards to hooks/run.py. Delete modules/ once this machine uses the ai-toolkit plugin."""
import os
import subprocess
import sys

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
name = os.path.splitext(os.path.basename(__file__))[0]
try:
    sys.exit(subprocess.call([sys.executable, os.path.join(root, "hooks", "run.py"), "hindsight." + name]))
except Exception:
    sys.exit(0)
