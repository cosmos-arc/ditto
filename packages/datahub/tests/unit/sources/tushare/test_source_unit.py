"""Tests for TushareSource."""

from datetime import date

import httpx
import polars as pl
import pytest
from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.source import TushareSource


class TestTushareSourceCalendar:
    """Tests for TushareSource.fetch_calendar."""

    def test_fetch_calendar_returns_dataframe(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_calendar returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_calendar("2024-01-01", "2024-01-03")

        # Verify schema
        assert result.schema == {
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {"trade_date": date(2024, 1, 1), "is_open": False},
            {"trade_date": date(2024, 1, 2), "is_open": True},
            {"trade_date": date(2024, 1, 3), "is_open": True},
        ]

    def test_fetch_calendar_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_calendar handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_calendar("2024-01-01", "2024-01-03")

        assert result.is_empty()

    def test_fetch_calendar_api_error_raises(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_calendar raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()

        with pytest.raises(SourceFetchError):
            source.fetch_calendar("2024-01-01", "2024-01-03")


class TestTushareSourceEtfBasic:
    """Tests for TushareSource.fetch_etf_basic."""

    def test_fetch_etf_basic_returns_dataframe(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_etf_basic returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - fund_basic API
        # 注意: fund_basic 返回 ts_code, name, exchange, list_date
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "name", "exchange", "list_date"],
                        "items": [
                            ["510300.SH", "沪深300ETF", "SSE", "20120706"],
                            ["159919.SZ", "沪深300ETF", "SZSE", "20190624"],
                        ],
                    },
                },
            )
        )

        source = TushareSource()
        result = source.fetch_etf_basic()

        # Verify schema
        assert result.schema == {
            "src_code": pl.String,
            "symbol": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {
                "src_code": "510300.SH",
                "symbol": "510300",
                "name": "沪深300ETF",
                "exchange": "SSE",
                "list_date": date(2012, 7, 6),
            },
            {
                "src_code": "159919.SZ",
                "symbol": "159919",
                "name": "沪深300ETF",
                "exchange": "SZSE",
                "list_date": date(2019, 6, 24),
            },
        ]

    def test_fetch_etf_basic_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_etf_basic handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "name", "exchange", "list_date"],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource()
        result = source.fetch_etf_basic()

        assert result.is_empty()


