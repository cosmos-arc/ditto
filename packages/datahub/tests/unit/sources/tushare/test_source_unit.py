"""Tests for TushareSource."""

from datetime import date

import httpx
import polars as pl
import pytest
from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.tushare_source import TushareSource


def _settings(token: str | None = None) -> DataSourceSettings:
    if token is None:
        token = "not_a_secret"
    return DataSourceSettings(tushare_token=token)


class TestTushareSourceCalendar:
    """Tests for TushareSource.fetch_calendar."""

    def test_fetch_calendar_returns_dataframe(self, respx_mock) -> None:
        """Test fetch_calendar returns DataFrame with correct schema."""

        # Mock HTTP 响应
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["cal_date", "is_open"],
                        "items": [["20240101", 0], ["20240102", 1], ["20240103", 1]],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_calendar("2024-01-01", "2024-01-03")

        # Verify schema
        assert dict(result.schema) == {
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {"trade_date": date(2024, 1, 1), "is_open": False},
            {"trade_date": date(2024, 1, 2), "is_open": True},
            {"trade_date": date(2024, 1, 3), "is_open": True},
        ]

    def test_fetch_calendar_empty_response(self, respx_mock) -> None:
        """Test fetch_calendar handles empty response."""

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date", "is_open"], "items": []},
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_calendar("2024-01-01", "2024-01-03")

        assert result.is_empty()

    def test_fetch_calendar_api_error_raises(self, tushare_source, respx_mock) -> None:
        """Test fetch_calendar raises SourceFetchError on API error."""
        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(SourceFetchError):
            tushare_source.fetch_calendar("2024-01-01", "2024-01-03")


class TestTushareSourceEtfBasic:
    """Tests for TushareSource.fetch_etf_basic."""

    def test_fetch_etf_basic_returns_dataframe(self, respx_mock) -> None:
        """Test fetch_etf_basic returns DataFrame with correct schema."""

        # Mock HTTP 响应 - fund_basic API
        # [REVIEW]: fund_basic 返回 ts_code, name, list_date
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": [
                            "ts_code",
                            "name",
                            "list_date",
                        ],
                        "items": [
                            ["510300.SH", "沪深300ETF", "20120706"],
                            ["159919.SZ", "沪深300ETF", "20190624"],
                        ],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_etf_basic()

        # Verify schema
        assert dict(result.schema) == {
            "source_ticker": pl.String,
            "ticker": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {
                "source_ticker": "510300.SH",
                "ticker": "510300",
                "name": "沪深300ETF",
                "exchange": "SSE",
                "list_date": date(2012, 7, 6),
            },
            {
                "source_ticker": "159919.SZ",
                "ticker": "159919",
                "name": "沪深300ETF",
                "exchange": "SZSE",
                "list_date": date(2019, 6, 24),
            },
        ]

    def test_fetch_etf_basic_empty_response(self, respx_mock) -> None:
        """Test fetch_etf_basic handles empty response."""

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": [
                            "ts_code",
                            "name",
                            "list_date",
                        ],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_etf_basic()

        assert result.is_empty()


class TestTushareSourceEtfDaily:
    """Tests for TushareSource.fetch_etf_daily."""

    def test_fetch_etf_daily_returns_dataframe(self, respx_mock) -> None:
        """Test fetch_etf_daily returns DataFrame with correct schema."""

        # Mock HTTP 响应 - fund_daily API
        # [REVIEW]: fund_daily 返回 vol, amount, pct_chg
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": [
                            "ts_code",
                            "trade_date",
                            "pre_close",
                            "open",
                            "high",
                            "low",
                            "close",
                            "change",
                            "pct_chg",
                            "vol",
                            "amount",
                        ],
                        "items": [
                            [
                                "510300.SH",
                                "20240102",
                                "3.5",
                                "3.5",
                                "3.6",
                                "3.4",
                                "3.55",
                                "0.05",
                                "1.5",
                                "100000.0",
                                "355000.0",
                            ],
                        ],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_etf_daily("2024-01-02")

        # Verify schema matches ETF_DAILY_SCHEMA
        expected_schema = {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation:
        # - vol->volume, pct_chg->pct_change
        # - knowledge_date = trade_date + 1
        assert result.to_dicts() == [
            {
                "source_ticker": "510300.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 3),
                "open": 3.5,
                "high": 3.6,
                "low": 3.4,
                "close": 3.55,
                "pre_close": 3.5,
                "volume": 100000.0,
                "amount": 355000.0,
                "pct_change": 1.5,
            },
        ]

    def test_fetch_etf_daily_empty_response(self, respx_mock) -> None:
        """Test fetch_etf_daily handles empty response."""

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": [
                            "ts_code",
                            "trade_date",
                            "pre_close",
                            "open",
                            "high",
                            "low",
                            "close",
                            "change",
                            "pct_chg",
                            "vol",
                            "amount",
                        ],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_etf_daily("2024-01-02")

        assert result.is_empty()


