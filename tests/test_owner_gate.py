import asyncio
import sqlite3
from types import SimpleNamespace

from helpers import MovableClock, Sender, make_drainer, open_store

from leregister.adapters.telegram.bot import handle_update
from leregister.core.access import is_owner

OWNER = 42
VALID_NEW = "New 2 Sam +96171123456 12-15 dec"
PREVIEW = "Understood (not saved yet): Chalet 2, Sam, +96171123456, 2026-12-12 to 2026-12-15 (3 nights)"


class Env:
    def __init__(self, tmp_path, owner=OWNER):
        self.clock = MovableClock()
        self.store = open_store(tmp_path)
        self.sender = Sender()
        self.owner = owner
        self.db = tmp_path / "t.db"

    def send(self, user_id=OWNER, chat_type="private", text=VALID_NEW, update_id=1, edited=False, with_message=True):
        message = SimpleNamespace(text=text) if with_message else None
        update = SimpleNamespace(
            update_id=update_id,
            effective_user=SimpleNamespace(id=user_id) if user_id is not None else None,
            effective_chat=SimpleNamespace(type=chat_type, id=1) if chat_type else None,
            effective_message=message,
            edited_message=message if edited else None,
        )
        ctx = SimpleNamespace(
            bot_data={
                "owner_id": self.owner,
                "clock": self.clock,
                "chalet_count": 40,
                "max_stay": 60,
                "store": self.store,
                "drainer": make_drainer(self.store, self.clock, self.sender),
            }
        )
        asyncio.run(handle_update(update, ctx))

    def rows(self, sql):
        con = sqlite3.connect(self.db)
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def texts(self):
        return [text for _, text in self.sender.sent]


def test_owner_valid_new_is_echoed_not_journaled(tmp_path):
    env = Env(tmp_path)
    env.send()
    assert env.texts() == [PREVIEW]
    assert env.rows("SELECT COUNT(*) FROM journal") == [(0,)]
    assert env.rows("SELECT status FROM outbox") == [("done",)]


def test_rejected_command_is_journaled_with_reason_and_answered(tmp_path):
    env = Env(tmp_path)
    env.send(text="New 2 Sam 12-15 dec")
    (text,) = env.texts()
    assert text.startswith("Could not understand, please resend like: New 2 Sam +96171123456 12-15 dec")
    assert "phone" in text
    rows = env.rows("SELECT event_type, subject_type, subject_id, payload FROM journal")
    assert len(rows) == 1 and rows[0][:3] == ("command_rejected", "command", "1")
    assert "phone" in rows[0][3] and "Sam" not in rows[0][3]  # reason only, never the message text
    assert env.rows("SELECT update_id FROM processed_updates") == [(1,)]


def test_non_new_message_gets_generic_reply(tmp_path):
    env = Env(tmp_path)
    env.send(text="hello")
    assert env.texts()[0].startswith("Could not understand")


def test_duplicate_update_id_is_ignored(tmp_path):
    env = Env(tmp_path)
    env.send(text="hello", update_id=7)
    env.send(text="hello", update_id=7)
    assert len(env.texts()) == 1
    assert env.rows("SELECT COUNT(*) FROM journal") == [(1,)]
    assert env.rows("SELECT COUNT(*) FROM outbox") == [(1,)]


def test_edited_message_changes_nothing_and_asks_for_change_command(tmp_path):
    env = Env(tmp_path)
    env.send(edited=True, update_id=9)
    assert env.texts() == ["Edits are not applied, please send a Change command instead"]
    assert env.rows("SELECT COUNT(*) FROM journal") == [(0,)]


def test_other_account_group_and_empty_updates_leave_no_trace(tmp_path):
    env = Env(tmp_path)
    env.send(user_id=7)
    env.send(chat_type="group", update_id=2)
    env.send(user_id=None, chat_type="channel", update_id=3)
    env.send(with_message=False, update_id=4)
    assert env.sender.sent == []
    for table in ("journal", "outbox", "processed_updates"):
        assert env.rows(f"SELECT COUNT(*) FROM {table}") == [(0,)]


def test_new_owner_id_only_new_account_accepted(tmp_path):
    env = Env(tmp_path, owner=99)
    env.send(user_id=OWNER)
    assert env.sender.sent == []
    env.send(user_id=99, update_id=2)
    assert env.texts() == [PREVIEW]


def test_is_owner_pure():
    assert is_owner(1, "private", 1)
    assert not is_owner(None, "private", 1)
    assert not is_owner(1, "supergroup", 1)


def test_build_application_wires_owner_store_drainer_and_retry_job(tmp_path):
    from telegram.ext import MessageHandler

    from leregister.adapters.telegram.bot import build_application
    from leregister.config import Settings

    clock = MovableClock()
    store = open_store(tmp_path)
    app = build_application(
        Settings(bot_token="123:abc", owner_id=77, chalet_count=12, max_stay=10), clock, store, store
    )
    assert app.bot_data["owner_id"] == 77
    assert app.bot_data["clock"] is clock and app.bot_data["store"] is store
    assert (app.bot_data["chalet_count"], app.bot_data["max_stay"]) == (12, 10)
    assert app.bot_data["drainer"] is not None
    handlers = [h for group in app.handlers.values() for h in group]
    assert any(isinstance(h, MessageHandler) and h.callback is handle_update for h in handlers)
    assert app.error_handlers
    assert len(app.job_queue.jobs()) == 1
    store.close()


def test_real_send_wiring_and_retry_job_deliver_queued_rows(tmp_path, monkeypatch):
    from leregister.adapters.telegram.bot import build_application, retry_outbox
    from leregister.config import Settings
    from leregister.core.commands import edited_message_decision

    clock = MovableClock()
    store = open_store(tmp_path)
    app = build_application(Settings(bot_token="123:abc", owner_id=77), clock, store, store)
    sent = []

    async def fake_send_message(self, chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(type(app.bot), "send_message", fake_send_message)
    asyncio.run(store.record_command(1, 55, edited_message_decision(), clock.now()))
    asyncio.run(retry_outbox(SimpleNamespace(bot_data=app.bot_data)))
    assert sent == [(55, "Edits are not applied, please send a Change command instead")]
    store.close()
