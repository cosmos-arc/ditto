"""Tests for DerivedCatalogService."""

from ditto_datahub.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from pytest_mock import MockerFixture


class TestDerivedCatalogService:
    """Tests for DerivedCatalogService."""

    def test_save_spec_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """save_spec() should delegate to catalog writer."""
        spec = DerivedSpecRecord(
            derived_id="factor.momentum_20d",
            version=3,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="spec-hash-v3",
            spec_json={"expression": "ts_mean(close, 20)"},
            created_at="2026-03-13T16:00:00+08:00",
        )
        writer = mocker.Mock()
        service = DerivedCatalogService(
            catalog_reader=mocker.Mock(),
            catalog_writer=writer,
        )

        service.save_spec(spec)

        writer.write_spec.assert_called_once_with(spec)

    def test_get_spec_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """get_spec() should delegate to catalog reader."""
        spec = DerivedSpecRecord(
            derived_id="factor.momentum_20d",
            version=3,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="spec-hash-v3",
            spec_json={"expression": "ts_mean(close, 20)"},
            created_at="2026-03-13T16:00:00+08:00",
        )
        reader = mocker.Mock()
        reader.read_spec = mocker.Mock(return_value=spec)
        service = DerivedCatalogService(
            catalog_reader=reader,
            catalog_writer=mocker.Mock(),
        )

        result = service.get_spec("factor.momentum_20d", 3)

        assert result == spec
        reader.read_spec.assert_called_once_with("factor.momentum_20d", 3)

    def test_get_latest_run_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """get_latest_run() should delegate to catalog reader."""
        run = DerivedRunRecord(
            run_id="run-001",
            derived_id="factor.momentum_20d",
            version=3,
            mode="incremental",
            trigger="manual",
            request_start="2026-03-01",
            request_end="2026-03-13",
            compute_start="2026-02-10",
            compute_end="2026-03-13",
            source_snapshot_id="market:20260313-001",
            status="SUCCESS",
            rows_written=240,
            partitions_written=("2026-03",),
            error_message=None,
            created_at="2026-03-13T16:10:00+08:00",
            started_at="2026-03-13T16:10:05+08:00",
            finished_at="2026-03-13T16:10:55+08:00",
        )
        reader = mocker.Mock()
        reader.get_latest_run = mocker.Mock(return_value=run)
        service = DerivedCatalogService(
            catalog_reader=reader,
            catalog_writer=mocker.Mock(),
        )

        result = service.get_latest_run("factor.momentum_20d", 3)

        assert result == run
        reader.get_latest_run.assert_called_once_with("factor.momentum_20d", 3)

    def test_save_partitions_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """save_partitions() should delegate to catalog writer."""
        partitions = (
            DerivedPartitionRecord(
                run_id="run-001",
                derived_id="factor.momentum_20d",
                version=3,
                partition_key="2026-03",
                partition_path="factors/style/momentum_20d/2026-03.parquet",
                row_count=120,
                checksum="sha256:part-03",
                written_at="2026-03-13T16:10:50+08:00",
            ),
        )
        writer = mocker.Mock()
        service = DerivedCatalogService(
            catalog_reader=mocker.Mock(),
            catalog_writer=writer,
        )

        service.save_partitions(partitions)

        writer.write_partitions.assert_called_once_with(partitions)
