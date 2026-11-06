"""Reply wording and the single renderer. Plain text, English (AR10)."""

from __future__ import annotations

from datetime import date
from typing import Any

from leregister.core.parser import ParsedNew, Rejected

EXAMPLE = "New 2 Sam +96171123456 12-15 dec"
TELEGRAM_LIMIT = 4096
EDIT_NOTICE = "Edits are not applied, please send a Change command instead"


def reject_reply(rejected: Rejected) -> str:
    return (
        f"Could not understand, please resend like: {EXAMPLE}\n"
        f"Problem: {rejected.reason}"
    )


def understood_reply(parsed: ParsedNew) -> str:
    nights = parsed.nights
    unit = "night" if nights == 1 else "nights"
    return (
        f"Understood (not saved yet): Chalet {parsed.chalet}, {parsed.name}, {parsed.phone}, "
        f"{parsed.check_in.isoformat()} to {parsed.check_out.isoformat()} ({nights} {unit})"
    )


def render(kind: str, args: dict[str, Any], journal_payload: dict[str, Any] | None) -> str:
    """Turn an outbox row (ids and small arguments) into the text to send."""
    if kind == "rejected":
        return reject_reply(Rejected((journal_payload or {}).get("reason", "unknown")))
    if kind == "new_preview":
        return understood_reply(
            ParsedNew(
                chalet=args["chalet"],
                name=args["name"],
                phone=args["phone"],
                check_in=date.fromisoformat(args["check_in"]),
                check_out=date.fromisoformat(args["check_out"]),
            )
        )
    if kind == "edit_notice":
        return EDIT_NOTICE
    raise ValueError(f"unknown reply kind: {kind}")


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
