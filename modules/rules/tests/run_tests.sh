#!/usr/bin/env bash
# Offline tests: temporary HOME, fake glab. Runs under the oldest python hooks may use.
cd "$(dirname "$0")"
PY="${PYTHON:-/usr/bin/python3}"
command -v "$PY" >/dev/null || PY=python3
"$PY" -m unittest discover -s . -p "test_*.py" -v
