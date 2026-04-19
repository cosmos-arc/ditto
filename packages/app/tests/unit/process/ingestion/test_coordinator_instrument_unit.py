"""Tests for IngestionCoordinator.ingest_by_instrument method."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_app.process.ingestion.config import IngestionCoordinatorConfig
from ditto_app.process.ingestion.coordinator import (
    IngestionCoordinator,
    MarketServices,
)
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_infra.foundation.config.environment import Environment
from ditto_infra.foundation.observability import init, reset_for_testing
from ditto_infra.foundation.observability.config import ObservabilityConfig
from ditto_kernel.instrument import InstrumentIngestParams


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性."""
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
def mock_metadata_service():
    """创建 Mock MetadataService."""
    service = MagicMock()
    service.is_trading_day.return_value = True
    service.upsert.return_value = len
    service.list_trading_days.return_value = []
    service.get_securities.return_value = pl.DataFrame()

    # Instrument 相关方法
    service.register_instruments_batch = MagicMock()
    service.resolve_or_create_instruments_batch = MagicMock()
    service.resolve_instrument_ids_batch = MagicMock()

    # 设置 resolve_or_create_instruments_batch 的 side_effect
    stock_counter = [1_000_000]

    def resolve_side_effect(df, source, asset_class, **kwargs):
        _ = source, kwargs
        if asset_class == "stock":
            instrument_id = stock_counter[0]
            stock_counter[0] += 1
        else:
            instrument_id = 2_000_000
        source_tickers = df["source_ticker"].to_list()
        return {source_tickers[0]: instrument_id}

    def resolve_ids_side_effect(identifiers, source, asof, **kwargs):
        """为 resolve_instrument_ids_batch 模拟返回值."""
        _ = source, asof, kwargs
        result = {}
        for i, ticker in enumerate(identifiers):
            result[ticker] = 1_000_000 + i
        return result

    service.resolve_or_create_instruments_batch.side_effect = resolve_side_effect
    service.resolve_instrument_ids_batch.side_effect = resolve_ids_side_effect

    # resolve_source_ticker 默认返回测试值
    service.resolve_source_ticker.return_value = "000001.SZ"

    return service


@pytest.fixture
def mock_market_write_service():
    """创建 Mock MarketService."""
    service = MagicMock()
    service.save_bars.return_value = 1
    service.save_adj_factor.return_value = 1
    service.save_stock_status.return_value = 1
    return service


@pytest.fixture
def mock_fundamental_service():
    """创建 Mock FundamentalService."""
    service = MagicMock()
    service.write.return_value = MagicMock(records_written=1)
    return service


@pytest.fixture
def mock_capital_service():
    """创建 Mock CapitalService."""
    service = MagicMock()
    service.write.return_value = MagicMock(records_written=1)
    return service


@pytest.fixture
def mock_macro_service():
    """创建 Mock MacroService."""
    service = MagicMock()
    service.write.return_value = MagicMock(records_written=1)
    return service


@pytest.fixture
def mock_ingestion_log_service():
    """创建 Mock IngestionLogService."""
    service = MagicMock()
    service.get_log = MagicMock(return_value=None)
    service.save_log = MagicMock(return_value=None)
    service.list_ingested_dates = MagicMock(return_value=[])
    return service


@pytest.fixture
def mock_source():
    """创建 Mock DataSource."""
    source = MagicMock()
    return source


@pytest.fixture
def coordinator(
    mock_metadata_service,
    mock_market_write_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_ingestion_log_service,
    mock_source,
):
    """创建 IngestionCoordinator 实例."""
    return IngestionCoordinator(
        metadata_service=mock_metadata_service,
        market_services=MarketServices(
            query=mock_market_write_service,
            write=mock_market_write_service,
        ),
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source=mock_source,
        config=IngestionCoordinatorConfig(
            ingestion_log_service=mock_ingestion_log_service,
        ),
    )


