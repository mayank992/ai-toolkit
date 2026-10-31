# hindsight

Self-improving memory for Claude Code. It captures the moments where you push back on Claude, distills them into a small curated set of lessons, injects only the relevant ones at session start, and measures whether repeat pushbacks drop.

| Step | Status | What |
|---|---|---|
| 1 Capture | ✅ | Correction prompts, rejected tool uses and `/lesson` are written to a local queue |
| 2 Distill | ⏳ | SessionEnd → Haiku turns moments into candidate lessons |
| 3 Curate  | ⏳ | Merge, promote at 2 hits, retire, cap 50/scope, `hs review` |
| 4 Inject  | ⏳ | SessionStart loads lessons for this repo, language or global |
| 5 Measure | ⏳ | Per-lesson efficacy and pushbacks/session report |

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
- Everything is redacted before it is written: API keys and tokens, JWTs, AWS keys, `password=`-style values, emails, URL credentials, and `$HOME` → `~`.
- For rejected tool uses, only the tool name, file extension and your typed feedback are kept. Never the diff or the command.
- Hooks no-op when `HINDSIGHT_DISABLE=1`.

## CLI (`hs`)

```
hs status                 config, stores, which store this repo routes to, queue counts
hs queue [-n 30] [--json] captured moments
hs capture "text"         explicit lesson (what /lesson uses)
hs store list|init|add    e.g. hs store add org --match '*example-corp.com/*' --remote git@…:me/ai-memory.git
hs doctor                 health check
hs purge --queue          delete the local queue
```

## Tests

```bash
modules/hindsight/tests/run_tests.sh          # all steps, offline, throwaway HOME
modules/hindsight/tests/run_tests.sh step1
```
