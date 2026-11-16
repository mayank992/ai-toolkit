#!/usr/bin/env python3
"""Entry point for every ai-toolkit hook: `run.py <feature>.<hook>`, wired up in hooks/hooks.json.

The only place that puts src/ on sys.path for hooks. Exits 0 whatever happens (see core/hookrun.py).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

try:
    from ai_toolkit.core.hookrun import main
except Exception:  # a broken checkout must not break Claude Code either
    sys.exit(0)

sys.exit(main(sys.argv[1:]))
