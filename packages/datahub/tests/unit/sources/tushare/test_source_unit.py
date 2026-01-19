"""Tests for TushareSource."""

import json
from datetime import date

import httpx
import polars as pl
import pytest
from ditto_datahub.sources.source import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.tushare_source import TushareSource


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
        assert dict(result.schema) == {
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
        assert dict(result.schema) == {
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


class TestTushareSourceFetchSuspendData:
    """Tests for TushareSource._fetch_suspend_data private method."""

    def test_fetch_suspend_data_returns_dataframe_with_data(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_suspend_data returns DataFrame with correct schema
        when data exists.
        """
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - suspend_d API
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "suspend_timing"],
                        "items": [
                            ["000001.SZ", "09:30-10:00"],
                            ["600000.SH", "13:00-14:30"],
                        ],
                    },
                },
            )
        )

        source = TushareSource()
        result = source._fetch_suspend_data("20240102")

        # Verify schema
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "suspend_timing": pl.String,
        }

        # Verify data
        assert result.to_dicts() == [
            {"ts_code": "000001.SZ", "suspend_timing": "09:30-10:00"},
            {"ts_code": "600000.SH", "suspend_timing": "13:00-14:30"},
        ]

    def test_fetch_suspend_data_returns_empty_dataframe_on_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_suspend_data returns empty DataFrame when API returns no data."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "suspend_timing"],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource()
        result = source._fetch_suspend_data("20240102")

        # Should return empty DataFrame with correct schema
        assert result.is_empty()
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "suspend_timing": pl.String,
        }

    def test_fetch_suspend_data_returns_empty_dataframe_on_api_error(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_suspend_data returns empty DataFrame on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()
        result = source._fetch_suspend_data("20240102")

        # Should return empty DataFrame with correct schema
        # (The method logs a warning but doesn't raise exception)
        assert result.is_empty()
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "suspend_timing": pl.String,
        }

    def test_fetch_suspend_data_passes_correct_date_format(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_suspend_data passes ts_date parameter to API correctly."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Track the request
        request_captured = []

        def capture_request(request):
            body = json.loads(request.content)
            request_captured.append(body)
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "suspend_timing"],
                        "items": [],
                    },
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=capture_request)

        source = TushareSource()
        # _fetch_suspend_data expects ts_date in YYYYMMDD format
        source._fetch_suspend_data("20240102")

        # Verify the date was passed correctly to the API
        assert len(request_captured) == 1
        assert request_captured[0]["params"]["suspend_date"] == "20240102"


class TestTushareSourceFetchStData:
    """Tests for TushareSource._fetch_st_data private method."""

    def test_fetch_st_data_returns_dataframe_with_data(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_st_data returns DataFrame with correct schema
        when data exists.
        """
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - stock_st API
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "name"],
                        "items": [
                            ["000001.SZ", "ST平安"],
                            ["600000.SH", "*ST浦发"],
                        ],
                    },
                },
            )
        )

        source = TushareSource()
        result = source._fetch_st_data()

        # Verify schema
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "name": pl.String,
        }

        # Verify data
        assert result.to_dicts() == [
            {"ts_code": "000001.SZ", "name": "ST平安"},
            {"ts_code": "600000.SH", "name": "*ST浦发"},
        ]

    def test_fetch_st_data_returns_empty_dataframe_on_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_st_data returns empty DataFrame when API returns no data."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "name"],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource()
        result = source._fetch_st_data()

        # Should return empty DataFrame with correct schema
        assert result.is_empty()
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "name": pl.String,
        }

    def test_fetch_st_data_returns_empty_dataframe_on_api_error(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_st_data returns empty DataFrame on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()
        result = source._fetch_st_data()

        # Should return empty DataFrame with correct schema
        # (The method logs a warning but doesn't raise exception)
        assert result.is_empty()
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "name": pl.String,
        }

    def test_fetch_st_data_does_not_require_date_parameter(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_st_data calls stock_st API without date parameter."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Track the request
        request_captured = []

        def capture_request(request):
            body = json.loads(request.content)
            request_captured.append(body)
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "name"],
                        "items": [],
                    },
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=capture_request)

        source = TushareSource()
        source._fetch_st_data()

        # Verify the API was called without date parameter
        assert len(request_captured) == 1
        request_body = request_captured[0]
        assert request_body["api_name"] == "stock_st"
        assert request_body["fields"] == "ts_code,name"
        # Verify no date parameter in params
        assert "suspend_date" not in request_body["params"]
        assert "trade_date" not in request_body["params"]


