"""Ports owned by the core. Adapters implement them."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from leregister.core.events import Decision, Draft, OutboxItem, ReplyRequest


class Clock(Protocol):
    """The only way core reads time."""

    def now(self) -> datetime:
        """Current timezone-aware instant."""
        ...


class InterpreterUnavailable(Exception):
    """The Interpreter could not give an answer: timeout, network error, HTTP error or unreadable reply."""


class Interpreter(Protocol):
    """Turns free text into raw model output. The caller validates it; the model can only propose."""

    async def complete(self, system: str, user: str) -> str:
        """Return the model's raw text answer, or raise InterpreterUnavailable."""
        ...


class Store(Protocol):
    """Records one Command atomically."""

    async def record_command(self, update_id: int, chat_id: int, decision: Decision, at: datetime) -> bool:
        """Write processed_updates, the journal row (if any) and the reply outbox row in one
        transaction. Returns False, writing nothing, when `update_id` was already processed."""
        ...

    async def get_draft(self, chat_id: int, now: datetime, ttl: timedelta) -> Draft | None:
        """The waiting draft for this chat, or None. A draft not changed within `ttl` is deleted and not returned."""
        ...

    async def purge_drafts(self, older_than: datetime) -> None:
        """Delete every draft last changed before `older_than`, so guest details do not linger."""
        ...

    async def queue_reply(self, chat_id: int, reply: ReplyRequest, at: datetime) -> None:
        """Queue one reply that belongs to no recorded Command (no processed_updates, no journal)."""
        ...


class OutboxQueue(Protocol):
    """What a drainer needs from the outbox."""

    async def fetch_due(self, destination: str, now: datetime, limit: int = 50) -> list[OutboxItem]: ...

    async def mark_done(self, row_id: int, now: datetime) -> None: ...

    async def mark_failed(self, row_id: int, retry_at: datetime) -> None: ...
