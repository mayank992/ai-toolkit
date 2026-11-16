# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] — unreleased

Names only: nothing behaves differently, and everything written by 0.2 is still read.

### Changed
- The `hindsight` feature is now `lessons`: `ait lessons ...`, the `"lessons"` config section, `~/.local/state/ai-toolkit/lessons/`, `lessons.<hook>` hook targets and `src/ai_toolkit/lessons/`. `hs` is unchanged. `ait hindsight`, a `"hindsight"` config section, the old state folder (moved on first use) and `hindsight.<hook>` targets still work.
- `HINDSIGHT_LLM_CMD`, `HINDSIGHT_NO_LLM` and `HINDSIGHT_NO_BACKGROUND` are now `AI_TOOLKIT_LLM_CMD`, `AI_TOOLKIT_NO_LLM` and `AI_TOOLKIT_NO_BACKGROUND`. The old names still work.
- The dashboard says "feature" where it said "module": `GET /api/features` and `GET /api/features/<name>/snapshot` (were `/api/modules` and `/api/m/<name>/snapshot`), and a view is declared with `defineFeature`. Reload an open dashboard tab after upgrading.
- Store commits are prefixed `lessons:` (were `hindsight:`), and the injected block is headed "Lessons from past corrections".
- Modules renamed to say what they hold: `core/install.py` → `core/plugin.py`; in the lessons feature `measure.py` → `report.py`, `capture.py` → `queue.py`, `context.py` → `turn.py`, `lessons.py` → `model.py`.

## [0.2.0] — unreleased

The repo is restructured as a Claude Code plugin and a single Python package. Behaviour is the same; how it is installed, invoked and laid out has changed. See [docs/decisions/0002](docs/decisions/0002-claude-code-plugin.md) and [0003](docs/decisions/0003-one-package-stdlib.md).

### Added
- Claude Code plugin: `.claude-plugin/plugin.json`, a marketplace that lists the repo itself, `hooks/hooks.json`, and `bin/ait` / `bin/hs` on the Bash tool's PATH.
- `ait`, one CLI for every feature: `ait hindsight|rules|setup|ui|doctor|snapshot`. `hs` stays as the short form of `ait hindsight`.
- `ait migrate-legacy`: removes what the 0.1 `install.sh` added (hooks in settings.json, symlinks), with a backup and `--dry-run`.
- `"enabled": false` in a feature's config section turns its hooks off and hides it from the dashboard.
- Docs: getting started, architecture, a page per feature, generated CLI reference, configuration reference, privacy, decision records, contributing.
- CI on Python 3.9 and 3.13 (Linux and macOS), plus the dashboard typecheck and build. `make check` runs the same steps.
- hindsight captures what you add when you send a request again (signal `resend`), and stops counting the tool calls you rejected on the way as pushbacks.
- hindsight flags a lesson you repeated in 2+ sessions where it was injected as "make it a hook", in `hs report` and the dashboard.
- Tests for the import rules between packages, config fallback, `CLAUDE_CONFIG_DIR`, the hook runner and the docs references.

### Fixed
- `hs report` counted headless runs (SDK jobs, `claude -p`) as sessions, which pushed the weekly pushback rate and every lesson's before/after rate toward zero. Only sessions with a SessionStart, an injection or a pushback count now.
- Pushbacks distilled late (a backlog, or after `hs backfill`) were dated at distill time. Reports now use the time they were captured, so before/after rates and the weekly chart put them in the right place.
- SessionEnd no longer starts a distill process when the queue is empty and one ran in the last 24 hours.
- `ait doctor` failed for good after one error in `hindsight.log`. It now looks at the last 7 days.
- `ait rules show` follows `@path` imports in CLAUDE.md files (so `@AGENTS.md` is listed with its rules) and lists the hooks of enabled plugins.
- Docs said a plugin added from a local clone loads in place. Claude Code runs a copy; `ait doctor` now reports when that copy differs from the checkout.

### Changed
- Code moved from `modules/*/lib` to `src/ai_toolkit/{core,hindsight,rules,setup,dashboard}`, and dashboard views moved to `ui/src/features/`.
- One config file, `~/.config/ai-toolkit/config.json`, with a section per feature. The old `hindsight.json` and `setup.json` are read until the first save.
- hindsight state moved from `~/.local/state/hindsight` to `~/.local/state/ai-toolkit/hindsight`, automatically on first use.
- `/lesson` and `/mr-retro` are now skills.
- `ai-rules retro-data` / `retro-log` are now `ait rules retro collect` / `ait rules retro log`.
- `CLAUDE_CONFIG_DIR` is honoured by every feature (before, setup and hindsight's backfill ignored it).
- Credential patterns are defined once in `core/secrets.py`, for both hindsight redaction and setup export.
- The dashboard builds snapshots in-process, with a timeout per feature, instead of one subprocess per request.
- Environment variables: `AI_TOOLKIT_DISABLE` (was `HINDSIGHT_DISABLE`, which still works), `AI_TOOLKIT_NOW` (was `HINDSIGHT_NOW` / `AI_SETUP_NOW`), `AI_TOOLKIT_<TOOL>_CMD` (was `AI_SETUP_<TOOL>_CMD` / `AI_RULES_GLAB`), and `AI_TOOLKIT_SECRET_<ID>` (`AI_SETUP_SECRET_<ID>` still works).
- Tests moved to `tests/<feature>/`, named by topic instead of build step, and run with pytest.

### Removed
- `install.sh`, `uninstall.sh`, `lib/settings_merge.py`, and the whole `modules/` tree (including `module.json` files, `setup.sh` and hook build steps, `--steps`). A 0.1 machine has to install the plugin and run `ait migrate-legacy`; `ait doctor` flags leftovers.
- `hs ui` (use `ait ui`), `hs snapshot`, `ai-rules snapshot` and `ai-setup snapshot` (use `ait snapshot <feature>`).


## [0.1.0]

The first version: hindsight, rules, setup and the dashboard, installed with `install.sh`.
