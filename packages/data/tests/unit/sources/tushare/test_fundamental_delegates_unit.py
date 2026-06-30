"""Unit tests for Tushare fundamental fetch delegate helpers."""

from __future__ import annotations

from collections.abc import Callable
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


@pytest.mark.unit
class TestFinancialStatementDelegates:
    """Balance/income/cash-flow delegate behavior."""

    @pytest.mark.parametrize(
        ("fetch_fn", "vip_method", "standard_method"),
        [
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
        ],
    )
    def test_trade_date_uses_vip_api_with_compact_ann_date(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        vip_method: str,
        standard_method: str,
    ) -> None:
        """Date-batch mode delegates to the VIP API with compact ann_date."""
        fundamental = MagicMock()
        getattr(fundamental, vip_method).return_value = _frame("vip")

        result = fetch_fn(fundamental, _compact, trade_date="2024-05-06")

        assert result["dataset"].item() == "vip"
        getattr(fundamental, vip_method).assert_called_once_with(ann_date="20240506")
        getattr(fundamental, standard_method).assert_not_called()

    @pytest.mark.parametrize(
        ("fetch_fn", "vip_method", "standard_method"),
        [
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
        ],
    )
    def test_ticker_mode_requires_range_and_delegates_to_standard_api(
        self,
        fetch_fn: Callable[..., pl.DataFrame],
        vip_method: str,
        standard_method: str,
    ) -> None:
        """Ticker mode delegates to the standard API with compact date range."""
        fundamental = MagicMock()
        getattr(fundamental, standard_method).return_value = _frame("standard")

        result = fetch_fn(
            fundamental,
            _compact,
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert result["dataset"].item() == "standard"
        getattr(fundamental, vip_method).assert_not_called()
        getattr(fundamental, standard_method).assert_called_once_with(
            ts_code="000001.SZ",
            start_date="20240101",
            end_date="20241231",
        )

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
        """Dividend ticker mode forwards optional compact start/end dates."""
        fundamental = MagicMock()
        fundamental.fetch_dividend.return_value = _frame("dividend")

        result = _fundamental.fetch_dividend(
            fundamental,
            _compact,
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert result["dataset"].item() == "dividend"
        fundamental.fetch_dividend.assert_called_once_with(
            ts_code="000001.SZ",
            start_date="20240101",
            end_date="20241231",
        )

    def test_ticker_mode_without_range_forwards_none_dates(self) -> None:
        """Dividend ticker mode can query by ticker alone."""
        fundamental = MagicMock()
        fundamental.fetch_dividend.return_value = _frame("dividend")

        _fundamental.fetch_dividend(
            fundamental,
            _compact,
            source_ticker="000001.SZ",
        )

        fundamental.fetch_dividend.assert_called_once_with(
            ts_code="000001.SZ",
            start_date=None,
            end_date=None,
        )

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

    def test_trade_date_queries_single_compact_date_range(self) -> None:
        """Corporate actions query uses compact trade date as start and end."""
        fundamental = MagicMock()
        fundamental.fetch_corporate_actions.return_value = _frame("actions")

        result = _fundamental.fetch_corporate_actions(
            fundamental, _compact, "2024-05-06"
        )

        assert result["dataset"].item() == "actions"
        fundamental.fetch_corporate_actions.assert_called_once_with(
            ts_code=None,
            start_date="20240506",
            end_date="20240506",
        )