@pytest.mark.unit
class TestIngestByInstrument:
    """测试 ingest_by_instrument 方法."""

    def test_ingest_by_instrument_with_ticker(
        self,
        coordinator,
        mock_metadata_service,
        mock_source,
        mock_market_write_service,
        mock_ingestion_log_service,
    ) -> None:
        """成功通过 ticker 按标的摄取数据."""
        # Arrange
        params = InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"] * 3,
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "open": [10.0, 10.5, 10.2],
                "high": [10.5, 10.8, 10.5],
                "low": [9.8, 10.2, 10.0],
                "close": [10.2, 10.6, 10.3],
                "pre_close": [10.0, 10.2, 10.6],
                "volume": [1000000, 1200000, 1100000],
                "amount": [10200000, 12720000, 11330000],
                "pct_change": [2.0, 3.9, -2.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df
        mock_market_write_service.save_bars.return_value = 3
        mock_ingestion_log_service.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=3,
        )

        # Act
        result = coordinator.ingest_by_instrument("stock_daily", params)

        # Assert
        assert result.status == "success"
        assert result.row_count == 3
        # 验证调用了 resolve_source_ticker
        mock_metadata_service.resolve_source_ticker.assert_called_once_with(
            ticker="000001",
            standard_ticker=None,
            instrument_id=None,
            asset_class="stock",
            source="tushare",
        )
        mock_source.fetch_stock_daily.assert_called_once_with(
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

    def test_ingest_by_instrument_with_instrument_id(
        self,
        coordinator,
        mock_metadata_service,
        mock_source,
        mock_market_write_service,
        mock_ingestion_log_service,
    ) -> None:
        """成功通过 instrument_id 按标的摄取数据."""
        # Arrange
        mock_metadata_service.resolve_source_ticker.return_value = "600519.SH"
        params = InstrumentIngestParams(
            instrument_id=1000001,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        source_df = pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": [date(2024, 1, 2)],
                "open": [1800.0],
                "close": [1820.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df
        mock_market_write_service.save_bars.return_value = 1
        mock_ingestion_log_service.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.SUCCESS,
            checksum="checksum",
            rows=1,
        )

        # Act
        result = coordinator.ingest_by_instrument("stock_daily", params)

        # Assert
        assert result.status == "success"
        mock_metadata_service.resolve_source_ticker.assert_called_once_with(
            ticker=None,
            standard_ticker=None,
            instrument_id=1000001,
            asset_class="stock",
            source="tushare",
        )

    def test_ingest_by_instrument_with_standard_ticker(
        self,
        coordinator,
        mock_metadata_service,
        mock_source,
        mock_market_write_service,
        mock_ingestion_log_service,
    ) -> None:
        """成功通过 standard_ticker 按标的摄取数据."""
        # Arrange
        mock_metadata_service.resolve_source_ticker.return_value = "000001.SZ"
        params = InstrumentIngestParams(
            standard_ticker="000001.XSHE",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "close": [10.2],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df
        mock_market_write_service.save_bars.return_value = 1
        mock_ingestion_log_service.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.SUCCESS,
            checksum="checksum",
            rows=1,
        )

        # Act
        result = coordinator.ingest_by_instrument("stock_daily", params)

        # Assert
        assert result.status == "success"
        mock_metadata_service.resolve_source_ticker.assert_called_once_with(
            ticker=None,
            standard_ticker="000001.XSHE",
            instrument_id=None,
            asset_class="stock",
            source="tushare",
        )

    def test_ingest_by_instrument_empty_data(
        self, coordinator, mock_source, mock_ingestion_log_service
    ) -> None:
        """数据源返回空数据时返回失败结果."""
        # Arrange
        params = InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        mock_source.fetch_stock_daily.return_value = pl.DataFrame()
        mock_ingestion_log_service.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.FAIL,
            error_code="EMPTY_DATA",
            error_message="获取的数据为空",
        )

        # Act
        result = coordinator.ingest_by_instrument("stock_daily", params)

        # Assert
        assert result.status == "failed"
        assert result.error == "EMPTY_DATA"
        mock_source.fetch_stock_daily.assert_called_once()

    def test_ingest_by_instrument_unsupported_dataset(self, coordinator) -> None:
        """不支持的数据集抛出 ValueError."""
        # Arrange
        params = InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # Act & Assert
        with pytest.raises(ValueError, match="不支持按标的摄取"):
            coordinator.ingest_by_instrument("calendar", params)

    def test_ingest_by_instrument_fetch_error(
        self, coordinator, mock_source, mock_ingestion_log_service
    ) -> None:
        """数据源获取失败时返回失败结果."""
        # Arrange
        params = InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        mock_source.fetch_stock_daily.side_effect = Exception("Network error")
        mock_ingestion_log_service.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.FAIL,
            error_code="UNKNOWN_ERROR",
            error_message="Network error",
        )

        # Act
        result = coordinator.ingest_by_instrument("stock_daily", params)

        # Assert
        assert result.status == "failed"
        assert result.error == "UNKNOWN_ERROR"


# ---------------------------------------------------------------------------
# _infer_exchange_suffix tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInferExchangeSuffix:
    """测试 _infer_exchange_suffix 边界校验."""

    @staticmethod
    def _import():
        from ditto_app.process.ingestion.auto_init import infer_exchange_suffix

        return infer_exchange_suffix

    def test_sh_main_board(self) -> None:
        f = self._import()
        assert f("600519") == "SH"

    def test_sh_star_board(self) -> None:
        f = self._import()
        assert f("688001") == "SH"

    def test_sz_main_board(self) -> None:
        f = self._import()
        assert f("000001") == "SZ"

    def test_sz_chi_next(self) -> None:
        f = self._import()
        assert f("300001") == "SZ"

    def test_bj_stock_8(self) -> None:
        f = self._import()
        assert f("830001") == "BJ"

    def test_bj_stock_4(self) -> None:
        f = self._import()
        assert f("430001") == "BJ"

    def test_non_standard_short_code_returns_none(self) -> None:
        """非标准短代码不应匹配."""
        f = self._import()
        assert f("8") is None

    def test_non_standard_alpha_returns_none(self) -> None:
        """字母代码不应匹配."""
        f = self._import()
        assert f("8ABC") is None

    def test_empty_returns_none(self) -> None:
        f = self._import()
        assert f("") is None

    def test_unknown_prefix_returns_none(self) -> None:
        f = self._import()
        assert f("999999") is None
