---
name: mr-retro
description: Post-merge retro — turn one MR's transcripts and review comments into rule updates you approve
argument-hint: <MR/PR number or URL>
allowed-tools: Bash(ait rules retro collect:*), Bash(ait rules retro log:*), Bash(ait rules show:*), Read
---
Run a retro for this merge request: $ARGUMENTS

The goal is to keep the rules Claude follows in this project accurate, so generated code needs less rework next time. Work only from the evidence; propose, never apply, until the developer answers.

1. Take the MR number from the argument (the last number in a URL). Run `ait rules retro collect <number>` from this project. It prints a JSON path and a one-line summary. Read the JSON with the Read tool. It holds:
   - `meta`: title, branch, author, merge commit.
   - `share`: how many new merged lines trace to Claude Code transcripts (`cc_pct`, `src_pct`, `test_pct`), per session, and `least_cc_files` (where the developer or another tool wrote most of the code). It is an upper bound.
   - `sessions[].prompts` / `sessions[].pushback`: the developer's prompts on this branch; `pushback` are the ones that look corrective.
   - `notes`: MR comments with `kind` = human, self (the MR author), ai-review or bot.
   - `rules`: the current CLAUDE.md / CLAUDE.local.md bullets, memory notes and lessons.
2. Read the pushback prompts and the human, self and ai-review notes. Ignore bot notes and questions that changed nothing. Group them into **findings**: one recurring mistake or one workflow habit each. A finding needs at least two pieces of evidence, or one from a human reviewer. For each, note whether it is about how code is written (a convention) or how the work was run (workflow: plan inputs, scope, review triage, verification).
3. For each finding, check `rules`:
   - **covered and held**: an existing rule says it and it was not violated here; skip it.
   - **covered but violated**: an existing rule says it and Claude still did it. Propose sharpening that rule (more specific trigger or example), or a hook if it was violated more than twice.
   - **new**: no rule says it. Propose one.
   - **stale or contradicted**: the merged code or a reviewer went the other way from an existing rule. Propose editing or removing the rule.
   Also flag rules from `rules` that overlap each other.
4. Put each proposal in the right place:
   - how code is written → a bullet in the repo-root `CLAUDE.local.md` (personal), under the matching section;
   - how Claude should behave, with a why → a memory note (new file plus a `MEMORY.md` line, or an edit to the existing note);
   - something Claude keeps doing despite a rule → a hook idea, described but not written.
   Never edit a committed `CLAUDE.md`, `.claude/settings.json` or anything shared with the team.
5. Show the developer one numbered table: `# | finding | evidence (session id + time, or note author + short quote ≤15 words) | proposal (new / sharpen / remove) | target file`. Under it, two lines: Claude's share of the merged code (overall / src / tests) and how it compares with the last retro, if the Retros list in `ait rules show` has one. Then stop and wait.
6. When the developer answers (for example "1, 3, 4; skip 2"), apply exactly the approved items. Keep memory notes in the existing format (frontmatter with name, description, metadata.type; body with **Why:** and **How to apply:**). Then run `ait rules retro log <number> --proposed <N> --applied <M> --note "<one line on what changed>"`, and reply with what changed and where.

Keep quotes short and never copy secrets, tokens or personal data into rules.
