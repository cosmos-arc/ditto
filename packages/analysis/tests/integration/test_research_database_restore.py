"""Backup and independent restore proof for the migrated Research database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from ditto_analysis.errors import ExperimentSchemaError
from ditto_analysis.storage.sqlite.experiments import ResearchExperimentDatabase, schema
from ditto_platform.foundation.storage.sqlite_backup import restore_database


def _snapshot(path: Path) -> tuple[int, int, tuple[tuple[object, ...], ...]]:
    with sqlite3.connect(path) as connection:
        return (
            int(connection.execute("PRAGMA application_id").fetchone()[0]),
            int(connection.execute("PRAGMA user_version").fetchone()[0]),
            tuple(
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT type, name, tbl_name, sql FROM sqlite_schema
                    WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name
                    """
                )
            ),
        )


def test_backup_restore_reopen_preserves_v2_schema_and_rows(tmp_path: Path) -> None:
    database = ResearchExperimentDatabase(tmp_path / "live")
    database.initialize()
    manifest_payload = json.dumps(
        {
            "campaign_id": "campaign-restore",
            "lineage_root": "b" * 64,
            "schema_id": "r5-research-campaign-manifest",
            "schema_version": 1,
            "search_axis": "factor_code",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    manifest_hash = hashlib.sha256(manifest_payload.encode()).hexdigest()
    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO research_campaign(
                campaign_id, manifest_hash, manifest_schema_version, manifest_json,
                search_axis, lineage_root, created_at_epoch_us
            ) VALUES (?, ?, 1, ?, 'factor_code', ?, ?)
            """,
            ("campaign-restore", manifest_hash, manifest_payload, "b" * 64, 1),
        )
        connection.commit()

    backup = tmp_path / "evidence" / "research-v2.backup.sqlite"
    database.backup_to(backup)
    restored = tmp_path / "restored" / "research" / "research.sqlite"
    report = restore_database(backup, restored)

    assert report.integrity_check == "ok"
    assert report.table_row_counts["research_campaign"] == 1
    assert _snapshot(restored) == _snapshot(database.path)

    reopened = ResearchExperimentDatabase(tmp_path / "restored")
    reopened.initialize()
    with reopened.connection() as connection:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == (
            schema.APPLICATION_ID
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT manifest_hash FROM research_campaign WHERE campaign_id=?",
                ("campaign-restore",),
            ).fetchone()[0]
            == manifest_hash
        )


def test_backup_is_non_overwriting_and_rejects_invalid_destination(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path / "live")
    database.initialize()
    backup = tmp_path / "backup.sqlite"
    database.backup_to(backup)

    with pytest.raises(FileExistsError):
        database.backup_to(backup)
    with pytest.raises(ValueError):
        database.backup_to(database.path)


def test_backup_fails_closed_on_broken_foreign_key_without_creating_copy(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path / "live")
    database.initialize()
    with database.connection() as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            """
            INSERT INTO research_campaign_event(
                event_id, campaign_id, ordinal, event_type, previous_status,
                status, detail_json, occurred_at_epoch_us
            ) VALUES ('orphan-event', 'missing-campaign', 0, 'created', NULL,
                      'draft', '{}', 1)
            """
        )
        connection.commit()
        connection.execute("PRAGMA foreign_keys=ON")

    backup = tmp_path / "evidence" / "invalid.backup.sqlite"
    with pytest.raises(ExperimentSchemaError) as exc_info:
        database.backup_to(backup)

    assert exc_info.value.details["reason_code"] == (
        "research_database_foreign_key_violation"
    )
    assert not backup.exists()
