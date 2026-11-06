"""Story 1.5: unexpected errors reach the Owner; a failing reply never blocks later Commands."""

import asyncio
import logging
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest
from helpers import MovableClock, Sender, make_drainer, open_store

import leregister.adapters.telegram.bot as bot_module
from leregister.adapters.telegram.bot import handle_update, retry_outbox
from leregister.core.replies import COMMAND_FAILED

OWNER = 42
NEW = "New 2 Sam +96171123456 12-15 dec"


class Harness:
    def __init__(self, tmp_path, store=None):
        self.clock = MovableClock()
        self.store = store or open_store(tmp_path)
        self.sender = Sender()
        self.drainer = make_drainer(self.store, self.clock, self.sender)
        self.db = tmp_path / "t.db"

    def send(self, text=NEW, update_id=1):
        message = SimpleNamespace(text=text)
        update = SimpleNamespace(
            update_id=update_id,
            effective_user=SimpleNamespace(id=OWNER),
            effective_chat=SimpleNamespace(type="private", id=1),
            effective_message=message,
            edited_message=None,
        )
        ctx = SimpleNamespace(
            bot_data={
                "owner_id": OWNER,
                "clock": self.clock,
                "chalet_count": 40,
                "max_stay": 60,
                "store": self.store,
                "drainer": self.drainer,
                "send": self.sender,
            }
        )
        asyncio.run(handle_update(update, ctx))
        return ctx

    def rows(self, sql):
        con = sqlite3.connect(self.db)
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def texts(self):
        return [text for _, text in self.sender.sent]


def bad_decision(real_decide):
    """A decision that fails after the client and booking rows were written, before commit."""

    def decide(*args, **kwargs):
        d = real_decide(*args, **kwargs)
        return replace(d, journal=replace(d.journal, payload={"x": object()}))

    return decide


