"""Store adapter: records one Command in one transaction, and serves the outbox."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import datetime

from leregister.adapters.store.db import Database, StoreError, iso_utc
from leregister.core.events import BookingView, Decision, OutboxItem, ReplyRequest

__all__ = ["SqliteStore", "StoreError"]


class SqliteStore(Database):
    async def record_command(self, update_id: int, chat_id: int, decision: Decision, at: datetime) -> bool:
        def work(conn: sqlite3.Connection) -> bool:
            conn.execute("BEGIN IMMEDIATE")
            try:
                try:
                    conn.execute(
                        "INSERT INTO processed_updates (update_id, processed_at) VALUES (?, ?)",
                        (update_id, iso_utc(at)),
                    )
                except sqlite3.IntegrityError:
                    conn.execute("ROLLBACK")
                    return False
                entry = decision.journal
                reply_kind = decision.reply.kind
                booking_id: int | None = None
                if decision.booking is not None:
                    booking_id, is_new = _record_booking(conn, decision, at)
                    if is_new:
                        if entry is not None:
                            entry = dataclasses.replace(
                                entry, subject_id=str(booking_id), related_booking_id=booking_id
                            )
                    else:  # the identical active booking already exists: nothing new, nothing journaled
                        entry = None
                        reply_kind = "already_recorded"
                journal_id = None
                if entry is not None:
                    cursor = conn.execute(
                        "INSERT INTO journal (at, event_type, subject_type, subject_id, related_booking_id, payload)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            iso_utc(entry.at),
                            entry.event_type.value,
                            entry.subject_type,
                            entry.subject_id,
                            entry.related_booking_id,
                            json.dumps(entry.payload, sort_keys=True),
                        ),
                    )
                    journal_id = cursor.lastrowid
                conn.execute(
                    "INSERT INTO outbox (destination, chat_id, kind, args, journal_id, booking_id,"
                    " next_attempt_at, created_at) VALUES ('telegram', ?, ?, ?, ?, ?, ?, ?)",
                    (
                        chat_id,
                        reply_kind,
                        json.dumps(decision.reply.args, sort_keys=True),
                        journal_id,
                        booking_id,
                        iso_utc(at),
                        iso_utc(at),
                    ),
                )
                conn.execute("COMMIT")
                return True
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

        return await self.run(work)

    async def queue_reply(self, chat_id: int, reply: ReplyRequest, at: datetime) -> None:
        def work(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO outbox (destination, chat_id, kind, args, next_attempt_at, created_at)"
                " VALUES ('telegram', ?, ?, ?, ?, ?)",
                (chat_id, reply.kind, json.dumps(reply.args, sort_keys=True), iso_utc(at), iso_utc(at)),
            )

        await self.run(work)

    async def fetch_due(self, destination: str, now: datetime, limit: int = 50) -> list[OutboxItem]:
        def work(conn: sqlite3.Connection) -> list[OutboxItem]:
            rows = conn.execute(
                "SELECT o.id, o.chat_id, o.kind, o.args, o.attempts, j.payload,"
                " b.id, b.chalet, b.client_name, b.client_phone, b.check_in, b.check_out, b.status"
                " FROM outbox o"
                " LEFT JOIN journal j ON j.id = o.journal_id"
                " LEFT JOIN bookings b ON b.id = o.booking_id"
                " WHERE o.destination = ? AND o.status = 'pending' AND o.next_attempt_at <= ?"
                " ORDER BY o.id LIMIT ?",
                (destination, iso_utc(now), limit),
            ).fetchall()
            return [
                OutboxItem(
                    id=row[0],
                    chat_id=row[1],
                    kind=row[2],
                    args=json.loads(row[3]),
                    attempts=row[4],
                    journal_payload=json.loads(row[5]) if row[5] is not None else None,
                    booking=BookingView(*row[6:13]) if row[6] is not None else None,
                )
                for row in rows
            ]

        return await self.run(work)

    async def mark_done(self, row_id: int, now: datetime) -> None:
        def work(conn: sqlite3.Connection) -> None:
            conn.execute("UPDATE outbox SET status = 'done', done_at = ? WHERE id = ?", (iso_utc(now), row_id))

        await self.run(work)

    async def mark_failed(self, row_id: int, retry_at: datetime) -> None:
        def work(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE outbox SET attempts = attempts + 1, next_attempt_at = ? WHERE id = ?",
                (iso_utc(retry_at), row_id),
            )

        await self.run(work)


def _record_booking(conn: sqlite3.Connection, decision: Decision, at: datetime) -> tuple[int, bool]:
    """Create the Client (if new) and the booking. Returns (booking id, True if newly created).

    An identical active booking (same chalet, phone and dates) is returned as (its id, False).
    """
    b = decision.booking
    assert b is not None
    existing = conn.execute(
        "SELECT id FROM bookings WHERE status = 'active' AND chalet = ? AND client_phone = ?"
        " AND check_in = ? AND check_out = ?",
        (b.chalet, b.phone, b.check_in, b.check_out),
    ).fetchone()
    if existing is not None:
        return existing[0], False
    if conn.execute("SELECT 1 FROM clients WHERE phone = ?", (b.phone,)).fetchone() is None:
        conn.execute(
            "INSERT INTO clients (phone, name, created_at) VALUES (?, ?, ?)", (b.phone, b.name, iso_utc(at))
        )
    cursor = conn.execute(
        "INSERT INTO bookings (chalet, client_name, client_phone, check_in, check_out, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (b.chalet, b.name, b.phone, b.check_in, b.check_out, iso_utc(at)),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid, True