class TestTushareSourceStockBasic:
    """Tests for TushareSource.fetch_stock_basic."""

    def test_fetch_stock_basic_returns_dataframe(self, respx_mock) -> None:
        """Test fetch_stock_basic returns DataFrame with correct schema."""

        # Mock HTTP 响应 - stock_basic API
        # 现在 fetch_stock_basic 会分别查询 L、D、P 三种状态
        # 使用 side_effect 模拟多次调用
        call_count = 0

        def mock_response(request):
            nonlocal call_count
            call_count += 1
            # 第一次调用返回 L 状态，后续调用返回空数据
            if call_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "code": 0,
                        "msg": None,
                        "data": {
                            "fields": [
                                "ts_code",
                                "symbol",
                                "name",
                                "exchange",
                                "list_date",
                                "delist_date",
                                "list_status",
                            ],
                            "items": [
                                [
                                    "000001.SZ",
                                    "000001",
                                    "平安银行",
                                    "SZSE",
                                    "19910403",
                                    "",
                                    "L",
                                ],
                                [
                                    "600000.SH",
                                    "600000",
                                    "浦发银行",
                                    "SSE",
                                    "19991110",
                                    "",
                                    "L",
                                ],
                            ],
                        },
                    },
                )
            else:
                # D 和 P 状态返回空数据
                return httpx.Response(
                    200,
                    json={
                        "code": 0,
                        "msg": None,
                        "data": {
                            "fields": [
                                "ts_code",
                                "symbol",
                                "name",
                                "exchange",
                                "list_date",
                                "delist_date",
                                "list_status",
                            ],
                            "items": [],
                        },
                    },
                )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=mock_response)

        source = TushareSource(settings=_settings())
        result = source.fetch_stock_basic()

        # Verify schema - 现在包含 list_status 和 delist_date 字段
        assert dict(result.schema) == {
            "source_ticker": pl.String,
            "ticker": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
            "delist_date": pl.Date,
            "list_status": pl.String,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {
                "source_ticker": "000001.SZ",
                "ticker": "000001",
                "name": "平安银行",
                "exchange": "SZSE",
                "list_date": date(1991, 4, 3),
                "delist_date": None,
                "list_status": "L",
            },
            {
                "source_ticker": "600000.SH",
                "ticker": "600000",
                "name": "浦发银行",
                "exchange": "SSE",
                "list_date": date(1999, 11, 10),
                "delist_date": None,
                "list_status": "L",
            },
        ]

    def test_fetch_stock_basic_empty_response(self, respx_mock) -> None:
        """Test fetch_stock_basic handles empty response."""

        # Mock HTTP 响应 - 空数据（所有状态都返回空）
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": [
                            "ts_code",
                            "symbol",
                            "name",
                            "exchange",
                            "list_date",
                            "delist_date",
                            "list_status",
                        ],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_stock_basic()

        assert result.is_empty()

    def test_fetch_stock_basic_api_error_raises(
        self, tushare_source, respx_mock
    ) -> None:
        """Test fetch_stock_basic raises SourceFetchError on API error."""
        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(SourceFetchError):
            tushare_source.fetch_stock_basic()


class TestTushareSourceStockDaily:
    """Tests for TushareSource.fetch_stock_daily."""

    def test_fetch_stock_daily_returns_dataframe(self, respx_mock) -> None:
        """Test fetch_stock_daily returns DataFrame with correct schema."""

        # Mock HTTP 响应 - daily API
        # [REVIEW]: daily API 返回 vol, amount, pct_chg
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": [
                            "ts_code",
                            "trade_date",
                            "pre_close",
                            "open",
                            "high",
                            "low",
                            "close",
                            "change",
                            "pct_chg",
                            "vol",
                            "amount",
                        ],
                        "items": [
                            [
                                "000001.SZ",
                                "20240102",
                                "11.5",
                                "11.5",
                                "11.8",
                                "11.3",
                                "11.6",
                                "0.1",
                                "0.87",
                                "12500000.0",
                                "145000000.0",
                            ],
                        ],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_stock_daily("2024-01-02")

        # Verify schema matches STOCK_DAILY_SCHEMA
        expected_schema = {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation:
        # - vol->volume, pct_chg->pct_change
        # - knowledge_date = trade_date + 1
        assert result.to_dicts() == [
            {
                "source_ticker": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 3),
                "open": 11.5,
                "high": 11.8,
                "low": 11.3,
                "close": 11.6,
                "pre_close": 11.5,
                "volume": 12500000.0,
                "amount": 145000000.0,
                "pct_change": 0.87,
            },
        ]

    def test_fetch_stock_daily_empty_response(self, respx_mock) -> None:
        """Test fetch_stock_daily handles empty response."""

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": [
                            "ts_code",
                            "trade_date",
                            "pre_close",
                            "open",
                            "high",
                            "low",
                            "close",
                            "change",
                            "pct_chg",
                            "vol",
                            "amount",
                        ],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_stock_daily("2024-01-02")

        assert result.is_empty()

    def test_fetch_stock_daily_api_error_raises(
        self, tushare_source, respx_mock
    ) -> None:
        """Test fetch_stock_daily raises SourceFetchError on API error."""
        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(SourceFetchError):
            tushare_source.fetch_stock_daily("2024-01-02")


