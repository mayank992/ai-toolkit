# ai-toolkit

Portable personal AI tooling for Claude Code. Clone it on any machine and run `./install.sh`.

- **Code only.** This repo never contains memory, lessons, prompts or secrets.
- **Idempotent installer.** It symlinks `~/.claude/ai-toolkit` to this clone, links CLIs into `~/.local/bin`, and merges hook entries into `~/.claude/settings.json`. Your other hooks are preserved, and a timestamped backup is written first.
- **Clean uninstall.** `./uninstall.sh` removes only ai-toolkit entries.

## Modules

| Module | What it does |
|---|---|
| [`hindsight`](modules/hindsight/README.md) | Self-improving memory. Learns lessons from developer pushback, injects the relevant ones, and measures whether they reduce repeat corrections. |

## Install

```bash
git clone <this repo> ~/code/repos/ai-toolkit
cd ~/code/repos/ai-toolkit
./install.sh                 # everything
./install.sh --steps 1       # only hooks for build steps <= 1
```

Requirements: `python3` (3.9+, stdlib only) and `git`.

## Layout

```
install.sh / uninstall.sh
lib/settings_merge.py          # shared settings.json hook merge (tag: /.claude/ai-toolkit/)
modules/<name>/module.json     # hooks, CLI, slash commands a module registers
modules/<name>/setup.sh        # optional module bootstrap
```
