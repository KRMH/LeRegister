import asyncio
from types import SimpleNamespace

from leregister.adapters.telegram.bot import ACK_TEXT, handle_update
from leregister.core.access import is_owner

OWNER = 42


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def run(user_id, chat_type, owner=OWNER, with_message=True):
    msg = FakeMessage() if with_message else None
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id) if user_id is not None else None,
        effective_chat=SimpleNamespace(type=chat_type, id=1) if chat_type else None,
        effective_message=msg,
    )
    ctx = SimpleNamespace(bot_data={"owner_id": owner})
    asyncio.run(handle_update(update, ctx))
    return msg


def test_owner_private_gets_ack():
    assert run(OWNER, "private").replies == [ACK_TEXT] == ["LeRegister is running"]


def test_other_account_no_reply():
    assert run(7, "private").replies == []


def test_group_chat_no_reply():
    assert run(OWNER, "group").replies == []


def test_update_without_user_or_message_ignored():
    assert run(None, "channel").replies == []
    run(OWNER, "private", with_message=False)  # no crash


def test_new_owner_id_only_new_account_accepted():
    assert run(OWNER, "private", owner=99).replies == []
    assert run(99, "private", owner=99).replies == [ACK_TEXT]


def test_is_owner_pure():
    assert is_owner(1, "private", 1)
    assert not is_owner(None, "private", 1)
    assert not is_owner(1, "supergroup", 1)


def test_build_application_wires_owner_and_handler():
    from telegram.ext import MessageHandler

    from leregister.adapters.telegram.bot import build_application
    from leregister.config import Settings

    app = build_application(Settings(bot_token="123:abc", owner_id=77))
    assert app.bot_data["owner_id"] == 77
    handlers = [h for group in app.handlers.values() for h in group]
    assert any(isinstance(h, MessageHandler) and h.callback is handle_update for h in handlers)
    assert app.error_handlers
