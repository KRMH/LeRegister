import asyncio
import sqlite3

from helpers import MovableClock, Sender, make_drainer, open_store

from leregister.core.events import Decision, EventType, JournalEntry, ReplyRequest
from leregister.core.outbox import backoff_seconds
from leregister.core.replies import split_message


def queue_reply(store, clock, update_id, chat_id=5, kind="edit_notice"):
    asyncio.run(store.record_command(update_id, chat_id, Decision(None, ReplyRequest(kind)), clock.now()))


def statuses(store):
    con = sqlite3.connect(store.path)
    try:
        return con.execute("SELECT id, status, attempts FROM outbox ORDER BY id").fetchall()
    finally:
        con.close()


def test_rows_are_sent_in_id_order_and_marked_done(tmp_path):
    clock, sender, store = MovableClock(), Sender(), open_store(tmp_path)
    for uid, chat in ((1, 10), (2, 20), (3, 30)):
        queue_reply(store, clock, uid, chat)
    asyncio.run(make_drainer(store, clock, sender).drain())
    assert [chat for chat, _ in sender.sent] == [10, 20, 30]
    assert statuses(store) == [(1, "done", 0), (2, "done", 0), (3, "done", 0)]
    store.close()


def test_failed_row_stays_pending_waits_for_backoff_and_does_not_block_later_rows(tmp_path):
    clock, sender, store = MovableClock(), Sender(), open_store(tmp_path)
    queue_reply(store, clock, 1, chat_id=10)
    queue_reply(store, clock, 2, chat_id=20)
    sender.fail_chats = {10}
    drainer = make_drainer(store, clock, sender)
    asyncio.run(drainer.drain())
    assert [chat for chat, _ in sender.sent] == [20]
    assert statuses(store) == [(1, "pending", 1), (2, "done", 0)]

    asyncio.run(drainer.drain())  # still inside the backoff window: not retried
    assert statuses(store)[0] == (1, "pending", 1)

    clock.advance(backoff_seconds(1) + 1)
    sender.fail_chats = set()
    asyncio.run(drainer.drain())
    assert [chat for chat, _ in sender.sent] == [20, 10]
    assert statuses(store) == [(1, "done", 1), (2, "done", 0)]
    store.close()


def test_backoff_grows_and_is_capped():
    assert [backoff_seconds(n) for n in (1, 2, 3)] == [2, 4, 8]
    assert backoff_seconds(50) == 300


def test_long_reply_is_split_at_4096(tmp_path):
    clock, sender, store = MovableClock(), Sender(), open_store(tmp_path)
    entry = JournalEntry(clock.now(), EventType.COMMAND_REJECTED, "command", "1", {"reason": "x" * 9000})
    asyncio.run(store.record_command(1, 5, Decision(entry, ReplyRequest("rejected")), clock.now()))
    asyncio.run(make_drainer(store, clock, sender).drain())
    assert len(sender.sent) >= 3
    assert all(len(text) <= 4096 for _, text in sender.sent)
    store.close()


def test_split_message_keeps_short_text_whole_and_loses_nothing():
    assert split_message("short") == ["short"]
    text = "\n".join(f"line {i}" for i in range(2000))
    parts = split_message(text, 100)
    assert all(len(p) <= 100 for p in parts) and "\n".join(parts) == text
    blob = "y" * 250
    assert "".join(split_message(blob, 100)) == blob


def test_concurrent_drains_send_each_row_once(tmp_path):
    clock, store = MovableClock(), open_store(tmp_path)
    queue_reply(store, clock, 1, chat_id=10)
    sent = []

    async def slow_send(chat_id, text):
        await asyncio.sleep(0.01)  # lets the second drain start while the first is mid-send
        sent.append(chat_id)

    drainer = make_drainer(store, clock, slow_send)

    async def both():
        await asyncio.gather(drainer.drain(), drainer.drain())

    asyncio.run(both())
    assert sent == [10]
    store.close()


def test_status_write_failure_does_not_stop_later_rows(tmp_path):
    clock, sender, store = MovableClock(), Sender(), open_store(tmp_path)
    queue_reply(store, clock, 1, chat_id=10)
    queue_reply(store, clock, 2, chat_id=20)
    real_mark_done = store.mark_done
    calls = []

    async def flaky_mark_done(row_id, now):
        calls.append(row_id)
        if row_id == 1:
            raise RuntimeError("database is locked")
        await real_mark_done(row_id, now)

    store.mark_done = flaky_mark_done
    asyncio.run(make_drainer(store, clock, sender).drain())
    assert [chat for chat, _ in sender.sent] == [10, 20] and calls == [1, 2]
    assert statuses(store) == [(1, "pending", 0), (2, "done", 0)]  # row 1 is resent later: at-least-once
    store.close()


def test_second_failure_waits_longer(tmp_path):
    clock, sender, store = MovableClock(), Sender(), open_store(tmp_path)
    queue_reply(store, clock, 1, chat_id=10)
    sender.fail_chats = {10}
    drainer = make_drainer(store, clock, sender)
    asyncio.run(drainer.drain())
    clock.advance(backoff_seconds(1) + 1)
    asyncio.run(drainer.drain())
    assert statuses(store) == [(1, "pending", 2)]
    clock.advance(backoff_seconds(1) + 1)  # 3 s is not enough: the second wait is 4 s
    asyncio.run(drainer.drain())
    assert statuses(store) == [(1, "pending", 2)]
    store.close()


def test_split_message_never_returns_an_empty_chunk():
    parts = split_message("a" * 100 + "\n", 100)
    assert parts == ["a" * 100] and all(parts)
    assert split_message("") == [""]
