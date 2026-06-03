"""Tests for explicit maturity opt-in on experimental query route helpers."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
from ditto_apps.api.routes.capital import _fetch_margin, _fetch_valuation
from ditto_apps.api.routes.fundamental import (
    _fetch_corporate_actions,
    _fetch_dividend,
    _fetch_financials,
)
from ditto_apps.api.routes.macro import _find_indicators, _list_indicators
from ditto_apps.models.fundamental import FinancialType
from ditto_apps.models.macro import IndicatorQuery


def test_fundamental_financials_passes_maturity_opt_in_to_facade() -> None:
    facade = MagicMock(spec=["get_balance_sheet"])
    expected = pl.DataFrame()
    facade.get_balance_sheet.return_value = expected

    result = _fetch_financials(
        facade,
        FinancialType.BALANCE_SHEET,
        instrument_id=1,
        as_of_date=date(2026, 6, 1),
        allow_experimental_data=True,
    )

    assert result is expected
    facade.get_balance_sheet.assert_called_once_with(
        1,
        date(2026, 6, 1),
        allow_experimental_data=True,
    )


def test_fundamental_dividend_passes_maturity_opt_in_to_facade() -> None:
    facade = MagicMock(spec=["get_dividend"])
    expected = pl.DataFrame()
    facade.get_dividend.return_value = expected

    result = _fetch_dividend(
        facade,
        instrument_id=1,
        as_of_date=date(2026, 6, 1),
        allow_experimental_data=True,
    )

    assert result is expected
    facade.get_dividend.assert_called_once_with(
        1,
        date(2026, 6, 1),
        allow_experimental_data=True,
    )


def test_fundamental_corporate_actions_pass_maturity_opt_in_to_facade() -> None:
    facade = MagicMock(spec=["list_corporate_actions"])
    expected = pl.DataFrame()
    facade.list_corporate_actions.return_value = expected

    result = _fetch_corporate_actions(
        facade,
        instrument_id=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 1),
        as_of_date=None,
        allow_experimental_data=True,
    )

    assert result is expected
    facade.list_corporate_actions.assert_called_once_with(
        1,
        date(2026, 1, 1),
        date(2026, 6, 1),
        None,
        allow_experimental_data=True,
    )


def test_capital_margin_passes_maturity_opt_in_to_facade() -> None:
    facade = MagicMock(spec=["get_margin_trading"])
    expected = pl.DataFrame()
    facade.get_margin_trading.return_value = expected

    result = _fetch_margin(
        facade,
        instrument_id=1,
        as_of_date=date(2026, 6, 1),
        allow_experimental_data=True,
    )

    assert result is expected
    facade.get_margin_trading.assert_called_once_with(
        1,
        date(2026, 6, 1),
        allow_experimental_data=True,
    )


def test_capital_valuation_passes_maturity_opt_in_to_facade() -> None:
    facade = MagicMock(spec=["get_valuation_metrics"])
    expected = pl.DataFrame()
    facade.get_valuation_metrics.return_value = expected

    result = _fetch_valuation(
        facade,
        instrument_id=1,
        as_of_date=date(2026, 6, 1),
        allow_experimental_data=True,
    )

    assert result is expected
    facade.get_valuation_metrics.assert_called_once_with(
        1,
        date(2026, 6, 1),
        allow_experimental_data=True,
    )


def test_macro_post_indicators_passes_maturity_opt_in_to_facade() -> None:
    facade = MagicMock(spec=["find_indicators"])
    expected = pl.DataFrame()
    facade.find_indicators.return_value = expected
    query = IndicatorQuery(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 1),
        allow_experimental_data=True,
    )

    result = _find_indicators(facade, query)

    assert result is expected
    facade.find_indicators.assert_called_once_with(
        indicators=None,
        start="2026-01-01",
        end="2026-06-01",
        category=None,
        frequency=None,
        allow_experimental_data=True,
    )


def test_macro_metadata_passes_maturity_opt_in_to_facade() -> None:
    facade = MagicMock(spec=["list_indicators"])
    expected = pl.DataFrame()
    facade.list_indicators.return_value = expected

    result = _list_indicators(
        facade,
        start="2026-01-01",
        end="2026-06-01",
        category=None,
        allow_experimental_data=True,
    )

    assert result is expected
    facade.list_indicators.assert_called_once_with(
        start="2026-01-01",
        end="2026-06-01",
        category=None,
        allow_experimental_data=True,
    )
