# 0003: One Python package with a shared core, standard library only

Status: accepted (0.2).

## Context

In 0.1, each module had its own `lib/` of loose files (`common.py`, `core.py`, `store.py`) imported through `sys.path` edits in 12 places. The names would clash in a single interpreter, which is why the dashboard ran every snapshot in a subprocess. Helpers had been copied between modules and had drifted apart: `rules` honoured `CLAUDE_CONFIG_DIR` while `setup` and hindsight's backfill hard-coded `~/.claude`, and `normalize_remote` existed twice.

## Decision

- **One package, `src/ai_toolkit`**, with a subpackage per feature and a shared, feature-agnostic `core`.
- **Import rules:** `core` imports no feature, and features reach each other only through `api.py`. A test enforces both.
- **Standard library only** at runtime, and Python 3.9+ (the hooks run under macOS `/usr/bin/python3`). pytest and ruff are development tools only.
- **One CLI, `ait`,** made of feature groups (`ait hindsight|rules|setup`), plus `hs` as a permanent short alias for `ait hindsight`.

## Consequences

- The dashboard builds snapshots in-process, each on a thread with a timeout. A failing feature still answers only for its own card.
- `hs` subcommands stay flat (`hs list`, `hs review`) rather than being regrouped (`lessons list`), to keep muscle memory. Plumbing left the CLI: `snapshot` became `ait snapshot <feature>`, and `hs ui` is now `ait ui`.
- **Alternatives rejected:** click, typer and pydantic would break the stdlib-only constraint, and splitting hindsight into sub-packages (`capture/`, `learn/`, `memory/`) adds import depth for about 15 small, cohesive modules.
