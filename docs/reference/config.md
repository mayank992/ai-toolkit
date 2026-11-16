# Configuration reference

All settings live in one file, `~/.config/ai-toolkit/config.json` (or `$XDG_CONFIG_HOME/ai-toolkit/config.json`), with one section per feature. Every key is optional, and a missing key takes the default shown here. `AI_TOOLKIT_CONFIG` points at a different file.

```json
{
  "hindsight": { "enabled": true, "stores": [ ... ], "promote_at": 2 },
  "rules":     { "enabled": true },
  "setup":     { "enabled": true, "snapshot_dir": "~/code/ai-setup", "memory": true }
}
```

**Upgrading from 0.1:** until a section is first saved, it is read from the old `hindsight.json` or `setup.json` next to `config.json`. Saving writes the section into `config.json` and leaves the old file where it is. `ait hindsight status` shows which file is in use.

## Every feature

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | `false` turns the feature's hooks into no-ops and hides it from the dashboard. The CLI still works. |

## `hindsight`

| Key | Default | Meaning |
|---|---|---|
| `stores` | one `personal` store at `~/.ai-memory/personal`, matching `*`, default | Memory stores. Each one is `{name, path, remote, match: [globs], default}`. A correction goes to the first non-default store whose `match` glob fits the repo's normalized remote (e.g. `*example-corp.com/*`), and otherwise to the default store. Manage stores with `hs store add/init/list`. |
| `promote_at` | `2` | Distinct sessions with the same pushback before a candidate becomes active. |
| `auto_promote` | `true` | Promote automatically. When `false`, candidates wait for `hs review` / `hs promote`. |
| `cap_per_scope` | `50` | Maximum active lessons per scope. The least useful ones are retired first. |
| `retire_days` | `60` | Retire an active lesson that hasn't been hit or injected in this many days (unless it's pinned). |
| `inject_budget_lines` | `15` | At most this many lessons are injected at SessionStart. |
| `inject_budget_chars` | `1500` | At most this many characters are injected at SessionStart. |
| `capture_context` | `true` | Keep a short, redacted summary of the corrected agent turn in the local queue so distill can write `why` / `issue`. `false` keeps only the correction clause. |
| `distill_model` | `"haiku"` | The model `claude -p` uses for distill and consolidation. |

## `rules`

Only `enabled`. The hook-fire log and retro evidence are kept in `~/.local/state/ai-toolkit/rules/`.

## `setup`

| Key | Default | Meaning |
|---|---|---|
| `snapshot_dir` | `""` | The private git repo that snapshots are exported to and applied from. Set it with `ait setup init DIR`. |
| `memory` | `true` | Include `~/.claude/projects/*/memory/` in exports. `--no-memory` overrides it for one run. |

## Environment variables

| Variable | Effect |
|---|---|
| `AI_TOOLKIT_DISABLE=1` | Every hook does nothing. Distill sets this for its own `claude -p` call. The 0.1 name `HINDSIGHT_DISABLE` still works. |
| `AI_TOOLKIT_CONFIG` | Path of the config file. |
| `XDG_CONFIG_HOME`, `XDG_STATE_HOME` | Move the config and state roots. |
| `CLAUDE_CONFIG_DIR` | Where Claude Code's own files are read from (default `~/.claude`), as in Claude Code. |
| `AI_TOOLKIT_NOW` | Freezes the clock (unix seconds). For tests. |
| `AI_TOOLKIT_<TOOL>_CMD` | Replaces an external CLI (`CLAUDE`, `GLAB`, `GH`), e.g. with a fake in tests. |
| `AI_TOOLKIT_SECRET_<ID>` | A secret value for `ait setup apply` (`AI_SETUP_SECRET_<ID>` still works). |
| `HINDSIGHT_LLM_CMD`, `HINDSIGHT_NO_LLM=1` | Replace the distill LLM command, or force the rule-based fallback. |
| `HINDSIGHT_NO_BACKGROUND=1` | SessionEnd doesn't start distill. For tests. |

## Where data lives

| What | Where | Synced? |
|---|---|---|
| Code | this repo | public git |
| Settings | `~/.config/ai-toolkit/config.json` | never |
| Machine-local state (queues, offsets, caches, logs, backups, retro evidence) | `~/.local/state/ai-toolkit/<feature>/` | never |
| Lessons and events | each hindsight store's `path` (git repos) | `hs sync` to each store's private remote, manually |
| Setup snapshots | `setup.snapshot_dir` (git repo) | `ait setup export --push`, manually |

Nothing is kept in the plugin's own data folder, because Claude Code deletes that folder when the plugin is uninstalled, and your memory has to survive an uninstall.
