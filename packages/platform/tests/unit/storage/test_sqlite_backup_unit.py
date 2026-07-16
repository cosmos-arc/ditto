"""SQLite 在线备份与恢复工具的单元测试。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from ditto_platform.foundation.storage.sqlite_backup import (
    SQLiteBackupError,
    backup_database,
    inspect_database,
    restore_database,
)


def _seed_wal_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE fills (fill_id TEXT PRIMARY KEY, quantity INTEGER)"
    )
    connection.executemany(
        "INSERT INTO fills VALUES (?, ?)",
        (("fill-1", 100), ("fill-2", 200)),
    )
    connection.commit()
    return connection


def test_backup_database_captures_committed_wal_and_returns_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "metadata.sqlite"
    destination = tmp_path / "r1-backup.sqlite"
    writer = _seed_wal_database(source)

    try:
        report = backup_database(source, destination)
    finally:
        writer.close()

    assert destination.is_file()
    assert report.integrity_check == "ok"
    assert report.sha256.startswith("sha256:")
    assert len(report.sha256) == len("sha256:") + 64
    assert report.table_row_counts == {"fills": 2}
    assert report.size_bytes == destination.stat().st_size
    with sqlite3.connect(destination) as restored:
        assert restored.execute(
            "SELECT fill_id, quantity FROM fills ORDER BY fill_id"
        ).fetchall() == [("fill-1", 100), ("fill-2", 200)]


def test_restore_database_creates_independent_verified_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    backup = tmp_path / "backup.sqlite"
    restored = tmp_path / "restored" / "metadata.sqlite"
    writer = _seed_wal_database(source)
    writer.close()
    backup_report = backup_database(source, backup)

    restore_report = restore_database(backup, restored)

    assert restored.is_file()
    assert restore_report.integrity_check == "ok"
    assert restore_report.table_row_counts == backup_report.table_row_counts
    assert inspect_database(restored).table_row_counts == {"fills": 2}


@pytest.mark.parametrize("operation", [backup_database, restore_database])
def test_copy_operations_refuse_to_overwrite_destination(
    tmp_path: Path,
    operation: Callable[[Path, Path], object],
) -> None:
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "existing.sqlite"
    writer = _seed_wal_database(source)
    writer.close()
    destination.write_bytes(b"operator evidence")

    with pytest.raises(SQLiteBackupError, match="destination already exists"):
        operation(source, destination)

    assert destination.read_bytes() == b"operator evidence"


def test_backup_database_rejects_missing_or_same_source(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(SQLiteBackupError, match="source database does not exist"):
        backup_database(missing, tmp_path / "backup.sqlite")

    source = tmp_path / "source.sqlite"
    writer = _seed_wal_database(source)
    writer.close()
    with pytest.raises(SQLiteBackupError, match="must be different"):
        backup_database(source, source)


def test_backup_database_leaves_no_destination_for_corrupt_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "corrupt.sqlite"
    destination = tmp_path / "backup.sqlite"
    source.write_bytes(b"not a sqlite database")

    with pytest.raises(SQLiteBackupError, match="SQLite integrity verification failed"):
        backup_database(source, destination)

    assert not destination.exists()
    assert list(tmp_path.glob("*.partial")) == []
