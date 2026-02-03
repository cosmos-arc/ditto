"""Tests for MetadataManager."""

import polars as pl
import pytest
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_foundation.config.environment import Environment
from ditto_foundation.observability import init, reset_for_testing
from ditto_foundation.observability.config import ObservabilityConfig
from ditto_foundation.util.checksum import ChecksumCompute
from ditto_port.services.ingestion.metadata import MetadataManager


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        tracing_enabled=True,
        tracing_sample_rate=1.0,
        metrics_enabled=True,
    )
    init(config, force=True)
    yield
    reset_for_testing()


@pytest.mark.unit
class TestShouldSkip:
    """测试 should_skip 方法。"""

    def test_should_not_skip_when_force_is_true(self, mocker) -> None:
        """force=True 时不跳过。"""

        mock_hub = mocker.Mock()
        manager = MetadataManager(mock_hub)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=True,
        )

        assert should_skip is False
        assert reason is None

    def test_should_not_skip_when_no_history(self, mocker) -> None:
        """无历史记录时不跳过。"""

        mock_hub = mocker.Mock()
        # Mock get_log 返回 None（无历史记录）
        mock_hub.ingestion_log.get_log.return_value = None
        manager = MetadataManager(mock_hub)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None
        mock_hub.ingestion_log.get_log.assert_called_once()

    def test_should_skip_when_previous_success(self, mocker) -> None:
        """历史成功时跳过。"""

        mock_hub = mocker.Mock()
        # Mock get_log 返回成功的历史记录
        mock_hub.ingestion_log.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        manager = MetadataManager(mock_hub)

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

        mock_hub = mocker.Mock()
        # Mock get_log 返回失败的历史记录
        mock_hub.ingestion_log.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
        )
        manager = MetadataManager(mock_hub)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is False
        assert reason is None

    def test_should_not_skip_when_log_store_not_set(self, mocker) -> None:
        """hub 始终需要提供，不再支持 log_store=None 的情况。"""

        mock_hub = mocker.Mock()
        manager = MetadataManager(mock_hub)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        # hub.ingestion_log.get_log 默认返回 None（无历史记录）
        assert should_skip is False
        assert reason is None

    def test_should_skip_uses_source_parameter(self, mocker) -> None:
        """should_skip 应使用传入的 source 参数，而非硬编码。"""
        mock_hub = mocker.Mock()

        # Mock get_log 返回成功的历史记录
        mock_hub.ingestion_log.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="akshare",  # 不同的数据源
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        manager = MetadataManager(mock_hub)

        # 使用 akshare 数据源
        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            source="akshare",
            force=False,
        )

        # 验证 get_log 被调用时使用了正确的 source
        mock_hub.ingestion_log.get_log.assert_called_once_with(
            dataset="stock_daily",
            source="akshare",  # 应该是 akshare 而不是硬编码的 tushare
            trade_date="2024-12-27",
        )

        assert should_skip is True
        assert reason is not None


@pytest.mark.unit
class TestCompareData:
    """测试 compare_data 方法。"""

    def test_compare_returns_true_when_data_same(self, mocker) -> None:
        """相同数据返回 True。"""

        mock_hub = mocker.Mock()
        manager = MetadataManager(mock_hub)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df, "stock_daily")

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

    def test_compare_returns_false_when_data_different(self, mocker) -> None:
        """不同数据返回 False。"""

        mock_hub = mocker.Mock()
        manager = MetadataManager(mock_hub)

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

    def test_compare_returns_false_when_row_count_different(self, mocker) -> None:
        """行数不同返回 False。"""

        mock_hub = mocker.Mock()
        manager = MetadataManager(mock_hub)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df, "stock_daily")

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

    def test_compare_handles_null_checksum_in_log(self, mocker) -> None:
        """处理 log 中 checksum 为 None 的情况。"""

        mock_hub = mocker.Mock()
        manager = MetadataManager(mock_hub)

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

    def test_compare_returns_true_when_rows_is_none(self, mocker) -> None:
        """当 existing_log.rows 为 None 时，仅比较 checksum。"""
        mock_hub = mocker.Mock()
        manager = MetadataManager(mock_hub)

        df = pl.DataFrame(
            {
                "code": ["000001", "000002"],
                "close": [10.5, 20.3],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df, "stock_daily")

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
class TestShouldSkipEdgeCases:
    """测试 should_skip 方法的边界情况。"""

    def test_skip_reason_contains_checksum_and_rows(self, mocker) -> None:
        """跳过原因应包含 checksum 和 rows 信息。"""
        mock_hub = mocker.Mock()

        # Mock get_log 返回成功的历史记录
        mock_hub.ingestion_log.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abcdef1234567890",
            rows=1000,
        )
        manager = MetadataManager(mock_hub)

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
        mock_hub = mocker.Mock()

        # Mock get_log 返回成功但无 checksum 的历史记录
        mock_hub.ingestion_log.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum=None,
            rows=1000,
        )
        manager = MetadataManager(mock_hub)

        should_skip, reason = manager.should_skip(
            dataset="stock_daily",
            trade_date="2024-12-27",
            force=False,
        )

        assert should_skip is True
        assert reason is not None
        assert "N/A" in reason  # checksum 为 None 时显示 N/A
