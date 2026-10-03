"""Ingestion 状态 API 路由单元测试."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import ditto_application.queries.ingestion_status as ingestion_status_module
import pytest
from ditto_application.queries.ingestion_status import (
    DatasetStatus,
    HistoryItem,
    IngestionStatusQueryFacade,
)
from ditto_apps.api.routes.ingestion import (
    get_dq_summary,
    get_ingestion_history,
    get_ingestion_status,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.ingestion import (
    DQSummaryResponse,
    IngestionHistoryItem,
    IngestionStatusResponse,
)
from fastapi.params import Query

_StatusRoute = Callable[..., Awaitable[APIResponse[IngestionStatusResponse]]]
_HistoryRoute = Callable[..., Awaitable[APIResponse[list[IngestionHistoryItem]]]]
_DQSummaryRoute = Callable[..., Awaitable[APIResponse[DQSummaryResponse]]]
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_facade() -> MagicMock:
    return MagicMock(spec=IngestionStatusQueryFacade)


@pytest.fixture(autouse=True)
def _inline_ingestion_route_thread_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr("ditto_apps.api.routes.ingestion.run_blocking", run_inline)


async def _call_status(
    facade: IngestionStatusQueryFacade,
) -> APIResponse[IngestionStatusResponse]:
    route = cast(
        _StatusRoute,
        getattr(get_ingestion_status, "__dishka_orig_func__", get_ingestion_status),
    )
    return await route(facade=facade)


async def _call_history(
    facade: IngestionStatusQueryFacade,
    *,
    dataset: str,
    limit: int = 20,
) -> APIResponse[list[IngestionHistoryItem]]:
    route = cast(
        _HistoryRoute,
        getattr(get_ingestion_history, "__dishka_orig_func__", get_ingestion_history),
    )
    return await route(facade=facade, dataset=dataset, limit=limit)


async def _call_dq_summary() -> APIResponse[DQSummaryResponse]:
    route = cast(
        _DQSummaryRoute,
        getattr(get_dq_summary, "__dishka_orig_func__", get_dq_summary),
    )
    return await route()


class TestGetIngestionStatus:
    """GET /ingestion/status — 各数据集最新摄取状态."""

    async def test_returns_status_for_known_datasets(
        self,
        mock_facade: MagicMock,
    ) -> None:
        """返回所有已知数据集的摄取状态."""
        mock_facade.get_status.return_value = [
            DatasetStatus(
                dataset="stock_daily",
                latest_date="2024-01-15",
                latest_status="success",
                dataset_maturity="experimental",
                dataset_maturity_warning="experimental data requires research opt-in",
                record_count=5000,
                last_attempt=None,
                catalog_freshness_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
                catalog_storage_uri="stock_daily/2026",
                catalog_schema_hash="schema:stock_daily:v1",
                catalog_row_count=17,
                catalog_freshness_status="fresh",
                catalog_freshness_sla_hours=36,
            ),
            DatasetStatus(
                dataset="etf_daily",
                latest_date="2024-01-14",
                latest_status="failed",
                dataset_maturity="initial-focus",
                record_count=0,
                last_attempt=None,
                catalog_freshness_at=None,
                catalog_storage_uri=None,
                catalog_schema_hash=None,
                catalog_row_count=None,
                catalog_freshness_status="missing",
                catalog_freshness_sla_hours=36,
            ),
            DatasetStatus(
                dataset="macro_indicators",
                latest_date="2024-01-13",
                latest_status="success",
                dataset_maturity="experimental",
                record_count=10,
                last_attempt=None,
                catalog_freshness_at=None,
                catalog_storage_uri=None,
                catalog_schema_hash=None,
                catalog_row_count=None,
                catalog_freshness_status="stale",
                catalog_freshness_sla_hours=24,
            ),
        ]

        response = await _call_status(mock_facade)

        datasets = response.data.datasets
        assert len(datasets) == 3
        assert datasets[0].dataset == "stock_daily"
        assert datasets[0].latest_date == "2024-01-15"
        assert datasets[0].latest_status == "success"
        assert datasets[0].dataset_maturity == "experimental"
        assert datasets[0].dataset_maturity_warning == (
            "experimental data requires research opt-in"
        )
        assert datasets[0].record_count == 5000
        assert datasets[0].catalog_freshness_at == "2026-06-01T10:01:00+00:00"
        assert datasets[0].catalog_storage_uri == "stock_daily/2026"
        assert datasets[0].catalog_schema_hash == "schema:stock_daily:v1"
        assert datasets[0].catalog_row_count == 17
        assert datasets[0].catalog_freshness_status == "fresh"
        assert datasets[0].catalog_freshness_sla_hours == 36
        assert datasets[1].dataset == "etf_daily"
        assert datasets[1].latest_status == "failed"
        assert datasets[1].catalog_freshness_at is None
        assert datasets[1].catalog_freshness_status == "missing"
        summary = response.data.maturity_summary
        assert [(item.maturity, item.dataset_count) for item in summary] == [
            ("initial-focus", 1),
            ("experimental", 2),
        ]
        assert summary[0].fresh_count == 0
        assert summary[0].missing_count == 1
        assert summary[0].failed_count == 1
        assert summary[1].fresh_count == 1
        assert summary[1].stale_count == 1
        assert summary[1].warning_count == 1

    async def test_uses_application_maturity_summary_helper(
        self,
        mock_facade: MagicMock,
    ) -> None:
        """API summary mirrors the application query helper."""
        statuses = [
            DatasetStatus(
                dataset="stock_daily",
                latest_date="2024-01-15",
                latest_status="success",
                dataset_maturity="experimental",
                record_count=5000,
                last_attempt=None,
                catalog_freshness_status="fresh",
            )
        ]
        mock_facade.get_status.return_value = statuses

        response = await _call_status(mock_facade)

        expected = ingestion_status_module.summarize_status_by_maturity(statuses)
        assert [
            (
                item.maturity,
                item.dataset_count,
                item.fresh_count,
                item.failed_count,
            )
            for item in response.data.maturity_summary
        ] == [
            (
                item.maturity,
                item.dataset_count,
                item.fresh_count,
                item.failed_count,
            )
            for item in expected
        ]

    async def test_returns_empty_when_no_data(
        self,
        mock_facade: MagicMock,
    ) -> None:
        """无数据时返回空列表."""
        mock_facade.get_status.return_value = []

        response = await _call_status(mock_facade)

        assert response.data.datasets == []
        assert response.data.maturity_summary == []


@pytest.mark.unit
class TestGetIngestionHistory:
    """GET /ingestion/history — 数据集摄取历史."""

    async def test_returns_history_for_dataset(
        self,
        mock_facade: MagicMock,
    ) -> None:
        """返回指定数据集的摄取历史."""
        mock_facade.get_history.return_value = [
            HistoryItem(
                dataset="stock_daily",
                trade_date="2024-01-15",
                status="success",
                rows=5000,
                error_message=None,
                attempts=1,
                last_attempt_at="2024-01-15T18:05:00",
            ),
            HistoryItem(
                dataset="stock_daily",
                trade_date="2024-01-14",
                status="failed",
                rows=None,
                error_message="Connection timeout",
                attempts=2,
                last_attempt_at="2024-01-14T18:10:00",
            ),
        ]

        response = await _call_history(mock_facade, dataset="stock_daily", limit=10)

        items = response.data
        assert len(items) == 2
        assert items[0].trade_date == "2024-01-15"
        assert items[0].status == "success"
        assert items[0].rows == 5000
        assert items[1].status == "failed"
        assert items[1].error_message == "Connection timeout"

    def test_requires_dataset_param(
        self,
    ) -> None:
        """dataset 参数由 FastAPI 声明为必填."""
        route = getattr(
            get_ingestion_history, "__dishka_orig_func__", get_ingestion_history
        )
        default = inspect.signature(route).parameters["dataset"].default
        assert isinstance(default, Query)
        assert default.is_required()

    async def test_respects_limit_param(
        self,
        mock_facade: MagicMock,
    ) -> None:
        """limit 参数传递到 facade."""
        mock_facade.get_history.return_value = []

        await _call_history(mock_facade, dataset="etf_daily", limit=5)

        mock_facade.get_history.assert_called_once_with("etf_daily", 5)


@pytest.mark.unit
class TestGetDQSummary:
    """GET /ingestion/dq-summary — DQ 检查摘要."""

    async def test_returns_empty_datasets_placeholder(
        self,
    ) -> None:
        """V1 占位: 返回空 datasets 列表."""
        response = await _call_dq_summary()

        assert response.data.datasets == []
