"""Tests for IngestionCoordinator."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.models.storage import WriteResult
from ditto_datahub.sources.base import DataSource, SourceFetchError
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_foundation.observability import init, reset_for_testing
from ditto_port.services.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionResult,
)


def mock_hub_bars_write(file_path: str, checksum: str) -> WriteResult:
    """创建 Mock hub.bars.write() 的返回值。"""
    return WriteResult(
        file_path=file_path,
        checksum=checksum,
        rows_written=0,
        rows_total=0,
        blocked=False,
    )


def mock_hub_adj_factor_write(file_path: str, checksum: str) -> WriteResult:
    """创建 Mock hub.adj_factor.write() 的返回值。"""
    return WriteResult(
        file_path=file_path,
        checksum=checksum,
        rows_written=0,
        rows_total=0,
        blocked=False,
    )


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    init(
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        force=True,
    )
    yield
    reset_for_testing()


@pytest.fixture
def mock_hub(mocker):
    """创建 Mock DataHub。"""
    hub = mocker.Mock()
    hub.ingestion_log = mocker.Mock(spec=IngestionLogStore)

    # 添加 SidAllocator mock
    mock_sid_allocator = mocker.Mock()
    stock_counter = [1_000_000]
    etf_counter = [2_000_000]

    def allocate_side_effect(asset_class: str) -> int:
        if asset_class == "stock":
            sid = stock_counter[0]
            stock_counter[0] += 1
            return sid
        elif asset_class == "etf":
            sid = etf_counter[0]
            etf_counter[0] += 1
            return sid
        else:
            raise ValueError(f"Unknown asset class: {asset_class}")

    mock_sid_allocator.allocate.side_effect = allocate_side_effect
    hub.sid_allocator = mock_sid_allocator

    # 添加 SecurityStore mock（SecurityMapper 需要）
    hub.security_store = mocker.Mock()
    hub.security_store.resolve_sid.return_value = None  # 默认返回 None（不存在）
    hub.security_store.register.return_value = 1000001  # 返回注册的 SID

    # 添加 SecuritiesAccessor mock
    # (Coordinator._write_stock_basic/_write_etf_basic 需要)
    hub.securities = mocker.Mock()

    def register_batch_side_effect(df, source, asset_class, **kwargs):
        """根据 asset_class 返回不同的 file_path。"""
        file_path = f"security_store:{asset_class}_basic"
        checksum = f"checksum_{asset_class}"
        return (file_path, checksum)

    hub.securities.register_batch.side_effect = register_batch_side_effect

    # 添加 enrich_dataframe_with_sid mock
    # 方法签名: enrich_dataframe_with_sid(df, source, asset_class, src_code_col)
    def enrich_dataframe_with_sid_side_effect(df, source, asset_class, src_code_col):
        """根据 asset_class 返回不同的 sid。"""
        if asset_class == "stock":
            sid = stock_counter[0]
            stock_counter[0] += 1
        elif asset_class == "etf":
            sid = etf_counter[0]
            etf_counter[0] += 1
        else:
            raise ValueError(f"Unknown asset class: {asset_class}")
        return df.with_columns(
            pl.lit(sid).alias("sid"),
            pl.lit(source).alias("source"),
        )

    hub.securities.enrich_dataframe_with_sid = mocker.Mock(
        side_effect=enrich_dataframe_with_sid_side_effect
    )

    return hub


@pytest.fixture
def mock_source(mocker):
    """创建 Mock DataSource。"""
    source = mocker.Mock(spec=DataSource)
    return source


@pytest.fixture
def coordinator(mock_hub, mock_source):
    """创建 IngestionCoordinator 实例。"""
    return IngestionCoordinator(mock_hub, mock_source, "tushare")


@pytest.mark.unit
class TestIngestionResult:
    """测试 IngestionResult 类。"""

    def test_create_success_result(self) -> None:
        """创建成功结果。"""
        result = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-27",
            status="success",
            row_count=1000,
            checksum="abc123",
            message="数据摄取成功",
        )

        assert result.dataset == "stock_daily"
        assert result.trade_date == "2024-12-27"
        assert result.status == "success"
        assert result.row_count == 1000
        assert result.checksum == "abc123"
        assert result.message == "数据摄取成功"
        assert result.error is None

    def test_create_skipped_result(self) -> None:
        """创建跳过结果。"""
        result = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-27",
            status="skipped",
            message="数据已存在",
        )

        assert result.status == "skipped"
        assert result.row_count is None
        assert result.checksum is None

    def test_create_failed_result(self) -> None:
        """创建失败结果。"""
        result = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-27",
            status="failed",
            error="FETCH_ERROR",
            message="获取数据失败",
        )

        assert result.status == "failed"
        assert result.error == "FETCH_ERROR"
        assert result.row_count is None


@pytest.mark.unit
class TestIngestDate:
    """测试 ingest_date 方法。"""

    def test_ingest_date_skipped_when_previous_success(
        self, coordinator, mock_hub, mock_source
    ) -> None:
        """历史成功时跳过摄取。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "skipped"
        assert (
            "成功" in result.message
            or "SUCCESS" in result.message
            or "已存在" in result.message
        )
        # 不应该调用 source
        mock_source.fetch_stock_daily.assert_not_called()

    def test_ingest_date_success_etf_daily(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 etf_daily 数据。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None  # 无历史记录
        source_df = pl.DataFrame(
            {
                "src_code": ["510300.SH", "510500.SH"],
                "trade_date": [date(2024, 12, 27), date(2024, 12, 27)],
                "open": [4.0, 3.5],
                "high": [4.1, 3.6],
                "low": [3.9, 3.4],
                "close": [4.05, 3.55],
                "pre_close": [4.0, 3.5],
                "volume": [1000000, 800000],
                "amount": [4050000, 2840000],
                "pct_change": [1.25, 1.43],
            }
        )
        mock_source.fetch_etf_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="etf_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("etf_daily", "2024-12-27")

        # Assert
        assert result.status == "success"
        assert result.row_count == 2
        assert result.checksum == "checksum123"
        mock_source.fetch_etf_daily.assert_called_once_with("2024-12-27")
        mock_hub.bars.write.assert_called_once()
        mock_hub.ingestion_log.save_log.assert_called_once()

    def test_ingest_date_success_stock_daily(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 stock_daily 数据。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum456",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum456",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_stock_daily.assert_called_once_with("2024-12-27")

    def test_ingest_date_success_adj_factor(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 adj_factor 数据。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_source.fetch_adj_factor.return_value = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_hub.adj_factor = mocker.Mock()
        mock_hub.adj_factor.write.return_value = mock_hub_adj_factor_write(
            "/path/to/file.parquet",
            "checksum789",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="adj_factor",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum789",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("adj_factor", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_adj_factor.assert_called_once_with("2024-12-27")
        mock_hub.adj_factor.write.assert_called_once()

    def test_ingest_date_success_calendar(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 calendar 数据（范围数据）。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_source.fetch_calendar.return_value = pl.DataFrame(
            {
                "trade_date": [date(2024, 12, 27), date(2024, 12, 30)],
                "is_open": [True, True],
            }
        )

        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.upsert.return_value = 2
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="calendar",
            source="tushare",
            trade_date="2024-12-27",  # 对于 calendar，这是范围起始日期
            status=IngestionStatus.SUCCESS,
            checksum="checksum000",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("calendar", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_calendar.assert_called_once()

    def test_ingest_date_fetch_error(self, coordinator, mock_hub, mock_source) -> None:
        """获取数据失败时返回失败结果。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None

        mock_source.fetch_stock_daily.side_effect = SourceFetchError(
            "Network error", source="tushare", dataset="stock_daily"
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "FETCH_ERROR"
        assert "Network error" in result.message

    def test_ingest_date_empty_dataframe(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """获取到空数据时返回失败结果。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_source.fetch_stock_daily.return_value = pl.DataFrame()
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="EMPTY_DATA",
            error_message="获取的数据为空",
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "EMPTY_DATA"
        assert "空" in result.message or "empty" in result.message.lower()

    def test_ingest_date_force_overwrites_previous_success(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """force=True 时覆盖历史成功记录。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="old_checksum",
            rows=1000,
        )

        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "new_checksum",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="new_checksum",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27", force=True)

        # Assert
        assert result.status == "success"
        assert result.checksum == "new_checksum"
        mock_source.fetch_stock_daily.assert_called_once()

    def test_ingest_date_unknown_error(
        self, coordinator, mock_hub, mock_source
    ) -> None:
        """测试非 SourceFetchError 异常的处理。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_source.fetch_stock_daily.side_effect = RuntimeError("Unexpected error")
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="UNKNOWN_ERROR",
            error_message="RuntimeError: Unexpected error",
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "UNKNOWN_ERROR"
        assert "Unexpected error" in result.message

    def test_ingest_date_dq_blocked(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """测试 DQ 阻断时的处理。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()

        mock_hub.bars.write.return_value = WriteResult(
            file_path="/path/to/file.parquet",
            checksum="checksum123",
            rows_written=0,
            rows_total=0,
            blocked=True,
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="DQ_BLOCKED",
            error_message="DQ L1 check failed: 10 errors",
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "DQ_BLOCKED"
        assert "DQ" in result.message or "check failed" in result.message

    def test_ingest_date_unsupported_dataset_raises_error(
        self, coordinator, mock_hub, mock_source
    ) -> None:
        """不支持的 dataset 抛出 ValueError。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="不支持的数据集"):
            coordinator.ingest_date("unsupported_dataset", "2024-12-27")


@pytest.mark.unit
class TestIngestRange:
    """测试 ingest_range 方法。"""

    def test_ingest_range_multiple_dates(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取日期范围内的多个交易日。"""
        # Arrange
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_hub.ingestion_log.get_log.return_value = None  # 无历史记录

        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range("stock_daily", "2024-12-25", "2024-12-27")

        # Assert
        assert len(results) == 3
        assert all(r.status == "success" for r in results)
        mock_hub.calendar.list_trading_days.assert_called_once_with(
            "2024-12-25", "2024-12-27"
        )
        assert mock_source.fetch_stock_daily.call_count == 3

    def test_ingest_range_with_skipped_dates(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """日期范围内有跳过的日期。"""
        # Arrange
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # 模拟第二天已经成功
        def get_log_side_effect(dataset, source, trade_date):
            if trade_date == "2024-12-26":
                return IngestionLog(
                    dataset="stock_daily",
                    source="tushare",
                    trade_date=trade_date,
                    status=IngestionStatus.SUCCESS,
                    checksum="old_checksum",
                    rows=1000,
                )
            return None

        mock_hub.ingestion_log.get_log.side_effect = get_log_side_effect

        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range("stock_daily", "2024-12-25", "2024-12-27")

        # Assert
        assert len(results) == 3
        # 第二天应该被跳过
        skipped_results = [r for r in results if r.status == "skipped"]
        assert len(skipped_results) == 1
        assert skipped_results[0].trade_date == "2024-12-26"

    def test_ingest_range_empty_range(self, coordinator, mock_hub, mocker) -> None:
        """日期范围为空时返回空列表。"""
        # Arrange
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.list_trading_days.return_value = []

        # Act
        results = coordinator.ingest_range("stock_daily", "2024-12-25", "2024-12-27")

        # Assert
        assert len(results) == 0

    def test_ingest_range_with_force(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """force=True 时跳过所有历史检查。"""
        # Arrange
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.list_trading_days.return_value = ["2024-12-27"]

        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range(
            "stock_daily", "2024-12-27", "2024-12-27", force=True
        )

        # Assert
        assert len(results) == 1
        assert results[0].status == "success"


@pytest.mark.unit
class TestWriteT0Data:
    """测试 T0 数据（stock_basic, etf_basic）写入。"""

    def test_ingest_date_success_stock_basic(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 stock_basic 数据到 security_store。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_source.fetch_stock_basic.return_value = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "600000.SH"],
                "symbol": ["000001", "600000"],
                "name": ["平安银行", "浦发银行"],
                "exchange": ["SZSE", "SSE"],
                "list_date": [date(1991, 4, 3), date(1999, 11, 10)],
            }
        )

        mock_hub.ingestion_log.save_log.return_value = mocker.Mock(
            dataset="stock_basic",
            source="tushare",
            trade_date="2024-01-03",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("stock_basic", "2024-01-03")

        # Assert
        assert result.status == "success"
        assert result.row_count == 2
        mock_source.fetch_stock_basic.assert_called_once()

    def test_ingest_date_success_etf_basic(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 etf_basic 数据到 security_store。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_source.fetch_etf_basic.return_value = pl.DataFrame(
            {
                "src_code": ["510300.SH", "159919.SZ"],
                "symbol": ["510300", "159919"],
                "name": ["沪深300ETF", "沪深300ETF"],
                "exchange": ["SSE", "SZSE"],
                "list_date": [date(2012, 7, 6), date(2019, 6, 24)],
            }
        )

        mock_hub.ingestion_log.save_log.return_value = mocker.Mock(
            dataset="etf_basic",
            source="tushare",
            trade_date="2024-01-03",
            status=IngestionStatus.SUCCESS,
            checksum="checksum456",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("etf_basic", "2024-01-03")

        # Assert
        assert result.status == "success"
        assert result.row_count == 2
        mock_source.fetch_etf_basic.assert_called_once()

    def test_write_stock_basic_calls_mapper(
        self, coordinator, mock_hub, mocker
    ) -> None:
        """验证 _write_stock_basic 调用 SecurityMapper。"""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "symbol": ["000001"],
                "name": ["平安银行"],
                "exchange": ["SZSE"],
                "list_date": [date(1991, 4, 3)],
            }
        )

        # Act
        file_path, checksum = coordinator._write_stock_basic(df, "2024-01-03")

        # Assert
        assert file_path == "security_store:stock_basic"
        assert checksum is not None

    def test_write_etf_basic_calls_mapper(self, coordinator, mock_hub, mocker) -> None:
        """验证 _write_etf_basic 调用 SecurityMapper。"""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["510300.SH"],
                "symbol": ["510300"],
                "name": ["沪深300ETF"],
                "exchange": ["SSE"],
                "list_date": [date(2012, 7, 6)],
            }
        )

        # Act
        file_path, checksum = coordinator._write_etf_basic(df, "2024-01-03")

        # Assert
        assert file_path == "security_store:etf_basic"
        assert checksum is not None


@pytest.mark.unit
class TestWriteT1Data:
    """测试 T1 数据（etf_daily, stock_daily）写入与 SID 补齐。"""

    def test_write_stock_daily_enriches_sid_and_source(
        self, coordinator, mock_hub, mocker
    ) -> None:
        """验证 stock_daily 写入前补齐 sid 和 source 字段。"""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [date(2024, 12, 27), date(2024, 12, 27)],
                "open": [10.0, 15.0],
                "high": [10.5, 15.5],
                "low": [9.8, 14.8],
                "close": [10.2, 15.3],
                "pre_close": [10.0, 15.0],
                "volume": [1000000, 800000],
                "amount": [10200000, 12240000],
                "pct_change": [2.0, 2.0],
            }
        )

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/stock_daily/2024.parquet",
            "checksum123",
        )

        # Act
        write_result = coordinator._write_data("stock_daily", df, "2024-12-27")

        # Assert
        assert write_result.file_path == "/path/to/stock_daily/2024.parquet"
        assert write_result.checksum == "checksum123"
        # 验证 enrich_dataframe_with_sid 被正确调用
        mock_hub.securities.enrich_dataframe_with_sid.assert_called_once_with(
            df,
            source="tushare",
            asset_class="stock",
            src_code_col="src_code",
        )
        # 验证 bars.write 被调用，且 DataFrame 包含 sid 和 source 列
        mock_hub.bars.write.assert_called_once()
        call_args = mock_hub.bars.write.call_args
        written_df = call_args.kwargs.get("df")
        assert written_df is not None
        assert "sid" in written_df.columns
        assert "source" in written_df.columns
        assert written_df["source"].to_list() == ["tushare", "tushare"]

    def test_write_etf_daily_enriches_sid_and_source(
        self, coordinator, mock_hub, mocker
    ) -> None:
        """验证 etf_daily 写入前补齐 sid 和 source 字段。"""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["510300.SH", "510500.SH"],
                "trade_date": [date(2024, 12, 27), date(2024, 12, 27)],
                "open": [4.0, 3.5],
                "high": [4.1, 3.6],
                "low": [3.9, 3.4],
                "close": [4.05, 3.55],
                "pre_close": [4.0, 3.5],
                "volume": [1000000, 800000],
                "amount": [4050000, 2840000],
                "pct_change": [1.25, 1.43],
            }
        )

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/etf_daily/2024.parquet",
            "checksum456",
        )

        # Act
        write_result = coordinator._write_data("etf_daily", df, "2024-12-27")

        # Assert
        assert write_result.file_path == "/path/to/etf_daily/2024.parquet"
        assert write_result.checksum == "checksum456"
        # 验证 enrich_dataframe_with_sid 被正确调用
        mock_hub.securities.enrich_dataframe_with_sid.assert_called_once_with(
            df,
            source="tushare",
            asset_class="etf",
            src_code_col="src_code",
        )
        # 验证 bars.write 被调用，且 DataFrame 包含 sid 和 source 列
        mock_hub.bars.write.assert_called_once()
        call_args = mock_hub.bars.write.call_args
        written_df = call_args.kwargs.get("df")
        assert written_df is not None
        assert "sid" in written_df.columns
        assert "source" in written_df.columns
        assert written_df["source"].to_list() == ["tushare", "tushare"]


@pytest.mark.unit
class TestForceParameter:
    """测试 force 参数语义。"""

    def test_force_false_maps_to_error_on_duplicate(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """验证 force=False 映射到 OnDuplicate.ERROR。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        coordinator.ingest_date("stock_daily", "2024-12-27", force=False)

        # Assert
        mock_hub.bars.write.assert_called_once()
        call_kwargs = mock_hub.bars.write.call_args.kwargs
        assert "on_duplicate" in call_kwargs
        assert call_kwargs["on_duplicate"] == OnDuplicate.ERROR

    def test_force_true_maps_to_keep_last_on_duplicate(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """验证 force=True 映射到 OnDuplicate.KEEP_LAST。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        coordinator.ingest_date("stock_daily", "2024-12-27", force=True)

        # Assert
        mock_hub.bars.write.assert_called_once()
        call_kwargs = mock_hub.bars.write.call_args.kwargs
        assert "on_duplicate" in call_kwargs
        assert call_kwargs["on_duplicate"] == OnDuplicate.KEEP_LAST

    def test_force_true_for_adj_factor_uses_keep_last(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """验证 force=True 对 adj_factor 数据集也传递正确的 on_duplicate。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_source.fetch_adj_factor.return_value = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_hub.adj_factor = mocker.Mock()
        mock_hub.adj_factor.write.return_value = mock_hub_adj_factor_write(
            "/path/to/file.parquet",
            "checksum789",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="adj_factor",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum789",
            rows=1,
        )

        # Act
        coordinator.ingest_date("adj_factor", "2024-12-27", force=True)

        # Assert
        mock_hub.adj_factor.write.assert_called_once()
        call_kwargs = mock_hub.adj_factor.write.call_args.kwargs
        assert "on_duplicate" in call_kwargs
        assert call_kwargs["on_duplicate"] == OnDuplicate.KEEP_LAST


@pytest.mark.unit
class TestFetchDataEdgeCases:
    """测试 _fetch_data 方法的边界情况。"""

    def test_fetch_data_raises_value_error_for_unsupported_dataset(
        self, coordinator, mock_source
    ) -> None:
        """验证 _fetch_data 对不支持的数据集抛出 ValueError。"""
        # Arrange
        # 使用不在 _DATASET_METHODS 中的数据集
        unsupported_dataset = "unsupported_dataset"

        # Act & Assert
        with pytest.raises(ValueError, match="不支持的数据集"):
            coordinator._fetch_data(unsupported_dataset, "2024-12-27")

        # 验证没有调用 source 的任何方法
        mock_source.fetch_stock_daily.assert_not_called()
        mock_source.fetch_etf_daily.assert_not_called()


@pytest.mark.unit
class TestWriteDataEdgeCases:
    """测试 _write_data 方法的边界情况。"""

    def test_write_data_raises_value_error_for_unsupported_dataset(
        self, coordinator, mock_hub
    ) -> None:
        """验证 _write_data 对不支持的数据集抛出 ValueError。"""
        # Arrange
        unsupported_dataset = "unsupported_dataset"
        df = pl.DataFrame({"col1": [1, 2, 3]})

        # Act & Assert
        with pytest.raises(ValueError, match="不支持写入数据集"):
            coordinator._write_data(unsupported_dataset, df, "2024-12-27")

        # 验证没有调用任何 store 的 write 方法
        mock_hub.bars.write.assert_not_called()
        mock_hub.adj_factor.write.assert_not_called()


@pytest.mark.unit
class TestAdjFactorWithExistingSid:
    """测试 adj_factor/fund_adj 数据集已有 sid 列的情况。"""

    def test_write_adj_factor_with_existing_sid_column(
        self, coordinator, mock_hub, mocker
    ) -> None:
        """验证 adj_factor 已有 sid 列时不调用 enrich_dataframe（第311-320行）。"""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "sid": [1000001],  # 已有 sid 列
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_hub.adj_factor = mocker.Mock()
        mock_hub.adj_factor.write.return_value = mock_hub_adj_factor_write(
            "/path/to/file.parquet",
            "checksum789",
        )

        # Act
        write_result = coordinator._write_data("adj_factor", df, "2024-12-27")

        # Assert
        assert write_result.file_path == "/path/to/file.parquet"
        assert write_result.checksum == "checksum789"
        # 验证没有调用 enrich_dataframe_with_sid（因为已有 sid 列）
        mock_hub.securities.enrich_dataframe_with_sid.assert_not_called()
        # 验证 adj_factor_store.write 被调用
        mock_hub.adj_factor.write.assert_called_once()

    def test_write_fund_adj_with_existing_sid_column(
        self, coordinator, mock_hub, mocker
    ) -> None:
        """验证 fund_adj 数据集已有 sid 列时不调用 enrich_dataframe。"""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["510300.SH"],
                "sid": [2000001],  # 已有 sid 列
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.5],
            }
        )

        mock_hub.adj_factor = mocker.Mock()
        mock_hub.adj_factor.write.return_value = mock_hub_adj_factor_write(
            "/path/to/file.parquet",
            "checksum999",
        )

        # Act
        write_result = coordinator._write_data("fund_adj", df, "2024-12-27")

        # Assert
        assert write_result.file_path == "/path/to/file.parquet"
        assert write_result.checksum == "checksum999"
        # 验证没有调用 enrich_dataframe_with_sid（因为已有 sid 列）
        mock_hub.securities.enrich_dataframe_with_sid.assert_not_called()
        # 验证 adj_factor_store.write 被调用
        mock_hub.adj_factor.write.assert_called_once()

    def test_write_adj_factor_without_sid_column_calls_enrich(
        self, coordinator, mock_hub, mocker
    ) -> None:
        """验证 adj_factor 数据集没有 sid 列时调用 enrich_dataframe。"""
        # Arrange
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_hub.adj_factor = mocker.Mock()
        mock_hub.adj_factor.write.return_value = mock_hub_adj_factor_write(
            "/path/to/file.parquet",
            "checksum789",
        )

        # Act
        write_result = coordinator._write_data("adj_factor", df, "2024-12-27")

        # Assert
        assert write_result.file_path == "/path/to/file.parquet"
        assert write_result.checksum == "checksum789"
        # 验证调用了 enrich_dataframe_with_sid（因为没有 sid 列）
        mock_hub.securities.enrich_dataframe_with_sid.assert_called_once_with(
            df,
            source="tushare",
            asset_class="stock",
            src_code_col="src_code",
        )
        # 验证 adj_factor_store.write 被调用
        mock_hub.adj_factor.write.assert_called_once()


@pytest.mark.unit
class TestTradingDayCheck:
    """测试交易日检查（P0-2）。"""

    def test_stock_daily_skips_on_non_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """stock_daily 在非交易日静默跳过。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None  # 无历史记录
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        # 不应该调用 source
        mock_source.fetch_stock_daily.assert_not_called()
        # 不应该记录 ingestion_log（静默跳过）
        mock_hub.ingestion_log.save_log.assert_not_called()

    def test_etf_daily_skips_on_non_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """etf_daily 在非交易日静默跳过。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("etf_daily", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        # 不应该调用 source
        mock_source.fetch_etf_daily.assert_not_called()

    def test_stock_daily_proceeds_on_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """stock_daily 在交易日继续处理。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        source_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_hub.bars = mocker.Mock()
        mock_hub.bars.write.return_value = mock_hub_bars_write(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "success"
        # 验证调用了 source
        mock_source.fetch_stock_daily.assert_called_once_with("2024-12-27")

    def test_adj_factor_does_not_check_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """adj_factor 不检查交易日（参考类数据集）。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_hub.calendar = mocker.Mock()
        # 即使 calendar 返回非交易日，adj_factor 也不应该检查
        mock_hub.calendar.is_trading_day.return_value = False

        mock_source.fetch_adj_factor.return_value = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_hub.adj_factor = mocker.Mock()
        mock_hub.adj_factor.write.return_value = mock_hub_adj_factor_write(
            "/path/to/file.parquet",
            "checksum789",
        )
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="adj_factor",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum789",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("adj_factor", "2024-12-27")

        # Assert
        assert result.status == "success"
        # 验证调用了 source（没有因为非交易日而跳过）
        mock_source.fetch_adj_factor.assert_called_once()
        # 验证没有调用 is_trading_day
        mock_hub.calendar.is_trading_day.assert_not_called()

    def test_calendar_does_not_check_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """calendar 不检查交易日（基础类数据集）。"""
        # Arrange
        mock_hub.ingestion_log.get_log.return_value = None
        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.is_trading_day.return_value = False

        mock_source.fetch_calendar.return_value = pl.DataFrame(
            {
                "trade_date": [date(2024, 12, 27)],
                "is_open": [True],
            }
        )

        mock_hub.calendar = mocker.Mock()
        mock_hub.calendar.upsert.return_value = 1
        mock_hub.ingestion_log.save_log.return_value = IngestionLog(
            dataset="calendar",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum000",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("calendar", "2024-12-27")

        # Assert
        assert result.status == "success"
        # 验证调用了 source（没有因为非交易日而跳过）
        mock_source.fetch_calendar.assert_called_once()
        # 验证没有调用 is_trading_day
        mock_hub.calendar.is_trading_day.assert_not_called()
