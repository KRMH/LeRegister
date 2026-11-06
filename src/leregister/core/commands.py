"""Pure decision for one Owner message: what to record, journal, answer and remember."""

from __future__ import annotations

from dataclasses import replace

from leregister.core.events import Decision, Draft, EventType, JournalEntry, NewBooking, ReplyRequest
from leregister.core.interpret import (
    MAX_QUESTIONS,
    SYSTEM_PROMPT,
    Partial,
    build_user_message,
    has_content,
    has_reserved_word,
    has_stray_number,
    is_complete_by_itself,
    is_new_guest,
    is_stop_phrase,
    is_strict_attempt,
    merge,
    missing_part,
    parse_partial,
    redact_phones,
    render_strict_command,
)
from leregister.core.parser import ParsedNew, Rejected, parse_command
from leregister.core.ports import Clock, Interpreter, InterpreterUnavailable


def decide(text: str, *, update_id: int, clock: Clock, chalet_count: int, max_stay: int) -> Decision:
    result = parse_command(text, clock=clock, chalet_count=chalet_count, max_stay=max_stay)
    drop_draft = is_strict_attempt(text)  # a strict command, right or wrong, ends any waiting draft
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
        return Decision(journal=entry, reply=ReplyRequest("recorded"), booking=booking, clear_draft=drop_draft)
    entry = JournalEntry(
        at=clock.now(),
        event_type=EventType.COMMAND_REJECTED,
        subject_type="command",
        subject_id=str(update_id),
        payload={"reason": result.reason},
    )
    return Decision(journal=entry, reply=ReplyRequest("rejected"), clear_draft=drop_draft)


MANY_PHONES = "more than one phone number: send one booking at a time"
STRAY_NUMBER = "phone numbers must start with + and the country code, and dates must not be written with a year"
RESERVED_WORD = "please rephrase without the word PHONE_ followed by a digit"
NO_PROPOSAL = "that could not be turned into one booking"
STILL_INCOMPLETE = f"the booking was still incomplete after {MAX_QUESTIONS} questions"
UNAVAILABLE = "free text is unavailable right now"


async def decide_free_text(
    text: str,
    *,
    update_id: int,
    clock: Clock,
    chalet_count: int,
    max_stay: int,
    interpreter: Interpreter,
    draft: Draft | None = None,
) -> Decision:
    """Free text: the model may only propose. The strict parser judges; nothing is recorded here.

    An incomplete booking becomes a draft and one question; the next message fills or corrects it.
    """
    if draft is not None and is_stop_phrase(text):
        return Decision(journal=None, reply=ReplyRequest("draft_dropped"), clear_draft=True)
    if has_reserved_word(text):
        return _rejection(update_id, clock, RESERVED_WORD)
    redaction = redact_phones(text)
    if len(redaction.phones) > 1:
        return _rejection(update_id, clock, MANY_PHONES)
    if has_stray_number(redaction):
        return _rejection(update_id, clock, STRAY_NUMBER)
    phone = redaction.phones[0] if redaction.phones else None

    partial = Partial()
    content = has_content(redaction)
    if content:  # a message that is only a phone number needs no model call
        try:
            raw = await interpreter.complete(SYSTEM_PROMPT, build_user_message(redaction.text, draft))
        except InterpreterUnavailable:
            return _rejection(update_id, clock, UNAVAILABLE, reply_kind="free_text_unavailable")
        partial = parse_partial(raw) or Partial()

    base = draft or Draft()
    fresh = draft is not None and (is_new_guest(draft, partial) or is_complete_by_itself(partial, phone))
    if fresh:
        base = Draft()  # a different guest, or a whole booking of its own: start over
    elif draft is None and partial.is_empty() and (content or phone is None):
        return _rejection(update_id, clock, NO_PROPOSAL)  # nothing to build a draft from

    merged = merge(base, partial, phone)
    missing = missing_part(merged)
    if missing is None:
        command = render_strict_command(merged)
        result = parse_command(command, clock=clock, chalet_count=chalet_count, max_stay=max_stay)
        if isinstance(result, Rejected):
            return _rejection(update_id, clock, result.reason, clear_draft=True)
        return Decision(
            journal=None, reply=ReplyRequest("free_text_proposal", {"command": command}), clear_draft=True
        )
    if base.questions_asked >= MAX_QUESTIONS:  # at most 3 questions per draft, whatever the answers were
        return _rejection(update_id, clock, STILL_INCOMPLETE, clear_draft=True)
    asked = replace(merged, questions_asked=base.questions_asked + 1)
    return Decision(
        journal=None,
        reply=ReplyRequest("free_text_question", {"ask": missing, "name": asked.name, "chalet": asked.chalet}),
        draft=asked,
    )


def _rejection(
    update_id: int,
    clock: Clock,
    reason: str,
    *,
    reply_kind: str = "free_text_rejected",
    clear_draft: bool = False,
) -> Decision:
    entry = JournalEntry(
        at=clock.now(),
        event_type=EventType.COMMAND_REJECTED,
        subject_type="command",
        subject_id=str(update_id),
        payload={"reason": reason},
    )
    return Decision(journal=entry, reply=ReplyRequest(reply_kind), clear_draft=clear_draft)


def edited_message_decision() -> Decision:
    """An edited message changes nothing; the Owner is told to send a Change command."""
    return Decision(journal=None, reply=ReplyRequest("edit_notice"))
