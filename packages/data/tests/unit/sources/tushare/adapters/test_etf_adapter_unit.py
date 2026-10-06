"""ETFTushareAdapter universe 边界测试（#513）.

fund_daily/fund_adj/fund_nav 的全市场响应会混入 LOF 等非 ETF 品种
（Tushare #1891），adapter 统一按 etf_basic universe 交集过滤（按日）
并拒绝非 universe 标的（按标的）。
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_data.errors.network import SourceFetchError
from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter

_ETF = "510300.SH"
_ETF_2 = "159915.SZ"
_LOF = "160707.SZ"


def _etf_basic_response() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts_code": [_ETF, _ETF_2],
            "csname": ["沪深300ETF", "创业板ETF"],
            "list_date": ["20120504", "20110909"],
            "list_status": ["L", "L"],
            "index_code": ["000300.SH", "399006.SZ"],
            "etf_type": ["指数型", "指数型"],
        }
    )


def _fund_daily_response() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts_code": [_ETF, _LOF, _ETF_2],
            "trade_date": ["20240329"] * 3,
            "open": [4.0, 1.0, 2.0],
            "high": [4.1, 1.1, 2.1],
            "low": [3.9, 0.9, 1.9],
            "close": [4.05, 1.05, 2.05],
            "pre_close": [4.0, 1.0, 2.0],
            "vol": [1000.0, 10.0, 500.0],
            "amount": [4000.0, 10.0, 1000.0],
            "pct_chg": [1.25, 5.0, 2.5],
        }
    )


def _client_mock(mocker, responses: dict[str, pl.DataFrame]):
    client = mocker.Mock()
    client.query.side_effect = lambda **kw: responses[kw["api_name"]]
    return client


class TestFundDailyUniverseIntersection:
    """fund_daily 按日拉取与 etf_basic universe 交集（#513）."""

    def test_by_date_drops_non_etf_rows(self, mocker) -> None:
        client = _client_mock(
            mocker,
            {
                "etf_basic": _etf_basic_response(),
                "fund_daily": _fund_daily_response(),
            },
        )
        adapter = ETFTushareAdapter(_client=client)

        result = adapter.fetch_etf_daily(trade_date="2024-03-29")

        assert result["source_ticker"].to_list() == [_ETF, _ETF_2]
        assert _LOF not in result["source_ticker"].to_list()

    def test_universe_cached_across_fetches(self, mocker) -> None:
        client = _client_mock(
            mocker,
            {
                "etf_basic": _etf_basic_response(),
                "fund_daily": _fund_daily_response(),
            },
        )
        adapter = ETFTushareAdapter(_client=client)

        adapter.fetch_etf_daily(trade_date="2024-03-29")
        adapter.fetch_etf_daily(trade_date="2024-04-01")

        etf_basic_calls = [
            c
            for c in client.query.call_args_list
            if c.kwargs["api_name"] == "etf_basic"
        ]
        assert len(etf_basic_calls) == 1

    def test_by_date_all_non_etf_returns_empty(self, mocker) -> None:
        client = _client_mock(
            mocker,
            {
                "etf_basic": _etf_basic_response(),
                "fund_daily": _fund_daily_response().filter(pl.col("ts_code") == _LOF),
            },
        )
        adapter = ETFTushareAdapter(_client=client)

        result = adapter.fetch_etf_daily(trade_date="2024-03-29")

        assert result.is_empty()

    def test_empty_universe_fails_closed(self, mocker) -> None:
        client = _client_mock(
            mocker,
            {
                "etf_basic": _etf_basic_response().clear(),
                "fund_daily": _fund_daily_response(),
            },
        )
        adapter = ETFTushareAdapter(_client=client)

        with pytest.raises(SourceFetchError, match="etf_basic"):
            adapter.fetch_etf_daily(trade_date="2024-03-29")


class TestTickerModeUniverseGuard:
    """按标的模式拒绝非 ETF 品种（#513）."""

    def test_fund_daily_ticker_rejects_lof(self, mocker) -> None:
        client = _client_mock(mocker, {"etf_basic": _etf_basic_response()})
        adapter = ETFTushareAdapter(_client=client)

        with pytest.raises(ValueError, match="not in the etf_basic universe"):
            adapter.fetch_etf_daily(
                source_ticker=_LOF,
                start_date="2024-01-01",
                end_date="2024-03-29",
            )

    def test_fund_daily_ticker_accepts_etf(self, mocker) -> None:
        client = _client_mock(
            mocker,
            {
                "etf_basic": _etf_basic_response(),
                "fund_daily": _fund_daily_response().filter(pl.col("ts_code") == _ETF),
            },
        )
        adapter = ETFTushareAdapter(_client=client)

        result = adapter.fetch_etf_daily(
            source_ticker=_ETF,
            start_date="2024-01-01",
            end_date="2024-03-29",
        )

        assert result["source_ticker"].unique().to_list() == [_ETF]

    def test_fund_adj_ticker_rejects_lof(self, mocker) -> None:
        client = _client_mock(mocker, {"etf_basic": _etf_basic_response()})
        adapter = ETFTushareAdapter(_client=client)

        with pytest.raises(ValueError, match="not in the etf_basic universe"):
            adapter.fetch_fund_adj(
                source_ticker=_LOF,
                start_date="2024-01-01",
                end_date="2024-03-29",
            )


class TestFundAdjUniverseIntersection:
    """fund_adj 按日拉取同样与 universe 交集（同根修复）."""

    def test_by_date_drops_non_etf_rows(self, mocker) -> None:
        client = _client_mock(
            mocker,
            {
                "etf_basic": _etf_basic_response(),
                "fund_adj": pl.DataFrame(
                    {
                        "ts_code": [_ETF, _LOF],
                        "trade_date": ["20240329", "20240329"],
                        "adj_factor": [1.0, 3.5],
                    }
                ),
            },
        )
        adapter = ETFTushareAdapter(_client=client)

        result = adapter.fetch_fund_adj(trade_date="2024-03-29")

        assert result["source_ticker"].to_list() == [_ETF]


class TestFundNavUniverseIntersection:
    """fund_nav 全市场滚动窗拉取同样与 universe 交集（同根修复）."""

    def test_window_drops_non_etf_rows(self, mocker) -> None:
        nav_row = {
            "ts_code": [_ETF, _LOF],
            "ann_date": ["20240401", "20240401"],
            "nav_date": ["20240329", "20240329"],
            "unit_nav": [4.05, 1.05],
            "acc_nav": [4.2, 1.1],
        }
        client = _client_mock(
            mocker,
            {
                "etf_basic": _etf_basic_response(),
                "fund_nav": pl.DataFrame(nav_row),
            },
        )
        adapter = ETFTushareAdapter(_client=client)

        result = adapter.fetch_fund_nav(trade_date="2024-04-01")

        assert result["source_ticker"].unique().to_list() == [_ETF]

    def test_ticker_mode_rejects_lof(self, mocker) -> None:
        client = _client_mock(mocker, {"etf_basic": _etf_basic_response()})
        adapter = ETFTushareAdapter(_client=client)

        with pytest.raises(ValueError, match="not in the etf_basic universe"):
            adapter.fetch_fund_nav(
                source_ticker=_LOF,
                start_date="2024-01-01",
                end_date="2024-03-29",
            )
