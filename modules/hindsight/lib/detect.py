"""Correction ("pushback") detector for user prompts.

Score-based: each positive signal adds weight, negative patterns subtract.
A prompt is a pushback when score >= THRESHOLD. Only the sentences that carried
a signal are kept (the "clause"), never the full prompt.
"""
import re

THRESHOLD = 2.0
MAX_CLAUSE = 200
# Corrections are short and come first; long prompts are usually pasted material.
SCAN_LIMIT_LONG_PROMPT = 500
LONG_PROMPT = 1500

# (name, weight, regex). Matched case-insensitively per sentence.
SIGNALS = [
    ("lead_no", 2.0, r"^\s*(no|nope|nah)\b(?!-)[\s,.!:;]"),
    ("use_x_instead", 2.5, r"\b(use|try|prefer|go with|switch to)\b.{1,60}\binstead\b"),
    ("instead", 1.0, r"\binstead\b"),
    ("dont", 1.5, r"\b(don'?t|do not|never|please don'?t|stop)\s+(use|add|do|write|create|change|touch|modify|call|run|put|make|edit|delete|remove|install|commit|push|mock|import|rename|refactor|include)\b"),
    ("lead_dont", 2.0, r"^\s*(please\s+)?(don'?t|do not|never)\s+\w+"),
    ("lead_wrong", 2.0, r"^\s*(wrong\b|(that'?s|this is|it'?s|you'?re)\s+(wrong|incorrect|not (right|correct|what i)))"),
    ("lead_stop", 2.0, r"^\s*(stop|wait|hold on)\b"),
    ("wrong", 1.5, r"\b(that'?s|this is|it'?s|you'?re|is)\s+(wrong|incorrect|not (right|correct|what i))\b"),
    ("not_like_that", 2.0, r"^\s*not\s+(like\s+)?(that|this)\b"),
    ("revert", 2.0, r"\b(revert|undo|roll\s?back)\b"),
    ("i_said", 2.5, r"\bi\s+(already\s+)?(said|told you|asked( you)?\s+(to|for|not))\b"),
    ("why_did_you", 2.0, r"\bwhy\s+(did|would|are)\s+you\b"),
    ("should_have", 2.0, r"\byou\s+(should(n'?t)?\s+have|forgot|missed|ignored)\b"),
    ("no_need", 1.5, r"\bno need (to|for)\b"),
    ("lead_actually", 1.0, r"^\s*actually\b"),
    ("not_x_but_y", 1.0, r"\bnot\b.{1,40}\bbut\b"),
]

NEGATIVES = [
    r"\bno (problem|worries|idea|rush|doubt)\b",
    r"\bno-op\b",
    r"\b(don'?t|do not) (know|understand|worry|care|mind|remember)\b",
    r"\bthank(s| you)\b",
    r"\bnever ?mind\b",
]

_SIG = [(n, w, re.compile(p, re.I)) for n, w, p in SIGNALS]
_NEG = [re.compile(p, re.I) for p in NEGATIVES]
_SENT_SPLIT = re.compile(r"(?<=[.!?\n])\s+")


def _sentences(text):
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def detect(prompt):
    """Return dict(score, signals, clause) or None if not a pushback."""
    if not prompt or prompt.lstrip().startswith("/"):
        return None
    text = prompt if len(prompt) <= LONG_PROMPT else prompt[:SCAN_LIMIT_LONG_PROMPT]
    score = 0.0
    signals = []
    clause_parts = []
    for sent in _sentences(text):
        negs = sum(1 for rx in _NEG if rx.search(sent))
        hits = [(n, w) for n, w, rx in _SIG if rx.search(sent)]
        # A softener cancels a lead word in the same sentence ("No worries.", "No problem, thanks"):
        # drop the pair rather than letting the lead word's weight outvote its own softener.
        for n, w in [h for h in hits if h[0].startswith("lead_")]:
            if not negs:
                break
            hits.remove((n, w))
            negs -= 1
        names = {n for n, _ in hits}
        if "use_x_instead" in names:
            hits = [h for h in hits if h[0] != "instead"]  # implied by "use X instead"
        sent_weight = sum(w for _, w in hits)
        neg = 1.5 * negs
        for n, w in hits:
            if n not in signals:
                signals.append(n)
                score += w
        score -= neg
        # Keep a sentence whose signals outweigh its remaining softeners ("Thanks, but use pnpm instead").
        if sent_weight > neg:
            clause_parts.append(sent)
    # "instead" is implied by "use X instead"; don't double count.
    if "use_x_instead" in signals and "instead" in signals:
        score -= 1.0
    if score < THRESHOLD or not clause_parts:
        return None
    clause = " ".join(clause_parts)
    if len(clause) > MAX_CLAUSE:
        clause = clause[: MAX_CLAUSE - 1] + "…"
    return {"score": round(score, 2), "signals": signals, "clause": clause}
