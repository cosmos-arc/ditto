"""Tests for TdxSource."""

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.tdx.source import TdxSource
from ditto_datahub.stores.metadata.instrument import InstrumentStore
from pytest_mock import MockerFixture


@pytest.fixture
def mock_tdx_path(tmp_path: Path) -> Path:
    """创建临时 TDX 数据路径."""
    tdx_path = tmp_path / "tdx"
    tdx_path.mkdir(parents=True, exist_ok=True)
    return tdx_path


@pytest.fixture
def mock_instrument_store(mocker: MockerFixture) -> MagicMock:
    """Mock InstrumentStore."""
    store = mocker.MagicMock(spec=InstrumentStore)
    return store


@pytest.fixture
def data_source_settings(mock_tdx_path: Path) -> DataSourceSettings:
    """创建 DataSourceSettings."""
    return DataSourceSettings(
        tdx_path=str(mock_tdx_path),
    )


@pytest.fixture
def tdx_source(
    data_source_settings: DataSourceSettings, mock_instrument_store: MagicMock
) -> TdxSource:
    """创建 TdxSource 实例."""
    return TdxSource(
        data_source_settings=data_source_settings,
        instrument_store=mock_instrument_store,
    )


@pytest.mark.unit
class TestGetExchangeMapping:
    """测试 _get_exchange_mapping 方法."""

    def test_sse_mapping_by_prefix(self, tdx_source: TdxSource) -> None:
        """上海交易所映射."""
        result = tdx_source._get_exchange_mapping(["600000", "510300", "688001"])
        assert result["600000"] == "SSE"
        assert result["510300"] == "SSE"
        assert result["688001"] == "SSE"

    def test_szse_mapping_by_prefix(self, tdx_source: TdxSource) -> None:
        """深圳交易所映射."""
        result = tdx_source._get_exchange_mapping(["000001", "000002", "300001"])
        assert result["000001"] == "SZSE"
        assert result["000002"] == "SZSE"
        assert result["300001"] == "SZSE"

    def test_bse_mapping_by_prefix(self, tdx_source: TdxSource) -> None:
        """北京交易所映射."""
        result = tdx_source._get_exchange_mapping(["800000", "400001", "430001"])
        assert result["800000"] == "BSE"
        assert result["400001"] == "BSE"
        assert result["430001"] == "BSE"

    def test_unknown_symbol_returns_empty(self, tdx_source: TdxSource) -> None:
        """未知 symbol 返回空映射."""
        result = tdx_source._get_exchange_mapping(["999999"])
        assert "999999" not in result

    def test_none_symbol_skipped(self, tdx_source: TdxSource) -> None:
        """None symbol 被跳过."""
        result = tdx_source._get_exchange_mapping([None, "600000", "000001"])
        assert None not in result
        assert "600000" in result
        assert "000001" in result

    def test_non_string_symbol_skipped(self, tdx_source: TdxSource) -> None:
        """非字符串 symbol 被跳过."""
        result = tdx_source._get_exchange_mapping([123, "600000", None])
        assert 123 not in result
        assert "600000" in result


@pytest.mark.unit
class TestConvertToTdxExchange:
    """测试 _convert_to_tdx_exchange 方法."""

    def test_sse_to_sh(self, tdx_source: TdxSource) -> None:
        """SSE → SH."""
        assert tdx_source._convert_to_tdx_exchange("SSE") == "SH"

    def test_szse_to_sz(self, tdx_source: TdxSource) -> None:
        """SZSE → SZ."""
        assert tdx_source._convert_to_tdx_exchange("SZSE") == "SZ"

    def test_bse_to_bj(self, tdx_source: TdxSource) -> None:
        """BSE → BJ."""
        assert tdx_source._convert_to_tdx_exchange("BSE") == "BJ"

    def test_unknown_exchange_defaults_to_sz(self, tdx_source: TdxSource) -> None:
        """未知交易所默认 SZ."""
        assert tdx_source._convert_to_tdx_exchange("UNKNOWN") == "SZ"


