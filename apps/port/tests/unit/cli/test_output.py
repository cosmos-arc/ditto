"""输出格式化工具单元测试."""

import pytest
from ditto_port.cli.utils.output import (
    print_backfill_summary,
    print_ingestion_result,
)


@pytest.mark.unit
def test_print_ingestion_result_success(capsys):
    """测试成功结果输出"""
    result = {
        "dataset": "stock_daily",
        "trade_date": "2024-01-02",
        "status": "success",
        "row_count": 5000,
        "message": "数据摄取成功",
        "error": None,
    }
    print_ingestion_result(result, verbose=False)
    captured = capsys.readouterr()
    assert "success" in captured.out
    assert "5000" in captured.out
    assert "stock_daily" in captured.out


@pytest.mark.unit
def test_print_ingestion_result_skipped(capsys):
    """测试跳过结果输出"""
    result = {
        "dataset": "stock_daily",
        "trade_date": "2024-01-02",
        "status": "skipped",
        "row_count": None,
        "message": "数据已存在",
        "error": None,
    }
    print_ingestion_result(result, verbose=False)
    captured = capsys.readouterr()
    assert "skipped" in captured.out
    # verbose=False 时不打印 message
    assert "数据已存在" not in captured.out

    # 测试 verbose=True 时显示 message
    print_ingestion_result(result, verbose=True)
    captured = capsys.readouterr()
    assert "数据已存在" in captured.out


@pytest.mark.unit
def test_print_ingestion_result_failed(capsys):
    """测试失败结果输出"""
    result = {
        "dataset": "stock_daily",
        "trade_date": "2024-01-02",
        "status": "failed",
        "row_count": None,
        "message": "获取数据失败",
        "error": "FETCH_ERROR",
    }
    print_ingestion_result(result, verbose=False)
    captured = capsys.readouterr()
    assert "failed" in captured.out
    assert "FETCH_ERROR" in captured.out


@pytest.mark.unit
def test_print_ingestion_result_verbose(capsys):
    """测试详细输出模式"""
    result = {
        "dataset": "stock_daily",
        "trade_date": "2024-01-02",
        "status": "success",
        "row_count": 5000,
        "message": "数据摄取成功",
        "error": None,
    }
    print_ingestion_result(result, verbose=True)
    captured = capsys.readouterr()
    assert "数据摄取成功" in captured.out


@pytest.mark.unit
def test_print_backfill_summary(capsys):
    """测试回补摘要输出"""
    result = {
        "dataset": "stock_daily",
        "total_dates": 10,
        "success_count": 8,
        "skipped_count": 1,
        "failed_count": 1,
    }
    print_backfill_summary(result)
    captured = capsys.readouterr()
    assert "10" in captured.out
    assert "8" in captured.out
    assert "1" in captured.out


@pytest.mark.unit
def test_print_backfill_summary_with_failures(capsys):
    """测试带失败的回补摘要"""
    result = {
        "dataset": "stock_daily",
        "total_dates": 10,
        "success_count": 5,
        "skipped_count": 0,
        "failed_count": 5,
    }
    print_backfill_summary(result)
    captured = capsys.readouterr()
    assert "5" in captured.out
    # 失败数应该被突出显示
    assert "失败" in captured.out
