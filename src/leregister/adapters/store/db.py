"""SQLite connection, numbered migrations and the single serialized writer (AR2, AR4)."""

from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class StoreError(Exception):
    """The database cannot be opened or migrated."""


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


class Database:
    """One connection, used only on one worker thread: every access is serialized."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="store")

    def open(self) -> None:
        """Connect in WAL mode and apply pending migrations. Call once, before serving."""
        conn: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            _migrate(conn)
        except (sqlite3.Error, OSError) as exc:
            if conn is not None:
                conn.close()  # do not leave the file locked after a failed start
            raise StoreError(f"Cannot open the database at {self.path}: {exc}") from None
        self._conn = conn

    async def run(self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run `work(connection)` on the single writer thread."""
        if self._conn is None:
            raise StoreError("database is not open")
        conn = self._conn
        return await asyncio.get_running_loop().run_in_executor(self._executor, work, conn)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def _migrate(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
    for version, path in _migration_files():
        if version in applied:
            continue
        stamp = iso_utc(datetime.now(timezone.utc))
        script = (
            "BEGIN;\n"
            f"{path.read_text(encoding='utf-8').rstrip()}\n;\n"
            f"INSERT INTO schema_version (version, applied_at) VALUES ({version}, '{stamp}');\n"
            "COMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise


def _migration_files() -> list[tuple[int, Path]]:
    """Migration files ordered by their number (so 10 comes after 2). Numbers must be unique."""
    found: dict[int, Path] = {}
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = re.match(r"(\d+)_", path.name)
        if not match:
            raise sqlite3.Error(f"migration file name must start with a number: {path.name}")
        version = int(match.group(1))
        if version in found:
            raise sqlite3.Error(f"two migrations share the number {version}")
        found[version] = path
    return sorted(found.items())
