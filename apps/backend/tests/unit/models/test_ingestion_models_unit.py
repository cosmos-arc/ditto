"""Ingestion 状态 API 模型单元测试."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


@pytest.mark.unit
class TestDatasetStatusResponse:
    """测试 DatasetStatusResponse 模型."""

    def test_full_model(self) -> None:
        """完整字段创建."""
        from ditto_apps.models.ingestion import DatasetStatusResponse

        m = DatasetStatusResponse(
            dataset="stock_daily",
            latest_date="2024-01-15",
            latest_status="success",
            dataset_maturity="experimental",
            dataset_maturity_warning="experimental data requires research opt-in",
            record_count=5000,
            last_attempt="2024-01-15T18:05:00",
            catalog_freshness_at="2026-06-01T10:01:00+00:00",
            catalog_storage_uri="stock_daily/2026",
            catalog_schema_hash="schema:stock_daily:v1",
            catalog_row_count=17,
            catalog_freshness_status="fresh",
            catalog_freshness_sla_hours=36,
        )
        assert m.dataset == "stock_daily"
        assert m.latest_date == "2024-01-15"
        assert m.latest_status == "success"
        assert m.dataset_maturity == "experimental"
        assert m.dataset_maturity_warning == (
            "experimental data requires research opt-in"
        )
        assert m.record_count == 5000
        assert m.last_attempt == "2024-01-15T18:05:00"
        assert m.catalog_freshness_at == "2026-06-01T10:01:00+00:00"
        assert m.catalog_storage_uri == "stock_daily/2026"
        assert m.catalog_schema_hash == "schema:stock_daily:v1"
        assert m.catalog_row_count == 17
        assert m.catalog_freshness_status == "fresh"
        assert m.catalog_freshness_sla_hours == 36

    def test_defaults(self) -> None:
        """默认值验证."""
        from ditto_apps.models.ingestion import DatasetStatusResponse

        m = DatasetStatusResponse(dataset="etf_daily")
        assert m.latest_date is None
        assert m.latest_status is None
        assert m.record_count == 0
        assert m.last_attempt is None
        assert m.catalog_freshness_at is None
        assert m.catalog_storage_uri is None
        assert m.catalog_schema_hash is None
        assert m.catalog_row_count is None
        assert m.catalog_freshness_status is None
        assert m.catalog_freshness_sla_hours is None
        assert m.dataset_maturity_warning is None

    def test_model_dump(self) -> None:
        """序列化输出."""
        from ditto_apps.models.ingestion import DatasetStatusResponse

        m = DatasetStatusResponse(
            dataset="stock_daily",
            latest_date="2024-01-15",
            latest_status="success",
            record_count=100,
            dataset_maturity="experimental",
            dataset_maturity_warning="experimental data requires research opt-in",
            catalog_freshness_at="2026-06-01T10:01:00+00:00",
            catalog_freshness_status="fresh",
        )
        d = m.model_dump()
        assert d["dataset"] == "stock_daily"
        assert d["record_count"] == 100
        assert d["dataset_maturity"] == "experimental"
        assert d["dataset_maturity_warning"] == (
            "experimental data requires research opt-in"
        )
        assert d["catalog_freshness_at"] == "2026-06-01T10:01:00+00:00"
        assert d["catalog_freshness_status"] == "fresh"

    def test_strict_mode_rejects_wrong_type(self) -> None:
        """strict 模式拒绝类型错误."""
        from ditto_apps.models.ingestion import DatasetStatusResponse

        with pytest.raises(ValidationError):
            DatasetStatusResponse(dataset=123)  # type: ignore[arg-type]


@pytest.mark.unit
class TestIngestionStatusResponse:
    """测试 IngestionStatusResponse 模型."""

    def test_with_maturity_summary(self) -> None:
        """包含 maturity-aware 摘要."""
        from ditto_apps.models.ingestion import (
            DatasetMaturitySummaryResponse,
            IngestionStatusResponse,
        )

        resp = IngestionStatusResponse(
            datasets=[],
            maturity_summary=[
                DatasetMaturitySummaryResponse(
                    maturity="initial-focus",
                    dataset_count=2,
                    fresh_count=1,
                    stale_count=0,
                    missing_count=1,
                    not_applicable_count=0,
                    failed_count=1,
                    warning_count=1,
                )
            ],
        )

        assert resp.maturity_summary[0].maturity == "initial-focus"
        assert resp.maturity_summary[0].dataset_count == 2
        assert resp.maturity_summary[0].missing_count == 1
        assert resp.maturity_summary[0].warning_count == 1

    def test_with_datasets(self) -> None:
        """包含数据集列表."""
        from ditto_apps.models.ingestion import (
            DatasetStatusResponse,
            IngestionStatusResponse,
        )

        resp = IngestionStatusResponse(
            datasets=[
                DatasetStatusResponse(
                    dataset="stock_daily",
                    latest_date="2024-01-15",
                    latest_status="success",
                ),
            ]
        )
        assert len(resp.datasets) == 1
        assert resp.datasets[0].dataset == "stock_daily"
        assert resp.maturity_summary == []

    def test_empty_datasets(self) -> None:
        """空数据集列表."""
        from ditto_apps.models.ingestion import IngestionStatusResponse

        resp = IngestionStatusResponse(datasets=[])
        assert resp.datasets == []


@pytest.mark.unit
class TestIngestionHistoryItem:
    """测试 IngestionHistoryItem 模型."""

    def test_success_item(self) -> None:
        """成功摄取记录."""
        from ditto_apps.models.ingestion import IngestionHistoryItem

        item = IngestionHistoryItem(
            dataset="stock_daily",
            trade_date="2024-01-15",
            status="success",
            rows=5000,
            attempts=1,
            last_attempt_at="2024-01-15T18:05:00",
        )
        assert item.status == "success"
        assert item.rows == 5000
        assert item.error_message is None

    def test_failed_item(self) -> None:
        """失败摄取记录."""
        from ditto_apps.models.ingestion import IngestionHistoryItem

        item = IngestionHistoryItem(
            dataset="stock_daily",
            trade_date="2024-01-14",
            status="failed",
            rows=None,
            error_message="Connection timeout",
            attempts=3,
            last_attempt_at="2024-01-14T18:10:00",
        )
        assert item.status == "failed"
        assert item.error_message == "Connection timeout"
        assert item.rows is None
        assert item.attempts == 3

    def test_defaults(self) -> None:
        """默认值."""
        from ditto_apps.models.ingestion import IngestionHistoryItem

        item = IngestionHistoryItem(
            dataset="etf_daily",
            trade_date="2024-01-15",
            status="success",
        )
        assert item.rows is None
        assert item.error_message is None
        assert item.attempts == 1
        assert item.last_attempt_at is None


@pytest.mark.unit
class TestDQDatasetSummary:
    """测试 DQDatasetSummary 模型."""

    def test_full_model(self) -> None:
        """完整字段."""
        from ditto_apps.models.ingestion import DQDatasetSummary

        s = DQDatasetSummary(
            dataset="stock_daily",
            total_checks=100,
            passed=95,
            warnings=3,
            errors=2,
        )
        assert s.dataset == "stock_daily"
        assert s.total_checks == 100
        assert s.passed == 95
        assert s.warnings == 3
        assert s.errors == 2

    def test_defaults(self) -> None:
        """默认值."""
        from ditto_apps.models.ingestion import DQDatasetSummary

        s = DQDatasetSummary(dataset="etf_daily")
        assert s.total_checks == 0
        assert s.passed == 0
        assert s.warnings == 0
        assert s.errors == 0


@pytest.mark.unit
class TestDQSummaryResponse:
    """测试 DQSummaryResponse 模型."""

    def test_with_summaries(self) -> None:
        """包含数据集摘要列表."""
        from ditto_apps.models.ingestion import (
            DQDatasetSummary,
            DQSummaryResponse,
        )

        resp = DQSummaryResponse(
            datasets=[
                DQDatasetSummary(
                    dataset="stock_daily",
                    total_checks=50,
                    passed=48,
                    warnings=1,
                    errors=1,
                ),
            ]
        )
        assert len(resp.datasets) == 1
        assert resp.datasets[0].total_checks == 50

    def test_empty_datasets(self) -> None:
        """空列表（V1 占位）."""
        from ditto_apps.models.ingestion import DQSummaryResponse

        resp = DQSummaryResponse(datasets=[])
        assert resp.datasets == []
