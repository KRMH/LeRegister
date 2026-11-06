import asyncio
from types import SimpleNamespace

from datetime import datetime, timezone

from leregister.adapters.telegram.bot import handle_update
from leregister.core.access import is_owner

OWNER = 42
VALID_NEW = "New 2 Sam +96171123456 12-15 dec"


class FixedClock:
    def now(self):
        return datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def run(user_id, chat_type, owner=OWNER, with_message=True, text=VALID_NEW):
    msg = FakeMessage() if with_message else None
    if msg:
        msg.text = text
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id) if user_id is not None else None,
        effective_chat=SimpleNamespace(type=chat_type, id=1) if chat_type else None,
        effective_message=msg,
    )
    ctx = SimpleNamespace(
        bot_data={"owner_id": owner, "clock": FixedClock(), "chalet_count": 40, "max_stay": 60}
    )
    asyncio.run(handle_update(update, ctx))
    return msg


def test_owner_valid_new_is_echoed_not_saved():
    assert run(OWNER, "private").replies == [
        "Understood (not saved yet): Chalet 2, Sam, +96171123456, 2026-12-12 to 2026-12-15 (3 nights)"
    ]


def test_owner_bad_message_gets_could_not_understand():
    (reply,) = run(OWNER, "private", text="New 2 Sam 12-15 dec").replies
    assert reply.startswith("Could not understand, please resend like: New 2 Sam +96171123456 12-15 dec")
    assert "phone" in reply


def test_non_new_message_gets_generic_reply():
    (reply,) = run(OWNER, "private", text="hello").replies
    assert reply.startswith("Could not understand")


def test_other_account_no_reply():
    assert run(7, "private").replies == []


def test_group_chat_no_reply():
    assert run(OWNER, "group").replies == []


def test_update_without_user_or_message_ignored():
    assert run(None, "channel").replies == []
    run(OWNER, "private", with_message=False)  # no crash


def test_new_owner_id_only_new_account_accepted():
    assert run(OWNER, "private", owner=99).replies == []
    assert run(99, "private", owner=99).replies[0].startswith("Understood")


def test_is_owner_pure():
    assert is_owner(1, "private", 1)
    assert not is_owner(None, "private", 1)
    assert not is_owner(1, "supergroup", 1)


def test_build_application_wires_owner_and_handler():
    from telegram.ext import MessageHandler

    from leregister.adapters.telegram.bot import build_application
    from leregister.config import Settings

    clock = FixedClock()
    app = build_application(
        Settings(bot_token="123:abc", owner_id=77, chalet_count=12, max_stay=10), clock
    )
    assert app.bot_data["owner_id"] == 77
    assert app.bot_data["clock"] is clock
    assert (app.bot_data["chalet_count"], app.bot_data["max_stay"]) == (12, 10)
    handlers = [h for group in app.handlers.values() for h in group]
    assert any(isinstance(h, MessageHandler) and h.callback is handle_update for h in handlers)
    assert app.error_handlers
