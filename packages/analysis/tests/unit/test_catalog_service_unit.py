"""Tests for ResearchCatalogService (catalog_service.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.domain import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)


def _make_spine_spec_record(**overrides: object) -> ResearchSpineSpecRecord:
    """Create a ResearchSpineSpecRecord with sensible defaults."""
    defaults = {
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
    return ResearchSpineSpecRecord(**defaults)  # type: ignore[arg-type]


def _make_dataset_spec_record(**overrides: object) -> ResearchDatasetSpecRecord:
    """Create a ResearchDatasetSpecRecord with sensible defaults."""
    defaults = {
        "dataset_id": "research.alpha_beta",
        "spine_id": "spine.cn_stock.default",
        "derived_ids": ("factor.alpha",),
        "join_policy": "left_preserving_pit",
        "known_at_policy": "sample_time",
        "late_arrival_policy": "require_rebuild",
        "description": None,
        "created_at": "2026-01-01T00:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return ResearchDatasetSpecRecord(**defaults)  # type: ignore[arg-type]


def _make_spine_snapshot_record(**overrides: object) -> ResearchSpineSnapshotRecord:
    """Create a ResearchSpineSnapshotRecord with sensible defaults."""
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
    """Create a ResearchDatasetSnapshotRecord with sensible defaults."""
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
    }
    defaults.update(overrides)
    return ResearchDatasetSnapshotRecord(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def reader() -> MagicMock:
    return MagicMock()


@pytest.fixture
def writer() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(reader: MagicMock, writer: MagicMock) -> ResearchCatalogService:
    return ResearchCatalogService(
        catalog_reader=reader,
        catalog_writer=writer,
    )


class TestConstructor:
    """Tests for ResearchCatalogService constructor."""

    def test_constructor_stores_reader_writer(
        self, reader: MagicMock, writer: MagicMock
    ) -> None:
        svc = ResearchCatalogService(catalog_reader=reader, catalog_writer=writer)

        assert svc._catalog_reader is reader
        assert svc._catalog_writer is writer


class TestSaveSpineSpec:
    """Tests for save_spine_spec."""

    def test_save_spine_spec(
        self, service: ResearchCatalogService, writer: MagicMock
    ) -> None:
        record = _make_spine_spec_record()

        service.save_spine_spec(record)

        writer.write_spine_spec.assert_called_once_with(record)


class TestSaveDatasetSpec:
    """Tests for save_dataset_spec."""

    def test_save_dataset_spec(
        self, service: ResearchCatalogService, writer: MagicMock
    ) -> None:
        record = _make_dataset_spec_record()

        service.save_dataset_spec(record)

        writer.write_dataset_spec.assert_called_once_with(record)


class TestSaveSpineSnapshot:
    """Tests for save_spine_snapshot."""

    def test_save_spine_snapshot(
        self, service: ResearchCatalogService, writer: MagicMock
    ) -> None:
        record = _make_spine_snapshot_record()

        service.save_spine_snapshot(record)

        writer.write_spine_snapshot.assert_called_once_with(record)


class TestSaveDatasetSnapshot:
    """Tests for save_dataset_snapshot."""

    def test_save_dataset_snapshot(
        self, service: ResearchCatalogService, writer: MagicMock
    ) -> None:
        record = _make_dataset_snapshot_record()

        service.save_dataset_snapshot(record)

        writer.write_dataset_snapshot.assert_called_once_with(record)


class TestGetSpineSpec:
    """Tests for get_spine_spec."""

    def test_get_spine_spec_found(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        expected = _make_spine_spec_record()
        reader.read_spine_spec.return_value = expected

        result = service.get_spine_spec("spine.cn_stock.default")

        assert result is expected
        reader.read_spine_spec.assert_called_once_with("spine.cn_stock.default")

    def test_get_spine_spec_not_found(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        reader.read_spine_spec.return_value = None

        result = service.get_spine_spec("spine.nonexistent")

        assert result is None


class TestGetDatasetSpec:
    """Tests for get_dataset_spec."""

    def test_get_dataset_spec_found(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        expected = _make_dataset_spec_record()
        reader.read_dataset_spec.return_value = expected

        result = service.get_dataset_spec("research.alpha_beta")

        assert result is expected
        reader.read_dataset_spec.assert_called_once_with("research.alpha_beta")

    def test_get_dataset_spec_not_found(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        reader.read_dataset_spec.return_value = None

        result = service.get_dataset_spec("research.nonexistent")

        assert result is None


class TestGetSpineSnapshot:
    """Tests for get_spine_snapshot."""

    def test_get_spine_snapshot_found(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        expected = _make_spine_snapshot_record()
        reader.read_spine_snapshot.return_value = expected

        result = service.get_spine_snapshot("rsp-001")

        assert result is expected
        reader.read_spine_snapshot.assert_called_once_with("rsp-001")


class TestGetDatasetSnapshot:
    """Tests for get_dataset_snapshot."""

    def test_get_dataset_snapshot_found(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        expected = _make_dataset_snapshot_record()
        reader.read_dataset_snapshot.return_value = expected

        result = service.get_dataset_snapshot("rds-001")

        assert result is expected
        reader.read_dataset_snapshot.assert_called_once_with("rds-001")


class TestGetLatestSpineSnapshot:
    """Tests for get_latest_spine_snapshot."""

    def test_get_latest_spine_snapshot(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        expected = _make_spine_snapshot_record()
        reader.get_latest_spine_snapshot.return_value = expected

        result = service.get_latest_spine_snapshot("spine.cn_stock.default")

        assert result is expected
        reader.get_latest_spine_snapshot.assert_called_once_with(
            "spine.cn_stock.default"
        )


class TestGetLatestDatasetSnapshot:
    """Tests for get_latest_dataset_snapshot."""

    def test_get_latest_dataset_snapshot(
        self, service: ResearchCatalogService, reader: MagicMock
    ) -> None:
        expected = _make_dataset_snapshot_record()
        reader.get_latest_dataset_snapshot.return_value = expected

        result = service.get_latest_dataset_snapshot("research.alpha_beta")

        assert result is expected
        reader.get_latest_dataset_snapshot.assert_called_once_with(
            "research.alpha_beta"
        )
