"""Unit tests for Tushare fundamental/capital source helper functions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare import fundamental_source


def _frame(label: str) -> pl.DataFrame:
    return pl.DataFrame({"dataset": [label]})


@pytest.mark.unit
class TestFundamentalSourceWrappers:
    """Fundamental wrappers delegate with source-level date compaction."""

    @pytest.mark.parametrize(
        ("fetch_fn", "vip_method"),
        [
            (fundamental_source.fetch_balance_sheet, "fetch_balance_sheet_vip"),
            (fundamental_source.fetch_income_statement, "fetch_income_statement_vip"),
            (fundamental_source.fetch_cash_flow, "fetch_cash_flow_vip"),
        ],
    )
    def test_financial_statement_trade_date_pulls_quarter_periods(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        vip_method: str,
    ) -> None:
        """Financial statement wrappers pull trailing quarter periods on trade_date."""
        fundamental = MagicMock()
        frame = pl.DataFrame({"dataset": ["vip"], "knowledge_date": [date(2024, 5, 6)]})
        getattr(fundamental, vip_method).return_value = frame

        result = fetch_fn(fundamental, trade_date="2024-05-06")

        assert result["dataset"].unique().to_list() == ["vip"]
        assert result.height == 8  # 8 个报告期超集拼接
        calls = getattr(fundamental, vip_method).call_args_list
        assert [call.kwargs["period"] for call in calls] == [
            "20240331",
            "20231231",
            "20230930",
            "20230630",
            "20230331",
            "20221231",
            "20220930",
            "20220630",
        ]

    def test_dividend_trade_date_delegates_with_compact_ex_date(self) -> None:
        """Dividend wrapper compacts trade_date to ex_date."""
        fundamental = MagicMock()
        fundamental.fetch_dividend.return_value = _frame("dividend")

        result = fundamental_source.fetch_dividend(fundamental, trade_date="2024-05-06")

        assert result["dataset"].item() == "dividend"
        fundamental.fetch_dividend.assert_called_once_with(ex_date="20240506")

    def test_corporate_actions_delegates_with_exact_announcement_date(self) -> None:
        """Corporate-action wrapper compacts trade_date to announcement date."""
        fundamental = MagicMock()
        fundamental.fetch_corporate_actions.return_value = _frame("actions")

        result = fundamental_source.fetch_corporate_actions(fundamental, "2024-05-06")

        assert result["dataset"].item() == "actions"
        fundamental.fetch_corporate_actions.assert_called_once_with(ann_date="20240506")


@pytest.mark.unit
class TestCapitalSourceDelegates:
    """Capital source helper query mode behavior."""

    @pytest.mark.parametrize(
        ("fetch_fn", "method_name"),
        [
            (fundamental_source.fetch_valuation_metrics, "fetch_valuation_metrics"),
            (fundamental_source.fetch_margin_trading, "fetch_margin_trading"),
        ],
    )
    def test_date_batch_mode_compacts_trade_date(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        method_name: str,
    ) -> None:
        """Date-batch mode forwards a compact Tushare trade_date."""
        capital = MagicMock()
        getattr(capital, method_name).return_value = _frame(method_name)

        result = fetch_fn(capital, trade_date="2024-05-06")

        assert result["dataset"].item() == method_name
        getattr(capital, method_name).assert_called_once_with(trade_date="20240506")

    @pytest.mark.parametrize(
        ("fetch_fn", "method_name"),
        [
            (fundamental_source.fetch_valuation_metrics, "fetch_valuation_metrics"),
            (fundamental_source.fetch_margin_trading, "fetch_margin_trading"),
        ],
    )
    def test_ticker_mode_compacts_optional_range(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        method_name: str,
    ) -> None:
        """Ticker mode forwards source ticker and compact optional dates."""
        capital = MagicMock()
        getattr(capital, method_name).return_value = _frame(method_name)

        result = fetch_fn(
            capital,
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert result["dataset"].item() == method_name
        getattr(capital, method_name).assert_called_once_with(
            ts_code="000001.SZ",
            start_date="20240101",
            end_date="20241231",
        )

    @pytest.mark.parametrize(
        ("fetch_fn", "method_name"),
        [
            (fundamental_source.fetch_valuation_metrics, "fetch_valuation_metrics"),
            (fundamental_source.fetch_margin_trading, "fetch_margin_trading"),
        ],
    )
    def test_ticker_mode_forwards_missing_range_as_none(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        method_name: str,
    ) -> None:
        """Ticker mode can query a symbol without a bounded range."""
        capital = MagicMock()
        getattr(capital, method_name).return_value = _frame(method_name)

        fetch_fn(capital, source_ticker="000001.SZ")

        getattr(capital, method_name).assert_called_once_with(
            ts_code="000001.SZ",
            start_date=None,
            end_date=None,
        )

    def test_pledge_ratio_trade_date_resolves_weekly_snapshot(self) -> None:
        """Pledge ratio date-batch mode resolves the latest Friday ≤ trade_date.

        pledge_stat 的 end_date 是周快照日精确匹配（非快照日返回空），
        非周五的交易日必须映射到最近的周快照日。
        """
        capital = MagicMock()
        capital.fetch_pledge_ratio.return_value = _frame("pledge")

        result = fundamental_source.fetch_pledge_ratio(capital, trade_date="2024-03-31")

        assert result["dataset"].item() == "pledge"
        # 2024-03-31 是周日，≤该日的最近周五是 2024-03-29
        capital.fetch_pledge_ratio.assert_called_once_with(report_date="20240329")

    @pytest.mark.parametrize(
        ("trade_date", "expected_snapshot"),
        [
            ("2024-03-29", "20240329"),  # 周五本身
            ("2024-03-30", "20240329"),  # 周六
            ("2024-04-01", "20240329"),  # 下周一仍属上一快照周
            ("2024-04-04", "20240329"),  # 周四 -> 上一周五（≤D 的最近快照）
        ],
    )
    def test_pledge_snapshot_date_mapping(
        self, trade_date: str, expected_snapshot: str
    ) -> None:
        """Snapshot mapping covers Friday/self, weekend, and Monday cases."""
        assert fundamental_source._pledge_snapshot_date(trade_date) == expected_snapshot

    def test_pledge_ratio_ticker_mode_ignores_range(self) -> None:
        """Pledge ratio API only forwards source ticker in ticker mode."""
        capital = MagicMock()
        capital.fetch_pledge_ratio.return_value = _frame("pledge")

        result = fundamental_source.fetch_pledge_ratio(
            capital,
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert result["dataset"].item() == "pledge"
        capital.fetch_pledge_ratio.assert_called_once_with(ts_code="000001.SZ")

    @pytest.mark.parametrize(
        "fetch_fn",
        [
            fundamental_source.fetch_valuation_metrics,
            fundamental_source.fetch_margin_trading,
            fundamental_source.fetch_pledge_ratio,
        ],
    )
    def test_trade_date_and_source_ticker_are_mutually_exclusive(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
    ) -> None:
        """Capital delegates reject ambiguous query modes."""
        with pytest.raises(ValueError, match="互斥"):
            fetch_fn(
                MagicMock(),
                trade_date="2024-05-06",
                source_ticker="000001.SZ",
            )

    @pytest.mark.parametrize(
        "fetch_fn",
        [
            fundamental_source.fetch_valuation_metrics,
            fundamental_source.fetch_margin_trading,
            fundamental_source.fetch_pledge_ratio,
        ],
    )
    def test_requires_one_query_mode(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
    ) -> None:
        """Capital delegates require date-batch or ticker mode."""
        with pytest.raises(ValueError, match="必须指定"):
            fetch_fn(MagicMock())

    @pytest.mark.parametrize(
        ("fetch_fn", "missing_kwargs"),
        [
            (fundamental_source.fetch_valuation_metrics, {"source_ticker": ""}),
            (fundamental_source.fetch_margin_trading, {"source_ticker": ""}),
            (fundamental_source.fetch_pledge_ratio, {"source_ticker": ""}),
        ],
    )
    def test_blank_source_ticker_is_missing(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        missing_kwargs: dict[str, Any],
    ) -> None:
        """Blank source tickers are treated as missing query modes."""
        with pytest.raises(ValueError, match="必须指定"):
            fetch_fn(MagicMock(), **missing_kwargs)


def _income_raw_rows() -> list[dict[str, object]]:
    return [
        # 同披露 update_flag 0/1 两行（值不同时也不允许双写，取 1）
        {
            "ts_code": "600519.SH",
            "end_date": "20260630",
            "f_ann_date": "20260815",
            "report_type": "1",
            "update_flag": "0",
            "total_revenue": 92.0e10,
            "revenue": 90.0e10,
            "operate_cost": 55.0e9,
            "sale_exp": 16.0e9,
            "admin_exp": 18.0e9,
            "fin_exp": 0.1e9,
            "rd_exp": 0.6e9,
            "operate_profit": 61.0e10,
            "total_profit": 61.4e10,
            "income_tax": 15.0e10,
            "n_income": 46.0e10,
            "basic_eps": 35.56,
            "diluted_eps": 35.56,
        },
        {
            "ts_code": "600519.SH",
            "end_date": "20260630",
            "f_ann_date": "20260815",
            "report_type": "1",
            "update_flag": "1",
            "total_revenue": 92.2783e10,
            "revenue": 90.7033e10,
            "operate_cost": 55.2073e9,
            "sale_exp": 16.0576e9,
            "admin_exp": 18.5376e9,
            "fin_exp": 0.1e9,
            "rd_exp": 0.6e9,
            "operate_profit": 61.4113e10,
            "total_profit": 61.4384e10,
            "income_tax": 15.4051e10,
            "n_income": 46.0333e10,
            "basic_eps": 35.57,
            "diluted_eps": 35.57,
        },
        # 非合并报表类型行（type 2 单季）：排除
        {
            "ts_code": "600519.SH",
            "end_date": "20260630",
            "f_ann_date": "20260815",
            "report_type": "2",
            "update_flag": "1",
            "total_revenue": 41.0e10,
            "revenue": 40.0e10,
            "operate_cost": 20.0e9,
            "sale_exp": 8.0e9,
            "admin_exp": 9.0e9,
            "fin_exp": 0.0,
            "rd_exp": 0.3e9,
            "operate_profit": 28.0e10,
            "total_profit": 28.1e10,
            "income_tax": 7.0e10,
            "n_income": 21.0e10,
            "basic_eps": 16.7,
            "diluted_eps": 16.7,
        },
    ]


@pytest.mark.unit
class TestFinancialStatementWindowRowIdentity:
    """#482：窗口模式行身份过滤（update_flag 去重 + 合并报表口径）。"""

    def _adapter(self, rows: list[dict[str, object]]) -> Any:
        from ditto_data.sources.tushare.adapters.fundamental import (
            FundamentalTushareAdapter,
        )

        adapter = FundamentalTushareAdapter.__new__(FundamentalTushareAdapter)
        adapter._client = MagicMock()
        adapter._client.query.return_value = pl.DataFrame(rows)
        return adapter

    def test_window_rows_collapse_to_latest_consolidated(self) -> None:
        """update_flag 0/1 同披露 → 取 1（最新值）；type 2 行排除。"""
        adapter = self._adapter(_income_raw_rows())

        frame = adapter.fetch_income_statement(
            ts_code="600519.SH", start_date="20240101", end_date="20261005"
        )

        assert frame.height == 1
        row = frame.row(0, named=True)
        assert row["net_profit"] == pytest.approx(46.0333e10)
        assert row["eps"] == pytest.approx(35.57)
        # 身份列不进输出帧
        assert "update_flag" not in frame.columns
        assert "report_type" not in frame.columns
        # 请求字段携带身份列
        fields = adapter._client.query.call_args.kwargs["fields"]
        assert "report_type" in fields
        assert "update_flag" in fields

    def test_distinct_disclosures_both_kept(self) -> None:
        """不同披露日（修订 vintage）各自成行，不跨 vintage 合并。"""
        rows = _income_raw_rows()
        revised = dict(rows[1])
        revised["f_ann_date"] = "20260901"
        revised["n_income"] = 46.10e10
        adapter = self._adapter([*rows, revised])

        frame = adapter.fetch_income_statement(
            ts_code="600519.SH", start_date="20240101", end_date="20261005"
        )

        assert frame.height == 2
        assert sorted(frame["knowledge_date"].to_list()) == [
            date(2026, 8, 15),
            date(2026, 9, 1),
        ]


