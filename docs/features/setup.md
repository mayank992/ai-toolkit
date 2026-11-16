# setup

**Per machine, what is installed.** (Per project, what Claude is told, is [rules](rules.md).)

See your AI tool setup and replicate it on another machine. Today it covers Claude Code. The core
(home-path templating, secret placeholders, diff, backup) is tool-agnostic; each tool is an adapter in `src/ai_toolkit/setup/adapters/`.

```
ait setup init DIR [--remote URL] [--no-memory]   where snapshots live: a PRIVATE git repo
ait setup show [--json]                           inventory + health of this machine
ait setup status                                  what changed since the last export
ait setup export [DIR] [--no-memory] [--push]     write the snapshot, commit it, optionally push
ait setup apply [DIR] [--dry-run] [--yes]         make this machine match a snapshot
```

The **Setup** section of `ait ui` shows the same inventory, any problems, and exactly what an export would write.

## What a snapshot holds (Claude Code)

| From | In the snapshot |
|---|---|
| `~/.claude/settings.json` | `settings.json`. Hooks a pre-0.2 ai-toolkit `install.sh` wrote are left out; the plugin (listed in `enabledPlugins`) provides them now. `env` secrets become placeholders. |
| `CLAUDE.md`, `agents/`, `commands/`, `skills/`, `output-styles/`, `keybindings.json` | copied. Links a pre-0.2 ai-toolkit install created, and `skills/synced` (synced by Claude Code), are skipped. |
| MCP servers in `~/.claude.json` (user and per-project) | `mcp.json`. Nothing else from `~/.claude.json` (OAuth, caches, history) is read. |
| plugins and marketplaces | `plugins.json` |
| scripts that hooks or the status line run from outside `~/.claude` | `files/<path under ~>`, executable bit kept |
| `~/.claude/projects/*/memory/` | `memory/~<project>/`, unless `--no-memory` |

Paths under your home folder are stored as `{{HOME}}`, and memory folders are keyed relative to it. So a snapshot taken
as `/Users/alice` applies cleanly as `/home/bob`.

## Secrets

- Values of secret-looking env vars and headers, `--token X` / `KEY=value` arguments, and token-shaped strings
  (the shapes in `src/ai_toolkit/core/secrets.py`, shared with the lessons feature) are replaced with `${secret:<id>}`.
- If any other exported file (a memory note, a skill) contains a token, export **refuses** and names the file.
  Compiled programs (such as a hook binary) are copied as-is and are not scanned.
- On apply, each placeholder is filled from the target machine's existing config, then
  `AI_TOOLKIT_SECRET_<ID>` env vars (`AI_SETUP_SECRET_<ID>` still works), then a prompt (skipped with `--yes`). Anything still missing is reported as BLOCKED
  and left untouched.

## Apply semantics

- Settings are merged: snapshot scalars win, dicts merge, lists and hooks are unioned, and nothing on the machine is removed.
- Files are added or overwritten. Every overwritten file is first copied to `~/.local/state/ai-toolkit/setup/backups/<time>/`.
- MCP servers go through `claude mcp add-json`, and plugins through `claude plugin marketplace add` / `claude plugin install`.
- A project-scoped MCP server is applied only if that project folder exists.
- Re-running is a no-op: `apply --dry-run` on the machine that exported reports `0 change(s)`.

Settings: the `setup` section of `~/.config/ai-toolkit/config.json` (`snapshot_dir`, `memory`; a pre-0.2 `setup.json` is read until the first save). Tests: `tests/setup/` (offline, fake `claude` via `AI_TOOLKIT_CLAUDE_CMD`).
