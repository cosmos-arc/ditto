"""Research SQLite v1-to-v2 migration and governed-campaign storage tests."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import sqlite3
from pathlib import Path

import pytest
from ditto_analysis.errors import ExperimentConflictError, ExperimentSchemaError
from ditto_analysis.experiments.campaign import SearchAxis
from ditto_analysis.storage.sqlite.experiments import ResearchExperimentDatabase, schema


def _manifest_payload(
    campaign_id: str,
    lineage_root: str,
    *,
    changed: bool = False,
) -> bytes:
    payload: dict[str, object] = {
        "campaign_id": campaign_id,
        "lineage_root": lineage_root,
        "schema_id": "r5-research-campaign-manifest",
        "schema_version": 1,
        "search_axis": SearchAxis.FACTOR_CODE.value,
    }
    if changed:
        payload["objective"] = "changed"
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _create_v1_database(root: Path) -> Path:
    path = root / "research" / "research.sqlite"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        for statement in schema.schema_body_statements(schema.load_v1_schema_sql()):
            connection.execute(statement)
        connection.execute(f"PRAGMA application_id={schema.APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={schema.V1_USER_VERSION}")
        connection.commit()
    return path


def _v1_rows(path: Path) -> dict[str, tuple[tuple[object, ...], ...]]:
    with sqlite3.connect(path) as connection:
        names = tuple(
            str(row[0])
            for row in connection.execute(
                """
                SELECT name FROM sqlite_schema
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        )
        return {
            name: tuple(
                tuple(row) for row in connection.execute(f'SELECT * FROM "{name}"')
            )
            for name in names
        }


def test_migration_resource_hash_and_final_marker_match_approved_constants() -> None:
    payload = (
        importlib.resources.files("ditto_analysis.storage.sqlite.experiments")
        .joinpath("migration_v1_to_v2.sql")
        .read_bytes()
    )

    assert hashlib.sha256(payload).hexdigest() == schema.MIGRATION_DDL_SHA256
    statements = schema.iter_schema_statements(payload.decode())
    assert statements[-1] == f"PRAGMA user_version = {schema.USER_VERSION};"
    migration_statements = schema.migration_body_statements(payload.decode())
    assert len(migration_statements) == len(statements) - 1


def test_v1_fixture_migrates_in_place_without_changing_r3_rows(tmp_path: Path) -> None:
    path = _create_v1_database(tmp_path)
    before = _v1_rows(path)

    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()

    with database.connection() as connection:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == (
            schema.APPLICATION_ID
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert names >= schema.V2_TABLE_NAMES
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    after = _v1_rows(path)
    assert {name: after[name] for name in before} == before


def test_failed_v1_migration_rolls_back_every_new_object_and_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _create_v1_database(tmp_path)
    before = _v1_rows(path)
    original = schema.migration_body_statements

    def broken(sql: str) -> tuple[str, ...]:
        statements = original(sql)
        return (*statements[:2], "CREATE TABLE broken(", *statements[2:])

    monkeypatch.setattr(schema, "migration_body_statements", broken)

    with pytest.raises(ExperimentSchemaError) as exc_info:
        ResearchExperimentDatabase(tmp_path).initialize()

    assert exc_info.value.details["reason_code"] == "research_schema_migration_failed"
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not any(
            row[0] in schema.V2_TABLE_NAMES
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        )
    assert _v1_rows(path) == before


def test_unknown_future_version_fails_closed_without_mutation(tmp_path: Path) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    with database.connection() as connection:
        connection.execute("PRAGMA user_version=99")
        connection.commit()
    before = _v1_rows(database.path)

    with pytest.raises(ExperimentSchemaError) as exc_info:
        ResearchExperimentDatabase(tmp_path).initialize()

    assert exc_info.value.details["reason_code"] == "research_schema_future_version"
    assert _v1_rows(database.path) == before


def test_campaign_tables_reject_update_delete_and_conflicting_replay(
    tmp_path: Path,
) -> None:
    from ditto_analysis.experiments.campaign_persistence import CampaignManifestRecord
    from ditto_analysis.experiments.models import ContentHash, ExperimentId
    from ditto_analysis.storage.sqlite.experiments.campaign_writer import (
        SQLiteCampaignWriter,
    )

    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    writer = SQLiteCampaignWriter(database)
    payload = _manifest_payload("campaign-1", "b" * 64)
    record = CampaignManifestRecord(
        campaign_id=ExperimentId("campaign-1"),
        manifest_hash=ContentHash(hashlib.sha256(payload).hexdigest()),
        manifest_payload=payload,
        search_axis=SearchAxis.FACTOR_CODE,
        lineage_root=ContentHash("b" * 64),
        created_at_epoch_us=1_786_521_600_000_000,
    )
    writer.add_campaign(record)
    writer.add_campaign(record)

    changed_payload = _manifest_payload("campaign-1", "b" * 64, changed=True)
    changed_record = CampaignManifestRecord(
        campaign_id=record.campaign_id,
        manifest_hash=ContentHash(hashlib.sha256(changed_payload).hexdigest()),
        manifest_payload=changed_payload,
        search_axis=record.search_axis,
        lineage_root=record.lineage_root,
        created_at_epoch_us=record.created_at_epoch_us,
    )
    with pytest.raises(ExperimentConflictError) as exc_info:
        writer.add_campaign(changed_record)
    assert exc_info.value.details["reason_code"] == "campaign_immutable_conflict"

    with database.connection() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE research_campaign SET search_axis='model_code' "
                "WHERE campaign_id='campaign-1'"
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM research_campaign WHERE campaign_id='campaign-1'"
            )
        connection.rollback()


def test_typed_campaign_reader_round_trips_losslessly(tmp_path: Path) -> None:
    from ditto_analysis.experiments.campaign_persistence import (
        CampaignManifestRecord,
        CampaignReaderProtocol,
        CampaignWriterProtocol,
    )
    from ditto_analysis.experiments.models import ContentHash, ExperimentId
    from ditto_analysis.storage.sqlite.experiments.campaign_reader import (
        SQLiteCampaignReader,
    )
    from ditto_analysis.storage.sqlite.experiments.campaign_writer import (
        SQLiteCampaignWriter,
    )

    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    writer: CampaignWriterProtocol = SQLiteCampaignWriter(database)
    reader: CampaignReaderProtocol = SQLiteCampaignReader(database)
    payload = _manifest_payload("campaign-round-trip", "e" * 64)
    record = CampaignManifestRecord(
        campaign_id=ExperimentId("campaign-round-trip"),
        manifest_hash=ContentHash(hashlib.sha256(payload).hexdigest()),
        manifest_payload=payload,
        search_axis=SearchAxis.FACTOR_CODE,
        lineage_root=ContentHash("e" * 64),
        created_at_epoch_us=1_786_521_600_000_000,
    )

    writer.add_campaign(record)

    assert reader.get_campaign(record.campaign_id) == record
