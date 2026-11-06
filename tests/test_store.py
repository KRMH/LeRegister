import asyncio
import sqlite3
import threading
from pathlib import Path

import pytest
from helpers import MovableClock, open_store

from leregister.adapters.store import SqliteStore, StoreError
from leregister.core.events import Decision, EventType, JournalEntry, ReplyRequest

CLOCK = MovableClock()


def rejected(update_id=1, payload=None):
    entry = JournalEntry(CLOCK.now(), EventType.COMMAND_REJECTED, "command", str(update_id), payload or {"reason": "x"})
    return Decision(entry, ReplyRequest("rejected"))


def query(store, sql):
    con = sqlite3.connect(store.path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_fresh_db_has_only_this_story_tables_and_wal(tmp_path):
    store = open_store(tmp_path)
    tables = {r[0] for r in query(store, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables - {"sqlite_sequence"} == {
        "journal", "outbox", "processed_updates", "schema_version", "clients", "bookings", "drafts"
    }
    assert query(store, "PRAGMA journal_mode") == [("wal",)]
    assert query(store, "SELECT version FROM schema_version") == [(1,), (2,), (3,)]
    store.close()


def test_migrations_apply_once_on_reopen(tmp_path):
    open_store(tmp_path).close()
    store = open_store(tmp_path)
    assert query(store, "SELECT version FROM schema_version") == [(1,), (2,), (3,)]
    store.close()


def test_journal_update_trigger_aborts(tmp_path):
    store = open_store(tmp_path)
    asyncio.run(store.record_command(1, 5, rejected(), CLOCK.now()))
    con = sqlite3.connect(store.path)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE journal SET payload = '{}'")
    con.close()
    store.close()


def test_journal_delete_trigger_aborts(tmp_path):
    store = open_store(tmp_path)
    asyncio.run(store.record_command(1, 5, rejected(), CLOCK.now()))
    con = sqlite3.connect(store.path)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM journal")
    con.close()
    assert query(store, "SELECT COUNT(*) FROM journal") == [(1,)]
    store.close()


def test_journal_rejects_event_type_outside_the_closed_list(tmp_path):
    store = open_store(tmp_path)
    con = sqlite3.connect(store.path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO journal (at, event_type, subject_type, subject_id, payload) VALUES ('t','nope','x','1','{}')"
        )
    con.close()
    store.close()


def test_sql_event_list_matches_core_event_list(tmp_path):
    store = open_store(tmp_path)
    (sql,) = query(store, "SELECT sql FROM sqlite_master WHERE name='journal'")[0]
    quoted = {part for part in sql.split("'")[1::2]}
    assert {event.value for event in EventType} == quoted
    store.close()


def test_record_command_writes_three_rows_in_utc(tmp_path):
    store = open_store(tmp_path)
    assert asyncio.run(store.record_command(1, 5, rejected(), CLOCK.now())) is True
    (at,) = query(store, "SELECT at FROM journal")[0]
    assert at.startswith("2026-11-06T12:00:00") and at.endswith("+00:00")
    assert query(store, "SELECT chat_id, kind, journal_id, status FROM outbox") == [(5, "rejected", 1, "pending")]
    assert query(store, "SELECT update_id FROM processed_updates") == [(1,)]
    store.close()


def test_duplicate_update_id_writes_nothing(tmp_path):
    store = open_store(tmp_path)
    asyncio.run(store.record_command(1, 5, rejected(), CLOCK.now()))
    assert asyncio.run(store.record_command(1, 5, rejected(), CLOCK.now())) is False
    for table in ("journal", "outbox", "processed_updates"):
        assert query(store, f"SELECT COUNT(*) FROM {table}") == [(1,)]
    store.close()


def test_failure_mid_transaction_rolls_everything_back(tmp_path):
    store = open_store(tmp_path)
    bad = rejected(payload={"reason": object()})  # not JSON serialisable: fails after the processed_updates insert
    with pytest.raises(TypeError):
        asyncio.run(store.record_command(1, 5, bad, CLOCK.now()))
    for table in ("journal", "outbox", "processed_updates"):
        assert query(store, f"SELECT COUNT(*) FROM {table}") == [(0,)]
    assert asyncio.run(store.record_command(1, 5, rejected(), CLOCK.now())) is True  # update id not burned
    store.close()


def test_all_access_runs_on_one_worker_thread(tmp_path):
    store = open_store(tmp_path)

    async def go():
        return await asyncio.gather(*(store.run(lambda c: threading.get_ident()) for _ in range(20)))

    idents = set(asyncio.run(go()))
    assert len(idents) == 1 and threading.get_ident() not in idents
    store.close()


def test_unopenable_database_raises_store_error(tmp_path):
    with pytest.raises(StoreError, match="Cannot open the database"):
        SqliteStore(tmp_path).open()  # a directory, not a file


def test_store_source_never_uses_insert_or_replace():
    import leregister.adapters.store as pkg

    for path in Path(pkg.__file__).parent.rglob("*"):
        if path.suffix in {".py", ".sql"}:
            assert "or replace" not in path.read_text(encoding="utf-8").lower()


def test_failed_migration_rolls_back_and_raises_store_error(tmp_path, monkeypatch):
    import leregister.adapters.store.db as db_module

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_ok.sql").write_text("CREATE TABLE a (x INTEGER)", encoding="utf-8")  # no trailing semicolon
    (migrations / "002_bad.sql").write_text("CREATE TABLE b (x INTEGER); CREATE TABLE b (y INTEGER);", encoding="utf-8")
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", migrations)
    store = SqliteStore(tmp_path / "m.db")
    with pytest.raises(StoreError):
        store.open()
    con = sqlite3.connect(tmp_path / "m.db")
    assert con.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    assert con.execute("SELECT name FROM sqlite_master WHERE name = 'b'").fetchall() == []  # rolled back
    con.close()


def test_migrations_apply_in_numeric_order_and_duplicates_are_refused(tmp_path, monkeypatch):
    import leregister.adapters.store.db as db_module

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "10_late.sql").write_text("INSERT INTO t VALUES (10);", encoding="utf-8")
    (migrations / "2_early.sql").write_text("CREATE TABLE t (x INTEGER); INSERT INTO t VALUES (2);", encoding="utf-8")
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", migrations)
    store = SqliteStore(tmp_path / "o.db")
    store.open()
    assert query(store, "SELECT x FROM t ORDER BY rowid") == [(2,), (10,)]
    store.close()

    (migrations / "002_dup.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(StoreError, match="share the number"):
        SqliteStore(tmp_path / "d.db").open()
