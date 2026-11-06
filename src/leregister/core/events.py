"""Journal events and the small value types passed between core and adapters (AR5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Closed list of journal event types. Mirrored by a CHECK in the store migration."""

    BOOKING_RECORDED = "booking_recorded"
    BOOKING_CHANGED = "booking_changed"
    BOOKING_CANCELLED = "booking_cancelled"
    OVERLAP_DETECTED = "overlap_detected"
    RATING_CHANGED = "rating_changed"
    COMMAND_REJECTED = "command_rejected"
    SUMMARY_SENT = "summary_sent"
    BACKUP_DONE = "backup_done"
    SYNC_FAILED = "sync_failed"
    BOT_STARTED = "bot_started"
    PROPOSAL_CONFIRMED = "proposal_confirmed"
    PROPOSAL_DISCARDED = "proposal_discarded"


@dataclass(frozen=True)
class JournalEntry:
    at: datetime  # timezone-aware; the store writes it as UTC
    event_type: EventType
    subject_type: str
    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    related_booking_id: int | None = None


@dataclass(frozen=True)
class ReplyRequest:
    """What to tell the Owner. Rendered to text only at send time."""

    kind: str  # rejected | new_preview | edit_notice
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    journal: JournalEntry | None
    reply: ReplyRequest


@dataclass(frozen=True)
class OutboxItem:
    id: int
    chat_id: int
    kind: str
    args: dict[str, Any]
    journal_payload: dict[str, Any] | None
    attempts: int
