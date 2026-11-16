"""The current time. AI_TOOLKIT_NOW (unix seconds) freezes it, so tests are deterministic."""
import os
import time
from datetime import datetime, timezone


def now_ts():
    v = os.environ.get("AI_TOOLKIT_NOW")
    return float(v) if v else time.time()


def iso(ts=None):
    """UTC timestamp like 2026-11-16T09:30:00Z."""
    return datetime.fromtimestamp(now_ts() if ts is None else ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
