#!/usr/bin/env bash
# Remove ai-toolkit hooks, links and commands. Never touches memory stores or config.
#   ./uninstall.sh [--module NAME]
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
MODULE=""; [[ "${1:-}" == "--module" ]] && MODULE="$2"

if [[ -n "$MODULE" ]]; then
  python3 "$REPO/lib/settings_merge.py" remove "$CLAUDE_DIR/settings.json" --module "$MODULE"
else
  python3 "$REPO/lib/settings_merge.py" remove "$CLAUDE_DIR/settings.json"
fi
PREFIX="/.claude/ai-toolkit/modules/"; [[ -n "$MODULE" ]] && PREFIX+="$MODULE/"
for l in "$HOME"/.local/bin/* "$CLAUDE_DIR"/commands/*; do
  [[ -L "$l" ]] || continue
  t=$(readlink "$l")
  [[ "$t" == *"$PREFIX"* ]] && rm "$l" && echo "  unlinked $l"
done
if [[ -z "$MODULE" && -L "$HOME/.local/bin/ai-toolkit" ]]; then rm "$HOME/.local/bin/ai-toolkit"; echo "  unlinked $HOME/.local/bin/ai-toolkit"; fi
if [[ -z "$MODULE" && -L "$CLAUDE_DIR/ai-toolkit" ]]; then rm "$CLAUDE_DIR/ai-toolkit"; echo "  unlinked $CLAUDE_DIR/ai-toolkit"; fi
echo "done. Memory stores and ~/.config/ai-toolkit were left untouched."
