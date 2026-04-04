"""共享类型单元测试。"""

from dataclasses import FrozenInstanceError

import pytest
from ditto_data.models.ingestion import IngestionResult, ResultCounts


@pytest.mark.unit
def test_ingestion_result_creation() -> None:
    """测试 IngestionResult 创建。"""
    result = IngestionResult(
        dataset="stock_daily",
        trade_date="2024-01-01",
        status="success",
    )
    assert result.dataset == "stock_daily"
    assert result.trade_date == "2024-01-01"
    assert result.status == "success"
    assert result.row_count is None
    assert result.checksum is None
    assert result.message == ""
    assert result.error is None


@pytest.mark.unit
def test_ingestion_result_with_all_fields() -> None:
    """测试 IngestionResult 带所有字段。"""
    result = IngestionResult(
        dataset="stock_daily",
        trade_date="2024-01-01",
        status="success",
        row_count=1000,
        checksum="abc123",
        message="数据摄取成功",
    )
    assert result.row_count == 1000
    assert result.checksum == "abc123"
    assert result.message == "数据摄取成功"


@pytest.mark.unit
def test_ingestion_result_frozen() -> None:
    """测试 IngestionResult 不可变。"""
    result = IngestionResult(
        dataset="x",
        trade_date="y",
        status="success",
    )
    with pytest.raises(FrozenInstanceError):
        result.status = "failed"  # type: ignore[misc]


@pytest.mark.unit
def test_ingestion_result_failed() -> None:
    """测试 IngestionResult 失败状态。"""
    result = IngestionResult(
        dataset="stock_daily",
        trade_date="2024-01-01",
        status="failed",
        error="FETCH_ERROR",
        message="获取数据失败",
    )
    assert result.status == "failed"
    assert result.error == "FETCH_ERROR"


@pytest.mark.unit
def test_ingestion_result_skipped() -> None:
    """测试 IngestionResult 跳过状态。"""
    result = IngestionResult(
        dataset="stock_daily",
        trade_date="2024-01-01",
        status="skipped",
        message="数据已存在",
    )
    assert result.status == "skipped"


@pytest.mark.unit
def test_result_counts_creation() -> None:
    """测试 ResultCounts 创建。"""
    counts = ResultCounts(success=10, failed=2, skipped=1)
    assert counts.success == 10
    assert counts.failed == 2
    assert counts.skipped == 1


@pytest.mark.unit
def test_result_counts_frozen() -> None:
    """测试 ResultCounts 不可变。"""
    counts = ResultCounts(success=10, failed=2, skipped=1)
    with pytest.raises(FrozenInstanceError):
        counts.success = 20  # type: ignore[misc]
