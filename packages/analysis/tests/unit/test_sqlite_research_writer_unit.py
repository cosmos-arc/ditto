"""Tests for SQLiteResearchCatalogWriter (writer.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import orjson
import pytest
from ditto_analysis.storage.sqlite.research.writer import SQLiteResearchCatalogWriter
from ditto_kernel.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)


def _make_spine_spec_record(**overrides: object) -> ResearchSpineSpecRecord:
    defaults = {
        "spine_id": "spine.cn_stock.default",
        "universe_id": "universe.cn.all",
        "calendar": "cn_stock",
        "grain": "1d",
        "entity_key": "instrument_id",
        "description": "test spine",
        "created_at": "2026-01-01T00:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return ResearchSpineSpecRecord(**defaults)  # type: ignore[arg-type]


def _make_dataset_spec_record(**overrides: object) -> ResearchDatasetSpecRecord:
    defaults = {
        "dataset_id": "research.alpha_beta",
        "spine_id": "spine.cn_stock.default",
        "derived_ids": ("factor.alpha", "factor.beta"),
        "join_policy": "left_preserving_pit",
        "known_at_policy": "sample_time",
        "late_arrival_policy": "require_rebuild",
        "description": "test dataset",
        "created_at": "2026-01-01T00:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return ResearchDatasetSpecRecord(**defaults)  # type: ignore[arg-type]


def _make_spine_snapshot_record(**overrides: object) -> ResearchSpineSnapshotRecord:
    defaults = {
        "spine_snapshot_id": "rsp-001",
        "spine_id": "spine.cn_stock.default",
        "snapshot_start": "2026-03-10",
        "snapshot_end": "2026-03-11",
        "row_count": 100,
        "data_path": "spines/data.parquet",
        "manifest_hash": "abc123",
        "created_at": "2026-03-14T12:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return ResearchSpineSnapshotRecord(**defaults)  # type: ignore[arg-type]


def _make_dataset_snapshot_record(**overrides: object) -> ResearchDatasetSnapshotRecord:
    defaults = {
        "snapshot_id": "rds-001",
        "dataset_id": "research.alpha_beta",
        "dataset_spec_version": 1,
        "spine_snapshot_id": "rsp-001",
        "snapshot_start": "2026-03-10",
        "snapshot_end": "2026-03-11",
        "row_count": 50,
        "data_path": "datasets/data.parquet",
        "manifest_hash": "def456",
        "known_at_policy": "sample_time",
        "effective_cutoff": None,
        "spine_spec_version": 1,
        "resolved_versions": {"factor.alpha": 2},
        "resolved_inputs": ({"derived_id": "factor.alpha", "version": 2},),
        "source_snapshot_ids": ("snap_001",),
        "builder_version": "v1",
        "created_at": "2026-03-14T12:00:00+08:00",
    }
    defaults.update(overrides)
    return ResearchDatasetSnapshotRecord(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def sqlite_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def writer(sqlite_client: MagicMock) -> SQLiteResearchCatalogWriter:
    return SQLiteResearchCatalogWriter(sqlite_client=sqlite_client)


class TestCommit:
    """Tests for commit."""

    def test_commit(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        writer.commit()

        sqlite_client.commit.assert_called_once()


class TestRollback:
    """Tests for rollback."""

    def test_rollback(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        writer.rollback()

        sqlite_client.rollback.assert_called_once()


class TestExecuteSpineSpec:
    """Tests for execute_spine_spec."""

    def test_execute_spine_spec(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_spine_spec_record()

        writer.execute_spine_spec(record)

        sqlite_client.execute.assert_called_once()
        args = sqlite_client.execute.call_args[0]
        sql = args[0]
        params = args[1]
        assert "INSERT OR REPLACE INTO research_spine_spec" in sql
        assert params[0] == "spine.cn_stock.default"
        assert params[1] == "universe.cn.all"
        assert params[4] == "instrument_id"
        assert params[7] == 1


class TestExecuteDatasetSpec:
    """Tests for execute_dataset_spec."""

    def test_execute_dataset_spec(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_dataset_spec_record()

        writer.execute_dataset_spec(record)

        sqlite_client.execute.assert_called_once()
        args = sqlite_client.execute.call_args[0]
        sql = args[0]
        params = args[1]
        assert "INSERT OR REPLACE INTO research_dataset_spec" in sql
        # derived_ids should be serialized as JSON
        assert params[2] == orjson.dumps(("factor.alpha", "factor.beta")).decode()


class TestExecuteSpineSnapshot:
    """Tests for execute_spine_snapshot."""

    def test_execute_spine_snapshot(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_spine_snapshot_record()

        writer.execute_spine_snapshot(record)

        sqlite_client.execute.assert_called_once()
        args = sqlite_client.execute.call_args[0]
        sql = args[0]
        params = args[1]
        assert "INSERT OR REPLACE INTO research_spine_snapshot" in sql
        assert params[0] == "rsp-001"
        assert params[4] == 100


class TestExecuteDatasetSnapshot:
    """Tests for execute_dataset_snapshot."""

    def test_execute_dataset_snapshot(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_dataset_snapshot_record()

        writer.execute_dataset_snapshot(record)

        sqlite_client.execute.assert_called_once()
        args = sqlite_client.execute.call_args[0]
        sql = args[0]
        params = args[1]
        assert "INSERT OR REPLACE INTO research_dataset_snapshot" in sql
        assert params[0] == "rds-001"
        # Verify JSON serialization of complex fields
        assert params[12] == orjson.dumps({"factor.alpha": 2}).decode()
        assert (
            params[13]
            == orjson.dumps(({"derived_id": "factor.alpha", "version": 2},)).decode()
        )
        assert params[14] == orjson.dumps(("snap_001",)).decode()


class TestWriteSpineSpec:
    """Tests for write_spine_spec."""

    def test_write_spine_spec(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_spine_spec_record()

        writer.write_spine_spec(record)

        sqlite_client.execute.assert_called_once()
        sqlite_client.commit.assert_called_once()


class TestWriteDatasetSpec:
    """Tests for write_dataset_spec."""

    def test_write_dataset_spec(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_dataset_spec_record()

        writer.write_dataset_spec(record)

        sqlite_client.execute.assert_called_once()
        sqlite_client.commit.assert_called_once()


class TestWriteSpineSnapshot:
    """Tests for write_spine_snapshot."""

    def test_write_spine_snapshot(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_spine_snapshot_record()

        writer.write_spine_snapshot(record)

        sqlite_client.execute.assert_called_once()
        sqlite_client.commit.assert_called_once()


class TestWriteDatasetSnapshot:
    """Tests for write_dataset_snapshot."""

    def test_write_dataset_snapshot(
        self, writer: SQLiteResearchCatalogWriter, sqlite_client: MagicMock
    ) -> None:
        record = _make_dataset_snapshot_record()

        writer.write_dataset_snapshot(record)

        sqlite_client.execute.assert_called_once()
        sqlite_client.commit.assert_called_once()
