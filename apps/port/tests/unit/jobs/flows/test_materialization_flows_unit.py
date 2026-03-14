"""Unit tests for Phase 3 materialization Prefect flows."""

from __future__ import annotations

from ditto_port.jobs.flows.materialization import (
    daily_materialization_flow,
    repair_from_invalidation_flow,
)
from pytest_mock import MockerFixture


class TestDailyMaterializationFlow:
    """Tests for daily materialization flow."""

    def test_flow_calls_service_for_durable_profiles(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Flow should request durable materialization from the bundle service."""
        bundle = mocker.MagicMock()
        bundle.materialization_service.materialize_daily.return_value = (
            {"derived_id": "factor.alpha_simple"},
        )
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = daily_materialization_flow(trade_date="2026-03-13")

        bundle.materialization_service.materialize_daily.assert_called_once_with(
            trade_date="2026-03-13",
            mode="incremental",
            derived_ids=None,
        )
        assert result["summary"]["materialized_count"] == 1


class TestRepairFromInvalidationFlow:
    """Tests for invalidation repair flow."""

    def test_flow_repairs_pending_invalidations(self, mocker: MockerFixture) -> None:
        """Repair flow should delegate to the invalidation service."""
        bundle = mocker.MagicMock()
        bundle.invalidation_service.repair_pending.return_value = (
            {"derived_id": "factor.alpha_simple"},
            {"derived_id": "factor.alpha_other"},
        )
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch(
            "ditto_port.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = repair_from_invalidation_flow(limit=20)

        bundle.invalidation_service.repair_pending.assert_called_once_with(limit=20)
        assert result["summary"]["repaired_count"] == 2
