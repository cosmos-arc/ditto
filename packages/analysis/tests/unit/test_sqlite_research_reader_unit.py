"""Tests for SQLiteResearchCatalogReader (reader.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import orjson
import pytest
from ditto_analysis.storage.sqlite.research.reader import SQLiteResearchCatalogReader
from ditto_kernel.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)


@pytest.fixture
def sqlite_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def reader(sqlite_client: MagicMock) -> SQLiteResearchCatalogReader:
    return SQLiteResearchCatalogReader(sqlite_client=sqlite_client)


# ---- Helpers to build mock row dicts ----


def _spine_spec_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "spine_id": "spine.cn_stock.default",
        "universe_id": "universe.cn.all",
        "calendar": "cn_stock",
        "grain": "1d",
        "entity_key": "instrument_id",
        "description": None,
        "created_at": "2026-01-01T00:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return defaults


def _dataset_spec_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "dataset_id": "research.alpha_beta",
        "spine_id": "spine.cn_stock.default",
        "derived_ids": orjson.dumps(["factor.alpha", "factor.beta"]).decode(),
        "join_policy": "left_preserving_pit",
        "known_at_policy": "sample_time",
        "late_arrival_policy": "require_rebuild",
        "description": None,
        "created_at": "2026-01-01T00:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return defaults


def _spine_snapshot_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
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
    return defaults


def _dataset_snapshot_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
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
        "resolved_versions": orjson.dumps({"factor.alpha": 2}).decode(),
        "resolved_inputs": orjson.dumps(
            [{"derived_id": "factor.alpha", "version": 2}]
        ).decode(),
        "source_snapshot_ids": orjson.dumps(["snap_001"]).decode(),
        "builder_version": "v1",
        "created_at": "2026-03-14T12:00:00+08:00",
    }
    defaults.update(overrides)
    return defaults


class TestReadSpineSpec:
    """Tests for read_spine_spec."""

    def test_read_spine_spec_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = _spine_spec_row()

        result = reader.read_spine_spec("spine.cn_stock.default")

        assert result is not None
        assert isinstance(result, ResearchSpineSpecRecord)
        assert result.spine_id == "spine.cn_stock.default"
        assert result.grain == "1d"
        sqlite_client.fetchone.assert_called_once()
        args = sqlite_client.fetchone.call_args
        assert "spine.cn_stock.default" in args[0][1]

    def test_read_spine_spec_not_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = None

        result = reader.read_spine_spec("spine.nonexistent")

        assert result is None


class TestReadDatasetSpec:
    """Tests for read_dataset_spec."""

    def test_read_dataset_spec_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = _dataset_spec_row()

        result = reader.read_dataset_spec("research.alpha_beta")

        assert result is not None
        assert isinstance(result, ResearchDatasetSpecRecord)
        assert result.dataset_id == "research.alpha_beta"
        assert result.derived_ids == ("factor.alpha", "factor.beta")

    def test_read_dataset_spec_not_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = None

        result = reader.read_dataset_spec("research.nonexistent")

        assert result is None


class TestReadSpineSnapshot:
    """Tests for read_spine_snapshot."""

    def test_read_spine_snapshot_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = _spine_snapshot_row()

        result = reader.read_spine_snapshot("rsp-001")

        assert result is not None
        assert isinstance(result, ResearchSpineSnapshotRecord)
        assert result.spine_snapshot_id == "rsp-001"
        assert result.row_count == 100

    def test_read_spine_snapshot_not_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = None

        result = reader.read_spine_snapshot("rsp-nonexistent")

        assert result is None


class TestReadDatasetSnapshot:
    """Tests for read_dataset_snapshot."""

    def test_read_dataset_snapshot_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = _dataset_snapshot_row()

        result = reader.read_dataset_snapshot("rds-001")

        assert result is not None
        assert isinstance(result, ResearchDatasetSnapshotRecord)
        assert result.snapshot_id == "rds-001"
        assert result.resolved_versions == {"factor.alpha": 2}
        assert result.resolved_inputs == ({"derived_id": "factor.alpha", "version": 2},)
        assert result.source_snapshot_ids == ("snap_001",)

    def test_read_dataset_snapshot_not_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = None

        result = reader.read_dataset_snapshot("rds-nonexistent")

        assert result is None


class TestGetLatestSpineSnapshot:
    """Tests for get_latest_spine_snapshot."""

    def test_get_latest_spine_snapshot(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = _spine_snapshot_row()

        result = reader.get_latest_spine_snapshot("spine.cn_stock.default")

        assert result is not None
        assert isinstance(result, ResearchSpineSnapshotRecord)
        # Verify ORDER BY DESC in the SQL query
        sql = sqlite_client.fetchone.call_args[0][0]
        assert "ORDER BY created_at DESC" in sql
        assert "LIMIT 1" in sql

    def test_get_latest_spine_snapshot_not_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = None

        result = reader.get_latest_spine_snapshot("spine.empty")

        assert result is None


class TestGetLatestDatasetSnapshot:
    """Tests for get_latest_dataset_snapshot."""

    def test_get_latest_dataset_snapshot(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = _dataset_snapshot_row()

        result = reader.get_latest_dataset_snapshot("research.alpha_beta")

        assert result is not None
        assert isinstance(result, ResearchDatasetSnapshotRecord)
        # Verify ORDER BY DESC in the SQL query
        sql = sqlite_client.fetchone.call_args[0][0]
        assert "ORDER BY created_at DESC" in sql
        assert "LIMIT 1" in sql

    def test_get_latest_dataset_snapshot_not_found(
        self, reader: SQLiteResearchCatalogReader, sqlite_client: MagicMock
    ) -> None:
        sqlite_client.fetchone.return_value = None

        result = reader.get_latest_dataset_snapshot("research.empty")

        assert result is None
