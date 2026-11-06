from helpers import MovableClock

from leregister.core.commands import decide, edited_message_decision
from leregister.core.events import EventType


def run(text):
    return decide(text, update_id=5, clock=MovableClock(), chalet_count=40, max_stay=60)


def test_rejection_is_journaled_with_reason_only():
    d = run("New 2 Sam 12-15 dec")
    assert d.journal.event_type is EventType.COMMAND_REJECTED
    assert (d.journal.subject_type, d.journal.subject_id) == ("command", "5")
    assert list(d.journal.payload) == ["reason"] and "phone" in d.journal.payload["reason"]
    assert d.reply.kind == "rejected" and d.reply.args == {}


def test_valid_new_has_no_journal_and_carries_parsed_values():
    d = run("New 2 Sam +96171123456 12-15 dec")
    assert d.journal is None and d.reply.kind == "new_preview"
    assert d.reply.args["check_in"] == "2026-12-12" and d.reply.args["name"] == "Sam"


def test_edited_message_decision_changes_nothing():
    d = edited_message_decision()
    assert d.journal is None and d.reply.kind == "edit_notice"
