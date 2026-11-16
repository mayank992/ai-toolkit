# Privacy and security

ai-toolkit reads your prompts, transcripts and Claude Code config. This page lists what it keeps, where it keeps it, and what never leaves your machine. The hindsight details are in [hindsight internals: privacy and security](features/hindsight.md#6-privacy-and-security).

## What is stored

| Feature | Stored | Never stored |
|---|---|---|
| hindsight | The sentence that carried a correction (≤200 chars, redacted). For a rejected tool use: the tool name, the file extension and a one-line summary of the call. In the **local queue only**, until distill: a short redacted summary of the corrected agent turn. In memory stores: lesson text and the abstract `why` / `issue` | Whole prompts, diffs, file contents, the agent-turn summary (after distill) |
| rules | The hook-fire log (hook name, decision, project path) and per-MR retro evidence, both local | Anything outside your machine |
| setup | Snapshot files with `{{HOME}}` paths and `${secret:id}` placeholders | Secret values. Export refuses if any exported file still contains a token |
| dashboard | Nothing; it reads on each request | Nothing |

## Redaction

Before anything is written, provider tokens (Anthropic/OpenAI, GitHub, GitLab, Slack, AWS, Google, JWTs, private keys, bearer tokens; see `src/ai_toolkit/core/secrets.py`) are redacted. hindsight also redacts `password=`-style assignments, credentials in URLs, emails and long opaque blobs, and replaces `$HOME` with `~`.

## What leaves your machine

- **hindsight** calls `claude -p --model haiku` during distill, after the session ends, using your existing Claude Code login. It sends the queued, redacted moments. `HINDSIGHT_NO_LLM=1` switches to rule-based distill.
- **Memory stores** are pushed only when you run `hs sync`. It scans the whole store for secrets first and refuses to push if it finds one.
- **Setup snapshots** are pushed only with `ait setup export --push`.
- **The dashboard** binds to 127.0.0.1 and rejects requests whose `Host` header isn't local.

Nothing else is sent anywhere. To wipe local data, run `hs purge --queue | --local | --store NAME`.
