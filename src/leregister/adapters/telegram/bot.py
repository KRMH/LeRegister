"""Telegram adapter: long polling, Owner gate, `New` command replies."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

from leregister.config import Settings
from leregister.core.access import is_owner
from leregister.core.parser import ParsedNew, parse_command
from leregister.core.ports import Clock
from leregister.core.replies import reject_reply, understood_reply

log = logging.getLogger(__name__)


def build_application(settings: Settings, clock: Clock) -> Application:
    app = ApplicationBuilder().token(settings.bot_token).build()
    app.bot_data["owner_id"] = settings.owner_id
    app.bot_data["clock"] = clock
    app.bot_data["chalet_count"] = settings.chalet_count
    app.bot_data["max_stay"] = settings.max_stay
    app.add_handler(MessageHandler(filters.ALL, handle_update))
    app.add_error_handler(handle_error)
    return app


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error type only: tracebacks and updates can carry names, phones or the token."""
    log.error("update handling failed: %s", type(context.error).__name__)


async def handle_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner gate first. Everything else is dropped silently (AD-6, FR-3)."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message
    user_id = user.id if user else None
    chat_type = chat.type if chat else None
    owner_id: int = context.bot_data["owner_id"]

    if not is_owner(user_id, chat_type, owner_id):
        # ids only: never names, phones or text
        log.info("ignored update from user_id=%s chat_id=%s", user_id, chat.id if chat else None)
        return
    if message is None:
        return
    result = parse_command(
        message.text or "",
        clock=context.bot_data["clock"],
        chalet_count=context.bot_data["chalet_count"],
        max_stay=context.bot_data["max_stay"],
    )
    # Story 1.2: a valid New is only echoed back, never saved (Story 1.4 records it).
    reply = understood_reply(result) if isinstance(result, ParsedNew) else reject_reply(result)
    await message.reply_text(reply)
