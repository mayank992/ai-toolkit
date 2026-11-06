#!/usr/bin/env bash
# ai-toolkit installer — idempotent, safe to re-run.
#   ./install.sh                         install all modules, all steps
#   ./install.sh --module hindsight      install one module
#   ./install.sh --steps 1               register only hooks for steps <= 1
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"
BIN_DIR="$HOME/.local/bin"
MODULE=""; STEPS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --module) MODULE="$2"; shift 2 ;;
    --steps)  STEPS="$2"; shift 2 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

for dep in python3 git; do
  command -v "$dep" >/dev/null || { echo "missing dependency: $dep" >&2; exit 1; }
done

mkdir -p "$CLAUDE_DIR/commands" "$BIN_DIR"

# Stable path so hook commands in settings.json work wherever the repo is cloned.
LINK="$CLAUDE_DIR/ai-toolkit"
if [[ -e "$LINK" && ! -L "$LINK" ]]; then
  echo "$LINK exists and is not a symlink; refusing to overwrite" >&2; exit 1
fi
ln -sfn "$REPO" "$LINK"
echo "linked $LINK -> $REPO"
ln -sfn "$LINK/bin/ai-toolkit" "$BIN_DIR/ai-toolkit"
echo "cli: $BIN_DIR/ai-toolkit"

modules=()
if [[ -n "$MODULE" ]]; then modules=("$MODULE"); else
  for d in "$REPO"/modules/*/; do modules+=("$(basename "$d")"); done
fi

for m in "${modules[@]}"; do
  MDIR="$REPO/modules/$m"
  [[ -f "$MDIR/module.json" ]] || { echo "no module.json in $MDIR" >&2; exit 1; }
  echo "== $m"
  # CLI
  cli=$(python3 -c 'import json,sys;c=json.load(open(sys.argv[1])).get("cli");print(c and c["name"]+" "+c["path"] or "")' "$MDIR/module.json")
  if [[ -n "$cli" ]]; then
    set -- $cli
    ln -sfn "$LINK/modules/$m/$2" "$BIN_DIR/$1"
    echo "  cli: $BIN_DIR/$1"
    case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "  NOTE: add $BIN_DIR to PATH";; esac
  fi
  # Slash commands
  for c in $(python3 -c 'import json,sys;print(" ".join(json.load(open(sys.argv[1])).get("commands",[])))' "$MDIR/module.json"); do
    ln -sfn "$LINK/modules/$m/$c" "$CLAUDE_DIR/commands/$(basename "$c")"
    echo "  command: /$(basename "$c" .md)"
  done
  # Hooks
  if [[ -n "$STEPS" ]]; then
    python3 "$REPO/lib/settings_merge.py" add "$SETTINGS" "$MDIR" --max-step "$STEPS"
  else
    python3 "$REPO/lib/settings_merge.py" add "$SETTINGS" "$MDIR"
  fi
  # Module-specific setup
  [[ -x "$MDIR/setup.sh" ]] && "$MDIR/setup.sh"
done
[[ -f "$REPO/ui/dist/index.html" ]] || echo "dashboard: not built (optional, needs Node): pnpm -C $REPO/ui install && pnpm -C $REPO/ui build"
echo "done. Restart Claude Code sessions to pick up hook changes."
