# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] — unreleased

The repo is restructured as a Claude Code plugin and a single Python package. Behaviour is the same; how it is installed, invoked and laid out has changed. See [docs/decisions/0002](docs/decisions/0002-claude-code-plugin.md) and [0003](docs/decisions/0003-one-package-stdlib.md).

### Added
- Claude Code plugin: `.claude-plugin/plugin.json`, a marketplace that lists the repo itself, `hooks/hooks.json`, and `bin/ait` / `bin/hs` on the Bash tool's PATH.
- `ait`, one CLI for every feature: `ait hindsight|rules|setup|ui|doctor|snapshot`. `hs` stays as the short form of `ait hindsight`.
- `ait migrate-legacy`: removes what the 0.1 `install.sh` added (hooks in settings.json, symlinks), with a backup and `--dry-run`.
- `"enabled": false` in a feature's config section turns its hooks off and hides it from the dashboard.
- Docs: getting started, architecture, a page per feature, generated CLI reference, configuration reference, privacy, decision records, contributing.
- CI on Python 3.9 and 3.13 (Linux and macOS), plus the dashboard typecheck and build. `make check` runs the same steps.
- Tests for the import rules between packages, config fallback, `CLAUDE_CONFIG_DIR`, the hook runner and the docs references.

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