class TestTushareSourceEtfDaily:
    """Tests for TushareSource.fetch_etf_daily."""

    def test_fetch_etf_daily_returns_dataframe(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_etf_daily returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - fund_daily API
        # 注意: fund_daily 返回 vol, amount, pct_chg
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

        source = TushareSource()
        result = source.fetch_etf_daily("2024-01-02")

        # Verify schema matches ETF_DAILY_SCHEMA
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
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

        # Verify data transformation (vol->volume, pct_chg->pct_change)
        assert result.to_dicts() == [
            {
                "src_code": "510300.SH",
                "trade_date": date(2024, 1, 2),
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

    def test_fetch_etf_daily_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_etf_daily handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_etf_daily("2024-01-02")

        assert result.is_empty()


class TestTushareSourceStockBasic:
    """Tests for TushareSource.fetch_stock_basic."""

    def test_fetch_stock_basic_returns_dataframe(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_stock_basic returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - stock_basic API
        # 注意: stock_basic API 返回 ts_code, symbol, name, exchange, list_date
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
                        ],
                        "items": [
                            ["000001.SZ", "000001", "平安银行", "SZSE", "19910403"],
                            ["600000.SH", "600000", "浦发银行", "SSE", "19991110"],
                        ],
                    },
                },
            )
        )

        source = TushareSource()
        result = source.fetch_stock_basic()

        # Verify schema
        assert result.schema == {
            "src_code": pl.String,
            "symbol": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "exchange": "SZSE",
                "list_date": date(1991, 4, 3),
            },
            {
                "src_code": "600000.SH",
                "symbol": "600000",
                "name": "浦发银行",
                "exchange": "SSE",
                "list_date": date(1999, 11, 10),
            },
        ]

    def test_fetch_stock_basic_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_stock_basic handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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
                            "symbol",
                            "name",
                            "exchange",
                            "list_date",
                        ],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource()
        result = source.fetch_stock_basic()

        assert result.is_empty()

    def test_fetch_stock_basic_api_error_raises(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_stock_basic raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()

        with pytest.raises(SourceFetchError):
            source.fetch_stock_basic()


class TestTushareSourceStockDaily:
    """Tests for TushareSource.fetch_stock_daily."""

    def test_fetch_stock_daily_returns_dataframe(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_stock_daily returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - daily API
        # 注意: daily API 返回 vol, amount, pct_chg
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

        source = TushareSource()
        result = source.fetch_stock_daily("2024-01-02")

        # Verify schema matches STOCK_DAILY_SCHEMA
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
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

        # Verify data transformation (vol->volume, pct_chg->pct_change)
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
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

    def test_fetch_stock_daily_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_stock_daily handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_stock_daily("2024-01-02")

        assert result.is_empty()

    def test_fetch_stock_daily_api_error_raises(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_stock_daily raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()

        with pytest.raises(SourceFetchError):
            source.fetch_stock_daily("2024-01-02")


class TestTushareSourceAdjFactor:
    """Tests for TushareSource.fetch_adj_factor."""

    def test_fetch_adj_factor_returns_dataframe(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_adj_factor returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_adj_factor("2024-01-02")

        # Verify schema
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation (knowledge_date = trade_date)
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.2345,
            },
            {
                "src_code": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.5678,
            },
        ]

    def test_fetch_adj_factor_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_adj_factor handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_adj_factor("2024-01-02")

        assert result.is_empty()

    def test_fetch_adj_factor_api_error_raises(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_adj_factor raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()

        with pytest.raises(SourceFetchError):
            source.fetch_adj_factor("2024-01-02")


class TestTushareSourceFundAdj:
    """Tests for TushareSource.fetch_fund_adj."""

    def test_fetch_fund_adj_returns_dataframe(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_fund_adj returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_fund_adj("2024-01-02")

        # Verify schema
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation (knowledge_date = trade_date)
        assert result.to_dicts() == [
            {
                "src_code": "510300.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.0123,
            },
            {
                "src_code": "159919.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.0456,
            },
        ]

    def test_fetch_fund_adj_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_fund_adj handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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

        source = TushareSource()
        result = source.fetch_fund_adj("2024-01-02")

        assert result.is_empty()

    def test_fetch_fund_adj_api_error_raises(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fetch_fund_adj raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()

        with pytest.raises(SourceFetchError):
            source.fetch_fund_adj("2024-01-02")


class TestTushareSourceErrorHandler:
    """Tests for TushareSource._tushare_fetch_error_handler context manager."""

    def test_error_handler_re_raises_authentication_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test context manager re-raises SourceAuthenticationError."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
        source = TushareSource()

        # 验证方法存在（会失败因为还未实现）
        assert hasattr(source, "_tushare_fetch_error_handler")

        # 测试认证错误直接抛出
        with pytest.raises(SourceAuthenticationError):
            with source._tushare_fetch_error_handler("test_dataset", "test_api"):
                raise SourceAuthenticationError("Auth failed")

    def test_error_handler_re_raises_rate_limit_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test context manager re-raises SourceRateLimitError."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
        source = TushareSource()

        # 测试限流错误直接抛出
        with pytest.raises(SourceRateLimitError):
            with source._tushare_fetch_error_handler("test_dataset", "test_api"):
                raise SourceRateLimitError("Rate limit exceeded")

    def test_error_handler_wraps_generic_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test context manager wraps generic exceptions as SourceFetchError."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
        source = TushareSource()

        # 测试普通异常被包装为 SourceFetchError
        with pytest.raises(SourceFetchError) as exc_info:
            with source._tushare_fetch_error_handler("test_dataset", "test_api"):
                raise ValueError("Generic error")

        # 验证错误信息包含原始错误
        assert "test_dataset" in str(exc_info.value)
        assert "Generic error" in exc_info.value.details.get("original_error", "")
