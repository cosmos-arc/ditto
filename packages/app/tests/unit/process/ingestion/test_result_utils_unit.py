"""测试结果统计辅助函数。"""

import pytest
from ditto_app.process.ingestion.result_handler import count_results
from ditto_data.models.ingestion import IngestionResult


@pytest.mark.unit
class TestCountResultsWithIngestionResultList:
    """测试 count_results 函数处理 IngestionResult 列表。"""

    def test_count_all_success(self) -> None:
        """测试全部成功的情况。"""
        results = [
            IngestionResult(
                dataset="stock_daily", trade_date="2024-01-01", status="success"
            ),
            IngestionResult(
                dataset="stock_daily", trade_date="2024-01-02", status="success"
            ),
            IngestionResult(
                dataset="stock_daily", trade_date="2024-01-03", status="success"
            ),
        ]

        counts = count_results(results)

        assert counts.success == 3
        assert counts.failed == 0
        assert counts.skipped == 0

    def test_count_all_failed(self) -> None:
        """测试全部失败的情况。"""
        results = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-01",
                status="failed",
                error="FETCH_ERROR",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-02",
                status="failed",
                error="EMPTY_DATA",
            ),
        ]

        counts = count_results(results)

        assert counts.success == 0
        assert counts.failed == 2
        assert counts.skipped == 0

    def test_count_all_skipped(self) -> None:
        """测试全部跳过的情况。"""
        results = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-01",
                status="skipped",
                message="非交易日",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-02",
                status="skipped",
                message="数据已存在",
            ),
        ]

        counts = count_results(results)

        assert counts.success == 0
        assert counts.failed == 0
        assert counts.skipped == 2

    def test_count_mixed_results(self) -> None:
        """测试混合结果的情况。"""
        results = [
            IngestionResult(
                dataset="stock_daily", trade_date="2024-01-01", status="success"
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-02",
                status="skipped",
                message="非交易日",
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-03",
                status="failed",
                error="FETCH_ERROR",
            ),
            IngestionResult(
                dataset="stock_daily", trade_date="2024-01-04", status="success"
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-05",
                status="skipped",
                message="数据已存在",
            ),
        ]

        counts = count_results(results)

        assert counts.success == 2
        assert counts.failed == 1
        assert counts.skipped == 2

    def test_count_empty_list(self) -> None:
        """测试空列表的情况。"""
        results: list[IngestionResult] = []

        counts = count_results(results)

        assert counts.success == 0
        assert counts.failed == 0
        assert counts.skipped == 0


@pytest.mark.unit
class TestCountResultsWithDict:
    """测试 count_results 函数处理字典结果。"""

    def test_count_dict_mixed_results(self) -> None:
        """测试字典类型的混合结果。"""
        results = {
            "task1": {"status": "success", "dataset": "stock_daily"},
            "task2": {
                "status": "failed",
                "dataset": "etf_daily",
                "error": "FETCH_ERROR",
            },
            "task3": {
                "status": "skipped",
                "dataset": "stock_daily",
                "message": "非交易日",
            },
            "task4": {"status": "success", "dataset": "adj_factor"},
        }

        counts = count_results(results)

        assert counts.success == 2
        assert counts.failed == 1
        assert counts.skipped == 1

    def test_count_dict_empty(self) -> None:
        """测试空字典的情况。"""
        results: dict[str, dict[str, object]] = {}

        counts = count_results(results)

        assert counts.success == 0
        assert counts.failed == 0
        assert counts.skipped == 0


@pytest.mark.unit
class TestCountResultsEdgeCases:
    """测试边界情况。"""

    def test_count_with_none_values(self) -> None:
        """测试包含 None 值的情况。"""
        results = [
            IngestionResult(
                dataset="stock_daily", trade_date="2024-01-01", status="success"
            ),
            None,  # type: ignore
            IngestionResult(
                dataset="stock_daily",
                trade_date="2024-01-02",
                status="failed",
                error="FETCH_ERROR",
            ),
        ]

        # 应该跳过 None 值
        counts = count_results(results)

        assert counts.success == 1
        assert counts.failed == 1
        assert counts.skipped == 0

    def test_count_dict_with_missing_status(self) -> None:
        """测试字典中缺少 status 字段的情况。"""
        results = {
            "task1": {"status": "success"},
            "task2": {"dataset": "stock_daily"},  # 缺少 status
            "task3": {"status": "failed"},
        }

        # 缺少 status 的应该被忽略
        counts = count_results(results)

        assert counts.success == 1
        assert counts.failed == 1
        assert counts.skipped == 0

    def test_count_dict_with_invalid_status(self) -> None:
        """测试字典中包含无效 status 值的情况。"""
        results = {
            "task1": {"status": "success"},
            "task2": {"status": "invalid"},  # 无效状态
            "task3": {"status": "failed"},
        }

        # 无效状态应该被忽略
        counts = count_results(results)

        assert counts.success == 1
        assert counts.failed == 1
        assert counts.skipped == 0
