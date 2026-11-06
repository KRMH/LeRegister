"""Telegram adapter: long polling, Owner gate, temporary acknowledgement."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

from leregister.config import Settings
from leregister.core.access import is_owner

log = logging.getLogger(__name__)

ACK_TEXT = "LeRegister is running"


def build_application(settings: Settings) -> Application:
    app = ApplicationBuilder().token(settings.bot_token).build()
    app.bot_data["owner_id"] = settings.owner_id
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
    await message.reply_text(ACK_TEXT)
