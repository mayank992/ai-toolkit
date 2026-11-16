# 0001: hindsight design decisions

Status: accepted (0.1). The feature was renamed `lessons` in 0.3; this record keeps the name it had. Recorded together because they were made together while building hindsight.


| Decision | Alternatives considered | Why |
|---|---|---|
| Hooks run deterministic capture; the LLM runs only off the hot path | LLM classification on every prompt; asking Claude to self-report mistakes | Zero latency and zero cost per prompt. Capture is predictable and testable. The LLM's judgement is only needed in distill. |
| Markdown in git is the source of truth | SQLite or JSON database | You can read and edit it with any editor. You get diffs, history and revert for free. It syncs through ordinary git. |
| Append-only events per host; stats derived | Counters stored in the lesson files | No merge conflicts across machines. Stats can be recalculated whenever the formulas change. |
| Promote on distinct sessions, not on raw hits | Promote on the first correction | One heated session shouldn't create a permanent rule. The repeat is the evidence that the lesson matters. |
| Inject a small, scored subset | Load everything (like a big CLAUDE.md) | Context budget, relevance, and a clean "was it injected?" signal for measurement. |
| Route by git remote | One store; a manual store per session | Automatic and correct by construction for an org/personal split. |
| Manual sync | Automatic push on commit | Pushing to a remote is an outward-facing action. The secret scan runs at a point the developer chooses. |
| `claude -p --model haiku` | Calling the Anthropic API directly | Reuses the developer's existing Claude Code login, so there are no API keys to manage. |

