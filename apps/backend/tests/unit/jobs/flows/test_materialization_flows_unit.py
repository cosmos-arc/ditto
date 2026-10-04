"""Unit tests for the daily materialization Prefect flow."""

from collections.abc import Callable
from typing import Any

import ditto_apps.jobs.flows.materialization as materialization_module
from ditto_apps.jobs.flows.materialization import daily_materialization_flow
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint: Any) -> Callable[..., Any]:
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


DAILY_MATERIALIZATION_FLOW_RUNNER = _prefect_runner(daily_materialization_flow)


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
            "ditto_apps.jobs.flows.materialization.create_materialization_bundle",
            return_value=context,
        )

        result = DAILY_MATERIALIZATION_FLOW_RUNNER(trade_date="2026-03-13")

        bundle.materialization_service.materialize_daily.assert_called_once_with(
            trade_date="2026-03-13",
            mode="incremental",
            derived_ids=None,
        )
        assert result["summary"]["materialized_count"] == 1

    def test_plain_runner_uses_same_materialization_business_function(
        self,
        mocker: MockerFixture,
    ) -> None:
        """CLI 可直接运行未装饰的物化业务函数。"""
        assert hasattr(materialization_module, "run_daily_materialization")
        bundle = mocker.MagicMock()
        bundle.materialization_service.materialize_daily.return_value = ()
        context = mocker.MagicMock()
        context.__enter__.return_value = bundle
        context.__exit__.return_value = None
        mocker.patch.object(
            materialization_module,
            "create_materialization_bundle",
            return_value=context,
        )

        result = materialization_module.run_daily_materialization(
            trade_date="2026-07-16"
        )

        summary = result["summary"]
        assert isinstance(summary, dict)
        assert summary["materialized_count"] == 0
        bundle.materialization_service.materialize_daily.assert_called_once_with(
            trade_date="2026-07-16",
            mode="incremental",
            derived_ids=None,
        )
