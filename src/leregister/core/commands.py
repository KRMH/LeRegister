"""Pure decision for one Owner message: what to record, journal and answer."""

from __future__ import annotations

from leregister.core.events import Decision, EventType, JournalEntry, NewBooking, ReplyRequest
from leregister.core.interpret import (
    SYSTEM_PROMPT,
    has_reserved_word,
    has_stray_number,
    parse_proposal,
    redact_phones,
    render_strict_command,
)
from leregister.core.parser import ParsedNew, Rejected, parse_command
from leregister.core.ports import Clock, Interpreter, InterpreterUnavailable


def decide(text: str, *, update_id: int, clock: Clock, chalet_count: int, max_stay: int) -> Decision:
    result = parse_command(text, clock=clock, chalet_count=chalet_count, max_stay=max_stay)
    if isinstance(result, ParsedNew):
        booking = NewBooking(
            chalet=result.chalet,
            name=result.name,
            phone=result.phone,
            check_in=result.check_in.isoformat(),
            check_out=result.check_out.isoformat(),
        )
        # The store decides "recorded" vs "already recorded" inside its transaction and fills in the
        # booking id: subject_id is a placeholder here.
        entry = JournalEntry(
            at=clock.now(),
            event_type=EventType.BOOKING_RECORDED,
            subject_type="booking",
            subject_id="",
            payload={
                "chalet": booking.chalet,
                "phone": booking.phone,
                "check_in": booking.check_in,
                "check_out": booking.check_out,
            },
        )
        return Decision(journal=entry, reply=ReplyRequest("recorded"), booking=booking)
    entry = JournalEntry(
        at=clock.now(),
        event_type=EventType.COMMAND_REJECTED,
        subject_type="command",
        subject_id=str(update_id),
        payload={"reason": result.reason},
    )
    return Decision(journal=entry, reply=ReplyRequest("rejected"))


PHONE_MISSING = "phone is missing: include the number with + and the country code"
MANY_PHONES = "more than one phone number: send one booking at a time"
STRAY_NUMBER = "phone numbers must start with + and the country code, and dates must not be written with a year"
RESERVED_WORD = "please rephrase without the word PHONE_ followed by a digit"
NO_PROPOSAL = "that could not be turned into one booking"
UNAVAILABLE = "free text is unavailable right now"


async def decide_free_text(
    text: str,
    *,
    update_id: int,
    clock: Clock,
    chalet_count: int,
    max_stay: int,
    interpreter: Interpreter,
) -> Decision:
    """Free text: the model may only propose. The strict parser judges; nothing is recorded here (Story 1.7 confirms)."""
    if has_reserved_word(text):
        return _rejection(update_id, clock, RESERVED_WORD)
    redaction = redact_phones(text)
    if not redaction.phones:
        return _rejection(update_id, clock, PHONE_MISSING)
    if len(redaction.phones) > 1:
        return _rejection(update_id, clock, MANY_PHONES)
    if has_stray_number(redaction):
        return _rejection(update_id, clock, STRAY_NUMBER)
    try:
        raw = await interpreter.complete(SYSTEM_PROMPT, redaction.text)
    except InterpreterUnavailable:
        return _rejection(update_id, clock, UNAVAILABLE, reply_kind="free_text_unavailable")
    proposal = parse_proposal(raw)
    if proposal is None:
        return _rejection(update_id, clock, NO_PROPOSAL)
    command = render_strict_command(proposal, redaction.phones[0])
    result = parse_command(command, clock=clock, chalet_count=chalet_count, max_stay=max_stay)
    if isinstance(result, Rejected):
        return _rejection(update_id, clock, result.reason)
    return Decision(journal=None, reply=ReplyRequest("free_text_proposal", {"command": command}))


def _rejection(update_id: int, clock: Clock, reason: str, *, reply_kind: str = "rejected") -> Decision:
    entry = JournalEntry(
        at=clock.now(),
        event_type=EventType.COMMAND_REJECTED,
        subject_type="command",
        subject_id=str(update_id),
        payload={"reason": reason},
    )
    return Decision(journal=entry, reply=ReplyRequest(reply_kind))


def edited_message_decision() -> Decision:
    """An edited message changes nothing; the Owner is told to send a Change command."""
    return Decision(journal=None, reply=ReplyRequest("edit_notice"))
