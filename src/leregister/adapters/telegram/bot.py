"""Telegram adapter: long polling, Owner gate, records each Command, drains the reply outbox."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

from leregister.adapters.telegram.drainer import TelegramDrainer
from leregister.config import Settings
from leregister.core.access import is_owner
from leregister.core.commands import decide, edited_message_decision
from leregister.core.ports import Clock, OutboxQueue, Store

log = logging.getLogger(__name__)

RETRY_INTERVAL_SECONDS = 5


def build_application(settings: Settings, clock: Clock, store: Store, queue: OutboxQueue) -> Application:
    app = ApplicationBuilder().token(settings.bot_token).build()
    app.bot_data["owner_id"] = settings.owner_id
    app.bot_data["clock"] = clock
    app.bot_data["chalet_count"] = settings.chalet_count
    app.bot_data["max_stay"] = settings.max_stay
    app.bot_data["store"] = store
    app.bot_data["drainer"] = TelegramDrainer(queue, clock, lambda chat_id, text: app.bot.send_message(chat_id, text))
    app.add_handler(MessageHandler(filters.ALL, handle_update))
    app.add_error_handler(handle_error)
    if app.job_queue is not None:
        app.job_queue.run_repeating(retry_outbox, interval=RETRY_INTERVAL_SECONDS, first=RETRY_INTERVAL_SECONDS)
    return app


async def retry_outbox(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pick up rows whose backoff has passed."""
    await context.bot_data["drainer"].drain()


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
    if message is None or chat is None:
        return

    clock: Clock = context.bot_data["clock"]
    if update.edited_message is not None:
        decision = edited_message_decision()
    else:
        decision = decide(
            message.text or "",
            update_id=update.update_id,
            clock=clock,
            chalet_count=context.bot_data["chalet_count"],
            max_stay=context.bot_data["max_stay"],
        )
    store: Store = context.bot_data["store"]
    recorded = await store.record_command(update.update_id, chat.id, decision, clock.now())
    if not recorded:
        log.info("duplicate update ignored update_id=%s", update.update_id)
        return
    await context.bot_data["drainer"].drain()
