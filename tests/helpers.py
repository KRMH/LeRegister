"""Shared test helpers: a movable clock, a fake sender and a real store on a temp DB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from leregister.adapters.store import SqliteStore
from leregister.adapters.telegram.drainer import TelegramDrainer


class MovableClock:
    def __init__(self, now=None):
        self.current = now or datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)

    def now(self):
        return self.current

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)


def open_store(tmp_path, name="t.db"):
    store = SqliteStore(tmp_path / name)
    store.open()
    return store


class Sender:
    """Records sends; `fail_chats` makes sends to those chats raise."""

    def __init__(self):
        self.sent = []
        self.fail_chats = set()

    async def __call__(self, chat_id, text):
        if chat_id in self.fail_chats:
            raise RuntimeError("telegram down")
        self.sent.append((chat_id, text))


def make_drainer(store, clock, sender):
    return TelegramDrainer(store, clock, sender)
