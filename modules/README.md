# Transitional shims (delete after switching to the plugin)

Before 0.2, `install.sh` pointed `~/.claude/settings.json` hooks, `~/.local/bin/{hs,ai-rules,ai-setup}` and
`~/.claude/commands/{lesson,mr-retro}.md` at files in this folder. These shims forward those paths to the new
layout so an old install keeps working until you run the migration in docs/getting-started.md. Nothing new goes here.
