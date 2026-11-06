"""Telegram outbox drainer: id order, retry with backoff, done only after success (AR10)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from leregister.core.outbox import backoff_seconds
from leregister.core.ports import Clock, OutboxQueue
from leregister.core.replies import render, split_message

log = logging.getLogger(__name__)

Send = Callable[[int, str], Awaitable[None]]


class TelegramDrainer:
    def __init__(self, queue: OutboxQueue, clock: Clock, send: Send) -> None:
        self._queue = queue
        self._clock = clock
        self._send = send
        self._lock = asyncio.Lock()  # one drainer: never two sends of the same row at once

    async def drain(self) -> None:
        async with self._lock:
            now = self._clock.now()
            for item in await self._queue.fetch_due("telegram", now):
                try:
                    text = render(item.kind, item.args, item.journal_payload, item.booking)
                    for chunk in split_message(text):
                        await self._send(item.chat_id, chunk)
                except Exception as exc:  # a failed row waits; later rows are not blocked
                    log.warning("send failed outbox_id=%s error=%s", item.id, type(exc).__name__)
                    retry_at = self._clock.now() + timedelta(seconds=backoff_seconds(item.attempts + 1))
                    await self._bookkeeping(self._queue.mark_failed(item.id, retry_at), item.id)
                else:
                    await self._bookkeeping(self._queue.mark_done(item.id, self._clock.now()), item.id)

    @staticmethod
    async def _bookkeeping(call: Awaitable[None], row_id: int) -> None:
        """A failed status write must not stop later rows (the row is then resent: at-least-once)."""
        try:
            await call
        except Exception as exc:
            log.warning("outbox status update failed outbox_id=%s error=%s", row_id, type(exc).__name__)
