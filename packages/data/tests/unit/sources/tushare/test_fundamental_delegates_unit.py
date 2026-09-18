"""Unit tests for Tushare fundamental fetch delegate helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare import _fundamental


def _compact(value: str) -> str:
    """Compact YYYY-MM-DD dates for assertions."""
    return value.replace("-", "")


def _frame(label: str) -> pl.DataFrame:
    return pl.DataFrame({"dataset": [label]})


def _knowledge_frame() -> pl.DataFrame:
    """Disclosure rows spanning past/future/null anchors at the 2024-05-06 cutoff."""
    return pl.DataFrame(
        {
            "source_ticker": ["past", "future", "edge", "null"],
            "knowledge_date": [
                date(2024, 5, 5),
                date(2024, 5, 7),
                date(2024, 5, 6),
                None,
            ],
        }
    )


_STATEMENT_PARAMS: list[tuple[Callable[..., pl.DataFrame], str, str]] = [
    (
        _fundamental.fetch_balance_sheet,
        "fetch_balance_sheet_vip",
        "fetch_balance_sheet",
    ),
    (
        _fundamental.fetch_income_statement,
        "fetch_income_statement_vip",
        "fetch_income_statement",
    ),
    (_fundamental.fetch_cash_flow, "fetch_cash_flow_vip", "fetch_cash_flow"),
]


@pytest.mark.unit
class TestFinancialStatementDelegates:
    """Balance/income/cash-flow delegate behavior."""

    @pytest.mark.parametrize(
        ("fetch_fn", "vip_method", "standard_method"), _STATEMENT_PARAMS
    )
    def test_trade_date_pulls_trailing_quarter_periods(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        vip_method: str,
        standard_method: str,
    ) -> None:
        """Disclosure-delta mode pulls trailing quarter periods via the VIP API."""
        fundamental = MagicMock()
        getattr(fundamental, vip_method).return_value = _knowledge_frame()

        result = fetch_fn(fundamental, _compact, trade_date="2024-05-06")

        periods = [
            call.kwargs.get("period")
            for call in getattr(fundamental, vip_method).call_args_list
        ]
        assert periods == [
            "20240331",
            "20231231",
            "20230930",
            "20230630",
            "20230331",
            "20221231",
            "20220930",
            "20220630",
        ]
        assert periods == sorted(periods, reverse=True)
        getattr(fundamental, standard_method).assert_not_called()
        assert set(result["source_ticker"].to_list()) == {"past", "edge", "null"}

    @pytest.mark.pit
    @pytest.mark.parametrize(("fetch_fn", "vip_method", "_standard"), _STATEMENT_PARAMS)
    def test_disclosure_delta_never_returns_future_knowledge(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        vip_method: str,
        _standard: str,
    ) -> None:
        """Future disclosure rows are dropped; null anchors survive to the gate."""
        fundamental = MagicMock()
        getattr(fundamental, vip_method).return_value = _knowledge_frame()

        result = fetch_fn(fundamental, _compact, trade_date="2024-05-06")

        assert result["knowledge_date"].drop_nulls().max() == date(2024, 5, 6)
        # null 锚未被静默剔除，交由 sparse PIT 校验 fail-closed 拒收
        assert result["knowledge_date"].null_count() >= 1

    @pytest.mark.parametrize(
        ("fetch_fn", "vip_method", "standard_method"), _STATEMENT_PARAMS
    )
    def test_ticker_mode_requires_range_and_delegates_to_standard_api(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        vip_method: str,
        standard_method: str,
    ) -> None:
        """Ticker mode delegates to the standard API with compact date range."""
        fundamental = MagicMock()
        getattr(fundamental, standard_method).return_value = _knowledge_frame()

        result = fetch_fn(
            fundamental,
            _compact,
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-05-06",
        )

        getattr(fundamental, vip_method).assert_not_called()
        getattr(fundamental, standard_method).assert_called_once_with(
            ts_code="000001.SZ",
            start_date="20240101",
            end_date="20240506",
        )
        assert set(result["source_ticker"].to_list()) == {"past", "edge", "null"}

    @pytest.mark.parametrize(
        "fetch_fn",
        [
            _fundamental.fetch_balance_sheet,
            _fundamental.fetch_income_statement,
            _fundamental.fetch_cash_flow,
        ],
    )
    def test_trade_date_and_source_ticker_are_mutually_exclusive(
        self, fetch_fn: Callable[..., pl.DataFrame]
    ) -> None:
        """Financial statement delegates reject ambiguous query modes."""
        with pytest.raises(ValueError, match="互斥"):
            fetch_fn(
                MagicMock(),
                _compact,
                trade_date="2024-05-06",
                source_ticker="000001.SZ",
                start_date="2024-01-01",
                end_date="2024-12-31",
            )

    @pytest.mark.parametrize(
        "fetch_fn",
        [
            _fundamental.fetch_balance_sheet,
            _fundamental.fetch_income_statement,
            _fundamental.fetch_cash_flow,
        ],
    )
    def test_financial_statement_requires_one_query_mode(
        self, fetch_fn: Callable[..., pl.DataFrame]
    ) -> None:
        """Financial statement delegates require date-batch or ticker mode."""
        with pytest.raises(ValueError, match="必须指定"):
            fetch_fn(MagicMock(), _compact)

    @pytest.mark.parametrize(
        "missing_kwargs",
        [
            {"start_date": "2024-01-01"},
            {"end_date": "2024-12-31"},
            {},
        ],
    )
    @pytest.mark.parametrize(
        "fetch_fn",
        [
            _fundamental.fetch_balance_sheet,
            _fundamental.fetch_income_statement,
            _fundamental.fetch_cash_flow,
        ],
    )
    def test_ticker_mode_requires_start_and_end_dates(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        missing_kwargs: dict[str, Any],
    ) -> None:
        """Ticker mode for financial statements requires a complete range."""
        with pytest.raises(ValueError, match="start_date 和 end_date"):
            fetch_fn(
                MagicMock(),
                _compact,
                source_ticker="000001.SZ",
                **missing_kwargs,
            )


@pytest.mark.unit
class TestDividendDelegate:
    """Dividend delegate behavior."""

    def test_trade_date_uses_ex_date(self) -> None:
        """Dividend date-batch mode delegates with compact ex_date."""
        fundamental = MagicMock()
        fundamental.fetch_dividend.return_value = _frame("dividend")

        result = _fundamental.fetch_dividend(
            fundamental, _compact, trade_date="2024-05-06"
        )

        assert result["dataset"].item() == "dividend"
        fundamental.fetch_dividend.assert_called_once_with(ex_date="20240506")

    def test_ticker_mode_allows_optional_range(self) -> None:
        """Dividend ticker mode applies the optional range to announcement dates."""
        fundamental = MagicMock()
        fundamental.fetch_dividend.return_value = pl.DataFrame(
            {
                "dataset": ["outside", "dividend", "outside"],
                "knowledge_date": [
                    date(2023, 12, 31),
                    date(2024, 6, 1),
                    date(2025, 1, 1),
                ],
            }
        )

        result = _fundamental.fetch_dividend(
            fundamental,
            _compact,
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert result["dataset"].item() == "dividend"
        fundamental.fetch_dividend.assert_called_once_with(ts_code="000001.SZ")

    def test_ticker_mode_without_range_forwards_none_dates(self) -> None:
        """Dividend ticker mode can query by ticker alone."""
        fundamental = MagicMock()
        fundamental.fetch_dividend.return_value = _frame("dividend")

        _fundamental.fetch_dividend(
            fundamental,
            _compact,
            source_ticker="000001.SZ",
        )

        fundamental.fetch_dividend.assert_called_once_with(ts_code="000001.SZ")

    def test_trade_date_and_source_ticker_are_mutually_exclusive(self) -> None:
        """Dividend delegate rejects ambiguous query modes."""
        with pytest.raises(ValueError, match="互斥"):
            _fundamental.fetch_dividend(
                MagicMock(),
                _compact,
                trade_date="2024-05-06",
                source_ticker="000001.SZ",
            )

    def test_requires_one_query_mode(self) -> None:
        """Dividend delegate requires date-batch or ticker mode."""
        with pytest.raises(ValueError, match="必须指定"):
            _fundamental.fetch_dividend(MagicMock(), _compact)


@pytest.mark.unit
class TestCorporateActionsDelegate:
    """Corporate-action delegate behavior."""

    def test_trade_date_queries_exact_compact_announcement_date(self) -> None:
        """Corporate actions query uses the compact announcement date."""
        fundamental = MagicMock()
        fundamental.fetch_corporate_actions.return_value = _frame("actions")

        result = _fundamental.fetch_corporate_actions(
            fundamental, _compact, "2024-05-06"
        )

        assert result["dataset"].item() == "actions"
        fundamental.fetch_corporate_actions.assert_called_once_with(ann_date="20240506")


@pytest.mark.unit
class TestRecentQuarterEnds:
    """Trailing quarter-end period derivation."""

    @pytest.mark.parametrize(
        ("trade_date", "expected_head"),
        [
            ("2024-05-06", ["20240331", "20231231"]),
            # 当季期末报告不可能当天披露，窗口从上一季度末起算
            ("2024-03-31", ["20231231", "20230930"]),
            ("2024-01-01", ["20231231", "20230930"]),
            ("2024-12-31", ["20240930", "20240630"]),
            ("2024-11-15", ["20240930", "20240630"]),
        ],
    )
    def test_trailing_quarter_ends(
        self, trade_date: str, expected_head: list[str]
    ) -> None:
        assert _fundamental._recent_quarter_ends(trade_date)[:2] == expected_head

    def test_window_crosses_year_boundary(self) -> None:
        assert _fundamental._recent_quarter_ends("2024-02-01")[-2:] == [
            "20220630",
            "20220331",
        ]


@pytest.mark.unit
class TestDisclosureRange:
    """Bounded disclosure-interval fetch used by sparse PIT backfill."""

    def test_range_keeps_rows_inside_interval_and_nulls(self) -> None:
        vip_fetch = MagicMock(return_value=_knowledge_frame())

        result = _fundamental.fetch_disclosure_range(
            vip_fetch, "2024-05-05", "2024-05-06"
        )

        # 闭区间：past(05-05)/edge(05-06) 在界内，future(05-07) 剔除，null 保留
        assert set(result["source_ticker"].to_list()) == {"past", "edge", "null"}
        assert vip_fetch.call_count == _fundamental._DISCLOSURE_PERIOD_WINDOW


@pytest.mark.unit
class TestStatementMappings:
    """Financial-statement mappings anchor knowledge_date on f_ann_date."""

    def test_statement_mappings_anchor_knowledge_date_on_f_ann_date(self) -> None:
        """三大报表映射把 f_ann_date 解析为 knowledge_date（ADR 红线 4）。"""
        from ditto_data.sources.tushare.processors.mappings import (
            BALANCE_SHEET_MAPPING,
            CASH_FLOW_MAPPING,
            INCOME_STATEMENT_MAPPING,
        )
        from ditto_data.sources.tushare.processors.transformer import (
            TushareDataTransformer,
        )

        raw = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20240331"],
                "ann_date": ["20240401"],
                "f_ann_date": ["20240506"],
                "total_assets": [100.0],
                "total_liab": [60.0],
                "total_revenue": [10.0],
                "n_cashflow_act": [1.0],
            }
        )

        for mapping in (
            BALANCE_SHEET_MAPPING,
            INCOME_STATEMENT_MAPPING,
            CASH_FLOW_MAPPING,
        ):
            result = TushareDataTransformer.transform(raw, "sample", mapping)
            assert result["knowledge_date"].item() == date(2024, 5, 6)
