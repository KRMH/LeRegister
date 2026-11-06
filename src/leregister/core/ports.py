"""Ports owned by the core. Adapters implement them."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from leregister.core.events import Decision, OutboxItem


class Clock(Protocol):
    """The only way core reads time."""

    def now(self) -> datetime:
        """Current timezone-aware instant."""
        ...


class Store(Protocol):
    """Records one Command atomically."""

    async def record_command(self, update_id: int, chat_id: int, decision: Decision, at: datetime) -> bool:
        """Write processed_updates, the journal row (if any) and the reply outbox row in one
        transaction. Returns False, writing nothing, when `update_id` was already processed."""
        ...


class OutboxQueue(Protocol):
    """What a drainer needs from the outbox."""

    async def fetch_due(self, destination: str, now: datetime, limit: int = 50) -> list[OutboxItem]: ...

    async def mark_done(self, row_id: int, now: datetime) -> None: ...

    async def mark_failed(self, row_id: int, retry_at: datetime) -> None: ...
