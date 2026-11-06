"""Reply wording. The only place that renders Owner-facing text for commands."""

from __future__ import annotations

from leregister.core.parser import ParsedNew, Rejected

EXAMPLE = "New 2 Sam +96171123456 12-15 dec"


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
