# Contributing

## Set up

```bash
git clone git@github.com:mayank992/ai-toolkit.git && cd ai-toolkit
claude plugin marketplace add "$PWD"            # Claude Code copies the plugin; see the note below
claude plugin install ai-toolkit@ai-toolkit
```

Claude Code runs the plugin from a copy it makes at install time (`~/.claude/plugins/cache/`), not from your clone. After changing hooks or skills, run `claude plugin update ai-toolkit@ai-toolkit` and start a new session. `ait doctor` lists the files that differ.

Tools: [uv](https://docs.astral.sh/uv/) for tests and lint, and pnpm for the dashboard. Runtime code uses the standard library only.

## Check your change

```bash
make check     # ruff, pytest on Python 3.9, dashboard typecheck, plugin validate: what CI runs
make test FILTER="-k inject"
make docs      # after changing any CLI argument (regenerates docs/reference/cli.md; a test checks it)
make ui-dev    # dashboard with hot reload against the real API
```

Tests run offline in throwaway HOMEs, with a fixed clock (`AI_TOOLKIT_NOW`) and a fake LLM. They never touch your real `~/.claude`.

## Where things go

- Shared, feature-agnostic code goes in `src/ai_toolkit/core/`. **`core` never imports a feature.**
- A feature uses another feature only through that feature's `api.py`.
- Tests mirror `src/`: `tests/<feature>/test_<topic>.py`. A regression test goes into the file for the topic it covers, with a comment saying what broke.
- A user-visible change gets a line in `CHANGELOG.md` and an update to the feature's page in `docs/features/`.
- A decision that would surprise a future reader gets a record in `docs/decisions/`.

## Adding a feature

1. Create `src/ai_toolkit/<name>/` with `__init__.py`, `api.py` (at least `snapshot()` if it has a dashboard view) and `cli.py` (`register(parent)`).
2. Register the CLI group in `build_parser()` in `src/ai_toolkit/cli.py`.
3. If it has hooks, add `hooks.py` with one function per hook and a line per hook in `hooks/hooks.json`: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/run.py" <name>.<hook>`.
4. If it has a dashboard view, add an entry to `src/ai_toolkit/dashboard/registry.py` and create `ui/src/features/<name>/index.tsx` default-exporting `defineModule({ View, freshKeys })` from `@toolkit/ui`.
5. If it needs settings, read them with `core.config.load("<name>", DEFAULTS)` and document each key in `docs/reference/config.md`.
6. Write `docs/features/<name>.md`, add a row to the README table, and run `make docs` and `make check`.

## Commits

Use short, imperative messages scoped by area, as in the history: `hindsight: …`, `rules: …`, `setup: …`, `ui: …`, `core: …`, `docs: …`.
