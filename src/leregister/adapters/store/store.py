"""Store adapter: records one Command in one transaction, and serves the outbox."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from leregister.adapters.store.db import Database, StoreError, iso_utc
from leregister.core.events import Decision, OutboxItem

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
                journal_id = None
                entry = decision.journal
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
                    "INSERT INTO outbox (destination, chat_id, kind, args, journal_id, next_attempt_at, created_at)"
                    " VALUES ('telegram', ?, ?, ?, ?, ?, ?)",
                    (
                        chat_id,
                        decision.reply.kind,
                        json.dumps(decision.reply.args, sort_keys=True),
                        journal_id,
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

    async def fetch_due(self, destination: str, now: datetime, limit: int = 50) -> list[OutboxItem]:
        def work(conn: sqlite3.Connection) -> list[OutboxItem]:
            rows = conn.execute(
                "SELECT o.id, o.chat_id, o.kind, o.args, o.attempts, j.payload"
                " FROM outbox o LEFT JOIN journal j ON j.id = o.journal_id"
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
