"""Schedule-aware R2 bootstrap planner tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_data.ingestion.partition_state import PartitionLifecycleStatus


def _metadata_service(mocker):
    service = mocker.Mock()
    service.list_trading_days.return_value = [
        "2026-01-30",
        "2026-02-02",
        "2026-02-03",
    ]
    return service


class TestBootstrapPlannerSchedules:
    def test_trading_schedule_groups_expected_dates_by_product_chunk(
        self, mocker
    ) -> None:
        service = _metadata_service(mocker)
        planner = BootstrapPlanner(metadata_service=service)

        plan = planner.plan(
            dataset_id="stock_daily",
            source="tushare",
            start_date="2026-01-30",
            end_date="2026-02-03",
        )

        assert [chunk.partition_dates for chunk in plan.chunks] == [
            ("2026-01-30",),
            ("2026-02-02", "2026-02-03"),
        ]
        assert [chunk.chunk_key for chunk in plan.chunks] == ["2026-01", "2026-02"]
        assert all(chunk.execution_mode == "date_range" for chunk in plan.chunks)
        service.list_trading_days.assert_called_once_with("2026-01-30", "2026-02-03")

    def test_natural_schedule_includes_weekends(self, mocker) -> None:
        planner = BootstrapPlanner(metadata_service=_metadata_service(mocker))

        plan = planner.plan(
            dataset_id="fx_daily",
            source="tushare",
            start_date="2026-01-30",
            end_date="2026-02-02",
        )

        assert [chunk.partition_dates for chunk in plan.chunks] == [
            ("2026-01-30", "2026-01-31"),
            ("2026-02-01", "2026-02-02"),
        ]

    def test_source_defined_schedule_uses_provider_release_dates(self, mocker) -> None:
        resolver = mocker.Mock(return_value=("2026-01-15", "2026-02-20"))
        planner = BootstrapPlanner(
            metadata_service=_metadata_service(mocker),
            source_schedule_resolver=resolver,
        )

        plan = planner.plan(
            dataset_id="macro_indicators",
            source="fred",
            start_date="2026-01-01",
            end_date="2026-03-31",
        )

        assert [chunk.partition_dates for chunk in plan.chunks] == [
            ("2026-01-15",),
            ("2026-02-20",),
        ]
        assert [chunk.chunk_key for chunk in plan.chunks] == [
            "source:2026-01-15",
            "source:2026-02-20",
        ]
        resolver.assert_called_once_with(
            "macro_indicators", "fred", "2026-01-01", "2026-03-31"
        )

    def test_source_defined_without_resolver_plans_one_range_request(
        self, mocker
    ) -> None:
        planner = BootstrapPlanner(metadata_service=_metadata_service(mocker))

        plan = planner.plan(
            dataset_id="macro_indicators",
            source="tushare",
            start_date="2026-01-01",
            end_date="2026-03-31",
        )

        assert len(plan.chunks) == 1
        assert plan.chunks[0].partition_dates == ("2026-03-31",)
        assert plan.chunks[0].request_start == "2026-01-01"
        assert plan.chunks[0].request_end == "2026-03-31"


class TestBootstrapPlannerCapabilitiesAndResume:
    def test_selects_instrument_range_when_instruments_are_supplied(
        self, mocker
    ) -> None:
        planner = BootstrapPlanner(metadata_service=_metadata_service(mocker))

        plan = planner.plan(
            dataset_id="stock_daily",
            source="tushare",
            start_date="2026-01-30",
            end_date="2026-02-03",
            instrument_ids=(2, 1),
        )

        assert all(chunk.execution_mode == "instrument_range" for chunk in plan.chunks)
        assert all(chunk.instrument_ids == (1, 2) for chunk in plan.chunks)

    def test_filters_chunks_already_marked_complete(self, mocker) -> None:
        service = _metadata_service(mocker)
        lifecycle_reader = mocker.Mock()
        planner = BootstrapPlanner(
            metadata_service=service,
            partition_lifecycle_reader=lifecycle_reader,
        )
        initial = BootstrapPlanner(metadata_service=service).plan(
            dataset_id="stock_daily",
            source="tushare",
            start_date="2026-01-30",
            end_date="2026-02-03",
        )
        complete_id = initial.chunks[0].chunk_id
        lifecycle_reader.get_checkpoint.side_effect = lambda chunk_id: (
            SimpleNamespace(status=PartitionLifecycleStatus.COMPLETE)
            if chunk_id == complete_id
            else None
        )

        resumed = planner.plan(
            dataset_id="stock_daily",
            source="tushare",
            start_date="2026-01-30",
            end_date="2026-02-03",
        )

        assert resumed.skipped_complete_chunk_ids == (complete_id,)
        assert len(resumed.chunks) == 1
        assert resumed.chunks[0].chunk_key == "2026-02"

    def test_rejects_invalid_interval(self, mocker) -> None:
        planner = BootstrapPlanner(metadata_service=_metadata_service(mocker))

        with pytest.raises(AppProcessError, match="end_date"):
            planner.plan(
                dataset_id="stock_daily",
                source="tushare",
                start_date="2026-02-02",
                end_date="2026-01-30",
            )

    def test_chunk_identity_is_deterministic(self, mocker) -> None:
        planner = BootstrapPlanner(metadata_service=_metadata_service(mocker))

        first = planner.plan(
            dataset_id="stock_daily",
            source="tushare",
            start_date="2026-01-30",
            end_date="2026-02-03",
        )
        second = planner.plan(
            dataset_id="stock_daily",
            source="tushare",
            start_date="2026-01-30",
            end_date="2026-02-03",
        )

        assert first == second
