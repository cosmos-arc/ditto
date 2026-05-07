"""Tests for FundamentalQueryFacade — 封装 FundamentalService."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
from ditto_application.queries.fundamental import FundamentalQueryFacade


class TestFundamentalQueryFacadeGetBalanceSheet:
    """FundamentalQueryFacade.get_balance_sheet — 委托到 FundamentalService."""

    def test_returns_dataframe_when_found(self) -> None:
        service = MagicMock(spec=["get_balance_sheet"])
        service.get_balance_sheet.return_value = pl.DataFrame({"total_assets": [1e9]})
        facade = FundamentalQueryFacade(fundamental_service=service)

        result = facade.get_balance_sheet(1, date(2024, 1, 15))

        assert result is not None
        assert len(result) == 1
        service.get_balance_sheet.assert_called_once_with(1, date(2024, 1, 15))

    def test_returns_none_when_empty(self) -> None:
        service = MagicMock(spec=["get_balance_sheet"])
        service.get_balance_sheet.return_value = None
        facade = FundamentalQueryFacade(fundamental_service=service)

        result = facade.get_balance_sheet(999, date(2024, 1, 15))

        assert result is None


class TestFundamentalQueryFacadeGetIncomeStatement:
    """FundamentalQueryFacade.get_income_statement — 委托到 FundamentalService."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["get_income_statement"])
        service.get_income_statement.return_value = pl.DataFrame({"revenue": [1e9]})
        facade = FundamentalQueryFacade(fundamental_service=service)

        result = facade.get_income_statement(1, date(2024, 1, 15))

        assert result is not None
        service.get_income_statement.assert_called_once_with(1, date(2024, 1, 15))


class TestFundamentalQueryFacadeGetCashFlow:
    """FundamentalQueryFacade.get_cash_flow — 委托到 FundamentalService."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["get_cash_flow"])
        service.get_cash_flow.return_value = pl.DataFrame({"ocf": [1e8]})
        facade = FundamentalQueryFacade(fundamental_service=service)

        result = facade.get_cash_flow(1, date(2024, 1, 15))

        assert result is not None
        service.get_cash_flow.assert_called_once_with(1, date(2024, 1, 15))


class TestFundamentalQueryFacadeGetDividend:
    """FundamentalQueryFacade.get_dividend — 委托到 FundamentalService."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["get_dividend"])
        service.get_dividend.return_value = pl.DataFrame({"cash_div": [0.5]})
        facade = FundamentalQueryFacade(fundamental_service=service)

        result = facade.get_dividend(1, date(2024, 1, 15))

        assert result is not None
        service.get_dividend.assert_called_once_with(1, date(2024, 1, 15))


class TestFundamentalQueryFacadeListCorporateActions:
    """FundamentalQueryFacade.list_corporate_actions — 委托到 FundamentalService."""

    def test_delegates_with_date_range(self) -> None:
        service = MagicMock(spec=["list_corporate_actions"])
        service.list_corporate_actions.return_value = pl.DataFrame(
            {"action_type": ["split"]}
        )
        facade = FundamentalQueryFacade(fundamental_service=service)

        result = facade.list_corporate_actions(1, date(2024, 1, 1), date(2024, 12, 31))

        assert len(result) == 1
        service.list_corporate_actions.assert_called_once_with(
            1, date(2024, 1, 1), date(2024, 12, 31), None
        )

    def test_delegates_with_as_of_date(self) -> None:
        service = MagicMock(spec=["list_corporate_actions"])
        service.list_corporate_actions.return_value = pl.DataFrame(
            {"action_type": ["split"]}
        )
        facade = FundamentalQueryFacade(fundamental_service=service)

        result = facade.list_corporate_actions(
            1, date(2024, 1, 1), date(2024, 12, 31), as_of_date=date(2024, 6, 30)
        )

        assert len(result) == 1
        service.list_corporate_actions.assert_called_once_with(
            1, date(2024, 1, 1), date(2024, 12, 31), date(2024, 6, 30)
        )
