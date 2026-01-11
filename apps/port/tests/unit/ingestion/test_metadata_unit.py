"""Tests for MetadataManager."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.sources.metadata import IngestionLog, IngestionStatus
from ditto_foundation.observability import Mode, init, reset_for_testing
from ditto_port.services.ingestion.metadata import (
    MetadataManager,
    _json_serializable,
)


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)
    yield
    reset_for_testing()


@pytest.mark.unit
class TestComputeChecksum:
    """测试 compute_checksum 方法。"""

    def test_same_data_produces_same_checksum(self) -> None:
        """相同数据应产生相同 checksum。"""

        manager = MetadataManager()

        # 创建相同的数据
        df1 = pl.DataFrame(
            {
                "code": ["000001", "000002", "000003"],
                "close": [10.5, 20.3, 15.8],
                "volume": [1000, 2000, 1500],
            }
        )

        df2 = pl.DataFrame(
            {
                "code": ["000001", "000002", "000003"],
                "close": [10.5, 20.3, 15.8],
                "volume": [1000, 2000, 1500],
            }
        )

        checksum1 = manager.compute_checksum(df1)
        checksum2 = manager.compute_checksum(df2)

        assert checksum1 == checksum2

    def test_different_data_produces_different_checksum(self) -> None:
        """不同数据应产生不同 checksum。"""

        manager = MetadataManager()

        df1 = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        df2 = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.6, 20.3],  # 不同的值
            }
        )

        checksum1 = manager.compute_checksum(df1)
        checksum2 = manager.compute_checksum(df2)

        assert checksum1 != checksum2

    def test_empty_dataframe_produces_valid_checksum(self) -> None:
        """空数据框应产生有效 checksum。"""

        manager = MetadataManager()

        df = pl.DataFrame()

        checksum = manager.compute_checksum(df)

        assert checksum is not None
        assert isinstance(checksum, str)
        assert len(checksum) > 0

    def test_checksum_is_deterministic(self) -> None:
        """checksum 应该是确定性的。"""

        manager = MetadataManager()

        df = pl.DataFrame(
            {
                "code": ["000001", "000002", "000003"],
                "close": [10.5, 20.3, 15.8],
                "volume": [1000, 2000, 1500],
            }
        )

        # 多次计算应得到相同结果
        checksums = [manager.compute_checksum(df) for _ in range(5)]

        assert all(c == checksums[0] for c in checksums)

    def test_checksum_considers_row_order(self) -> None:
        """checksum 应考虑行顺序。"""

        manager = MetadataManager()

        df1 = pl.DataFrame(
            {
                "code": ["000001", "000002", "000003"],
                "close": [10.5, 20.3, 15.8],
            }
        )

        df2 = pl.DataFrame(
            {
                "code": ["000003", "000001", "000002"],  # 不同顺序
                "close": [15.8, 10.5, 20.3],
            }
        )

        checksum1 = manager.compute_checksum(df1)
        checksum2 = manager.compute_checksum(df2)

        # 行顺序不同，checksum 应不同
        assert checksum1 != checksum2


@pytest.mark.unit
class TestShouldSkip:
    """测试 should_skip 方法。"""

    def test_should_not_skip_when_force_is_true(self, mocker) -> None:
        """force=True 时不跳过。"""

        manager = MetadataManager()
        manager._log_store = mocker.Mock()

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=True,
        )

        assert should_skip is False
        assert reason is None

    def test_should_not_skip_when_no_history(self, mocker) -> None:
        """无历史记录时不跳过。"""

        manager = MetadataManager()

        # Mock get_log 返回 None（无历史记录）
        mock_store = mocker.Mock()
        mock_store.get_log.return_value = None
        manager._log_store = mock_store

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None
        mock_store.get_log.assert_called_once()

    def test_should_skip_when_previous_success(self, mocker) -> None:
        """历史成功时跳过。"""

        manager = MetadataManager()

        # Mock get_log 返回成功的历史记录
        mock_store = mocker.Mock()
        mock_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        manager._log_store = mock_store

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is True
        assert reason is not None
        assert "成功" in reason or "SUCCESS" in reason

    def test_should_not_skip_when_previous_failed(self, mocker) -> None:
        """历史失败时不跳过。"""

        manager = MetadataManager()

        # Mock get_log 返回失败的历史记录
        mock_store = mocker.Mock()
        mock_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
        )
        manager._log_store = mock_store

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None

    def test_should_not_skip_when_log_store_not_set(self) -> None:
        """log_store 未设置时不跳过。"""

        manager = MetadataManager(log_store=None)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None

    def test_should_skip_uses_source_parameter(self, mocker) -> None:
        """should_skip 应使用传入的 source 参数，而非硬编码。"""
        manager = MetadataManager()

        # Mock get_log 返回成功的历史记录
        mock_store = mocker.Mock()
        mock_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="akshare",  # 不同的数据源
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        manager._log_store = mock_store

        # 使用 akshare 数据源
        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            source="akshare",
            force=False,
        )

        # 验证 get_log 被调用时使用了正确的 source
        mock_store.get_log.assert_called_once_with(
            dataset="stock_daily",
            source="akshare",  # 应该是 akshare 而不是硬编码的 tushare
            trade_date="2024-12-27",
        )

        assert should_skip is True
        assert reason is not None


@pytest.mark.unit
class TestCompareData:
    """测试 compare_data 方法。"""

    def test_compare_returns_true_when_data_same(self) -> None:
        """相同数据返回 True。"""

        manager = MetadataManager()

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = manager.compute_checksum(df)

        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=2,
        )

        result = manager.compare_data(df, existing_log)

        assert result is True

    def test_compare_returns_false_when_data_different(self) -> None:
        """不同数据返回 False。"""

        manager = MetadataManager()

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        # 不同的 checksum
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="different_checksum",
            rows=2,
        )

        result = manager.compare_data(df, existing_log)

        assert result is False

    def test_compare_returns_false_when_row_count_different(self) -> None:
        """行数不同返回 False。"""

        manager = MetadataManager()

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = manager.compute_checksum(df)

        # 行数不匹配
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=999,  # 不匹配
        )

        result = manager.compare_data(df, existing_log)

        assert result is False

    def test_compare_handles_null_checksum_in_log(self) -> None:
        """处理 log 中 checksum 为 None 的情况。"""

        manager = MetadataManager()

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        # checksum 为 None（失败的记录）
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            checksum=None,
            error_code="ERROR",
            error_message="Some error",
        )

        result = manager.compare_data(df, existing_log)

        assert result is False

    def test_compare_returns_true_when_rows_is_none(self) -> None:
        """当 existing_log.rows 为 None 时，仅比较 checksum。"""
        manager = MetadataManager()

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = manager.compute_checksum(df)

        # rows 为 None（老数据可能没有记录行数）
        existing_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=checksum,
            rows=None,  # 行数为 None
        )

        result = manager.compare_data(df, existing_log)

        # checksum 相同，rows 为 None 时不比较行数，应返回 True
        assert result is True


@pytest.mark.unit
class TestJsonSerializable:
    """测试 _json_serializable 辅助函数。"""

    def test_json_serializable_with_date(self) -> None:
        """date 类型应转换为 ISO 格式字符串。"""

        test_date = date(2024, 12, 27)
        result = _json_serializable(test_date)

        assert result == "2024-12-27"

    def test_json_serializable_with_unsupported_type(self) -> None:
        """不支持的类型应抛出 TypeError。"""

        # 使用一个不支持的自定义类
        class CustomClass:
            pass

        with pytest.raises(TypeError, match=r"Type .* not serializable"):
            _json_serializable(CustomClass())


@pytest.mark.unit
class TestShouldSkipEdgeCases:
    """测试 should_skip 方法的边界情况。"""

    def test_skip_reason_contains_checksum_and_rows(self, mocker) -> None:
        """跳过原因应包含 checksum 和 rows 信息。"""
        manager = MetadataManager()

        # Mock get_log 返回成功的历史记录
        mock_store = mocker.Mock()
        mock_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abcdef1234567890",
            rows=1000,
        )
        manager._log_store = mock_store

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is True
        assert reason is not None
        assert "2024-12-27" in reason
        assert "abcdef12" in reason  # checksum 前 8 个字符
        assert "1000" in reason  # 行数

    def test_skip_reason_handles_missing_checksum(self, mocker) -> None:
        """跳过原因应处理 checksum 为 None 的情况。"""
        manager = MetadataManager()

        # Mock get_log 返回成功但无 checksum 的历史记录
        mock_store = mocker.Mock()
        mock_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=None,
            rows=1000,
        )
        manager._log_store = mock_store

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is True
        assert reason is not None
        assert "N/A" in reason  # checksum 为 None 时显示 N/A
