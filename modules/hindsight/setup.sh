#!/usr/bin/env bash
# hindsight setup: create default machine config (if missing) and initialize stores.
set -euo pipefail
CFG="${HINDSIGHT_CONFIG:-$HOME/.config/ai-toolkit/hindsight.json}"
HS="$(dirname "${BASH_SOURCE[0]}")/bin/hs"
if [[ ! -f "$CFG" ]]; then
  mkdir -p "$(dirname "$CFG")"
  python3 -c 'import sys,json,os; sys.path.insert(0, sys.argv[2]); from common import DEFAULT_CONFIG as D; json.dump(D, open(sys.argv[1],"w"), indent=2)' "$CFG" "$(dirname "${BASH_SOURCE[0]}")/lib"
  echo "  config: created $CFG (personal store only; add an org store with: hs store add org --match '*yourorg.com/*')"
else
  echo "  config: $CFG (kept)"
fi
"$HS" store init | sed 's/^/  store /'
