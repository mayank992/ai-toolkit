# ai-toolkit

Portable personal AI tooling for Claude Code. Clone it on any machine and run `./install.sh`.

- **Code only.** This repo never contains memory, lessons, prompts or secrets.
- **Idempotent installer.** It symlinks `~/.claude/ai-toolkit` to this clone, links CLIs into `~/.local/bin`, and merges hook entries into `~/.claude/settings.json`. Your other hooks are preserved, and a timestamped backup is written first.
- **Clean uninstall.** `./uninstall.sh` removes only ai-toolkit entries.

## Modules

| Module | What it does |
|---|---|
| [`hindsight`](modules/hindsight/README.md) | Self-improving memory. Learns lessons from developer pushback, injects the relevant ones, and measures whether they reduce repeat corrections. |

## Dashboard

`ai-toolkit ui` serves one live, read-only dashboard at http://127.0.0.1:7319 with a section per module.

```bash
pnpm -C ui install && pnpm -C ui build   # once; needs Node
ai-toolkit ui [--module hindsight]
```

Each module owns its view and mounts it into the shell:

- `modules/<name>/ui/index.tsx` default-exports `defineModule({ View, freshKeys })` from `@toolkit/ui`. The shell finds it at build time, so there is no registry to edit. Rebuild the dashboard after adding one.
- `module.json` gets a `"ui"` block: `{"title", "tagline", "snapshot": ["bin/<cli>", "snapshot"]}`. The server runs that command in a subprocess on each poll and passes its JSON to `View`.

The shell owns the page frame, module nav, theme, live polling, shared styles and icons (`ui/src/base.css`, `@toolkit/ui`). The server binds to 127.0.0.1, rejects non-local `Host` headers and never writes. For UI work, run `ai-toolkit ui --api-only` and `pnpm -C ui dev`; Vite proxies `/api` to it.

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
bin/ai-toolkit                 # cross-module CLI (ai-toolkit ui)
lib/settings_merge.py          # shared settings.json hook merge (tag: /.claude/ai-toolkit/)
lib/dashboard.py               # dashboard server: /api/modules, /api/m/<name>/snapshot, ui/dist
ui/                            # dashboard shell (Vite + React); mounts modules/*/ui
modules/<name>/ui/             # optional: the module's own dashboard view
modules/<name>/module.json     # hooks, CLI, slash commands a module registers
modules/<name>/setup.sh        # optional module bootstrap
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how it all fits together.
