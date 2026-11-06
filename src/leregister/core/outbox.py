"""Outbox retry policy."""

from __future__ import annotations

MAX_BACKOFF_SECONDS = 300


def backoff_seconds(attempts: int) -> int:
    """Wait before the next try, after `attempts` failures: 2, 4, 8 ... capped at 5 minutes."""
    return min(2 ** max(attempts, 1), MAX_BACKOFF_SECONDS)
