"""Integration proof for combined R2 SQLite and payload backup/restore."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ditto_apps.scripts.r2_data_acceptance import (
    R2BackupError,
    create_r2_backup,
    restore_r2_backup,
)
from ditto_platform.foundation.storage.payload_backup import inspect_payload_tree
from ditto_platform.foundation.storage.sqlite_backup import inspect_database


def _fixture_runtime(tmp_path: Path) -> tuple[Path, Path]:
    database = tmp_path / "runtime" / "metadata.sqlite"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE certification_reports "
            "(report_id TEXT PRIMARY KEY, value TEXT)"
        )
        connection.executemany(
            "INSERT INTO certification_reports VALUES (?, ?)",
            [("report-1", "alpha"), ("report-2", "beta")],
        )
        connection.commit()
    payload = tmp_path / "runtime" / "payload"
    (payload / "stock_daily" / "2026" / "07").mkdir(parents=True)
    (payload / "stock_daily" / "2026" / "07" / "17.parquet").write_bytes(
        b"PAR1-stock-daily-fixture"
    )
    (payload / "index_weight").mkdir()
    (payload / "index_weight" / "intervals.parquet").write_bytes(
        b"PAR1-index-weight-fixture"
    )
    return database, payload


@pytest.mark.integration
def test_sqlite_and_payload_backup_restore_are_verified_together(
    tmp_path: Path,
) -> None:
    database, payload = _fixture_runtime(tmp_path)
    backup_root = tmp_path / "backup" / "r2-acceptance"

    backup = create_r2_backup(
        sqlite_source=database,
        payload_source=payload,
        backup_root=backup_root,
    )

    assert backup.manifest_path.is_file()
    assert backup.sqlite.table_row_counts == {"certification_reports": 2}
    assert backup.payload.file_count == 2
    database.unlink()
    (payload / "stock_daily" / "2026" / "07" / "17.parquet").write_bytes(
        b"mutated-after-backup"
    )

    restored_database = tmp_path / "restore" / "metadata.sqlite"
    restored_payload = tmp_path / "restore" / "payload"
    restored = restore_r2_backup(
        backup_root=backup_root,
        sqlite_destination=restored_database,
        payload_destination=restored_payload,
    )

    assert restored.sqlite.table_row_counts == {"certification_reports": 2}
    assert inspect_database(restored_database).table_row_counts == {
        "certification_reports": 2
    }
    assert restored.payload.root_sha256 == backup.payload.root_sha256
    assert (
        inspect_payload_tree(restored_payload).root_sha256 == backup.payload.root_sha256
    )
    assert (
        restored_payload / "stock_daily" / "2026" / "07" / "17.parquet"
    ).read_bytes() == b"PAR1-stock-daily-fixture"


@pytest.mark.integration
def test_backup_and_restore_refuse_existing_destinations(tmp_path: Path) -> None:
    database, payload = _fixture_runtime(tmp_path)
    existing_backup = tmp_path / "existing-backup"
    existing_backup.mkdir()

    with pytest.raises(R2BackupError, match="backup root already exists"):
        create_r2_backup(
            sqlite_source=database,
            payload_source=payload,
            backup_root=existing_backup,
        )

    backup_root = tmp_path / "backup"
    create_r2_backup(
        sqlite_source=database,
        payload_source=payload,
        backup_root=backup_root,
    )
    sqlite_destination = tmp_path / "restore.sqlite"
    sqlite_destination.write_bytes(b"do-not-overwrite")
    with pytest.raises(R2BackupError, match="restore destination already exists"):
        restore_r2_backup(
            backup_root=backup_root,
            sqlite_destination=sqlite_destination,
            payload_destination=tmp_path / "restored-payload",
        )
    assert sqlite_destination.read_bytes() == b"do-not-overwrite"
