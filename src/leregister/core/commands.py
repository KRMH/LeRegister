"""Pure decision for one Owner message: what to journal and what to answer."""

from __future__ import annotations

from leregister.core.events import Decision, EventType, JournalEntry, ReplyRequest
from leregister.core.parser import ParsedNew, parse_command
from leregister.core.ports import Clock


def decide(text: str, *, update_id: int, clock: Clock, chalet_count: int, max_stay: int) -> Decision:
    result = parse_command(text, clock=clock, chalet_count=chalet_count, max_stay=max_stay)
    if isinstance(result, ParsedNew):
        # Story 1.3: a valid New is only echoed back. Story 1.4 records it and journals booking_recorded.
        return Decision(
            journal=None,
            reply=ReplyRequest(
                "new_preview",
                {
                    "chalet": result.chalet,
                    "name": result.name,
                    "phone": result.phone,
                    "check_in": result.check_in.isoformat(),
                    "check_out": result.check_out.isoformat(),
                },
            ),
        )
    entry = JournalEntry(
        at=clock.now(),
        event_type=EventType.COMMAND_REJECTED,
        subject_type="command",
        subject_id=str(update_id),
        payload={"reason": result.reason},
    )
    return Decision(journal=entry, reply=ReplyRequest("rejected"))


def edited_message_decision() -> Decision:
    """An edited message changes nothing; the Owner is told to send a Change command."""
    return Decision(journal=None, reply=ReplyRequest("edit_notice"))
