# Proposal 0001: Restructure ai-toolkit

Status: **Implemented in 0.2** · Date: 2026-11-16 · Scope: whole repo

> **As built.** The structure below shipped with these deviations, each for the reason given:
> - `ait hindsight` keeps hs's flat subcommands (`hs list`, `hs review`) instead of `lessons …` / `stores …` groups, to keep muscle memory ([0003](../decisions/0003-one-package-stdlib.md)).
> - hindsight stays one flat package (about 15 small modules) instead of `capture/`, `learn/`, `memory/` subpackages.
> - `llm.py` stayed in hindsight (no other feature calls an LLM). Credential *patterns* moved to `core/secrets.py` and are shared by both features; redaction itself stayed in hindsight.
> - `core/claude_code.py` became `core/paths.claude_dir()` / `claude_json()`. The readers in `rules` and `setup` answer different questions, so only the locations are shared.
> - The two "review fixes" test files are now topic files (`test_lifecycle_edge_cases.py`, `test_status_edge_cases.py`) rather than being split across every feature file.
> - Added: `ait migrate-legacy`, and `modules/` forwarding shims so 0.1 machines keep working until they migrate.
> - Not done: renaming the repo or `setup` (naming deferred), a license (owner's call), and a pre-built `ui/dist` (Node is still needed for the dashboard).


## TL;DR

The code itself is in decent shape. Hindsight's design is careful, the tests are offline and run in throwaway HOMEs, and the privacy model is written down. The repo is hard to read because of how it is **packaged and laid out**, not because of what it does:

1. **Every module builds its own mini-framework.** It has its own `lib/` of loose top-level Python files (`common.py`, `core.py`, `store.py`), its own `sys.path.insert` (12 copies), its own `git()`, `run()`, `read_json()`, `state_dir()`, `config_path()` and `normalize_remote()`. Module names like `common` and `core` would clash in one interpreter. That clash is the real reason the dashboard has to run snapshots in subprocesses.
2. **Installation reinvents Claude Code plugins.** `install.sh`, `lib/settings_merge.py`, the `~/.claude/ai-toolkit` symlink, the `/.claude/ai-toolkit/` tag, and `setup`'s special case that strips our own hooks from exports all do what a Claude Code plugin (`.claude-plugin/plugin.json` + `hooks/hooks.json` + `${CLAUDE_PLUGIN_ROOT}`) does natively.
3. **Three CLIs, three conventions.** `hs` (25 subcommands), `ai-rules` and `ai-setup` each mix user commands with internal plumbing (`snapshot`, `fire`, `retro-data`, `capture`).
4. **History leaks into structure.** Hook `"step"` fields, `install.sh --steps N`, and tests named `test_step7_review_fixes.py` / `test_step8_review_round2.py` describe the order things were built in, not what they test.
5. **Docs are uneven.** `docs/ARCHITECTURE.md` is really "hindsight internals". There is no LICENSE, CONTRIBUTING, CHANGELOG, config reference, CI or lint setup.

The proposal: **one Python package (`src/ai_toolkit/`) with one subpackage per feature, shipped as one Claude Code plugin from a repo that is also its own marketplace, with one CLI (`ait`)**. Most popular open-source AI tooling repos converge on this shape (see [§2](#2-what-comparable-repos-do)).

---

## 1. Current state: what's actually wrong

Each item below is something I checked in the code, not a matter of taste.

| # | Problem | Evidence | Cost |
|---|---|---|---|
| P1 | No Python packages; flat module names | `modules/*/lib/*.py` imported as `import common`, `import core`, `import store`; `sys.path.insert` in 12 files | Can't import two features in one process. Tests and the dashboard need subprocesses. IDEs and linters can't resolve imports. |
| P2 | Duplicated helpers that have already drifted | `normalize_remote` lives in both `hindsight/lib/common.py` and `rules/lib/inventory.py`. `rules` honours `CLAUDE_CONFIG_DIR`, `setup/lib/claude_code.py:29` and `hindsight/lib/backfill.py:17` hard-code `~/.claude` | Bugs fixed in one copy stay unfixed in the others. With `CLAUDE_CONFIG_DIR` set, `rules` and `setup` read different directories. |
| P3 | Inconsistent data locations | hindsight state `~/.local/state/hindsight`, rules state `~/.local/state/ai-toolkit/rules`, config `~/.config/ai-toolkit/*.json` | Users can't predict where data lives, and `purge`/backup logic has to know each layout. |
| P4 | Cross-feature coupling through file formats | `rules/lib/inventory.py:286` reads `~/.config/ai-toolkit/hindsight.json` and parses hindsight's stores itself | Any change to hindsight's config or lesson format silently breaks `rules`. |
| P5 | Custom installer instead of a plugin | `install.sh` (71 lines) + `settings_merge.py` (133 lines) edit `~/.claude/settings.json`; `setup` must strip `TOOLKIT_TAG` hooks on export | We maintain about 250 lines of install and uninstall code plus a backup scheme. Editing users' settings is a risk, and `setup`'s export carries a special case. |
| P6 | Three CLIs, with plumbing mixed into user commands | `hs` has 25 subcommands, including `snapshot`, `capture` and `ui`, the last a duplicate of `ai-toolkit ui --module hindsight`. `ai-rules fire/retro-data/retro-log/snapshot` | `--help` is noisy, the surface is hard to learn, and there is no single "what can this do?". |
| P7 | Build-order artifacts | `"step": 1..4` in `module.json`, `install.sh --steps`, `test_step{1..11}_*.py`, two "review_fixes" test files | Readers have to reconstruct history to understand the structure. Regression tests sit apart from the features they cover. |
| P8 | Frontend code inside backend modules | `modules/*/ui/*.tsx` is bundled by `ui/vite.config.ts` through a glob that reaches outside the package (`../../modules/*/ui`) and needs `dedupe` plus an `fs.allow` hack | Two toolchains in every feature folder, and fragile resolution. |
| P9 | Missing project hygiene | No `pyproject.toml`, LICENSE, CONTRIBUTING, CHANGELOG, CI, linter or formatter | It doesn't look like, or behave like, a maintained OSS repo. Nothing stops regressions on Python 3.9. |
| P10 | `graphify-out/` sits untracked at the root | `git status` | Noise; it should be gitignored. |

## 2. What comparable repos do

| Pattern | Seen in | Adopt? |
|---|---|---|
| **Repo = Claude Code plugin marketplace.** `.claude-plugin/marketplace.json` at the root, each plugin has `.claude-plugin/plugin.json`, `hooks/hooks.json`, `skills/`, `commands/`, `agents/`. Install with `/plugin marketplace add <repo>` then `/plugin install`. | Anthropic's official plugin repos, obra/superpowers, claude-mem and most Claude Code tooling published since plugins shipped | **Yes.** It replaces P5 entirely. |
| **`pyproject.toml` + `src/<pkg>/` layout, one console script with subcommand groups** | simonw/llm, aider, datasette, uv-era Python tools generally | **Yes.** It fixes P1, P2 and P6. |
| **Feature subpackages behind a small internal API.** Other features import `pkg.feature.api`, never its internals. | llm (plugins via hooks), datasette | **Yes.** It fixes P4. |
| **Skills instead of slash-command files** (`skills/<name>/SKILL.md`, invocable as `/<name>`) | Current Claude Code guidance; superpowers | **Yes**, for `/lesson` and `/mr-retro`. |
| **Top-level `tests/` mirroring the package, pytest, shared `conftest.py` fixtures** | Nearly universal | **Yes.** It fixes P7. pytest runs the existing `unittest.TestCase`s as they are. |
| **One web app with `features/` folders** | Most React dashboards (claude-mem's viewer, Langfuse, Phoenix) | **Yes.** It fixes P8. |
| **docs/ split into getting-started / features / reference / decisions (ADRs)** | Diátaxis-style docs in most mature OSS repos | **Yes.** It fixes P9. |
| Runtime deps such as click/typer/pydantic | aider, llm | **No.** Hooks run under macOS `/usr/bin/python3` 3.9, and stdlib-only is a feature worth keeping. Use `argparse` and `dataclasses`. |
| Separate plugin per feature | Some marketplaces | **Not now.** Only hindsight has hooks, and per-feature plugins would force vendoring the shared core into each one. Use one plugin and per-feature `enabled` flags in config. Revisit if a feature is ever shared with people who don't want the others. |

## 3. Target layout

```
ai-toolkit/
├── .claude-plugin/
│   ├── marketplace.json          # this repo is a marketplace with one plugin: "ai-toolkit" (source: "./")
│   └── plugin.json               # name, version, description, author
├── hooks/
│   └── hooks.json                # SessionStart / UserPromptSubmit / Stop / SessionEnd →
│                                 #   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/run.py" hindsight.<hook>
│   └── run.py                    # the ONLY sys.path shim: adds src/, runs the hook, never exits non-zero
├── skills/
│   ├── lesson/SKILL.md           # was modules/hindsight/commands/lesson.md
│   └── mr-retro/SKILL.md         # was modules/rules/commands/mr-retro.md
│
├── src/ai_toolkit/
│   ├── __init__.py               # __version__
│   ├── __main__.py               # python -m ai_toolkit  ==  ait
│   ├── cli.py                    # root parser; each feature registers its subcommand group
│   ├── core/                     # shared, feature-agnostic; no feature imports another feature's internals
│   │   ├── paths.py              # config_dir(), state_dir(feature), claude_dir() (honours CLAUDE_CONFIG_DIR) — ONE place
│   │   ├── config.py             # load/save ~/.config/ai-toolkit/config.json; per-feature sections + defaults
│   │   ├── jsonio.py             # read_json, write_json_atomic, locked JSONL append/rewrite
│   │   ├── gitutil.py            # git(), normalize_remote(), repo_info()
│   │   ├── proc.py               # run() with timeout, tool_cmd() lookup
│   │   ├── clock.py              # now()/iso() with AI_TOOLKIT_NOW override for tests
│   │   ├── redact.py             # secrets/PII redaction + scanner (used by hindsight AND setup)
│   │   ├── llm.py                # `claude -p` wrapper + tolerant JSON extraction
│   │   └── claude_code.py        # read-only model of Claude Code's files: settings layers, hooks,
│   │                             #   memory dirs, projects, skills, MCP — shared by rules and setup
│   ├── hindsight/
│   │   ├── api.py                # PUBLIC: lessons_for(repo, langs), stores(), snapshot()
│   │   ├── cli.py                # `ait hindsight …`
│   │   ├── hooks.py              # capture_prompt, capture_transcript, session_start, session_end
│   │   ├── capture/              # detect.py, context.py, enqueue.py, backfill.py
│   │   ├── learn/                # distill.py, curate.py
│   │   ├── memory/               # lesson.py (model ↔ Markdown), store.py (git repo), events.py, stats.py
│   │   ├── inject.py
│   │   └── measure.py
│   ├── rules/
│   │   ├── api.py                # snapshot()
│   │   ├── cli.py                # `ait rules …`
│   │   ├── inventory.py          # uses core.claude_code + hindsight.api (no file-format peeking)
│   │   ├── checks.py             # split out of inventory.py: each check is a small function
│   │   ├── retro.py
│   │   └── forges.py             # GitLab (glab) / GitHub (gh) adapters behind one interface
│   ├── setup/                    # (consider renaming → "profile", see §5)
│   │   ├── api.py, cli.py
│   │   ├── snapshot_tree.py      # was core.py: templating, secret placeholders, trees, backups
│   │   ├── ops.py                # export / status / apply
│   │   └── adapters/claude_code.py
│   └── dashboard/
│       ├── server.py             # was lib/dashboard.py; calls feature api.snapshot() in-process
│       └── registry.py           # FEATURES = {"hindsight": hindsight.api, ...} — explicit, 3 lines
│
├── ui/                           # one Vite + React app
│   ├── src/
│   │   ├── shell/                # App.tsx, ModuleBoundary.tsx, useSnapshot.ts, Icon.tsx, base.css
│   │   ├── sdk.ts                # @toolkit/ui contract (unchanged)
│   │   └── features/
│   │       ├── hindsight/        # was modules/hindsight/ui/**
│   │       ├── rules/
│   │       └── setup/
│   └── package.json …
│
├── tests/
│   ├── conftest.py               # Env fixture (temp HOME/config/state/stores), fake clock
│   ├── fakes/                    # fake_llm.py, fake_claude.py, fake_glab
│   ├── core/                     # test_paths.py, test_redact.py, test_gitutil.py, …
│   ├── hindsight/                # test_detect.py, test_capture.py, test_context.py, test_distill.py,
│   │                             #   test_curate.py, test_inject.py, test_measure.py, test_backfill.py
│   ├── rules/  setup/  dashboard/
│   └── e2e/test_plugin_lifecycle.py   # was step6: every hook through hooks.json, privacy grep, sync
│
├── docs/                         # see §6
├── scripts/dev-install.sh        # `uv tool install -e .` (or pipx) + local marketplace add, for contributors
├── pyproject.toml                # [project.scripts] ait = "ai_toolkit.cli:main"; ruff + pytest config; requires-python >=3.9
├── Makefile                      # make test | lint | ui | ui-dev | check  (what CI runs)
├── .github/workflows/ci.yml      # py 3.9 + 3.13 matrix: ruff, pytest; node: pnpm typecheck + build
├── AGENTS.md  (+ CLAUDE.md → "@AGENTS.md")   # how AI agents should work in this repo
├── CONTRIBUTING.md  CHANGELOG.md  LICENSE  README.md
└── .gitignore                    # + graphify-out/, .venv/, .pytest_cache/, .ruff_cache/
```

### Why each top-level piece exists

| Path | Purpose | Rule |
|---|---|---|
| `.claude-plugin/`, `hooks/`, `skills/` | What Claude Code loads | Glue only. A hook entry is one line that calls `run.py`, and all logic lives in `src/`. |
| `src/ai_toolkit/core/` | Anything two features need | No feature imports another feature's internals. Use `core` or that feature's `api.py`. Enforce it with a small test that parses imports. |
| `src/ai_toolkit/<feature>/` | One user-facing capability | It always has `api.py` (what other features and the dashboard may use) and `cli.py` (its `ait` subcommand group). |
| `ui/` | All TypeScript | Python never contains `.tsx`. TypeScript never imports Python paths. The contract is the snapshot JSON. |
| `tests/` | Mirrors `src/` | Name tests after what they cover. A regression test goes into its feature's file and carries a comment that explains it. |

## 4. Key mechanics

### 4.1 Installation: plugin replaces `install.sh`

```jsonc
// hooks/hooks.json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "timeout": 5,
      "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/run.py\" hindsight.capture_prompt" }] }],
    "Stop":         [{ "hooks": [{ "type": "command", "timeout": 10, "command": "… hindsight.capture_transcript" }] }],
    "SessionEnd":   [{ "hooks": [{ "type": "command", "timeout": 10, "command": "… hindsight.session_end" }] }],
    "SessionStart": [{ "hooks": [{ "type": "command", "timeout": 10, "command": "… hindsight.session_start" }] }]
  }
}
```

- Users install with `/plugin marketplace add <git url>` and then `/plugin install ai-toolkit@ai-toolkit`. Claude Code owns enable, disable, update and uninstall, so `install.sh`, `uninstall.sh`, `settings_merge.py`, the symlink and the backup logic are deleted.
- `hooks/run.py` puts `src/` on the path, honours `AI_TOOLKIT_DISABLE=1` and the feature's `enabled` flag, catches every exception, logs it to `state_dir("hindsight")/errors.log`, and always exits 0. This keeps the current "hooks never break Claude Code" guarantee in one place instead of four.
- The terminal CLI is optional and separate: `uv tool install git+<repo>` (or `pipx`). It installs `ait`. The plugin does not depend on it.
- `setup`'s `TOOLKIT_TAG` special case disappears. Our hooks are no longer in `settings.json`, and `enabledPlugins` already records that the plugin is on.
- The **first-run bootstrap** that `setup.sh` does today (default config, store init) moves into `core.config.load()`, which creates defaults lazily, and into `ait hindsight init`.

### 4.2 One CLI: `ait`

```
ait ui [--feature NAME]                    dashboard
ait doctor                                 health of every enabled feature (replaces hs doctor)
ait hindsight status | report | inject
ait hindsight lessons list | show | edit | rm | promote | retire | dismiss | restore | review
ait hindsight stores list | add | sync
ait hindsight distill | curate | backfill   (maintenance; normally automatic)
ait rules show [PROJECT] | projects | retro MR
ait setup init | show | status | export | apply
ait purge [--feature NAME] [--queue|--local|--store S]
```

- **Plumbing leaves the CLI.** `snapshot` becomes `api.snapshot()`, called in-process by the dashboard. `hs capture` becomes a function the `/lesson` skill calls through `ait hindsight lessons add`. `ai-rules retro-data`/`retro-log` fold into `ait rules retro MR`, with `--collect` and `--log` as the skill's steps. `ai-rules fire` stays as the one documented, hook-facing command, `ait rules fire`.
- `hs` and `ai-rules` can be kept for one release as thin aliases that print a deprecation line.

### 4.3 Dashboard

- `dashboard/registry.py` lists the features explicitly. With real packages there is no import clash, so the server calls `feature.api.snapshot()` in a worker thread with a timeout. A broken feature still returns a 502 for its own card only, which is today's isolation without the subprocess cost.
- The UI's `import.meta.glob("./features/*/index.tsx")` stays inside `ui/src`, so the `fs.allow`, the alias reach-out and the `dedupe` workaround go away.
- **Built assets:** the plugin is installed from git, so `ui/dist` won't exist unless it is committed. Proposed: CI builds `ui/dist` and attaches it to a GitHub release, and `ait ui` downloads the dist for its own version on first run (opt-in prompt), falling back to the current "run pnpm build" message. Simpler alternative: keep today's behaviour. That is fine for a personal tool. See Open question Q2.

### 4.4 One config file, one state root

```
~/.config/ai-toolkit/config.json
{
  "hindsight": { "enabled": true, "stores": [...], "promote_at": 2, ... },
  "rules":     { "enabled": true },
  "setup":     { "enabled": true, "snapshot_dir": "~/code/ai-setup-snapshot", "memory": true }
}
~/.local/state/ai-toolkit/<feature>/…      (XDG_STATE_HOME honoured)
```

A one-time migration in `core.config` reads the old `hindsight.json` and `setup.json` and moves `~/.local/state/hindsight`. It runs once, writes a marker, and leaves the old files in place for one release.

## 5. Feature-by-feature review

The question for each feature: who is it for, what is its smallest useful surface, and what goes.

### hindsight: keep (core of the toolkit)
- **Value:** learns from pushback, injects lessons, measures whether they help. This is the most original piece in the repo.
- **Keep:** the capture → distill → curate → inject → measure pipeline, Markdown-in-git stores, the privacy gate, and the offline test harness.
- **Change:** split the 536-line `bin/hs` into `cli.py` plus the subpackages above, and drop `hs ui`, a duplicate of `ait ui`. Move `redact.py` and `llm.py` to `core`, since `setup` also needs secret scanning. Expose `api.lessons_for()` so `rules` stops parsing stores itself.
- **Think about:** `backfill` is a one-off migration tool. Keep it under the maintenance group and document when to use it, or delete it once the queues have been re-derived.

### rules: keep, tighten
- **Value:** one view of everything that steers Claude in a project, plus `/mr-retro` to evolve those rules.
- **Change:** replace its private Claude Code file readers with `core.claude_code`, which also fixes the `CLAUDE_CONFIG_DIR` drift for `setup`. Split `inventory.py` (389 lines) into `inventory.py` (collect) and `checks.py` (one function per check, each with a test). Move the forge code behind `forges.py` with a `Forge` protocol (`view_mr`, `list_notes`).
- **Think about:** "rules" overlaps with `setup show`, since both inventory `~/.claude`. The split works if `rules` is "per project, what Claude is told" and `setup` is "per machine, what is installed". Put that sentence at the top of both docs.

### setup: keep, consider renaming
- **Value:** export and apply your Claude Code setup across machines from a private repo.
- **Naming:** `setup` reads as "install this toolkit", which is confusing next to a plugin install. Suggested name: **`profile`** (`ait profile export/apply`). Other options: `sync` or `machine`.
- **Change:** `core.py` becomes `snapshot_tree.py`, and the adapters go in `adapters/`. It uses `core.redact` for its secret detection instead of keeping its own.

### dashboard: keep
- **Value:** a read-only, local view of all features. The security posture is good (127.0.0.1, Host check, no writes) and should be kept and tested.
- **Change:** run snapshots in-process, use an explicit registry, and move the frontend into `ui/src/features/`.

### Cut
- `install.sh`, `uninstall.sh`, `lib/settings_merge.py` and the `modules/*/setup.sh` scripts, all replaced by the plugin and lazy config.
- Hook `"step"` and `--steps`, which are build-order scaffolding.
- `module.json`. Its contents move into `plugin.json` (hooks), `cli.py` (CLI), `skills/` (commands) and `dashboard/registry.py` (ui title and tagline).

## 6. Documentation set

| File | Audience | Contents |
|---|---|---|
| `README.md` | New user, 2 minutes | What it is and why, a 3-command install, a feature table with one line each, a dashboard screenshot, links. No internals. |
| `docs/getting-started.md` | New user, 10 minutes | Install the plugin, install `ait`, first lesson captured, open the dashboard, uninstall. |
| `docs/architecture.md` | Contributor | Only the cross-cutting shape: the layer diagram (Claude Code → plugin glue → `src/ai_toolkit` → data), the import rule, data locations, the hook safety contract, the dashboard contract. |
| `docs/features/{hindsight,rules,setup}.md` | User and contributor | What and why, commands, config keys, data written, then the internals section. Hindsight's internals move here from today's `ARCHITECTURE.md` almost unchanged, since that content is good. |
| `docs/reference/cli.md` | User | Generated by `ait --help-all > docs/reference/cli.md`. CI fails if it is stale. |
| `docs/reference/config.md` | User | Every config key with its default and meaning, generated from the defaults dicts the same way. |
| `docs/privacy.md` | User | What is captured, redacted, stored, synced and never stored. It is linked from the README, because people need this before installing an AI memory tool. |
| `docs/decisions/NNNN-*.md` | Contributor | ADRs. Seed them from the existing "Key design decisions" table (markdown-in-git, LLM off the hot path, promote on distinct sessions, …) and add 0005 "plugin over custom installer" and 0006 "single package, stdlib-only". |
| `docs/proposals/` | Contributor | This file and later ones. |
| `CONTRIBUTING.md` | Contributor | Dev install, `make check`, how to add a feature (a 6-step checklist: subpackage, `api.py`, `cli.py`, registry line, `ui/src/features/x`, docs page), commit style. |
| `AGENTS.md` | AI agents in this repo | Layout map, import rule, "stdlib only, py3.9", where tests go, how to verify the dashboard by clicking through it. `CLAUDE.md` contains `@AGENTS.md`. |
| `CHANGELOG.md` | Everyone | Keep-a-Changelog format, starting with this restructure as 0.2.0. |
| `LICENSE` | Everyone | MIT or Apache-2.0. Your call. |

## 7. Migration plan

Each phase is one PR-sized change that keeps all tests green, so the work can stop after any phase.

| Phase | Change | Done when |
|---|---|---|
| 0. Hygiene | Add `pyproject.toml` (ruff, pytest), `Makefile`, CI, LICENSE, gitignore `graphify-out/`. No code moves. | `make check` passes locally and in CI on 3.9 and 3.13. |
| 1. Package | `git mv modules/*/lib → src/ai_toolkit/<feature>/`, add `__init__.py` files, switch to relative imports, and leave the old `bin/*` as shims that import the package. | Every existing test passes. `grep -r sys.path src` is empty. |
| 2. Core | Extract `core/` (paths, config, jsonio, gitutil, proc, clock, redact, llm, claude_code), delete the duplicates, and add the import-rule test. | `normalize_remote`, `git()` and `read_json` each exist once. `CLAUDE_CONFIG_DIR` is honoured everywhere, with a test. |
| 3. Tests | Move tests to `tests/<feature>/test_<topic>.py`, fold the step7/step8 regressions into their topic files, and create `conftest.py` from `helpers.py`. | The same test count passes under pytest. No file is named after a step. |
| 4. CLI | Add `ait` with subcommand groups, turn `hs`, `ai-rules` and `ai-setup` into deprecated aliases, and remove plumbing commands. | `ait --help` fits on one screen, and the reference doc is generated. |
| 5. Plugin | Add `.claude-plugin/`, `hooks/hooks.json`, `hooks/run.py`, convert commands to skills, and delete `install.sh`, `uninstall.sh` and `settings_merge.py`. Port the e2e test to drive hooks through `hooks.json`. | A fresh machine works through `/plugin install` alone, and the e2e test passes. |
| 6. Config/state | Unified `config.json` and state root, plus the one-time migration. | The old files are migrated on first run, with a test. |
| 7. UI | Move `modules/*/ui` to `ui/src/features/*`, add the explicit dashboard registry and in-process snapshots. | `pnpm typecheck && build` passes, and each feature is clicked through in the browser, not just loaded directly. |
| 8. Docs | Write the §6 doc set, retire the module READMEs, and split `ARCHITECTURE.md`. | Every feature has a page, and the CLI and config references are generated and checked in CI. |

Phases 0–3 are low-risk mechanical moves. Phase 5 is the only one that changes how users install, so do it last among the code phases and announce it in the CHANGELOG.

## 8. Open questions

- **Q1. Rename `setup` → `profile`?** This only touches names and docs, and is cheap to do during phase 4.
- **Q2. Ship a pre-built `ui/dist`?** The options are a release asset downloaded by `ait ui`, or keeping "needs Node". For a personal tool, keeping Node is acceptable.
- **Q3. One plugin or one per feature?** The proposal is one. Split only when someone wants hindsight without the rest.
- **Q4. Keep `hs` as a permanent short alias?** It is muscle memory, and keeping it costs little.
- **Q5. License choice.**
