"""Redaction: strip secrets and personal identifiers before anything touches disk.

Applied to every clause at capture time and re-run as a scanner before `hs sync`. Provider token
shapes come from core.secrets (shared with setup); the PII and generic patterns below are lessons's.
"""
import os
import re

from ..core.secrets import TOKEN_SHAPES

_PATTERNS = list(TOKEN_SHAPES) + [
    # Credentials embedded in URLs: scheme://user:pass@host
    ("url_credentials", re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)")),
    # key=value / key: value style secrets
    ("secret_assignment", re.compile(
        r"(?i)\b(pass(word|wd)?|secret|token|api[_-]?key|access[_-]?key|auth|bearer|credential)s?\b"
        r"(\s*[:=]\s*)['\"]?[^\s'\"]{6,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Long opaque blobs (hex / base64) — likely secrets or hashes.
    ("long_hex", re.compile(r"\b[0-9a-fA-F]{32,}\b")),
    # Without "/": any 40+ run that mixes letters and digits (tokens are often single-case).
    ("long_base64", re.compile(r"\b(?=[A-Za-z0-9+]*\d)(?=[A-Za-z0-9+]*[A-Za-z])[A-Za-z0-9+]{40,}={0,2}")),
    # With "/": also require upper AND lower case, so long paths ("frontend/src/components/…") don't match.
    ("long_base64", re.compile(r"\b(?=[A-Za-z0-9+/]*\d)(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[A-Z])"
                               r"[A-Za-z0-9+/]{40,}={0,2}")),
]


def redact(text):
    """Return text with secrets replaced by [REDACTED:<kind>] and $HOME replaced by ~."""
    if not text:
        return text
    out = text
    for kind, pat in _PATTERNS:
        if kind == "secret_assignment":
            out = pat.sub(lambda m: m.group(1) + m.group(3) + "[REDACTED:secret]", out)
        else:
            out = pat.sub("[REDACTED:%s]" % kind, out)
    home = os.path.expanduser("~")
    if home and home != "/":
        out = out.replace(home, "~")
    return out


def scan(text):
    """Return list of pattern kinds that match (used as a pre-push guard)."""
    hits = []
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text or ""):
            # Our own placeholders are fine.
            if "[REDACTED" in text[max(0, m.start() - 10):m.end() + 1]:
                continue
            hits.append(kind)
            break
    return hits
