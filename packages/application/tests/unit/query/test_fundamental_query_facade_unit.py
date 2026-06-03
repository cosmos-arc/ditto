"""Tests for FundamentalQueryFacade — 封装 FundamentalDataPort Protocol."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.fundamental import (
    FundamentalDataPort,
    FundamentalQueryFacade,
)
from ditto_data.catalog.promotion import DatasetMaturityPromotion


class _MaturityPromotionReader:
    def __init__(
        self,
        promotions_by_dataset: dict[str, DatasetMaturityPromotion] | None = None,
    ) -> None:
        self._promotions_by_dataset = promotions_by_dataset or {}

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        return self._promotions_by_dataset.get(dataset_id)


class _StubFundamentalData:
    """满足 FundamentalDataPort Protocol 的最小 stub."""

    def __init__(
        self,
        balance_sheet: pl.DataFrame | None = None,
        income_statement: pl.DataFrame | None = None,
        cash_flow: pl.DataFrame | None = None,
        dividend: pl.DataFrame | None = None,
        corporate_actions: pl.DataFrame | None = None,
    ) -> None:
        self._balance_sheet = balance_sheet
        self._income_statement = income_statement
        self._cash_flow = cash_flow
        self._dividend = dividend
        self._corporate_actions = corporate_actions

    def get_balance_sheet(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        return self._balance_sheet

    def get_income_statement(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        return self._income_statement

    def get_cash_flow(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        return self._cash_flow

    def get_dividend(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        return self._dividend

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        if self._corporate_actions is not None:
            return self._corporate_actions
        return pl.DataFrame()


def test_stub_satisfies_protocol() -> None:
    """Stub 满足 FundamentalDataPort Protocol（structural typing 验证）."""
    _stub: FundamentalDataPort = _StubFundamentalData()


class TestFundamentalQueryFacadeGetBalanceSheet:
    """FundamentalQueryFacade.get_balance_sheet — 委托到端口."""

    def test_returns_dataframe_when_found(self) -> None:
        bs = pl.DataFrame({"total_assets": [1e9]})
        stub = _StubFundamentalData(balance_sheet=bs)
        facade = FundamentalQueryFacade(fundamental_store=stub)

        result = facade.get_balance_sheet(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert result is not None
        assert len(result) == 1

    def test_returns_none_when_empty(self) -> None:
        stub = _StubFundamentalData(balance_sheet=None)
        facade = FundamentalQueryFacade(fundamental_store=stub)

        result = facade.get_balance_sheet(
            999,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert result is None


class TestFundamentalQueryFacadeMaturityGate:
    """FundamentalQueryFacade — 显式数据集 maturity read gate."""

    @pytest.mark.parametrize(
        ("method_name", "dataset_id", "args"),
        [
            ("get_balance_sheet", "balance_sheet", (1, date(2026, 6, 1))),
            ("get_income_statement", "income_statement", (1, date(2026, 6, 1))),
            ("get_cash_flow", "cash_flow", (1, date(2026, 6, 1))),
            ("get_dividend", "dividend", (1, date(2026, 6, 1))),
            (
                "list_corporate_actions",
                "corporate_actions",
                (1, date(2026, 1, 1), date(2026, 6, 1)),
            ),
        ],
    )
    def test_experimental_datasets_require_explicit_research_opt_in(
        self,
        method_name: str,
        dataset_id: str,
        args: tuple[object, ...],
    ) -> None:
        store = MagicMock(
            spec=[
                "get_balance_sheet",
                "get_income_statement",
                "get_cash_flow",
                "get_dividend",
                "list_corporate_actions",
            ]
        )
        facade = FundamentalQueryFacade(fundamental_store=store)

        with pytest.raises(AppQueryError, match="allow_experimental_data=True") as exc:
            getattr(facade, method_name)(*args)

        getattr(store, method_name).assert_not_called()
        assert dataset_id in str(exc.value)

    def test_allow_experimental_data_delegates_to_port(self) -> None:
        store = MagicMock(spec=["get_balance_sheet"])
        store.get_balance_sheet.return_value = pl.DataFrame({"total_assets": [1e9]})
        facade = FundamentalQueryFacade(fundamental_store=store)

        result = facade.get_balance_sheet(
            1,
            date(2026, 6, 1),
            allow_experimental_data=True,
        )

        assert result is not None
        store.get_balance_sheet.assert_called_once_with(1, date(2026, 6, 1))

    def test_promoted_dataset_does_not_need_research_opt_in(self) -> None:
        store = MagicMock(spec=["get_balance_sheet"])
        store.get_balance_sheet.return_value = pl.DataFrame({"total_assets": [1e9]})
        facade = FundamentalQueryFacade(
            fundamental_store=store,
            maturity_promotion_reader=_MaturityPromotionReader(
                {
                    "balance_sheet": DatasetMaturityPromotion(
                        dataset_id="balance_sheet",
                        previous_maturity="experimental",
                        promoted_maturity="initial-focus",
                        promoted_by="architecture-review",
                    )
                }
            ),
        )

        result = facade.get_balance_sheet(1, date(2026, 6, 1))

        assert result is not None
        store.get_balance_sheet.assert_called_once_with(1, date(2026, 6, 1))


class TestFundamentalQueryFacadeGetIncomeStatement:
    """FundamentalQueryFacade.get_income_statement — 委托到端口."""

    def test_delegates_to_port(self) -> None:
        is_df = pl.DataFrame({"revenue": [1e9]})
        stub = _StubFundamentalData(income_statement=is_df)
        facade = FundamentalQueryFacade(fundamental_store=stub)

        result = facade.get_income_statement(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert result is not None
        assert len(result) == 1


class TestFundamentalQueryFacadeGetCashFlow:
    """FundamentalQueryFacade.get_cash_flow — 委托到端口."""

    def test_delegates_to_port(self) -> None:
        cf = pl.DataFrame({"ocf": [1e8]})
        stub = _StubFundamentalData(cash_flow=cf)
        facade = FundamentalQueryFacade(fundamental_store=stub)

        result = facade.get_cash_flow(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert result is not None
        assert len(result) == 1


class TestFundamentalQueryFacadeGetDividend:
    """FundamentalQueryFacade.get_dividend — 委托到端口."""

    def test_delegates_to_port(self) -> None:
        div = pl.DataFrame({"cash_div": [0.5]})
        stub = _StubFundamentalData(dividend=div)
        facade = FundamentalQueryFacade(fundamental_store=stub)

        result = facade.get_dividend(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert result is not None
        assert len(result) == 1


class TestFundamentalQueryFacadeListCorporateActions:
    """FundamentalQueryFacade.list_corporate_actions — 委托到端口."""

    def test_delegates_with_date_range(self) -> None:
        actions = pl.DataFrame({"action_type": ["split"]})
        stub = _StubFundamentalData(corporate_actions=actions)
        facade = FundamentalQueryFacade(fundamental_store=stub)

        result = facade.list_corporate_actions(
            1,
            date(2024, 1, 1),
            date(2024, 12, 31),
            allow_experimental_data=True,
        )

        assert len(result) == 1

    def test_delegates_with_as_of_date(self) -> None:
        actions = pl.DataFrame({"action_type": ["split"]})
        stub = _StubFundamentalData(corporate_actions=actions)
        facade = FundamentalQueryFacade(fundamental_store=stub)

        result = facade.list_corporate_actions(
            1,
            date(2024, 1, 1),
            date(2024, 12, 31),
            as_of_date=date(2024, 6, 30),
            allow_experimental_data=True,
        )

        assert len(result) == 1


class TestFundamentalQueryFacadeAcceptsProtocol:
    """Facade 接受任意满足 FundamentalDataPort 的对象."""

    def test_magic_mock_satisfies_protocol(self) -> None:
        """MagicMock 满足 Protocol（鸭子类型）."""
        from unittest.mock import MagicMock

        spec = [
            "get_balance_sheet",
            "get_income_statement",
            "get_cash_flow",
            "get_dividend",
            "list_corporate_actions",
        ]
        mock_store = MagicMock(spec=spec)
        mock_store.get_balance_sheet.return_value = pl.DataFrame(
            {"total_assets": [1e9]},
        )

        facade = FundamentalQueryFacade(fundamental_store=mock_store)
        result = facade.get_balance_sheet(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert result is not None
        assert len(result) == 1
        mock_store.get_balance_sheet.assert_called_once_with(
            1,
            date(2024, 1, 15),
        )