@pytest.mark.unit
class TestFetchFundNavDelegation:
    """#483：fund_nav 双模式委托与窗口回看参数."""

    def test_trade_date_mode_passes_rolling_window(self) -> None:
        from ditto_data.sources.tushare.etf_index_source import fetch_fund_nav

        etf = MagicMock()
        fetch_fund_nav(etf, trade_date="2026-09-30")

        etf.fetch_fund_nav.assert_called_once_with(
            trade_date="2026-09-30",
            source_ticker=None,
            start_date=None,
            end_date=None,
        )

    def test_ticker_mode_requires_range(self) -> None:
        from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter

        adapter = ETFTushareAdapter(_client=MagicMock())
        # 聚焦 nav 参数校验：预热 universe 缓存避免 etf_basic 请求
        adapter._etf_universe = frozenset({"510300.SH"})
        with pytest.raises(ValueError, match="start_date 和 end_date"):
            adapter.fetch_fund_nav(source_ticker="510300.SH")

    def test_trade_date_mode_queries_rolling_nav_window(self) -> None:
        from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter

        # adapter._client 静态收窄为 TushareClient；mock 记录/回值经
        # 边界变量单点访问（同一对象），不经被测适配器的强类型视图。
        client = MagicMock()
        adapter = ETFTushareAdapter(_client=client)
        # 聚焦 nav 滚动窗行为：预热 universe 缓存避免 etf_basic 请求
        adapter._etf_universe = frozenset({"510300.SH"})
        client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "ann_date": ["20261001"],
                "nav_date": ["20260930"],
                "unit_nav": [4.4312],
                "acc_nav": [None],
            }
        )

        frame = adapter.fetch_fund_nav(trade_date="2026-09-30")

        # 全市场模式逐日 nav_date 查询（端点不接受无标的范围参数）：
        # D-7 滚动回看接住 QDII 迟披露行
        days = [c.kwargs["nav_date"] for c in client.query.call_args_list]
        assert days[0] == "20260923"
        assert days[-1] == "20260930"
        assert len(days) == 8
        row = frame.row(0, named=True)
        assert row["trade_date"] == date(2026, 9, 30)
        assert row["knowledge_date"] == date(2026, 10, 1)  # 披露锚 ann_date
        assert row["unit_nav"] == pytest.approx(4.4312)
