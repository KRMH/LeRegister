"""Reply wording and the single renderer. Plain text, English (AR10)."""

from __future__ import annotations

from datetime import date
from typing import Any

from leregister.core.events import BookingView
from leregister.core.parser import Rejected

EXAMPLE = "New 2 Sam +96171123456 12-15 dec"
TELEGRAM_LIMIT = 4096
EDIT_NOTICE = "Edits are not applied, please send a Change command instead"


def reject_reply(rejected: Rejected) -> str:
    return (
        f"Could not understand, please resend like: {EXAMPLE}\n"
        f"Problem: {rejected.reason}"
    )


def describe_booking(booking: BookingView) -> str:
    nights = (date.fromisoformat(booking.check_out) - date.fromisoformat(booking.check_in)).days
    unit = "night" if nights == 1 else "nights"
    return (
        f"Chalet {booking.chalet}, {booking.name}, {booking.phone}, "
        f"{booking.check_in} to {booking.check_out} ({nights} {unit})"
    )


def render(
    kind: str,
    args: dict[str, Any],
    journal_payload: dict[str, Any] | None,
    booking: BookingView | None = None,
) -> str:
    """Turn an outbox row (ids and small arguments) into the text to send."""
    if kind == "rejected":
        return reject_reply(Rejected((journal_payload or {}).get("reason", "unknown")))
    if kind == "recorded":
        return f"Recorded: {describe_booking(_required(booking))}"
    if kind == "already_recorded":
        return f"Already recorded: {describe_booking(_required(booking))}"
    if kind == "edit_notice":
        return EDIT_NOTICE
    raise ValueError(f"unknown reply kind: {kind}")


def _required(booking: BookingView | None) -> BookingView:
    if booking is None:
        raise ValueError("this reply needs its booking")
    return booking


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split into chunks of at most `limit` characters, preferring line breaks."""
    chunks: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:]
        if rest.startswith("\n"):
            rest = rest[1:]
    if rest or not chunks:
        chunks.append(rest)
    return chunks
