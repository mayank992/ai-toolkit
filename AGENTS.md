# Working in this repo (for AI agents)

ai-toolkit is a Claude Code plugin with a Python package (`src/ai_toolkit`) and a React dashboard (`ui/`). Read [docs/architecture.md](docs/architecture.md) before structural changes.

## Map

- `src/ai_toolkit/core/`: shared helpers (paths, config, hook runner, git, secrets). Imports no feature.
- `src/ai_toolkit/{lessons,rules,setup}/`: features. Each has `api.py` (public), `cli.py` (`ait <feature>`), and `hooks.py` if it has hooks.
- `hooks/hooks.json` + `hooks/run.py`: how Claude Code calls the hooks. `skills/`: `/lesson`, `/mr-retro`. `bin/`: `ait`, `hs`.
- `ui/src/features/<feature>/`: dashboard views. `ui/src/shell/`: the frame around them.
- `tests/` mirrors `src/`. Shared fixtures are in `tests/support/`.

## Rules

- Runtime code is **standard library only and Python 3.9 compatible** (no `match`, no `X | Y` types, no 3.10+ stdlib APIs). Hooks run under macOS `/usr/bin/python3`.
- `core` never imports a feature. Features reach each other only through `api.py`. Nothing in `src/` touches `sys.path`. `tests/core/test_architecture.py` enforces these.
- A hook must never fail a Claude Code session. Put logic in `<feature>/hooks.py` and let `core/hookrun.py` handle errors and the exit code. Keep SessionStart under 0.5 s: no network, LLM or heavy imports at module top.
- Every on-disk location comes from `core/paths.py`, and every setting from `core/config.py`. Never hard-code `~/.claude` (`CLAUDE_CONFIG_DIR` must work).
- Never write raw prompts, diffs or secrets to disk. Redact with `lessons/redact.py`, and add new credential shapes to `core/secrets.py`.

## Verify

- `make check` before you say a change is done. Run `make docs` if you changed CLI arguments.
- For dashboard changes, run `ait ui` and click through every feature and tab, including switching between features. Loading each page directly doesn't catch the bugs that only show up on a switch.
- Tests must not touch the real `~/.claude`. Use `tests/support/lessons_env.Env` or `clean_env()` with a temporary HOME.
