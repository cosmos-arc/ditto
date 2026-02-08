"""Tests for IngestionCoordinator."""

from datetime import date
from typing import Any

import polars as pl
import pytest
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.runtime.ingestion.ingestion_log_store import IngestionLogStore
from ditto_datahub.services.market import MarketWriteResult
from ditto_datahub.sources.base import DataSource, SourceFetchError
from ditto_foundation.config.environment import Environment
from ditto_foundation.observability import init, reset_for_testing
from ditto_foundation.observability.config import ObservabilityConfig
from ditto_port.services.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionResult,
)


def mock_hub_market_write_bars(file_path: str, checksum: str) -> MarketWriteResult:
    """创建 Mock hub.market.write() 的返回值（行情数据）。"""
    _ = file_path, checksum
    return MarketWriteResult(dataset="stock_daily", rows=2, files=1)


def mock_hub_market_write_adj_factor() -> MarketWriteResult:
    """创建 Mock hub.market.write() 的返回值（复权因子）。"""
    return MarketWriteResult(dataset="adj_factor", rows=1, files=1)


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


@pytest.fixture
def mock_hub(mocker):
    """创建 Mock DataHub。"""
    hub = mocker.Mock()
    hub.ingestion_log_store = mocker.Mock(spec=IngestionLogStore)
    stock_counter = [1_000_000]
    etf_counter = [2_000_000]

    _attach_allocator(hub, mocker, stock_counter, etf_counter)
    _attach_metadata(hub, mocker, stock_counter, etf_counter)
    _attach_market(hub, mocker)
    _attach_domain_services(hub, mocker)
    _attach_calendar(hub, mocker)

    return hub


def _attach_allocator(
    hub: Any, mocker: Any, stock_counter: list[int], etf_counter: list[int]
) -> None:
    mock_instrument_id_allocator = mocker.Mock()

    def allocate_side_effect(asset_class: str) -> int:
        if asset_class == "stock":
            instrument_id = stock_counter[0]
            stock_counter[0] += 1
            return instrument_id
        if asset_class == "etf":
            instrument_id = etf_counter[0]
            etf_counter[0] += 1
            return instrument_id
        raise ValueError(f"Unknown asset class: {asset_class}")

    mock_instrument_id_allocator.allocate.side_effect = allocate_side_effect
    hub.instrument_id_allocator = mock_instrument_id_allocator

    hub.instrument_store = mocker.Mock()
    hub.instrument_store.resolve_instrument_id.return_value = None
    hub.instrument_store.register.return_value = 1000001


def _attach_metadata(
    hub: Any, mocker: Any, stock_counter: list[int], etf_counter: list[int]
) -> None:
    hub.metadata = mocker.Mock()

    def register_securities_batch_side_effect(df, source, asset_class, **kwargs):
        _ = df, source, kwargs
        file_path = f"instrument_store:{asset_class}_basic"
        checksum = f"checksum_{asset_class}"
        return (file_path, checksum)

    def resolve_or_create_batch_side_effect(df, source, asset_class, **kwargs):
        _ = source, kwargs
        if asset_class == "stock":
            instrument_id = stock_counter[0]
            stock_counter[0] += 1
        elif asset_class == "etf":
            instrument_id = etf_counter[0]
            etf_counter[0] += 1
        else:
            raise ValueError(f"Unknown asset class: {asset_class}")
        source_tickers = df["source_ticker"].to_list()
        return {source_tickers[0]: instrument_id}

    hub.metadata.register_instruments_batch.side_effect = (
        register_securities_batch_side_effect
    )
    hub.metadata.resolve_or_create_instruments_batch.side_effect = (
        resolve_or_create_batch_side_effect
    )
    hub.metadata.get_securities.return_value = pl.DataFrame()


