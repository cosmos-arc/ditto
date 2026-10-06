"""例行 adj_factor 对账任务的失败隔离契约（#515 A3）."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.commands.quality_reconciliation import ReconcileSourcesHandler
from ditto_application.processes.quality.types import ReconciliationResult
from ditto_apps.jobs.tasks import dq_reconcile as dq_reconcile_module
from ditto_apps.jobs.tasks.dq_reconcile import run_dq_reconcile_adj_factor
from ditto_data.services.market_service import MarketService
from pytest_mock import MockerFixture


def _host(
    mocker: MockerFixture,
    *,
    handler: Any = None,
    handler_error: Exception | None = None,
    primary: pl.DataFrame | None = None,
) -> MagicMock:
    """构造 mock 容器：primary 为 None 时 get_adj_factors 返回空帧."""
    container = MagicMock()
    if handler_error is not None:
        # 容器解析阶段抛错（如辅源未配置：FUYAO_API_KEY 缺失）
        def raise_get(_type: object) -> object:
            raise handler_error

        container.get.side_effect = raise_get
    else:
        market = MagicMock(spec=MarketService)
        market.get_adj_factors.return_value = (
            primary
            if primary is not None
            else pl.DataFrame(
                {
                    "instrument_id": [1],
                    "trade_date": ["2026-07-16"],
                    "adj_factor": [10.0],
                }
            )
        )
        container.get.side_effect = lambda t: (
            handler if t is ReconcileSourcesHandler else market
        )
    context = MagicMock()
    context.__enter__.return_value = container
    context.__exit__.return_value = None
    mocker.patch.object(
        dq_reconcile_module,
        "create_prefect_host",
        return_value=context,
    )
    return container


@pytest.mark.unit
def test_reconciliation_result_passthrough(mocker: MockerFixture) -> None:
    handler = MagicMock(spec=ReconcileSourcesHandler)
    handler.handle.return_value = ReconciliationResult(
        trade_date="2026-07-16",
        dataset="adj_factor",
        passed=True,
        issue_count=0,
        comparable=True,
        diff_count=0,
    )
    _host(mocker, handler=handler)

    result = run_dq_reconcile_adj_factor("2026-07-16")

    assert result["passed"] is True
    assert result["diff_count"] == 0
    handler.handle.assert_called_once()


@pytest.mark.unit
def test_no_primary_data_skips(mocker: MockerFixture) -> None:
    handler = MagicMock(spec=ReconcileSourcesHandler)
    _host(mocker, handler=handler, primary=pl.DataFrame())

    result = run_dq_reconcile_adj_factor("2026-07-16")

    assert result["skipped"] is True
    assert result["skip_reason"] == "no_primary_data"
    handler.handle.assert_not_called()


@pytest.mark.unit
def test_unconfigured_secondary_source_degrades_to_skip(
    mocker: MockerFixture,
) -> None:
    """辅源未配置（容器解析抛错）显式 skip，不拖垮例行链."""
    _host(
        mocker,
        handler_error=RuntimeError(
            "secondary bars source is unconfigured: set FUYAO_API_KEY"
        ),
    )

    result = run_dq_reconcile_adj_factor("2026-07-16")

    assert result["passed"] is False
    assert result["skipped"] is True
    assert "FUYAO_API_KEY" in result["skip_reason"]


@pytest.mark.unit
def test_handler_failure_degrades_to_skip(mocker: MockerFixture) -> None:
    handler = MagicMock(spec=ReconcileSourcesHandler)
    handler.handle.side_effect = RuntimeError("dump not found")
    _host(mocker, handler=handler)

    result = run_dq_reconcile_adj_factor("2026-07-16")

    assert result["skipped"] is True
    assert "dump not found" in result["skip_reason"]
