"""Tests for CapitalQueryFacade — 封装 CapitalService."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
from ditto_app.query.capital import CapitalQueryFacade


class TestCapitalQueryFacadeGetMarginTrading:
    """CapitalQueryFacade.get_margin_trading — 委托到 CapitalService."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["get_margin_trading"])
        service.get_margin_trading.return_value = pl.DataFrame({"rzye": [100.0]})
        facade = CapitalQueryFacade(capital_service=service)

        result = facade.get_margin_trading(1, date(2024, 1, 15))

        assert len(result) == 1
        service.get_margin_trading.assert_called_once_with(1, date(2024, 1, 15))


class TestCapitalQueryFacadeGetValuationMetrics:
    """CapitalQueryFacade.get_valuation_metrics — 委托到 CapitalService."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["get_valuation_metrics"])
        service.get_valuation_metrics.return_value = pl.DataFrame({"pe": [15.0]})
        facade = CapitalQueryFacade(capital_service=service)

        result = facade.get_valuation_metrics(1, date(2024, 1, 15))

        assert len(result) == 1
        service.get_valuation_metrics.assert_called_once_with(1, date(2024, 1, 15))
