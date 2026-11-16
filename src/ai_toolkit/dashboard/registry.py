"""The features the dashboard shows, in nav order. Adding a feature to the dashboard = one entry here
plus ui/src/features/<name>/index.tsx. `api` is a module exposing snapshot() -> JSON-able dict."""

FEATURES = [
    {"name": "hindsight", "title": "hindsight", "api": "ai_toolkit.hindsight.api",
     "tagline": "Learns from your pushback so Claude doesn't repeat mistakes"},
    {"name": "rules", "title": "Rules", "api": "ai_toolkit.rules.api",
     "tagline": "What Claude is told in each project, where it lives, and whether it holds"},
    {"name": "setup", "title": "Setup", "api": "ai_toolkit.setup.api",
     "tagline": "Your Claude Code setup, its health, and what a new machine would get"},
]
