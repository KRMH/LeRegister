"""Telegram adapter: long polling, Owner gate, records each Command, drains the reply outbox."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

from leregister.adapters.telegram.drainer import TelegramDrainer
from leregister.config import Settings
from leregister.core.access import is_owner
from leregister.core.commands import decide, decide_free_text, edited_message_decision
from leregister.core.events import ReplyRequest
from leregister.core.interpret import is_free_text
from leregister.core.ports import Clock, Interpreter, OutboxQueue, Store
from leregister.core.replies import render

log = logging.getLogger(__name__)

RETRY_INTERVAL_SECONDS = 5


def build_application(
    settings: Settings,
    clock: Clock,
    store: Store,
    queue: OutboxQueue,
    interpreter: Interpreter | None = None,
) -> Application:
    builder = ApplicationBuilder().token(settings.bot_token)
    close_interpreter = getattr(interpreter, "aclose", None)
    if close_interpreter is not None:

        async def release_interpreter(_app: Application) -> None:
            await close_interpreter()

        builder = builder.post_shutdown(release_interpreter)
    app = builder.build()
    app.bot_data["interpreter"] = interpreter  # None: free text stays off
    app.bot_data["owner_id"] = settings.owner_id
    app.bot_data["clock"] = clock
    app.bot_data["chalet_count"] = settings.chalet_count
    app.bot_data["max_stay"] = settings.max_stay
    app.bot_data["store"] = store
    async def send(chat_id: int, text: str) -> None:
        await app.bot.send_message(chat_id, text)

    app.bot_data["send"] = send
    app.bot_data["drainer"] = TelegramDrainer(queue, clock, send)
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
    store: Store = context.bot_data["store"]
    try:
        text = message.text or ""
        interpreter: Interpreter | None = context.bot_data.get("interpreter")
        if update.edited_message is not None:
            decision = edited_message_decision()
        elif interpreter is not None and is_free_text(text):
            decision = await decide_free_text(
                text,
                update_id=update.update_id,
                clock=clock,
                chalet_count=context.bot_data["chalet_count"],
                max_stay=context.bot_data["max_stay"],
                interpreter=interpreter,
            )
        else:
            decision = decide(
                message.text or "",
                update_id=update.update_id,
                clock=clock,
                chalet_count=context.bot_data["chalet_count"],
                max_stay=context.bot_data["max_stay"],
            )
        recorded = await store.record_command(update.update_id, chat.id, decision, clock.now())
    except Exception as exc:  # the transaction is rolled back: nothing from this Command remains
        log.error(
            "command failed update_id=%s chat_id=%s error=%s origin=%s",
            update.update_id,
            chat.id,
            type(exc).__name__,
            _origin(exc),
        )
        await _tell_owner_not_recorded(context, chat.id, update.update_id)
        return
    if not recorded:
        log.info("duplicate update ignored update_id=%s", update.update_id)
        return
    try:
        await context.bot_data["drainer"].drain()
    except Exception as exc:  # the Command is recorded; the retry job delivers the reply
        log.warning("reply delivery deferred update_id=%s error=%s", update.update_id, type(exc).__name__)


def _origin(exc: BaseException) -> str:
    """Where the exception was raised (file:line of the innermost frame): diagnosable, and free of message text."""
    tb = exc.__traceback__
    if tb is None:
        return "unknown"
    while tb.tb_next is not None:
        tb = tb.tb_next
    return f"{tb.tb_frame.f_code.co_filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{tb.tb_lineno}"


async def _tell_owner_not_recorded(context: ContextTypes.DEFAULT_TYPE, chat_id: int, update_id: int) -> None:
    """Never leave the Owner believing a failed Command was saved (FR-8, AR10).

    First choice is the outbox, which retries. The store is the likeliest thing to be broken here, so
    when queueing fails the notice is sent directly, best effort.
    """
    store: Store = context.bot_data["store"]
    queued = False
    try:
        await store.queue_reply(chat_id, ReplyRequest("command_failed"), context.bot_data["clock"].now())
        queued = True
    except Exception as exc:
        log.error("could not queue the failure notice update_id=%s error=%s", update_id, type(exc).__name__)
    if queued:
        try:
            await context.bot_data["drainer"].drain()
        except Exception as exc:  # the row is queued; the retry job delivers it
            log.warning("failure notice delivery deferred update_id=%s error=%s", update_id, type(exc).__name__)
        return
    try:
        await context.bot_data["send"](chat_id, render("command_failed", {}, None))
    except Exception as exc:
        log.error("could not send the failure notice update_id=%s error=%s", update_id, type(exc).__name__)