def test_failure_after_the_state_change_rolls_back_and_tells_the_owner(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    monkeypatch.setattr(bot_module, "decide", bad_decision(bot_module.decide))
    h.send()
    assert h.texts() == [COMMAND_FAILED]
    for table in ("clients", "bookings", "journal", "processed_updates"):
        assert h.rows(f"SELECT COUNT(*) FROM {table}") == [(0,)]
    assert h.rows("SELECT kind, status, journal_id, booking_id FROM outbox") == [("command_failed", "done", None, None)]


def test_the_failure_log_line_carries_ids_only(tmp_path, monkeypatch, caplog):
    h = Harness(tmp_path)
    monkeypatch.setattr(bot_module, "decide", bad_decision(bot_module.decide))
    with caplog.at_level(logging.INFO):
        h.send(update_id=77)
    assert "update_id=77" in caplog.text and "chat_id=1" in caplog.text and "TypeError" in caplog.text
    for secret in ("Sam", "96171123456", "dec"):
        assert secret not in caplog.text


def test_a_bug_in_the_pure_decision_is_reported_too(tmp_path, monkeypatch):
    h = Harness(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(bot_module, "decide", boom)
    h.send()
    assert h.texts() == [COMMAND_FAILED]
    assert h.rows("SELECT COUNT(*) FROM processed_updates") == [(0,)]


class BrokenStore:
    """Everything raises: a locked or full database."""

    async def record_command(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    async def queue_reply(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")


def test_when_the_store_is_unusable_the_notice_is_sent_directly(tmp_path, caplog):
    h = Harness(tmp_path, store=BrokenStore())
    with caplog.at_level(logging.INFO):
        h.send()
    assert h.texts() == [COMMAND_FAILED]
    assert "OperationalError" in caplog.text and "Sam" not in caplog.text


def test_when_nothing_works_the_handler_still_does_not_raise(tmp_path, caplog):
    h = Harness(tmp_path, store=BrokenStore())
    h.sender.fail_chats = {1}
    with caplog.at_level(logging.ERROR):
        h.send()  # must not raise
    assert h.sender.sent == []
    assert "could not send the failure notice" in caplog.text


def test_a_queued_notice_that_cannot_be_drained_is_not_sent_twice(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    monkeypatch.setattr(bot_module, "decide", bad_decision(bot_module.decide))
    h.sender.fail_chats = {1}
    h.send()
    assert h.sender.sent == []  # no direct duplicate
    assert h.rows("SELECT kind, status, attempts FROM outbox") == [("command_failed", "pending", 1)]
    h.sender.fail_chats = set()
    h.clock.advance(10)
    asyncio.run(h.drainer.drain())
    assert h.texts() == [COMMAND_FAILED]


def test_a_failure_after_the_commit_never_says_not_recorded(tmp_path):
    h = Harness(tmp_path)

    class ExplodingDrainer:
        async def drain(self):
            raise RuntimeError("drain broke")

    h.drainer = ExplodingDrainer()
    h.send()  # must not raise
    assert h.rows("SELECT COUNT(*) FROM bookings") == [(1,)]
    assert h.sender.sent == []
    h.drainer = make_drainer(h.store, h.clock, h.sender)
    asyncio.run(retry_outbox(SimpleNamespace(bot_data={"drainer": h.drainer})))
    assert h.texts() == ["Recorded: Chalet 2, Sam, +96171123456, 2026-12-12 to 2026-12-15 (3 nights)"]


def test_a_failing_reply_stays_pending_and_does_not_block_later_commands(tmp_path):
    h = Harness(tmp_path)
    h.sender.fail_chats = {1}
    h.send(NEW, update_id=1)
    h.send("New 3 Lea +96171555555 20-22 dec", update_id=2)
    assert h.rows("SELECT COUNT(*) FROM bookings") == [(2,)]  # the second Command was recorded
    assert h.rows("SELECT status FROM outbox ORDER BY id") == [("pending",), ("pending",)]
    h.sender.fail_chats = set()
    h.clock.advance(60)
    asyncio.run(h.drainer.drain())
    assert [t.split(",")[0] for t in h.texts()] == ["Recorded: Chalet 2", "Recorded: Chalet 3"]  # id order
    assert h.rows("SELECT status FROM outbox ORDER BY id") == [("done",), ("done",)]


def test_a_duplicate_update_gets_no_failure_notice(tmp_path):
    h = Harness(tmp_path)
    h.send(update_id=5)
    h.send(update_id=5)
    assert len(h.texts()) == 1


def test_queue_reply_writes_one_outbox_row_and_nothing_else(tmp_path):
    from leregister.core.events import ReplyRequest

    store = open_store(tmp_path)
    asyncio.run(store.queue_reply(9, ReplyRequest("command_failed"), MovableClock().now()))
    con = sqlite3.connect(store.path)
    assert con.execute("SELECT chat_id, kind, status FROM outbox").fetchall() == [(9, "command_failed", "pending")]
    for table in ("processed_updates", "journal", "bookings", "clients"):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchall() == [(0,)]
    con.close()
    store.close()


def test_build_application_keeps_a_raw_sender_for_the_fallback(tmp_path):
    from leregister.adapters.telegram.bot import build_application
    from leregister.config import Settings

    store = open_store(tmp_path)
    app = build_application(Settings(bot_token="123:abc", owner_id=OWNER), MovableClock(), store, store)
    assert callable(app.bot_data["send"])
    store.close()


@pytest.fixture(autouse=True)
def _quiet_httpx():
    logging.getLogger("httpx").setLevel(logging.WARNING)


def test_failure_inside_the_transaction_after_the_booking_insert_rolls_back(tmp_path, monkeypatch):
    """Fault injection that does not depend on how the journal payload is serialised."""
    import leregister.adapters.store.store as store_module

    real = store_module._record_booking

    def insert_then_explode(conn, decision, at):
        real(conn, decision, at)  # client and booking rows are written inside the open transaction
        raise RuntimeError("disk full")

    monkeypatch.setattr(store_module, "_record_booking", insert_then_explode)
    h = Harness(tmp_path)
    h.send()
    assert h.texts() == [COMMAND_FAILED]
    for table in ("clients", "bookings", "journal", "processed_updates"):
        assert h.rows(f"SELECT COUNT(*) FROM {table}") == [(0,)]


def test_the_failure_log_names_where_it_happened_without_any_message_text(tmp_path, monkeypatch, caplog):
    h = Harness(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("Sam +96171123456 leaked")

    monkeypatch.setattr(bot_module, "decide", boom)
    with caplog.at_level(logging.INFO):
        h.send()
    assert "origin=test_failure_path.py:" in caplog.text
    assert "leaked" not in caplog.text and "Sam" not in caplog.text


def test_a_non_owner_whose_update_would_fail_gets_no_notice_and_no_store_access(tmp_path):
    h = Harness(tmp_path, store=BrokenStore())
    message = SimpleNamespace(text=NEW)
    update = SimpleNamespace(
        update_id=1,
        effective_user=SimpleNamespace(id=7),
        effective_chat=SimpleNamespace(type="private", id=1),
        effective_message=message,
        edited_message=None,
    )
    ctx = SimpleNamespace(
        bot_data={"owner_id": OWNER, "clock": h.clock, "chalet_count": 40, "max_stay": 60,
                  "store": h.store, "drainer": h.drainer, "send": h.sender}
    )
    asyncio.run(handle_update(update, ctx))
    assert h.sender.sent == []


def test_the_raw_sender_forwards_to_the_bot(tmp_path, monkeypatch):
    from leregister.adapters.telegram.bot import build_application
    from leregister.config import Settings

    sent = []

    async def fake_send_message(self, chat_id, text):
        sent.append((chat_id, text))

    store = open_store(tmp_path)
    app = build_application(Settings(bot_token="123:abc", owner_id=OWNER), MovableClock(), store, store)
    monkeypatch.setattr(type(app.bot), "send_message", fake_send_message)
    asyncio.run(app.bot_data["send"](5, "hello"))
    assert sent == [(5, "hello")]
    store.close()
