"""Tests for DerivedCatalogService."""

from __future__ import annotations

from ditto_data.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_data.services.derived_catalog_service import DerivedCatalogService
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


class TestCatalogDashboard:
    """Tests for DerivedCatalogService.catalog_dashboard."""

    def test_dashboard_returns_joined_view(self, mocker: MockerFixture) -> None:
        """catalog_dashboard() should return a joined view with all expected columns."""
        spec = DerivedSpecRecord(
            derived_id="factor.momentum_20d",
            version=3,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="spec-hash-v3",
            spec_json={"expression": "ts_mean(close, 20)"},
            created_at="2026-03-13T16:00:00+08:00",
        )
        version = DerivedVersionRecord(
            derived_id="factor.momentum_20d",
            version=3,
            status="published",
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-13T16:00:00+08:00",
            updated_at=None,
        )
        state = DerivedStateRecord(
            derived_id="factor.momentum_20d",
            active_version=3,
            coverage_start="2026-01-01",
            coverage_end="2026-03-13",
            watermark="2026-03-13",
            latest_run_id="run-001",
            latest_run_status="SUCCESS",
            total_rows=128,
            updated_at="2026-03-13T12:00:00+08:00",
        )
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
        reader.list_specs.return_value = (spec,)
        reader.read_version.return_value = version
        reader.read_state.return_value = state
        reader.get_latest_run.return_value = run

        service = DerivedCatalogService(
            catalog_reader=reader,
            catalog_writer=mocker.Mock(),
        )

        result = service.catalog_dashboard()

        expected_columns = [
            "derived_id",
            "version",
            "role",
            "profile",
            "version_status",
            "is_online",
            "is_primary",
            "active_version",
            "latest_run_id",
            "latest_run_status",
            "total_rows",
            "watermark",
        ]
        assert result.columns == expected_columns
        assert result.height == 1
        row = result.row(0, named=True)
        assert row["derived_id"] == "factor.momentum_20d"
        assert row["version"] == 3
        assert row["role"] == "factor"
        assert row["profile"] == "SERIES"
        assert row["version_status"] == "published"
        assert row["is_online"] is True
        assert row["is_primary"] is True
        assert row["active_version"] == 3
        assert row["latest_run_id"] == "run-001"
        assert row["latest_run_status"] == "SUCCESS"
        assert row["total_rows"] == 128
        assert row["watermark"] == "2026-03-13"

    def test_dashboard_empty_catalog(self, mocker: MockerFixture) -> None:
        """catalog_dashboard() should return empty DataFrame when catalog is empty."""
        reader = mocker.Mock()
        reader.list_specs.return_value = ()

        service = DerivedCatalogService(
            catalog_reader=reader,
            catalog_writer=mocker.Mock(),
        )

        result = service.catalog_dashboard()

        expected_columns = [
            "derived_id",
            "version",
            "role",
            "profile",
            "version_status",
            "is_online",
            "is_primary",
            "active_version",
            "latest_run_id",
            "latest_run_status",
            "total_rows",
            "watermark",
        ]
        assert result.is_empty()
        assert result.columns == expected_columns

    def test_dashboard_handles_missing_version_and_state(
        self, mocker: MockerFixture
    ) -> None:
        """catalog_dashboard() should use None for missing version/state/run records."""
        spec = DerivedSpecRecord(
            derived_id="factor.new_factor",
            version=1,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="spec-hash-v1",
            spec_json={"expression": "close"},
            created_at="2026-03-13T16:00:00+08:00",
        )

        reader = mocker.Mock()
        reader.list_specs.return_value = (spec,)
        reader.read_version.return_value = None
        reader.read_state.return_value = None
        reader.get_latest_run.return_value = None

        service = DerivedCatalogService(
            catalog_reader=reader,
            catalog_writer=mocker.Mock(),
        )

        result = service.catalog_dashboard()

        assert result.height == 1
        row = result.row(0, named=True)
        assert row["derived_id"] == "factor.new_factor"
        assert row["version_status"] is None
        assert row["is_online"] is None
        assert row["is_primary"] is None
        assert row["active_version"] is None
        assert row["latest_run_id"] is None
        assert row["latest_run_status"] is None
        assert row["total_rows"] is None
        assert row["watermark"] is None
