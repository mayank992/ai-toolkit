#!/usr/bin/env bash
# Run hindsight tests offline in throwaway HOMEs.
#   ./run_tests.sh           all steps built so far
#   ./run_tests.sh step1     one step
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-/usr/bin/python3}"   # oldest python hooks may run under (macOS system 3.9)
command -v "$PY" >/dev/null || PY=python3
pattern="test_${1:-step}*.py"
"$PY" -m unittest discover -s . -p "$pattern" -v