class TestTushareSourceAdjFactor:
    """Tests for TushareSource.fetch_adj_factor."""

    def test_fetch_adj_factor_returns_dataframe(self, respx_mock) -> None:
        """Test fetch_adj_factor returns DataFrame with correct schema."""

        # Mock HTTP 响应 - adj_factor API
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "trade_date", "adj_factor"],
                        "items": [
                            ["000001.SZ", "20240102", "1.2345"],
                            ["600000.SH", "20240102", "1.5678"],
                        ],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_adj_factor("2024-01-02")

        # Verify schema
        expected_schema = {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation (knowledge_date = trade_date)
        assert result.to_dicts() == [
            {
                "source_ticker": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.2345,
            },
            {
                "source_ticker": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.5678,
            },
        ]

    def test_fetch_adj_factor_empty_response(self, respx_mock) -> None:
        """Test fetch_adj_factor handles empty response."""

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "trade_date", "adj_factor"],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_adj_factor("2024-01-02")

        assert result.is_empty()

    def test_fetch_adj_factor_api_error_raises(
        self, tushare_source, respx_mock
    ) -> None:
        """Test fetch_adj_factor raises SourceFetchError on API error."""
        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(SourceFetchError):
            tushare_source.fetch_adj_factor("2024-01-02")


class TestTushareSourceFundAdj:
    """Tests for TushareSource.fetch_fund_adj."""

    def test_fetch_fund_adj_returns_dataframe(self, respx_mock) -> None:
        """Test fetch_fund_adj returns DataFrame with correct schema."""

        # Mock HTTP 响应 - fund_adj API
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "trade_date", "adj_factor"],
                        "items": [
                            ["510300.SH", "20240102", "1.0123"],
                            ["159919.SZ", "20240102", "1.0456"],
                        ],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_fund_adj("2024-01-02")

        # Verify schema
        expected_schema = {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation (knowledge_date = trade_date)
        assert result.to_dicts() == [
            {
                "source_ticker": "510300.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.0123,
            },
            {
                "source_ticker": "159919.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.0456,
            },
        ]

    def test_fetch_fund_adj_empty_response(self, respx_mock) -> None:
        """Test fetch_fund_adj handles empty response."""

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "trade_date", "adj_factor"],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource(settings=_settings())
        result = source.fetch_fund_adj("2024-01-02")

        assert result.is_empty()

    def test_fetch_fund_adj_api_error_raises(self, tushare_source, respx_mock) -> None:
        """Test fetch_fund_adj raises SourceFetchError on API error."""
        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(SourceFetchError):
            tushare_source.fetch_fund_adj("2024-01-02")


class TestTushareErrorHandler:
    """Tests for tushare_fetch_error_handler context manager."""

    def test_error_handler_re_raises_authentication_error(self) -> None:
        """Test context manager re-raises SourceAuthenticationError."""
        with pytest.raises(SourceAuthenticationError):
            with tushare_fetch_error_handler("test_dataset", "test_api"):
                raise SourceAuthenticationError("Auth failed")

    def test_error_handler_re_raises_rate_limit_error(self) -> None:
        """Test context manager re-raises SourceRateLimitError."""
        with pytest.raises(SourceRateLimitError):
            with tushare_fetch_error_handler("test_dataset", "test_api"):
                raise SourceRateLimitError("Rate limit exceeded")

    def test_error_handler_wraps_generic_exception(self) -> None:
        """Test context manager wraps generic exceptions as SourceFetchError."""
        with pytest.raises(SourceFetchError) as exc_info:
            with tushare_fetch_error_handler("test_dataset", "test_api"):
                raise ValueError("Generic error")

        # Verify错误信息包含原始错误
        assert "test_dataset" in str(exc_info.value)
        assert "Generic error" in exc_info.value.details.get("original_error", "")


class TestTushareSourceMacroIndicators:
    """Tests for TushareSource.fetch_macro_indicators."""

    def test_fetch_macro_indicators_delegates_to_macro_adapter(self, mocker) -> None:
        """fetch_macro_indicators 应委托给 macro adapter."""
        source = TushareSource(settings=_settings())
        expected = pl.DataFrame(
            {
                "indicator_code": ["SHIBOR_ON"],
                "indicator_name": ["隔夜Shibor"],
                "category": ["interest_rate"],
                "frequency": ["daily"],
                "need_pit": [False],
                "date": [date(2024, 1, 2)],
                "value": [1.91],
                "knowledge_date": [date(2024, 1, 3)],
            }
        )
        mocker.patch.object(
            source._macro,  # pyright: ignore[reportPrivateUsage]
            "fetch_macro_indicators",
            return_value=expected,
        )

        result = source.fetch_macro_indicators("2024-01-02")
        assert result.equals(expected)
