"""Fail-closed SQLite online backup and restore primitives."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path


class SQLiteBackupError(RuntimeError):
    """Raised when an operational SQLite copy cannot be proven safe."""


@dataclass(frozen=True, slots=True)
class SQLiteDatabaseReport:
    """Integrity and logical evidence for one SQLite database file."""

    database_name: str
    integrity_check: str
    sha256: str
    size_bytes: int
    table_row_counts: dict[str, int]


def inspect_database(database: Path) -> SQLiteDatabaseReport:
    """Return integrity, checksum and row-count evidence for ``database``."""
    path = _validated_source(database)
    try:
        with _read_only_connection(path) as connection:
            integrity, row_counts = _integrity_and_row_counts(connection)
    except (OSError, sqlite3.Error) as exc:
        raise SQLiteBackupError("SQLite integrity verification failed") from exc
    if integrity != "ok":
        raise SQLiteBackupError("SQLite integrity verification failed")
    return SQLiteDatabaseReport(
        database_name=path.name,
        integrity_check=integrity,
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
        table_row_counts=row_counts,
    )


def backup_database(source: Path, destination: Path) -> SQLiteDatabaseReport:
    """Create an atomic online backup without overwriting operator evidence."""
    return _copy_database(source, destination)


def restore_database(backup: Path, destination: Path) -> SQLiteDatabaseReport:
    """Restore a backup into a new independent database and verify it."""
    return _copy_database(backup, destination)


def _copy_database(source: Path, destination: Path) -> SQLiteDatabaseReport:
    source_path = _validated_source(source)
    destination_path = destination.expanduser().resolve(strict=False)
    if source_path == destination_path:
        raise SQLiteBackupError("source and destination must be different")
    if destination_path.exists():
        raise SQLiteBackupError("destination already exists")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".partial",
        dir=destination_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with (
            _read_only_connection(source_path) as source_connection,
            sqlite3.connect(temporary_path) as destination_connection,
        ):
            source_integrity, _ = _integrity_and_row_counts(source_connection)
            if source_integrity != "ok":
                raise SQLiteBackupError("SQLite integrity verification failed")
            source_connection.backup(destination_connection)
            destination_connection.commit()
            backup_integrity, backup_row_counts = _integrity_and_row_counts(
                destination_connection
            )
            if backup_integrity != "ok":
                raise SQLiteBackupError("SQLite integrity verification failed")
        try:
            # A same-directory hard link publishes the verified inode atomically and,
            # unlike replace/rename, cannot overwrite evidence created by a race.
            destination_path.hardlink_to(temporary_path)
        except FileExistsError as exc:
            raise SQLiteBackupError("destination already exists") from exc
        _remove_database_artifacts(temporary_path)
    except SQLiteBackupError:
        _remove_database_artifacts(temporary_path)
        raise
    except (OSError, sqlite3.Error) as exc:
        _remove_database_artifacts(temporary_path)
        raise SQLiteBackupError("SQLite integrity verification failed") from exc

    return SQLiteDatabaseReport(
        database_name=destination_path.name,
        integrity_check=backup_integrity,
        sha256=_sha256(destination_path),
        size_bytes=destination_path.stat().st_size,
        table_row_counts=backup_row_counts,
    )


def _validated_source(database: Path) -> Path:
    path = database.expanduser().resolve(strict=False)
    if not path.is_file():
        raise SQLiteBackupError("source database does not exist")
    return path


def _remove_database_artifacts(database: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        database.with_name(f"{database.name}{suffix}").unlink(missing_ok=True)


def _read_only_connection(database: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)


def _integrity_and_row_counts(
    connection: sqlite3.Connection,
) -> tuple[str, dict[str, int]]:
    integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
    integrity = "\n".join(str(row[0]) for row in integrity_rows)
    table_names = [
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]
    row_counts: dict[str, int] = {}
    for table_name in table_names:
        quoted_name = table_name.replace('"', '""')
        # Table names originate in sqlite_schema and are identifier-escaped above.
        row = connection.execute(
            f'SELECT COUNT(*) FROM "{quoted_name}"'  # noqa: S608
        ).fetchone()
        row_counts[table_name] = int(row[0]) if row is not None else 0
    return integrity, row_counts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


__all__ = [
    "SQLiteBackupError",
    "SQLiteDatabaseReport",
    "backup_database",
    "inspect_database",
    "restore_database",
]
