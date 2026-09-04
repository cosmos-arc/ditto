"""Integrity-failure and atomic-publication edges for SQLite backups."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import ditto_platform.foundation.storage.sqlite_backup as sqlite_backup_module
import pytest
from ditto_platform.foundation.storage.sqlite_backup import (
    SQLiteBackupError,
    backup_database,
    inspect_database,
)


def _seed_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO events VALUES (1)")


def test_inspection_wraps_sqlite_errors_for_a_corrupt_file(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not a sqlite database")

    with pytest.raises(SQLiteBackupError, match="integrity verification failed"):
        inspect_database(corrupt)


def test_inspection_rejects_a_non_ok_integrity_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    _seed_database(source)
    monkeypatch.setattr(
        sqlite_backup_module,
        "_integrity_and_row_counts",
        lambda _connection: ("database disk image is malformed", {}),
    )

    with pytest.raises(SQLiteBackupError, match="integrity verification failed"):
        inspect_database(source)


def test_backup_rejects_non_ok_source_integrity_and_cleans_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "backup.sqlite"
    _seed_database(source)
    monkeypatch.setattr(
        sqlite_backup_module,
        "_integrity_and_row_counts",
        lambda _connection: ("source corruption", {}),
    )

    with pytest.raises(SQLiteBackupError, match="integrity verification failed"):
        backup_database(source, destination)

    assert not destination.exists()
    assert list(tmp_path.glob("*.partial")) == []


def test_backup_rejects_non_ok_destination_integrity_and_cleans_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "backup.sqlite"
    _seed_database(source)
    results = iter([("ok", {"events": 1}), ("backup corruption", {})])
    monkeypatch.setattr(
        sqlite_backup_module,
        "_integrity_and_row_counts",
        lambda _connection: next(results),
    )

    with pytest.raises(SQLiteBackupError, match="integrity verification failed"):
        backup_database(source, destination)

    assert not destination.exists()
    assert list(tmp_path.glob("*.partial")) == []


def test_backup_handles_destination_created_during_atomic_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "backup.sqlite"
    _seed_database(source)

    def collide_during_publish(_path: Path, _target: Path) -> None:
        raise FileExistsError("simulated concurrent publisher")

    monkeypatch.setattr(Path, "hardlink_to", collide_during_publish)

    with pytest.raises(SQLiteBackupError, match="destination already exists"):
        backup_database(source, destination)

    assert not destination.exists()
    assert list(tmp_path.glob("*.partial")) == []
