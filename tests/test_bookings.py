import asyncio
import sqlite3
from dataclasses import replace

import pytest
from helpers import MovableClock, Sender, make_drainer, open_store

from leregister.core.commands import decide

NEW = "New 2 Sam +96171123456 12-15 dec"


def send(store, update_id, text, chat_id=5, clock=None):
    clock = clock or MovableClock()
    decision = decide(text, update_id=update_id, clock=clock, chalet_count=40, max_stay=60)
    return asyncio.run(store.record_command(update_id, chat_id, decision, clock.now()))


def rows(store, sql):
    con = sqlite3.connect(store.path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def raw(store):
    con = sqlite3.connect(store.path, isolation_level=None)
    con.execute("PRAGMA foreign_keys=ON")
    return con


def drained_texts(store):
    sender = Sender()
    asyncio.run(make_drainer(store, MovableClock(), sender).drain())
    return [text for _, text in sender.sent]


def test_valid_new_creates_client_booking_journal_and_reply_in_one_transaction(tmp_path):
    store = open_store(tmp_path)
    assert send(store, 1, NEW) is True
    assert rows(store, "SELECT phone, name, rating FROM clients") == [("+96171123456", "Sam", 5)]
    assert rows(store, "SELECT id, status, superseded_by FROM bookings") == [(1, "active", None)]
    assert rows(store, "SELECT created_at FROM bookings")[0][0].startswith("2026-11-06T12:00:00")
    assert rows(store, "SELECT event_type, subject_id, related_booking_id FROM journal") == [
        ("booking_recorded", "1", 1)
    ]
    assert drained_texts(store) == ["Recorded: Chalet 2, Sam, +96171123456, 2026-12-12 to 2026-12-15 (3 nights)"]
    store.close()


def test_identical_active_booking_is_not_duplicated_and_is_not_journaled(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    send(store, 2, "New 2 Samuel +96171123456 12-15 dec")  # same chalet, phone and dates: the name is ignored
    assert rows(store, "SELECT COUNT(*) FROM bookings") == [(1,)]
    assert rows(store, "SELECT COUNT(*) FROM journal") == [(1,)]
    assert rows(store, "SELECT COUNT(*) FROM clients") == [(1,)]
    texts = drained_texts(store)
    assert texts[1] == "Already recorded: Chalet 2, Sam, +96171123456, 2026-12-12 to 2026-12-15 (3 nights)"
    store.close()


def test_same_phone_other_name_keeps_booking_name_and_first_client_name(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    send(store, 2, "New 3 Samuel +96171123456 20-22 dec")
    assert rows(store, "SELECT client_name FROM bookings ORDER BY id") == [("Sam",), ("Samuel",)]
    assert rows(store, "SELECT name FROM clients") == [("Sam",)]
    assert drained_texts(store)[1].startswith("Recorded: Chalet 3, Samuel,")
    store.close()


@pytest.mark.parametrize(
    "text",
    [
        "New 3 Sam +96171123456 12-15 dec",  # other chalet
        "New 2 Sam +96171999999 12-15 dec",  # other phone
        "New 2 Sam +96171123456 12-16 dec",  # other dates
    ],
)
def test_differing_chalet_phone_or_dates_creates_a_new_booking(tmp_path, text):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    send(store, 2, text)
    assert rows(store, "SELECT COUNT(*) FROM bookings") == [(2,)]
    store.close()


def test_a_cancelled_booking_does_not_block_the_same_stay(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    con.execute("UPDATE bookings SET status = 'cancelled'")
    con.close()
    send(store, 2, NEW)
    assert rows(store, "SELECT status FROM bookings ORDER BY id") == [("cancelled",), ("active",)]
    store.close()


def test_rejected_new_records_nothing_but_the_rejection(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, "New 2 Sam 12-15 dec")
    assert rows(store, "SELECT COUNT(*) FROM bookings") == [(0,)]
    assert rows(store, "SELECT COUNT(*) FROM clients") == [(0,)]
    assert rows(store, "SELECT event_type FROM journal") == [("command_rejected",)]
    store.close()


def test_failure_after_the_booking_insert_leaves_nothing_behind(tmp_path):
    store = open_store(tmp_path)
    clock = MovableClock()
    decision = decide(NEW, update_id=1, clock=clock, chalet_count=40, max_stay=60)
    # not JSON serialisable: fails after the client and booking rows were written
    bad = replace(decision, journal=replace(decision.journal, payload={"x": object()}))
    with pytest.raises(TypeError):
        asyncio.run(store.record_command(1, 5, bad, clock.now()))
    for table in ("clients", "bookings", "journal", "outbox", "processed_updates"):
        assert rows(store, f"SELECT COUNT(*) FROM {table}") == [(0,)]
    assert send(store, 1, NEW) is True
    store.close()


def test_the_database_itself_refuses_a_second_identical_active_booking(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO bookings (chalet, client_name, client_phone, check_in, check_out, created_at)"
            " VALUES (2, 'X', '+96171123456', '2026-12-12', '2026-12-15', 't')"
        )
    con.close()
    store.close()


# ---- triggers -------------------------------------------------------------------------------------------


def test_delete_on_bookings_aborts(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    with pytest.raises(sqlite3.DatabaseError, match="never deleted"):
        con.execute("DELETE FROM bookings")
    con.close()
    assert rows(store, "SELECT COUNT(*) FROM bookings") == [(1,)]
    store.close()


@pytest.mark.parametrize(
    "assignment",
    [
        "chalet = 9",
        "client_name = 'Other'",
        "client_phone = '+96171999999'",
        "check_in = '2026-12-13'",
        "check_out = '2026-12-20'",
        "created_at = 'x'",
        "id = 99",
    ],
)
def test_update_of_a_fixed_field_aborts(tmp_path, assignment):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    con.execute("INSERT INTO clients (phone, name, created_at) VALUES ('+96171999999', 'O', 't')")
    with pytest.raises(sqlite3.DatabaseError, match="only status and superseded_by"):
        con.execute(f"UPDATE bookings SET {assignment}")
    con.close()
    store.close()


@pytest.mark.parametrize("target", ["changed", "cancelled"])
def test_active_may_move_to_changed_or_cancelled(tmp_path, target):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    send(store, 2, "New 3 Sam +96171123456 12-15 dec")
    con = raw(store)
    con.execute(f"UPDATE bookings SET status = '{target}', superseded_by = 2 WHERE id = 1")
    con.close()
    assert rows(store, "SELECT status, superseded_by FROM bookings WHERE id = 1") == [(target, 2)]
    store.close()


def test_superseded_by_alone_may_be_set(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    send(store, 2, "New 3 Sam +96171123456 12-15 dec")
    con = raw(store)
    con.execute("UPDATE bookings SET superseded_by = 2 WHERE id = 1")
    con.close()
    assert rows(store, "SELECT superseded_by FROM bookings WHERE id = 1") == [(2,)]
    store.close()


@pytest.mark.parametrize(
    "start,target",
    [("cancelled", "active"), ("changed", "active"), ("changed", "cancelled"), ("cancelled", "changed")],
)
def test_forbidden_status_moves_abort(tmp_path, start, target):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    con.execute(f"UPDATE bookings SET status = '{start}'")
    with pytest.raises(sqlite3.DatabaseError, match="may only move active"):
        con.execute(f"UPDATE bookings SET status = '{target}'")
    con.close()
    store.close()


def test_unknown_status_is_refused(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE bookings SET status = 'unknown'")
    con.close()
    store.close()


def test_client_rating_is_bounded_1_to_5(tmp_path):
    store = open_store(tmp_path)
    con = raw(store)
    for bad in (0, 6):
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO clients (phone, name, rating, created_at) VALUES ('+1', 'x', ?, 't')", (bad,))
    con.close()
    store.close()


def test_delete_on_a_cancelled_booking_also_aborts(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    con.execute("UPDATE bookings SET status = 'cancelled'")
    with pytest.raises(sqlite3.DatabaseError, match="never deleted"):
        con.execute("DELETE FROM bookings")
    con.close()
    store.close()


def test_status_may_stay_active_while_nothing_else_changes(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    con.execute("UPDATE bookings SET status = 'active'")
    con.close()
    store.close()


def test_a_booking_cannot_supersede_itself(tmp_path):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE bookings SET superseded_by = id")
    con.close()
    store.close()


@pytest.mark.parametrize("bad_date", ["12/12/2026", "2026-1-5", "tomorrow", ""])
def test_dates_must_be_zero_padded_iso(tmp_path, bad_date):
    store = open_store(tmp_path)
    send(store, 1, NEW)
    con = raw(store)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO bookings (chalet, client_name, client_phone, check_in, check_out, created_at)"
            " VALUES (3, 'X', '+96171123456', ?, '2027-01-01', 't')",
            (bad_date,),
        )
    con.close()
    store.close()


def test_replaying_a_recorded_update_changes_nothing(tmp_path):
    store = open_store(tmp_path)
    assert send(store, 1, NEW) is True
    assert send(store, 1, NEW) is False
    for table in ("bookings", "journal", "outbox", "processed_updates", "clients"):
        assert rows(store, f"SELECT COUNT(*) FROM {table}") == [(1,)]
    store.close()


def test_production_connection_enforces_foreign_keys(tmp_path):
    store = open_store(tmp_path)
    assert asyncio.run(store.run(lambda c: c.execute("PRAGMA foreign_keys").fetchone())) == (1,)
    store.close()


def test_one_night_stay_is_singular_and_a_reply_without_its_booking_fails_loudly():
    from leregister.core.replies import render

    from leregister.core.events import BookingView

    one = BookingView(1, 2, "Sam", "+96171123456", "2026-12-12", "2026-12-13", "active")
    assert render("recorded", {}, None, one).endswith("(1 night)")
    with pytest.raises(ValueError, match="needs its booking"):
        render("recorded", {}, None, None)


def test_upgrade_from_schema_1_keeps_old_rows_and_closes_pending_previews(tmp_path, monkeypatch):
    import shutil

    import leregister.adapters.store.db as db_module

    only_001 = tmp_path / "migrations_v1"
    only_001.mkdir()
    shutil.copy(db_module.MIGRATIONS_DIR / "001_init.sql", only_001)
    real_dir = db_module.MIGRATIONS_DIR
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", only_001)
    old = open_store(tmp_path)
    assert rows(old, "SELECT version FROM schema_version") == [(1,)]
    con = sqlite3.connect(old.path)
    for kind, status in (("new_preview", "pending"), ("rejected", "pending"), ("edit_notice", "done")):
        con.execute(
            "INSERT INTO outbox (destination, chat_id, kind, status, next_attempt_at, created_at)"
            " VALUES ('telegram', 5, ?, ?, '2026-11-06T00:00:00+00:00', '2026-11-06T00:00:00+00:00')",
            (kind, status),
        )
    con.commit()
    con.close()
    old.close()

    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", real_dir)
    store = open_store(tmp_path)
    assert rows(store, "SELECT version FROM schema_version") == [(1,), (2,)]
    assert rows(store, "SELECT kind, status, booking_id FROM outbox ORDER BY id") == [
        ("new_preview", "done", None),
        ("rejected", "pending", None),
        ("edit_notice", "done", None),
    ]
    items = asyncio.run(store.fetch_due("telegram", MovableClock().now()))
    assert [(i.kind, i.booking) for i in items] == [("rejected", None)]
    store.close()
