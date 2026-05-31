"""Unit tests for Tushare fundamental/capital source helper functions."""

from __future__ import annotations

from collections.abc import Callable
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
    def test_financial_statement_trade_date_delegates_to_vip_api(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        vip_method: str,
    ) -> None:
        """Financial statement wrappers compact trade_date before delegation."""
        fundamental = MagicMock()
        getattr(fundamental, vip_method).return_value = _frame("vip")

        result = fetch_fn(fundamental, trade_date="2024-05-06")

        assert result["dataset"].item() == "vip"
        getattr(fundamental, vip_method).assert_called_once_with(ann_date="20240506")

    def test_dividend_trade_date_delegates_with_compact_ex_date(self) -> None:
        """Dividend wrapper compacts trade_date to ex_date."""
        fundamental = MagicMock()
        fundamental.fetch_dividend.return_value = _frame("dividend")

        result = fundamental_source.fetch_dividend(fundamental, trade_date="2024-05-06")

        assert result["dataset"].item() == "dividend"
        fundamental.fetch_dividend.assert_called_once_with(ex_date="20240506")

    def test_corporate_actions_delegates_with_single_compact_range(self) -> None:
        """Corporate-action wrapper compacts trade_date to a one-day range."""
        fundamental = MagicMock()
        fundamental.fetch_corporate_actions.return_value = _frame("actions")

        result = fundamental_source.fetch_corporate_actions(fundamental, "2024-05-06")

        assert result["dataset"].item() == "actions"
        fundamental.fetch_corporate_actions.assert_called_once_with(
            ts_code=None,
            start_date="20240506",
            end_date="20240506",
        )


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

    def test_pledge_ratio_trade_date_uses_compact_report_date(self) -> None:
        """Pledge ratio date-batch mode forwards a compact report_date."""
        capital = MagicMock()
        capital.fetch_pledge_ratio.return_value = _frame("pledge")

        result = fundamental_source.fetch_pledge_ratio(capital, trade_date="2024-03-31")

        assert result["dataset"].item() == "pledge"
        capital.fetch_pledge_ratio.assert_called_once_with(report_date="20240331")

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
