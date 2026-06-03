"""Ingestion 状态 API 路由单元测试."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import ditto_application.queries.ingestion_status as ingestion_status_module
import pytest
from ditto_application.commands.catalog import (
    DatasetMaturityPromotionRevokeCommand,
    DatasetMaturityPromotionRevokeResult,
    DatasetPromotionReviewCommand,
    DatasetPromotionReviewResult,
)
from ditto_application.queries.ingestion_status import (
    DatasetMaturitySummary,
    DatasetPromotionCriterionCount,
    DatasetPromotionReadinessItem,
    DatasetPromotionReadinessReport,
    DatasetPromotionStatusCount,
    DatasetStatus,
    HistoryItem,
    IngestionStatusQueryFacade,
)
from ditto_apps.api.routes.ingestion import (
    get_catalog_maturity_governance_report,
    get_catalog_promotion_readiness_report,
    get_dq_summary,
    get_ingestion_history,
    get_ingestion_status,
    review_dataset_promotion_evidence,
    revoke_dataset_maturity_promotion,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.ingestion import (
    DQSummaryResponse,
    IngestionHistoryItem,
    IngestionStatusResponse,
    MaturityGovernanceReportResponse,
    MaturityPromotionRevokeRequest,
    MaturityPromotionRevokeResponse,
    PromotionEvidenceReviewRequest,
    PromotionEvidenceReviewResponse,
    PromotionReadinessReportResponse,
)
from fastapi.params import Query

_StatusRoute = Callable[..., Awaitable[APIResponse[IngestionStatusResponse]]]
_HistoryRoute = Callable[..., Awaitable[APIResponse[list[IngestionHistoryItem]]]]
_DQSummaryRoute = Callable[..., Awaitable[APIResponse[DQSummaryResponse]]]
_PromotionReviewRoute = Callable[
    ...,
    Awaitable[APIResponse[PromotionEvidenceReviewResponse]],
]
_PromotionRevokeRoute = Callable[
    ...,
    Awaitable[APIResponse[MaturityPromotionRevokeResponse]],
]
_PromotionReadinessRoute = Callable[
    ...,
    Awaitable[APIResponse[PromotionReadinessReportResponse]],
]
_MaturityGovernanceRoute = Callable[
    ...,
    Awaitable[APIResponse[MaturityGovernanceReportResponse]],
]
pytestmark = pytest.mark.asyncio

_PIT_CRITERION = "complete PIT/replay coverage for the dataset"
_SOURCE_CRITERION = "document runtime owner, freshness SLA, and source failover policy"
_RUNTIME_CRITERION = (
    "pass catalog-backed runtime/read-model tests without research opt-in"
)


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


async def _call_promotion_review(
    handler: object,
    request: PromotionEvidenceReviewRequest,
) -> APIResponse[PromotionEvidenceReviewResponse]:
    route = cast(
        _PromotionReviewRoute,
        getattr(
            review_dataset_promotion_evidence,
            "__dishka_orig_func__",
            review_dataset_promotion_evidence,
        ),
    )
    return await route(handler=handler, request=request)


async def _call_promotion_revoke(
    handler: object,
    request: MaturityPromotionRevokeRequest,
) -> APIResponse[MaturityPromotionRevokeResponse]:
    route = cast(
        _PromotionRevokeRoute,
        getattr(
            revoke_dataset_maturity_promotion,
            "__dishka_orig_func__",
            revoke_dataset_maturity_promotion,
        ),
    )
    return await route(handler=handler, request=request)


async def _call_promotion_readiness_report(
    facade: IngestionStatusQueryFacade,
    *,
    dataset_ids: list[str] | None = None,
) -> APIResponse[PromotionReadinessReportResponse]:
    route = cast(
        _PromotionReadinessRoute,
        getattr(
            get_catalog_promotion_readiness_report,
            "__dishka_orig_func__",
            get_catalog_promotion_readiness_report,
        ),
    )
    return await route(facade=facade, dataset_ids=dataset_ids)


async def _call_maturity_governance_report(
    facade: IngestionStatusQueryFacade,
    *,
    dataset_ids: list[str] | None = None,
) -> APIResponse[MaturityGovernanceReportResponse]:
    route = cast(
        _MaturityGovernanceRoute,
        getattr(
            get_catalog_maturity_governance_report,
            "__dishka_orig_func__",
            get_catalog_maturity_governance_report,
        ),
    )
    return await route(facade=facade, dataset_ids=dataset_ids)


@pytest.mark.unit
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
                dataset_promotion_criteria=("complete PIT replay coverage",),
                dataset_promotion_status="blocked",
                dataset_promotion_missing_criteria=("complete PIT replay coverage",),
                dataset_promotion_satisfied_criteria=(),
                dataset_promotion_rejected_criteria=("source failover policy missing",),
                latest_revocation_reason="policy_regression",
                latest_revoked_by="data-governance",
                latest_revoked_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
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
        assert datasets[0].dataset_promotion_criteria == [
            "complete PIT replay coverage"
        ]
        assert datasets[0].dataset_promotion_status == "blocked"
        assert datasets[0].dataset_promotion_missing_criteria == [
            "complete PIT replay coverage"
        ]
        assert datasets[0].dataset_promotion_satisfied_criteria == []
        assert datasets[0].dataset_promotion_rejected_criteria == [
            "source failover policy missing"
        ]
        assert datasets[0].latest_revocation_reason == "policy_regression"
        assert datasets[0].latest_revoked_by == "data-governance"
        assert datasets[0].latest_revoked_at == "2026-06-02T09:30:00+00:00"
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
        assert summary[1].promotion_blocked_count == 1

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
class TestReviewDatasetPromotionEvidence:
    """POST /ingestion/catalog/promotion/evidence — reviewer workflow."""

    async def test_reviews_promotion_evidence_through_application_handler(
        self,
    ) -> None:
        handler = MagicMock()
        handler.handle.return_value = DatasetPromotionReviewResult(
            dataset_id="stock_daily",
            reviewed_criterion="complete PIT replay coverage",
            evidence_uri="ditto://evidence/stock_daily/pit",
            reviewed_by="architecture-review",
            passed=True,
            reviewed_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
            promotion_status="blocked",
            missing_criteria=("source failover policy",),
            satisfied_criteria=("complete PIT replay coverage",),
            rejected_criteria=(),
            metadata_promoted=False,
            dataset_maturity_before="experimental",
            dataset_maturity_after="experimental",
        )
        request = PromotionEvidenceReviewRequest(
            dataset_id="stock_daily",
            criterion="complete PIT replay coverage",
            evidence_uri="ditto://evidence/stock_daily/pit",
            reviewed_by="architecture-review",
            passed=True,
            notes="PIT replay passed",
        )

        response = await _call_promotion_review(handler, request)

        handler.handle.assert_called_once_with(
            DatasetPromotionReviewCommand(
                dataset_id="stock_daily",
                criterion="complete PIT replay coverage",
                evidence_uri="ditto://evidence/stock_daily/pit",
                reviewed_by="architecture-review",
                passed=True,
                notes="PIT replay passed",
            )
        )
        assert response.data.dataset_id == "stock_daily"
        assert response.data.reviewed_criterion == "complete PIT replay coverage"
        assert response.data.promotion_status == "blocked"
        assert response.data.missing_criteria == ["source failover policy"]
        assert response.data.satisfied_criteria == ["complete PIT replay coverage"]
        assert response.data.rejected_criteria == []
        assert response.data.metadata_promoted is False
        assert response.data.dataset_maturity_before == "experimental"
        assert response.data.dataset_maturity_after == "experimental"


@pytest.mark.unit
class TestRevokeDatasetMaturityPromotion:
    """POST /ingestion/catalog/promotion/revoke — reversal workflow."""

    async def test_revokes_promotion_through_application_handler(self) -> None:
        handler = MagicMock()
        handler.handle.return_value = DatasetMaturityPromotionRevokeResult(
            dataset_id="stock_daily",
            revoked_by="architecture-review",
            revoked_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
            dataset_maturity_before="initial-focus",
            dataset_maturity_after="experimental",
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            revocation_reason="failed_revalidation",
            notes="PIT regression reopened promotion",
        )
        request = MaturityPromotionRevokeRequest(
            dataset_id="stock_daily",
            revoked_by="architecture-review",
            revocation_reason="failed_revalidation",
            notes="PIT regression reopened promotion",
        )

        response = await _call_promotion_revoke(handler, request)

        handler.handle.assert_called_once_with(
            DatasetMaturityPromotionRevokeCommand(
                dataset_id="stock_daily",
                revoked_by="architecture-review",
                revocation_reason="failed_revalidation",
                notes="PIT regression reopened promotion",
            )
        )
        assert response.data.dataset_id == "stock_daily"
        assert response.data.revoked_by == "architecture-review"
        assert response.data.dataset_maturity_before == "initial-focus"
        assert response.data.dataset_maturity_after == "experimental"
        assert (
            response.data.evidence_uri == "ditto://evidence/stock_daily/runtime-tests"
        )
        assert response.data.revocation_reason == "failed_revalidation"


@pytest.mark.unit
class TestGetPromotionReadinessReport:
    """GET /ingestion/catalog/promotion/readiness — governance report."""

    async def test_returns_aggregated_promotion_readiness_report(
        self,
        mock_facade: MagicMock,
    ) -> None:
        mock_facade.get_promotion_readiness_report.return_value = (
            DatasetPromotionReadinessReport(
                dataset_count=3,
                promotable_count=1,
                active_promotion_count=1,
                status_counts=(
                    DatasetPromotionStatusCount(status="ready", count=1),
                    DatasetPromotionStatusCount(status="blocked", count=1),
                    DatasetPromotionStatusCount(
                        status="not_applicable",
                        count=1,
                    ),
                ),
                missing_criteria_counts=(
                    DatasetPromotionCriterionCount(
                        criterion=_RUNTIME_CRITERION,
                        count=1,
                    ),
                ),
                rejected_criteria_counts=(
                    DatasetPromotionCriterionCount(
                        criterion=_SOURCE_CRITERION,
                        count=1,
                    ),
                ),
                datasets=(
                    DatasetPromotionReadinessItem(
                        dataset_id="stock_daily",
                        metadata_maturity="experimental",
                        current_maturity="experimental",
                        promotion_status="blocked",
                        active_maturity_promotion=False,
                        latest_revocation_reason="failed_revalidation",
                        latest_revoked_by="data-governance",
                        latest_revoked_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                        required_criteria=(
                            _PIT_CRITERION,
                            _SOURCE_CRITERION,
                            _RUNTIME_CRITERION,
                        ),
                        satisfied_criteria=(_PIT_CRITERION,),
                        missing_criteria=(_RUNTIME_CRITERION,),
                        rejected_criteria=(_SOURCE_CRITERION,),
                    ),
                    DatasetPromotionReadinessItem(
                        dataset_id="macro_indicators",
                        metadata_maturity="experimental",
                        current_maturity="initial-focus",
                        promotion_status="ready",
                        active_maturity_promotion=True,
                        required_criteria=(_PIT_CRITERION,),
                        satisfied_criteria=(_PIT_CRITERION,),
                        missing_criteria=(),
                        rejected_criteria=(),
                    ),
                ),
            )
        )

        response = await _call_promotion_readiness_report(
            mock_facade,
            dataset_ids=["stock_daily", "macro_indicators", "etf_daily"],
        )

        assert response.data.dataset_count == 3
        assert response.data.promotable_count == 1
        assert response.data.active_promotion_count == 1
        assert [(item.status, item.count) for item in response.data.status_counts] == [
            ("ready", 1),
            ("blocked", 1),
            ("not_applicable", 1),
        ]
        assert response.data.missing_criteria_counts[0].count == 1
        assert response.data.rejected_criteria_counts[0].criterion == _SOURCE_CRITERION
        stock = response.data.datasets[0]
        assert stock.dataset_id == "stock_daily"
        assert stock.metadata_maturity == "experimental"
        assert stock.current_maturity == "experimental"
        assert stock.promotion_status == "blocked"
        assert stock.active_maturity_promotion is False
        assert stock.latest_revocation_reason == "failed_revalidation"
        assert stock.latest_revoked_by == "data-governance"
        assert stock.latest_revoked_at == "2026-06-02T09:30:00+00:00"
        assert stock.satisfied_criteria == [_PIT_CRITERION]
        macro = response.data.datasets[1]
        assert macro.current_maturity == "initial-focus"
        assert macro.active_maturity_promotion is True
        mock_facade.get_promotion_readiness_report.assert_called_once_with(
            ["stock_daily", "macro_indicators", "etf_daily"]
        )


@pytest.mark.unit
class TestGetMaturityGovernanceReport:
    async def test_returns_unified_maturity_governance_report(
        self,
        mock_facade: MagicMock,
    ) -> None:
        mock_facade.get_maturity_governance_report.return_value = SimpleNamespace(
            dataset_count=3,
            warning_count=1,
            promotable_count=1,
            active_promotion_count=1,
            revoked_promotion_count=1,
            maturity_summary=(
                DatasetMaturitySummary(
                    maturity="initial-focus",
                    dataset_count=2,
                    fresh_count=0,
                    stale_count=0,
                    missing_count=2,
                    not_applicable_count=0,
                    failed_count=0,
                    warning_count=0,
                    promotion_ready_count=1,
                    promotion_blocked_count=0,
                ),
                DatasetMaturitySummary(
                    maturity="experimental",
                    dataset_count=1,
                    fresh_count=1,
                    stale_count=0,
                    missing_count=0,
                    not_applicable_count=0,
                    failed_count=0,
                    warning_count=1,
                    promotion_ready_count=0,
                    promotion_blocked_count=1,
                ),
            ),
            promotion_status_counts=(
                DatasetPromotionStatusCount(status="ready", count=1),
                DatasetPromotionStatusCount(status="blocked", count=1),
                DatasetPromotionStatusCount(status="not_applicable", count=1),
            ),
            datasets=(
                SimpleNamespace(
                    dataset_id="stock_daily",
                    current_maturity="experimental",
                    catalog_freshness_status="fresh",
                    promotion_status="blocked",
                    active_maturity_promotion=False,
                    has_maturity_warning=True,
                    latest_revocation_reason="failed_revalidation",
                    latest_revoked_by="data-governance",
                    latest_revoked_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                    missing_criteria=(_RUNTIME_CRITERION,),
                    rejected_criteria=(_SOURCE_CRITERION,),
                ),
                SimpleNamespace(
                    dataset_id="macro_indicators",
                    current_maturity="initial-focus",
                    catalog_freshness_status="missing",
                    promotion_status="ready",
                    active_maturity_promotion=True,
                    has_maturity_warning=False,
                    latest_revocation_reason=None,
                    latest_revoked_by=None,
                    latest_revoked_at=None,
                    missing_criteria=(),
                    rejected_criteria=(),
                ),
            ),
        )

        response = await _call_maturity_governance_report(
            mock_facade,
            dataset_ids=["stock_daily", "macro_indicators", "etf_daily"],
        )

        assert response.data.dataset_count == 3
        assert response.data.warning_count == 1
        assert response.data.promotable_count == 1
        assert response.data.active_promotion_count == 1
        assert response.data.revoked_promotion_count == 1
        assert response.data.maturity_summary[0].maturity == "initial-focus"
        assert response.data.promotion_status_counts[1].status == "blocked"
        stock = response.data.datasets[0]
        assert stock.dataset_id == "stock_daily"
        assert stock.current_maturity == "experimental"
        assert stock.catalog_freshness_status == "fresh"
        assert stock.promotion_status == "blocked"
        assert stock.active_maturity_promotion is False
        assert stock.has_maturity_warning is True
        assert stock.latest_revocation_reason == "failed_revalidation"
        assert stock.latest_revoked_by == "data-governance"
        assert stock.latest_revoked_at == "2026-06-02T09:30:00+00:00"
        assert stock.missing_criteria == [_RUNTIME_CRITERION]
        assert stock.rejected_criteria == [_SOURCE_CRITERION]
        mock_facade.get_maturity_governance_report.assert_called_once_with(
            ["stock_daily", "macro_indicators", "etf_daily"]
        )


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