class TestTushareSourceFetchListStatusData:
    """Tests for TushareSource._fetch_list_status_data private method."""

    def test_fetch_list_status_data_returns_dataframe_with_data(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_list_status_data returns DataFrame with correct schema
        when data exists.
        """
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - stock_basic API
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "list_status"],
                        "items": [
                            ["000001.SZ", "L"],
                            ["600000.SH", "L"],
                            ["000002.SZ", "D"],
                        ],
                    },
                },
            )
        )

        source = TushareSource()
        result = source._fetch_list_status_data()

        # Verify schema
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "list_status": pl.String,
        }

        # Verify data
        assert result.to_dicts() == [
            {"ts_code": "000001.SZ", "list_status": "L"},
            {"ts_code": "600000.SH", "list_status": "L"},
            {"ts_code": "000002.SZ", "list_status": "D"},
        ]

    def test_fetch_list_status_data_returns_empty_dataframe_on_empty_response(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_list_status_data returns empty DataFrame on empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - 空数据
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "list_status"],
                        "items": [],
                    },
                },
            )
        )

        source = TushareSource()
        result = source._fetch_list_status_data()

        # Should return empty DataFrame with correct schema
        assert result.is_empty()
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "list_status": pl.String,
        }

    def test_fetch_list_status_data_returns_empty_dataframe_on_api_error(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_list_status_data returns empty DataFrame on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock HTTP 响应 - API 错误
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        source = TushareSource()
        result = source._fetch_list_status_data()

        # Should return empty DataFrame with correct schema
        # (The method logs a warning but doesn't raise exception)
        assert result.is_empty()
        assert dict(result.schema) == {
            "ts_code": pl.String,
            "list_status": pl.String,
        }

    def test_fetch_list_status_data_does_not_require_date_parameter(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _fetch_list_status_data calls stock_basic API without date parameter."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Track the request
        request_captured = []

        def capture_request(request):
            body = json.loads(request.content)
            request_captured.append(body)
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["ts_code", "list_status"],
                        "items": [],
                    },
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=capture_request)

        source = TushareSource()
        source._fetch_list_status_data()

        # Verify the API was called correctly
        assert len(request_captured) == 1
        request_body = request_captured[0]
        assert request_body["api_name"] == "stock_basic"
        assert request_body["fields"] == "ts_code,list_status"
        # Verify no date parameter in params (stock_basic doesn't need date)
        assert "suspend_date" not in request_body["params"]
        assert "trade_date" not in request_body["params"]


class TestTushareSourceMergeStatusData:
    """Tests for TushareSource._merge_status_data private method."""

    def test_merge_status_data_with_all_sources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _merge_status_data merges all three data sources correctly."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Prepare test data
        list_status_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH", "000002.SZ"],
                "list_status": ["L", "L", "D"],
            }
        )

        suspend_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "suspend_timing": ["09:30-10:00", "13:00-14:30"],
            }
        )

        st_df = pl.DataFrame(
            {
                "ts_code": ["600000.SH", "000002.SZ"],
                "name": ["*ST浦发", "ST平安"],
            }
        )

        source = TushareSource()
        result = source._merge_status_data(
            list_status_df, suspend_df, st_df, "2024-01-02"
        )

        # Verify schema
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "is_suspended": pl.Boolean,
            "suspend_timing": pl.String,
            "is_st": pl.Boolean,
            "st_type": pl.String,
            "list_status": pl.String,
        }
        assert result.schema == expected_schema

        # Verify data
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "is_suspended": True,
                "suspend_timing": "09:30-10:00",
                "is_st": False,
                "st_type": "",
                "list_status": "L",
            },
            {
                "src_code": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "is_suspended": True,
                "suspend_timing": "13:00-14:30",
                "is_st": True,
                "st_type": "*ST浦发",
                "list_status": "L",
            },
            {
                "src_code": "000002.SZ",
                "trade_date": date(2024, 1, 2),
                "is_suspended": False,
                "suspend_timing": "",
                "is_st": True,
                "st_type": "ST平安",
                "list_status": "D",
            },
        ]

    def test_merge_status_data_with_empty_suspend_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _merge_status_data handles empty suspend_df correctly."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Prepare test data - suspend_df is empty
        list_status_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "list_status": ["L", "L"],
            }
        )

        suspend_df = pl.DataFrame(
            schema={"ts_code": pl.String, "suspend_timing": pl.String}
        )

        st_df = pl.DataFrame(
            {
                "ts_code": ["600000.SH"],
                "name": ["*ST浦发"],
            }
        )

        source = TushareSource()
        result = source._merge_status_data(
            list_status_df, suspend_df, st_df, "2024-01-02"
        )

        # Verify data - suspend columns should be False/empty
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "is_suspended": False,
                "suspend_timing": "",
                "is_st": False,
                "st_type": "",
                "list_status": "L",
            },
            {
                "src_code": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "is_suspended": False,
                "suspend_timing": "",
                "is_st": True,
                "st_type": "*ST浦发",
                "list_status": "L",
            },
        ]

    def test_merge_status_data_with_empty_st_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _merge_status_data handles empty st_df correctly."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Prepare test data - st_df is empty
        list_status_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "list_status": ["L", "L"],
            }
        )

        suspend_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "suspend_timing": ["09:30-10:00"],
            }
        )

        st_df = pl.DataFrame(schema={"ts_code": pl.String, "name": pl.String})

        source = TushareSource()
        result = source._merge_status_data(
            list_status_df, suspend_df, st_df, "2024-01-02"
        )

        # Verify data - ST columns should be False/empty
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "is_suspended": True,
                "suspend_timing": "09:30-10:00",
                "is_st": False,
                "st_type": "",
                "list_status": "L",
            },
            {
                "src_code": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "is_suspended": False,
                "suspend_timing": "",
                "is_st": False,
                "st_type": "",
                "list_status": "L",
            },
        ]

    def test_merge_status_data_with_all_empty_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _merge_status_data handles all empty data sources correctly."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Prepare test data - all empty except list_status
        list_status_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "list_status": ["L"],
            }
        )

        suspend_df = pl.DataFrame(
            schema={"ts_code": pl.String, "suspend_timing": pl.String}
        )

        st_df = pl.DataFrame(schema={"ts_code": pl.String, "name": pl.String})

        source = TushareSource()
        result = source._merge_status_data(
            list_status_df, suspend_df, st_df, "2024-01-02"
        )

        # Verify data - all optional columns should be False/empty
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "is_suspended": False,
                "suspend_timing": "",
                "is_st": False,
                "st_type": "",
                "list_status": "L",
            },
        ]

    def test_merge_status_data_default_list_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _merge_status_data fills null list_status with 'L' (正常)."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Prepare test data - list_status contains null
        list_status_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "list_status": ["L", None],
            }
        )

        suspend_df = pl.DataFrame(
            schema={"ts_code": pl.String, "suspend_timing": pl.String}
        )

        st_df = pl.DataFrame(schema={"ts_code": pl.String, "name": pl.String})

        source = TushareSource()
        result = source._merge_status_data(
            list_status_df, suspend_df, st_df, "2024-01-02"
        )

        # Verify data - null list_status should be filled with 'L'
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "is_suspended": False,
                "suspend_timing": "",
                "is_st": False,
                "st_type": "",
                "list_status": "L",
            },
            {
                "src_code": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "is_suspended": False,
                "suspend_timing": "",
                "is_st": False,
                "st_type": "",
                "list_status": "L",  # Filled with default
            },
        ]