def _attach_market(hub: Any, mocker: Any) -> None:
    hub.market = mocker.Mock()

    def write_side_effect(command) -> MarketWriteResult:
        return MarketWriteResult(
            dataset=command.dataset,
            rows=len(command.df),
            files=1,
        )

    hub.market.write = mocker.Mock(side_effect=write_side_effect)


def _attach_domain_services(hub: Any, mocker: Any) -> None:
    hub.fundamental = mocker.Mock()
    hub.fundamental.write.return_value = mocker.Mock(records_written=1)

    hub.capital = mocker.Mock()
    hub.capital.write.return_value = mocker.Mock(records_written=1)

    hub.macro = mocker.Mock()
    hub.macro.write.return_value = mocker.Mock(records_written=1)


def _attach_calendar(hub: Any, mocker: Any) -> None:
    hub.metadata.is_trading_day.return_value = True
    hub.metadata.upsert.return_value = len
    hub.metadata.list_trading_days.return_value = []


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
        mock_hub.ingestion_log_store.get_log.return_value = IngestionLog(
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
        mock_hub.ingestion_log_store.get_log.return_value = None  # 无历史记录
        source_df = pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "510500.SH"],
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

        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        # checksum 是实际计算的 MD5 值，只需验证非空即可
        assert result.checksum is not None
        assert len(result.checksum) > 0
        mock_source.fetch_etf_daily.assert_called_once_with("2024-12-27")
        mock_hub.market.write.assert_called_once()
        mock_hub.ingestion_log_store.save_log.assert_called_once()

    def test_ingest_date_success_stock_daily(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 stock_daily 数据。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market = mocker.Mock()
        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum456",
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_adj_factor.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_hub.market.write.return_value = mock_hub_market_write_adj_factor()
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.market.write.assert_called_once()

    def test_ingest_date_success_stock_status(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 stock_status 数据。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_status.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "is_suspended": [False],
                "suspend_timing": [None],
                "is_st": [False],
                "st_type": [None],
                "list_status": ["L"],
            }
        )

        mock_hub.market.write.return_value = MarketWriteResult(
            dataset="stock_status",
            rows=1,
            files=1,
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_status",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_status",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_status", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_stock_status.assert_called_once_with("2024-12-27")
        mock_hub.market.write.assert_called_once()

    def test_ingest_date_success_balance_sheet(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 balance_sheet 数据。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_balance_sheet.return_value = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "report_date": [date(2024, 12, 31)],
                "knowledge_date": [date(2025, 1, 1)],
                "effective_from": [date(2025, 1, 1)],
                "effective_to": [None],
                "total_assets": [100.0],
                "total_liabilities": [60.0],
                "net_assets": [40.0],
                "current_assets": [30.0],
                "current_liabilities": [20.0],
            }
        )
        mock_hub.fundamental.write.return_value = mocker.Mock(records_written=1)
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="balance_sheet",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_balance_sheet",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("balance_sheet", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_balance_sheet.assert_called_once_with("2024-12-27")
        mock_hub.fundamental.write.assert_called_once()

    def test_ingest_date_success_valuation_metrics(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 valuation_metrics 数据。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_valuation_metrics.return_value = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "pe_ratio": [12.5],
                "pb_ratio": [1.8],
                "ps_ratio": [2.1],
                "dividend_yield": [0.03],
                "market_cap": [1000000000.0],
            }
        )
        mock_hub.capital.write.return_value = mocker.Mock(records_written=1)
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="valuation_metrics",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_valuation_metrics",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("valuation_metrics", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_valuation_metrics.assert_called_once_with("2024-12-27")
        mock_hub.capital.write.assert_called_once()

    def test_ingest_date_success_macro_indicators(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 macro_indicators 数据。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_macro_indicators.return_value = pl.DataFrame(
            {
                "indicator_code": ["SHIBOR_ON"],
                "indicator_name": ["隔夜Shibor"],
                "category": ["interest_rate"],
                "frequency": ["daily"],
                "need_pit": [False],
                "date": [date(2024, 12, 27)],
                "value": [1.92],
                "knowledge_date": [date(2024, 12, 28)],
            }
        )
        mock_hub.macro.write.return_value = mocker.Mock(records_written=1)
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="macro_indicators",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_macro_indicators",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("macro_indicators", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_macro_indicators.assert_called_once_with("2024-12-27")
        mock_hub.macro.write.assert_called_once()

    def test_ingest_date_success_calendar(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """成功摄取 calendar 数据（范围数据）。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_calendar.return_value = pl.DataFrame(
            {
                "trade_date": [date(2024, 12, 27), date(2024, 12, 30)],
                "is_open": [True, True],
            }
        )

        mock_hub.metadata.reset_mock()
        mock_hub.metadata.upsert.return_value = 2
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.ingestion_log_store.get_log.return_value = None

        mock_source.fetch_stock_daily.side_effect = SourceFetchError(
            "Network error", source="tushare", dataset="stock_daily"
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_daily.return_value = pl.DataFrame()
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="old_checksum",
            rows=1000,
        )

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market = mocker.Mock()
        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "new_checksum",
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        # checksum 是实际计算的 MD5 值，只需验证非空即可
        assert result.checksum is not None
        assert len(result.checksum) > 0
        mock_source.fetch_stock_daily.assert_called_once()

    def test_ingest_date_unknown_error(
        self, coordinator, mock_hub, mock_source
    ) -> None:
        """测试非 SourceFetchError 异常的处理。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_daily.side_effect = RuntimeError("Unexpected error")
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        # 模拟 DQ 阻断：files=0 表示没有文件写入，被阻塞
        # 需要重置 side_effect 并设置 return_value
        mock_hub.market.write.side_effect = None
        mock_hub.market.write.return_value = MarketWriteResult(
            dataset="stock_daily",
            rows=0,
            files=0,
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.ingestion_log_store.get_log.return_value = None

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
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_hub.ingestion_log_store.get_log.return_value = None  # 无历史记录

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.metadata.list_trading_days.assert_called_once_with(
            "2024-12-25", "2024-12-27"
        )
        assert mock_source.fetch_stock_daily.call_count == 3

    def test_ingest_range_with_skipped_dates(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """日期范围内有跳过的日期。"""
        # Arrange
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.list_trading_days.return_value = [
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

        mock_hub.ingestion_log_store.get_log.side_effect = get_log_side_effect

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.list_trading_days.return_value = []

        # Act
        results = coordinator.ingest_range("stock_daily", "2024-12-25", "2024-12-27")

        # Assert
        assert len(results) == 0

    def test_ingest_range_with_force(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """force=True 时跳过所有历史检查。"""
        # Arrange
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.list_trading_days.return_value = ["2024-12-27"]

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        """成功摄取 stock_basic 数据到 instrument_store。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_basic.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "600000.SH"],
                "symbol": ["000001", "600000"],
                "name": ["平安银行", "浦发银行"],
                "exchange": ["SZSE", "SSE"],
                "list_date": [date(1991, 4, 3), date(1999, 11, 10)],
            }
        )

        mock_hub.ingestion_log_store.save_log.return_value = mocker.Mock(
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
        """成功摄取 etf_basic 数据到 instrument_store。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_etf_basic.return_value = pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "159919.SZ"],
                "symbol": ["510300", "159919"],
                "name": ["沪深300ETF", "沪深300ETF"],
                "exchange": ["SSE", "SZSE"],
                "list_date": [date(2012, 7, 6), date(2019, 6, 24)],
            }
        )

        mock_hub.ingestion_log_store.save_log.return_value = mocker.Mock(
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


@pytest.mark.unit
class TestForceParameter:
    """测试 force 参数语义。"""

    def test_force_false_maps_to_error_on_duplicate(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """验证 force=False 映射到 OnDuplicate.ERROR。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.market.write.assert_called_once()
        command = mock_hub.market.write.call_args.args[0]
        assert command.on_duplicate == "error"

    def test_force_true_maps_to_keep_last_on_duplicate(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """验证 force=True 映射到 OnDuplicate.KEEP_LAST。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.market.write.assert_called_once()
        command = mock_hub.market.write.call_args.args[0]
        assert command.on_duplicate == "overwrite"

    def test_force_true_for_adj_factor_uses_keep_last(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """验证 force=True 对 adj_factor 数据集也传递正确的 on_duplicate。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_source.fetch_adj_factor.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_hub.market.write.return_value = mock_hub_market_write_adj_factor()
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.market.write.assert_called_once()
        command = mock_hub.market.write.call_args.args[0]
        assert command.on_duplicate == "overwrite"


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
class TestTradingDayCheck:
    """测试交易日检查（P0-2）。"""

    def test_stock_daily_skips_on_non_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """stock_daily 在非交易日静默跳过。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None  # 无历史记录
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        # 不应该调用 source
        mock_source.fetch_stock_daily.assert_not_called()
        # 不应该记录 ingestion_log（静默跳过）
        mock_hub.ingestion_log_store.save_log.assert_not_called()

    def test_etf_daily_skips_on_non_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """etf_daily 在非交易日静默跳过。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("etf_daily", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        # 不应该调用 source
        mock_source.fetch_etf_daily.assert_not_called()

    def test_stock_status_skips_on_non_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """stock_status 在非交易日静默跳过。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("stock_status", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        mock_source.fetch_stock_status.assert_not_called()

    def test_stock_daily_proceeds_on_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """stock_daily 在交易日继续处理。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.is_trading_day.return_value = True

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
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

        mock_hub.market.write.return_value = mock_hub_market_write_bars(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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

    def test_adj_factor_skips_on_non_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """adj_factor 在非交易日静默跳过。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("adj_factor", "2024-12-27")

        # Assert
        assert result.status == "skipped"
        mock_source.fetch_adj_factor.assert_not_called()
        mock_hub.metadata.is_trading_day.assert_called_once_with("2024-12-27")

    def test_calendar_does_not_check_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """calendar 不检查交易日（基础类数据集）。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.is_trading_day.return_value = False

        mock_source.fetch_calendar.return_value = pl.DataFrame(
            {
                "trade_date": [date(2024, 12, 27)],
                "is_open": [True],
            }
        )

        mock_hub.metadata.reset_mock()
        mock_hub.metadata.upsert.return_value = 1
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
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
        mock_hub.metadata.is_trading_day.assert_not_called()

    def test_macro_indicators_does_not_check_trading_day(
        self, coordinator, mock_hub, mock_source, mocker
    ) -> None:
        """macro_indicators 不检查交易日（非交易日也允许摄取）。"""
        # Arrange
        mock_hub.ingestion_log_store.get_log.return_value = None
        mock_hub.metadata.reset_mock()
        mock_hub.metadata.is_trading_day.return_value = False

        mock_source.fetch_macro_indicators.return_value = pl.DataFrame(
            {
                "indicator_code": ["SHIBOR_ON"],
                "indicator_name": ["隔夜Shibor"],
                "category": ["interest_rate"],
                "frequency": ["daily"],
                "need_pit": [False],
                "date": [date(2024, 12, 28)],
                "value": [1.91],
                "knowledge_date": [date(2024, 12, 29)],
            }
        )

        mock_hub.macro.write.return_value = mocker.Mock(records_written=1)
        mock_hub.ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="macro_indicators",
            source="tushare",
            trade_date="2024-12-28",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_macro_indicators",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("macro_indicators", "2024-12-28")

        # Assert
        assert result.status == "success"
        mock_source.fetch_macro_indicators.assert_called_once_with("2024-12-28")
        mock_hub.metadata.is_trading_day.assert_not_called()
