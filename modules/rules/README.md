# rules

See every rule that shapes Claude Code in a project, where each one lives, and whether it holds. After each merged MR,
`/mr-retro` turns that MR's transcripts and review comments into rule changes you approve.

```
ai-rules show [PROJECT] [--json]          the rule stack: instructions, memory, hooks, lessons, problems
ai-rules projects                         projects with any rules, most recent first
ai-rules retro-data MR [--project DIR]    gather MR evidence for /mr-retro; prints the JSON path
ai-rules retro-log MR --proposed N --applied N [--note TEXT]
ai-rules fire HOOK DECISION               append to the hook-fire log (for hook scripts)
ai-rules snapshot                         dashboard JSON
```

The **Rules** section of `ai-toolkit ui` shows the same thing per project.

## What it reads (read-only)

| Layer | From | Marked |
|---|---|---|
| Instructions | `~/.claude/CLAUDE.md`, `<project>/CLAUDE.md`, `<project>/CLAUDE.local.md` | personal or shared, plus whether git tracks, ignores or would show the file |
| Memory | `~/.claude/projects/<key>/memory/*.md` and `MEMORY.md` | indexed or not, why / how to apply |
| Hooks | user `settings.json`, project `.claude/settings.json`, `.claude/settings.local.json` | scope, event, matcher, the script's docstring, fires in the last 30 days |
| Lessons | hindsight stores (`~/.config/ai-toolkit/hindsight.json`), lessons scoped global, `lang:*` or this repo | active or candidate |
| Retros | `retros.jsonl` written by `ai-rules retro-log` | MR, Claude's share of merged code, changes applied |

## Checks

- `CLAUDE.local.md` that git doesn't ignore (it would show in `git status`; fix: add it to `.git/info/exclude`).
- Memory notes missing from `MEMORY.md` (never loaded), index lines pointing at missing files, feedback notes without a **Why:**.
- Hook scripts that don't exist; personal hooks that don't write to the fire log.
- Rules said in more than one layer (overlap coefficient on content words, at least 4 shared).

## Hook-fire log

A hook opts in by appending one JSON line per decision to `$XDG_STATE_HOME/ai-toolkit/rules/fires.jsonl`
(default `~/.local/state/...`): `{"t": <unix>, "hook": "<script name>", "decision": "ask|deny|allow|warn", "project": "<cwd>"}`.
From a shell hook, `ai-rules fire <hook> <decision>` does the same. A hook that never fires is a candidate for removal;
one that fires a lot points at a rule Claude keeps missing.

## /mr-retro

1. `ai-rules retro-data <MR>` collects, for one MR (GitLab via `glab`, GitHub via `gh`):
   - Claude's share of the new merged lines (overall, source, tests, per session). A line counts as Claude's when a
     transcript wrote it before the merge; lines already in the repo are skipped. Bash scripts that quote old code make
     this an upper bound.
   - the developer's prompts in sessions on the MR branch, with the corrective ones flagged;
   - MR comments classed as human, self (the MR author), ai-review or bot;
   - the current rule stack.
2. Claude groups the evidence into findings, checks each against the existing rules (held / violated / new / stale),
   and shows one numbered table of proposals. Nothing is written until you answer.
3. Approved items go to `CLAUDE.local.md` (how code is written) or memory (how Claude behaves); repeat violations become
   hook ideas. Shared files are never edited. `ai-rules retro-log` records the result for the dashboard.

Evidence files stay local under `~/.local/state/ai-toolkit/rules/retro/`.

Tests: `tests/run_tests.sh` (offline, temporary HOME, fake `glab`).
