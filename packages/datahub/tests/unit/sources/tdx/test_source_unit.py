"""Tests for TdxSource."""

from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.tdx.source import TdxSource
from pytest_mock import MockerFixture


@pytest.fixture
def mock_tdx_path(tmp_path: Path) -> Path:
    """创建临时 TDX 数据路径."""
    tdx_path = tmp_path / "tdx"
    tdx_path.mkdir(parents=True, exist_ok=True)
    return tdx_path


@pytest.fixture
def data_source_settings(mock_tdx_path: Path) -> DataSourceSettings:
    """创建 DataSourceSettings."""
    return DataSourceSettings(
        tdx_path=str(mock_tdx_path),
    )


@pytest.fixture
def tdx_source(data_source_settings: DataSourceSettings) -> TdxSource:
    """创建 TdxSource 实例."""
    return TdxSource(
        data_source_settings=data_source_settings,
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

    def test_empty_symbols_list(self, tdx_source: TdxSource) -> None:
        """空股票列表."""
        result = tdx_source.fetch_stock_daily_bars([], "20240101")
        assert result.is_empty()

    def test_symbol_to_source_ticker_conversion(
        self,
        tdx_source: TdxSource,
        mocker: MockerFixture,
    ) -> None:
        """Symbol 转换为 source_ticker 格式."""
        # Arrange
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

        # Assert - 验证 reader 被调用时使用 TDX 格式代码
        mock_reader.fetch_stock_daily_bars.assert_called_once()
        call_args = mock_reader.fetch_stock_daily_bars.call_args
        tdx_codes = call_args[0][0]  # 第一个参数是 tdx_codes
        assert "000001.SZ" in tdx_codes
        assert "600000.SH" in tdx_codes

        # Assert - 验证返回 DataFrame 包含 symbol 列
        assert "symbol" in result.columns
        assert "source_ticker" not in result.columns
        assert set(result["symbol"].to_list()) == {"000001", "600000"}

    def test_multiple_symbols_batch(
        self,
        tdx_source: TdxSource,
        mocker: MockerFixture,
    ) -> None:
        """批量获取多个股票."""
        # Arrange
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
        mocker: MockerFixture,
    ) -> None:
        """验证返回数据包含预期列."""
        # Arrange
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
