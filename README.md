# ai-toolkit

A Claude Code plugin that helps Claude stop repeating your corrections. It learns lessons from your pushback, shows you every rule Claude is following in a project, and carries your whole Claude Code setup to a new machine.

| Feature | What it does | Docs |
|---|---|---|
| **hindsight** | Captures the moments you push back on Claude, distills them into a small set of lessons, injects only the relevant ones at session start, and measures whether repeat corrections drop. | [docs](docs/features/hindsight.md) |
| **rules** | Shows everything that steers Claude in a project (CLAUDE.md files, memory, hooks, lessons), flags problems, and runs a post-merge retro (`/mr-retro`) that turns review feedback into rule updates you approve. | [docs](docs/features/rules.md) |
| **setup** | Inventories your Claude Code setup (settings, hooks, MCP, plugins, skills, memory), exports it to a private git repo with secrets replaced by placeholders, and applies it on another machine. | [docs](docs/features/setup.md) |

All three appear in one local, read-only dashboard (`ait ui`).

## Install

```bash
claude plugin marketplace add mayank992/ai-toolkit
claude plugin install ai-toolkit@ai-toolkit
```

Then start a new Claude Code session. Requirements: `python3` 3.9+ and `git`; Node is needed only to build the dashboard. [Getting started](docs/getting-started.md) covers a local clone, the `ait` CLI in your own terminal, the dashboard, and upgrading from 0.1 (the `install.sh` era).

## Use

```bash
hs list                 # lessons hindsight has learned (hs = ait hindsight)
hs review               # approve or dismiss newly promoted lessons
hs report               # are repeat corrections going down?
ait rules show          # every rule Claude follows in this project, and problems with them
ait setup export        # snapshot this machine's Claude Code setup
ait ui                  # the dashboard
ait doctor              # is everything wired up?
```

Inside Claude Code: `/lesson <what Claude should do differently>` and `/mr-retro <MR number>`.

## Privacy

This repo holds only code. Lessons live in your own private git repos, and only the sentence that carried a correction is kept, redacted. Nothing is pushed until you run `hs sync`. See [privacy](docs/privacy.md).

## Documentation

- [Getting started](docs/getting-started.md): install, first lesson, dashboard, upgrading
- [Architecture](docs/architecture.md): how the plugin, package and data fit together
- Features: [hindsight](docs/features/hindsight.md) · [rules](docs/features/rules.md) · [setup](docs/features/setup.md)
- Reference: [CLI](docs/reference/cli.md) · [configuration](docs/reference/config.md)
- [Decision records](docs/decisions/README.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)
