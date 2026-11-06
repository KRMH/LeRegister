"""Reply wording and the single renderer. Plain text, English (AR10)."""

from __future__ import annotations

from datetime import date
from typing import Any

from leregister.core.events import BookingView
from leregister.core.parser import Rejected

EXAMPLE = "New 2 Sam +96171123456 12-15 dec"
TELEGRAM_LIMIT = 4096
EDIT_NOTICE = "Edits are not applied, please send a Change command instead"
COMMAND_FAILED = "That command was not recorded. Please resend it."
DRAFT_DROPPED = "Okay, I dropped that draft."
FREE_TEXT_UNAVAILABLE = f"Free text is unavailable right now. Please use the strict format, like: {EXAMPLE}"


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
    if kind == "command_failed":
        return COMMAND_FAILED
    if kind == "free_text_rejected":
        reason = (journal_payload or {}).get("reason", "unknown")
        return (
            "I could not turn that into a booking.\n"
            f"Problem: {reason}\n"
            'Please give the exact dates (for example "from the 20th to the 23rd of december") '
            f"and the phone with +, or use the strict format: {EXAMPLE}"
        )
    if kind == "free_text_question":
        return question_text(args["ask"], args.get("name"), args.get("chalet"))
    if kind == "draft_dropped":
        return DRAFT_DROPPED
    if kind == "free_text_unavailable":
        return FREE_TEXT_UNAVAILABLE
    if kind == "free_text_proposal":
        return f"I understood this, but nothing is saved yet. To record it, send exactly:\n{args['command']}"
    raise ValueError(f"unknown reply kind: {kind}")


def question_text(ask: str, name: str | None, chalet: int | None) -> str:
    """One question naming what is still missing and what is already known."""
    who = f" for {name}" if name else ""
    where = f" in chalet {chalet}" if chalet else ""
    if ask == "chalet":
        return f"Which chalet is it{who}?"
    if ask == "name":
        return f"What is the guest's name{where}?"
    if ask == "dates":
        return f'Which dates{who}{where}? Give the day and month, like "from the 20th to the 23rd of december".'
    if ask == "check_in":
        return f'From which day{who}{where}? Give the day and month, like "the 20th of december".'
    if ask == "check_out":
        return f'Until which day{who}{where}? Give the day and month, like "the 23rd of december".'
    if ask == "phone":
        return f"What is the guest's phone number{who}? Start with + and the country code, like +96171123456."
    raise ValueError(f"unknown question: {ask}")


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
