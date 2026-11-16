# 0002: Ship as a Claude Code plugin instead of a custom installer

Status: accepted (0.2). Supersedes the 0.1 `install.sh`.

## Context

0.1 installed itself with `install.sh`, `uninstall.sh` and `lib/settings_merge.py`, about 250 lines. They symlinked the clone to `~/.claude/ai-toolkit`, linked CLIs and slash commands, and merged tagged hook entries into the user's `~/.claude/settings.json` after taking a backup. `setup` then needed a special case to strip those entries from exports. Claude Code plugins now provide all of this natively: hooks in `hooks/hooks.json`, skills, a `bin/` folder on the Bash tool's PATH, `${CLAUDE_PLUGIN_ROOT}`, and enable, disable, update and uninstall.

## Decision

The repo root is a plugin, and also a marketplace that lists itself (`"source": "./"`). All hooks go through `hooks/run.py <feature>.<hook>`. `/lesson` and `/mr-retro` are skills, and `ait` and `hs` are in `bin/`.

## Consequences

- No code edits the user's `settings.json`. Claude Code owns installing and removing the plugin.
- Added from a local clone, the plugin loads in place, which matches the old symlink workflow for development.
- Hook paths no longer depend on where the repo is cloned.
- State stays in XDG folders, not `${CLAUDE_PLUGIN_DATA}`, because uninstalling a plugin deletes that folder.
- 0.1 machines need a one-time `ait migrate-legacy`. Until a machine runs it, the shims in `modules/` keep the old hook paths working.
- **Alternative rejected: one plugin per feature.** Only hindsight has hooks, and splitting would mean copying `core` into every plugin. A per-feature `"enabled"` flag gives the same opt-out.
