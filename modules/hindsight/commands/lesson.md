---
description: Record a lesson for hindsight (self-improving memory)
argument-hint: <what Claude should do differently>
allowed-tools: Bash(hs capture:*)
---
The developer wants to record this lesson: $ARGUMENTS

1. Rewrite it as ONE short imperative sentence (≤120 chars) that Claude should follow in future sessions, e.g. "Use pnpm, never npm, in this repo". Remove any secrets, tokens, emails or personal data. If it is ambiguous, use the conversation so far to make it concrete.
2. Record it by running exactly (stdin heredoc, no other arguments):

```
hs capture <<'LESSON'
<the rewritten sentence>
LESSON
```

3. Reply with one line: the recorded sentence. Do not do anything else.
