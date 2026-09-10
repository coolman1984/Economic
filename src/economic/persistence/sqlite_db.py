"""SQLite connection, migration runner, and schema versioning.

Only this package opens the database. CLI and application code use repositories.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_FILE_RE = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")


class DatabaseError(RuntimeError):
    """Raised for database setup, migration, or integrity problems."""


def utc_now() -> str:
    """Current UTC timestamp in ISO-8601 with a trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a configured SQLite connection (foreign keys on, row access by name)."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def available_migrations() -> List[tuple]:
    """Discovered migrations as ``(version, name, path)`` sorted by version."""
    migrations = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = MIGRATION_FILE_RE.match(path.name)
        if not match:
            raise DatabaseError(f"migration file has an unexpected name: {path.name}")
        migrations.append((int(match.group(1)), match.group(2), path))
    return migrations


def split_statements(sql: str) -> List[str]:
    """Split a migration file into complete SQL statements.

    ``executescript`` would commit the surrounding transaction, so migrations are
    applied statement by statement inside one explicit transaction instead.
    """
    statements = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        if line.strip().startswith("--") and not buffer.strip():
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement.rstrip(";").strip():
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        raise DatabaseError("migration ends with an incomplete SQL statement")
    return statements


def applied_versions(connection: sqlite3.Connection) -> List[int]:
    _ensure_migration_table(connection)
    rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [row["version"] for row in rows]


def schema_version(connection: sqlite3.Connection) -> int:
    versions = applied_versions(connection)
    return versions[-1] if versions else 0


def migrate(connection: sqlite3.Connection) -> List[int]:
    """Apply every pending migration in order. Returns the versions applied."""
    _ensure_migration_table(connection)
    already = set(applied_versions(connection))
    applied = []
    for version, name, path in available_migrations():
        if version in already:
            continue
        statements = split_statements(path.read_text(encoding="utf-8"))
        try:
            connection.execute("BEGIN")
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, utc_now()),
            )
            connection.execute("COMMIT")
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            connection.execute("ROLLBACK")
            raise DatabaseError(f"migration {version}_{name} failed: {exc}") from exc
        applied.append(version)
    return applied


def initialize(db_path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a database and bring it to the latest schema."""
    connection = connect(db_path)
    migrate(connection)
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Atomic unit of work. Rolls back on any exception."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except Exception:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def backup(connection: sqlite3.Connection, destination: Path) -> Path:
    """Create a consistent file backup before a destructive operation."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(str(destination))
    try:
        connection.backup(target)
    finally:
        target.close()
    return destination


def integrity_check(connection: sqlite3.Connection) -> Optional[str]:
    """Return None when the database is healthy, otherwise the failure text."""
    row = connection.execute("PRAGMA integrity_check").fetchone()
    result = row[0] if row else "unknown"
    return None if result == "ok" else result