@pytest.mark.unit
class TestFetchStockDailyBars:
    """测试 fetch_stock_daily_bars 方法."""

    def test_symbol_without_exchange_skips(
        self,
        tdx_source: TdxSource,
        mock_instrument_store: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """无 exchange 的 symbol 跳过."""
        # Arrange
        mock_instrument_store.enrich_with_symbol.return_value = pl.DataFrame(
            {
                "instrument_id": [1000001, 1000002],
                "symbol": ["000001", "999999"],
                "exchange": ["SZSE", None],
            }
        )

        mock_reader = mocker.MagicMock()
        mock_reader.fetch_stock_daily_bars.return_value = pl.DataFrame()
        tdx_source.reader = mock_reader

        # Act
        tdx_source.fetch_stock_daily_bars(["000001", "999999"], "20240101")

        # Assert - reader 应该只被调用一次（999999 被跳过）
        assert mock_reader.fetch_stock_daily_bars.call_count == 1

    def test_empty_symbols_list(self, tdx_source: TdxSource) -> None:
        """空股票列表."""
        result = tdx_source.fetch_stock_daily_bars([], "20240101")
        assert result.is_empty()

    def test_symbol_to_source_ticker_conversion(
        self,
        tdx_source: TdxSource,
        mock_instrument_store: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Symbol 转换为 source_ticker 格式."""
        # Arrange
        mock_instrument_store.enrich_with_symbol.return_value = pl.DataFrame(
            {
                "instrument_id": [1000001, 1000002],
                "symbol": ["000001", "600000"],
            }
        )

        mock_reader = mocker.MagicMock()
        mock_reader.fetch_stock_daily_bars.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "600000.SH"],
                "trade_date": ["20240101", "20240101"],
                "close": [10.0, 20.0],
            }
        )
        tdx_source.reader = mock_reader

        # Act
        result = tdx_source.fetch_stock_daily_bars(["000001", "600000"], "20240101")

        # Assert - 验证返回 DataFrame 包含 symbol 列
        assert "symbol" in result.columns
        assert "source_ticker" not in result.columns
        assert set(result["symbol"].to_list()) == {"000001", "600000"}

    def test_multiple_symbols_batch(
        self,
        tdx_source: TdxSource,
        mock_instrument_store: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """批量获取多个股票."""
        # Arrange
        mock_instrument_store.enrich_with_symbol.return_value = pl.DataFrame(
            {
                "instrument_id": [1000001, 1000002, 1000003],
                "symbol": ["000001", "600000", "510300"],
            }
        )

        mock_reader = mocker.MagicMock()
        mock_reader.fetch_stock_daily_bars.return_value = pl.DataFrame()
        tdx_source.reader = mock_reader

        # Act
        tdx_source.fetch_stock_daily_bars(["000001", "600000", "510300"], "20240101")

        # Assert - reader 应该被调用一次
        mock_reader.fetch_stock_daily_bars.assert_called_once()

    def test_fetch_returns_data_with_expected_columns(
        self,
        tdx_source: TdxSource,
        mock_instrument_store: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """验证返回数据包含预期列."""
        # Arrange
        mock_instrument_store.enrich_with_symbol.return_value = pl.DataFrame(
            {"instrument_id": [1000001], "symbol": ["000001"]}
        )

        mock_reader = mocker.MagicMock()
        mock_reader.fetch_stock_daily_bars.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": ["20240101"],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "vol": [1000000],
                "amount": [10200000],
            }
        )
        tdx_source.reader = mock_reader

        # Act
        result = tdx_source.fetch_stock_daily_bars(["000001"], "20240101")

        # Assert
        expected_columns = {
            "symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol",
            "amount",
        }
        assert set(result.columns) == expected_columns
        assert result["symbol"][0] == "000001"
