# hindsight

Self-improving memory for Claude Code. It captures the moments where you push back on Claude, distills them into a small curated set of lessons, injects only the relevant ones at session start, and measures whether repeat pushbacks drop.

| Step | Status | What |
|---|---|---|
| 1 Capture | ✅ | Correction prompts, rejected tool uses and `/lesson` are written to a local queue |
| 2 Distill | ✅ | SessionEnd → background `claude -p --model haiku` turns moments into candidate lessons (rule fallback) |
| 3 Curate  | ✅ | Merge duplicates, promote after hits in 2 sessions, retire unused/ineffective, cap 50/scope, `hs review` |
| 4 Inject  | ✅ | SessionStart loads lessons for this repo, its languages, and global ones (≤15 lines) |
| 5 Measure | ✅ | `hs report`: pushbacks/session by week, before→after efficacy per lesson, detector precision |

## The loop

```
you push back ──► capture (UserPromptSubmit / Stop) ──► local queue (redacted clause only)
                                                            │ SessionEnd
                                                            ▼
          inject ◄── active/*.md ◄── curate ◄── distill (Haiku: match existing or propose new)
   (SessionStart)                  promote at 2 sessions · merge · retire · cap
          │
          └── events/<host>.jsonl ──► hs report (did repeats drop after activation?)
```

## Editing lessons

Lessons are plain Markdown in each store's `lessons/` folder. Edit the text, change `status:`
(candidate → active → retired/dismissed), or delete a section. The next curate run:
- marks hand-edited lessons `pinned`, so they are never rewritten, merged away or auto-retired;
- moves sections to the right file when you change `status:`, and records that as your decision;
- logs deletions.

`hs edit [ID]` opens the right file in `$EDITOR`. Every change is a git commit in the store.

## How efficacy is measured

For each active lesson, hindsight counts pushbacks matched to it per *relevant* session (same repo, same
language, or any session for global lessons), before and after activation. A lesson with ≥5 injected
sessions whose rate didn't drop is flagged ⚠ and retired (unless pinned).

Caveat: lessons are created *because* of pushbacks, so "before" rates are biased upward
(regression to the mean). Trust the trend over many sessions more than any single lesson's number.

## Where things live

| What | Where | Synced? |
|---|---|---|
| Code | this repo | public git |
| Machine config | `~/.config/ai-toolkit/hindsight.json` | never |
| Queue, offsets, log | `~/.local/state/hindsight/` | never |
| Lessons + events | memory stores, e.g. `~/.ai-memory/{personal,org}` | manual `hs sync` to each store's private remote |

**Routing:** each correction goes to the store whose `match` glob fits the normalized git remote of the repo you were working in (e.g. `*example-corp.com/*` → `org`). Anything else goes to the default store. Org knowledge never lands in your personal memory repo.

## Privacy

- Raw prompts are never stored. For a correction prompt, only the sentences that carried the correction signal are kept (≤200 chars).
- To learn *why* you pushed back, the local queue also keeps a short summary of the agent turn you corrected: your previous request (≤300 chars), its tool calls (file names, commands cut to 80 chars) and its last reply (≤300 chars). It is redacted, never synced, and deleted after distill; stores keep only the abstract `issue` and `why`. Turn it off with `"capture_context": false` in `~/.config/ai-toolkit/hindsight.json`.
- Everything is redacted before it is written: API keys and tokens, JWTs, AWS keys, `password=`-style values, emails, URL credentials, and `$HOME` → `~`.
- For rejected tool uses, the tool name, file extension, a one-line summary of the call (file name, or the command cut to 80 chars) and your typed feedback are kept. Never the diff. `"capture_context": false` drops the call summary too.
- Hooks no-op when `HINDSIGHT_DISABLE=1`.

## CLI (`hs`)

```
hs status | queue                      what's captured and where it routes
hs capture "text"                      explicit lesson (what /lesson uses)
hs distill [--dry-run] [--no-llm]      process the queue now (normally automatic at SessionEnd)
hs backfill [--dry-run] [-v]           re-derive queued moments from their transcripts with current capture rules
hs curate [--store S]                  merge / promote / retire / cap now
hs list [--status all|active|…] [--here]
hs show ID                             lesson + stats
hs edit [ID] · hs rm ID                edit in $EDITOR (pins it) · delete permanently
hs promote|retire|dismiss|restore ID
hs review [--list]                     triage candidates + auto-promoted lessons
hs inject [--cwd DIR]                  preview what SessionStart would inject
hs report [--repo here] [--weeks 8] [--json]
hs store list|init|add                 e.g. hs store add org --match '*example-corp.com/*' --remote git@…:me/ai-memory.git
hs sync [STORE]                        secret scan → commit → pull --rebase → push (manual only)
hs doctor                              health check
hs ui [--port 7319] [--no-open]        live read-only dashboard in the browser
hs purge --queue | --local | --store S
```

## Dashboard (`hs ui`)

A live, read-only view of the whole pipeline: stage health (capture → queue → distill → curate → store → inject),
which hooks are registered, and lessons per store with their efficacy. **Queue → Inbox** shows each raw pushback in
plain words (what you corrected or rejected, and what Claude was working on). **Queue → Processed** shows what each one
became after distill: a lesson, or noise. **In Claude's context** shows exactly what SessionStart injects for each repo
you've worked in. Events, the report and `hindsight.log` are there too. It refreshes every 3 seconds and highlights what's new.

```bash
pnpm -C modules/hindsight/ui install && pnpm -C modules/hindsight/ui build   # once, needs Node
hs ui                     # serves http://127.0.0.1:7319 and opens it
```

The server binds to 127.0.0.1, rejects requests whose `Host` isn't local, and never writes. For UI work, run
`hs ui --api-only` and `pnpm -C modules/hindsight/ui dev`; Vite proxies `/api` to it.

## Architecture

See [../../docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md).

## Tests

```bash
modules/hindsight/tests/run_tests.sh          # all steps, offline, throwaway HOME
modules/hindsight/tests/run_tests.sh step1
```
