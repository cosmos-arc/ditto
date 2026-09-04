"""OPS-03 isolated workstation backup and restore integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_apps.operations.workstation_backup import (
    WORKSTATION_DATABASES,
    WorkstationBackupError,
    backup_workstation,
    restore_workstation,
    verify_workstation_backup,
)
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_platform.foundation.storage.sqlite_backup import inspect_database

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def test_backup_and_restore_all_four_domains_into_an_isolated_root(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    create_fresh_runtime(source)

    manifest = backup_workstation(source, backup)
    verified = verify_workstation_backup(backup)
    restored_manifest = restore_workstation(backup, restored)

    assert manifest == verified == restored_manifest
    assert {item.domain for item in manifest.databases} == {
        "data",
        "research",
        "trading",
        "agent",
    }
    assert tuple(item.relative_path for item in manifest.databases) == tuple(
        spec.relative_path for spec in WORKSTATION_DATABASES
    )
    assert (backup / "manifest.json").is_file()
    for item in manifest.databases:
        restored_report = inspect_database(restored / item.relative_path)
        assert restored_report.integrity_check == "ok"
        assert restored_report.table_row_counts == item.table_row_counts


def test_restore_rejects_a_tampered_database_and_leaves_no_partial_root(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    create_fresh_runtime(source)
    backup_workstation(source, backup)
    target = backup / WORKSTATION_DATABASES[0].relative_path
    target.write_bytes(target.read_bytes() + b"tampered")

    with pytest.raises(WorkstationBackupError, match="verification failed"):
        restore_workstation(backup, restored)

    assert not restored.exists()


def test_backup_and_restore_refuse_overlapping_or_existing_targets(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    create_fresh_runtime(source)

    with pytest.raises(WorkstationBackupError, match="must not overlap"):
        backup_workstation(source, source / "backup")

    backup = tmp_path / "backup"
    backup_workstation(source, backup)
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(WorkstationBackupError, match="already exists"):
        restore_workstation(backup, destination)
