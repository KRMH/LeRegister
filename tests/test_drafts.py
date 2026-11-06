"""Story 1.9: the drafts side table, its limits and its atomic writes."""

import asyncio
import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest
from helpers import MovableClock, open_store

from leregister.config import ConfigError, Settings
from leregister.core.events import Decision, Draft, EventType, JournalEntry, ReplyRequest

TTL = timedelta(minutes=10)
LEA = Draft(4, "Lea", "+96171555123", questions_asked=1)
QUESTION = ReplyRequest("free_text_question", {"ask": "dates", "name": "Lea", "chalet": 4})


def rows(store, sql):
    con = sqlite3.connect(store.path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def save(store, update_id, draft, clock, chat_id=5):
    decision = Decision(journal=None, reply=QUESTION, draft=draft)
    return asyncio.run(store.record_command(update_id, chat_id, decision, clock.now()))


def get(store, clock, chat_id=5):
    return asyncio.run(store.get_draft(chat_id, clock.now(), TTL))


def test_no_draft_means_none(tmp_path):
    store = open_store(tmp_path)
    assert get(store, MovableClock()) is None
    store.close()


def test_a_draft_round_trips_with_every_part_including_the_phone(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    full = Draft(4, "Lea", "+96171555123", 20, 12, 23, 12, 2)
    save(store, 1, full, clock)
    assert get(store, clock) == full
    store.close()


def test_a_draft_with_unknown_parts_keeps_them_unknown(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock)
    got = get(store, clock)
    assert got == LEA and got.check_in_day is None and got.check_out_month is None
    store.close()


def test_a_new_draft_replaces_the_old_one_for_the_same_chat(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock)
    save(store, 2, Draft(6, "Zoë", "+33612345678", questions_asked=1), clock)
    assert rows(store, "SELECT COUNT(*) FROM drafts") == [(1,)]
    assert get(store, clock).name == "Zoë"
    store.close()


def test_each_chat_has_its_own_draft(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock, chat_id=5)
    save(store, 2, replace(LEA, name="Sam"), clock, chat_id=6)
    assert get(store, clock, 5).name == "Lea" and get(store, clock, 6).name == "Sam"
    store.close()


def test_a_draft_expires_ten_minutes_after_its_last_change_and_is_deleted_when_found(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock)
    clock.advance(9 * 60 + 59)
    assert get(store, clock) == LEA
    clock.advance(2)
    assert get(store, clock) is None
    assert rows(store, "SELECT COUNT(*) FROM drafts") == [(0,)]
    store.close()


def test_every_change_restarts_the_clock(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock)
    clock.advance(8 * 60)
    save(store, 2, replace(LEA, questions_asked=2), clock)
    clock.advance(8 * 60)
    assert get(store, clock).questions_asked == 2
    store.close()


def test_clear_draft_deletes_it(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock)
    asyncio.run(store.record_command(2, 5, Decision(None, ReplyRequest("draft_dropped"), clear_draft=True), clock.now()))
    assert rows(store, "SELECT COUNT(*) FROM drafts") == [(0,)]
    store.close()


def test_clearing_when_there_is_no_draft_is_harmless(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    decision = Decision(None, ReplyRequest("draft_dropped"), clear_draft=True)
    assert asyncio.run(store.record_command(1, 5, decision, clock.now())) is True
    store.close()


def test_the_draft_is_written_in_the_same_transaction_as_the_command(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    entry = JournalEntry(clock.now(), EventType.COMMAND_REJECTED, "command", "1", {"x": object()})  # fails on insert
    bad = Decision(journal=entry, reply=QUESTION, draft=LEA)
    with pytest.raises(TypeError):
        asyncio.run(store.record_command(1, 5, bad, clock.now()))
    assert rows(store, "SELECT COUNT(*) FROM drafts") == [(0,)]
    assert rows(store, "SELECT COUNT(*) FROM processed_updates") == [(0,)]
    store.close()


def test_a_replayed_update_does_not_write_the_draft_twice(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    assert save(store, 1, LEA, clock) is True
    assert save(store, 1, replace(LEA, name="Other"), clock) is False
    assert get(store, clock).name == "Lea"
    store.close()


def test_drafts_never_touch_bookings_clients_or_the_journal(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock)
    for table in ("bookings", "clients", "journal"):
        assert rows(store, f"SELECT COUNT(*) FROM {table}") == [(0,)]
    store.close()


def test_the_database_limits_questions_to_three(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    with pytest.raises(sqlite3.IntegrityError):
        save(store, 1, replace(LEA, questions_asked=4), clock)
    store.close()


def test_the_migration_adds_drafts_after_bookings(tmp_path):
    store = open_store(tmp_path)
    assert rows(store, "SELECT version FROM schema_version") == [(1,), (2,), (3,)]
    store.close()


# ---- the setting -----------------------------------------------------------------------------------------


def _base(tmp_path):
    return {"LEREGISTER_BOT_TOKEN": "1:a", "LEREGISTER_OWNER_ID": "1", "LEREGISTER_ENV_FILE": str(tmp_path / "none")}


def test_the_draft_time_limit_defaults_to_ten_minutes_and_can_be_changed(tmp_path):
    assert Settings.load(_base(tmp_path)).draft_minutes == 10
    assert Settings.load({**_base(tmp_path), "LEREGISTER_DRAFT_MINUTES": "25"}).draft_minutes == 25


@pytest.mark.parametrize("value", ["0", "-5", "abc", "1441"])
def test_a_bad_draft_time_limit_stops_startup_naming_the_setting(tmp_path, value):
    with pytest.raises(ConfigError, match="LEREGISTER_DRAFT_MINUTES"):
        Settings.load({**_base(tmp_path), "LEREGISTER_DRAFT_MINUTES": value})


def test_a_draft_exactly_at_the_limit_survives_and_one_second_later_does_not(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock)
    clock.advance(10 * 60)
    assert get(store, clock) == LEA
    clock.advance(1)
    assert get(store, clock) is None
    store.close()


def test_timestamps_are_fixed_width_so_text_comparison_is_safe(tmp_path):
    from datetime import datetime, timezone

    from leregister.adapters.store.db import iso_utc

    widths = {
        len(iso_utc(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))),
        len(iso_utc(datetime(2026, 12, 31, 23, 59, 59, 123456, tzinfo=timezone.utc))),
    }
    assert len(widths) == 1


def test_purge_drafts_removes_only_old_ones(tmp_path):
    store, clock = open_store(tmp_path), MovableClock()
    save(store, 1, LEA, clock, chat_id=5)
    clock.advance(60)
    save(store, 2, replace(LEA, name="Sam"), clock, chat_id=6)
    asyncio.run(store.purge_drafts(clock.now() - timedelta(seconds=30)))
    assert rows(store, "SELECT chat_id FROM drafts") == [(6,)]
    store.close()


@pytest.mark.parametrize(
    "field,value",
    [("chalet", 0), ("check_in_day", 32), ("check_in_month", 13), ("check_out_day", 0), ("check_out_month", 13)],
)
def test_the_database_refuses_impossible_draft_values(tmp_path, field, value):
    store, clock = open_store(tmp_path), MovableClock()
    with pytest.raises(sqlite3.IntegrityError):
        save(store, 1, replace(LEA, **{field: value}), clock)
    store.close()
