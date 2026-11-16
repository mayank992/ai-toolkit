"""Shapes of credentials, shared by everything that must keep them out of git.

lessons redacts them from captured text and refuses to push a store that contains one; setup
refuses to export a file that contains one. Keep this list the single source of truth.
"""
import re

# (kind, pattern) for provider-issued tokens: high confidence, few false positives.
TOKEN_SHAPES = [
    ("anthropic_or_openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{20,}")),
]

# Names of settings / env vars / headers whose values are secrets whatever they look like.
SECRET_NAME = re.compile(r"token|secret|passw|api[_-]?key|apikey|private[_-]?key|credential|auth|cookie|session", re.I)


def token_hits(text):
    """Kinds of provider tokens present in text."""
    return [kind for kind, rx in TOKEN_SHAPES if rx.search(text or "")]
