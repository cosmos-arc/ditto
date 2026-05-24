"""Tests for CapitalQueryFacade — 封装 CapitalDataPort Protocol."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_application.queries.capital import CapitalDataPort, CapitalQueryFacade


class _StubCapitalData:
    """满足 CapitalDataPort Protocol 的最小 stub."""

    def __init__(
        self,
        margin: pl.DataFrame | None = None,
        valuation: pl.DataFrame | None = None,
    ) -> None:
        self._margin = margin
        self._valuation = valuation

    def get_margin_trading(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame:
        return self._margin if self._margin is not None else pl.DataFrame()

    def get_valuation_metrics(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame:
        return self._valuation if self._valuation is not None else pl.DataFrame()


def test_stub_satisfies_protocol() -> None:
    """Stub 满足 CapitalDataPort Protocol（structural typing 验证）."""
    _stub: CapitalDataPort = _StubCapitalData()


class TestCapitalQueryFacadeGetMarginTrading:
    """CapitalQueryFacade.get_margin_trading — 委托到端口."""

    def test_delegates_to_port(self) -> None:
        stub = _StubCapitalData(margin=pl.DataFrame({"rzye": [100.0]}))
        facade = CapitalQueryFacade(capital_store=stub)

        result = facade.get_margin_trading(1, date(2024, 1, 15))

        assert len(result) == 1
        assert result["rzye"][0] == 100.0


class TestCapitalQueryFacadeGetValuationMetrics:
    """CapitalQueryFacade.get_valuation_metrics — 委托到端口."""

    def test_delegates_to_port(self) -> None:
        stub = _StubCapitalData(valuation=pl.DataFrame({"pe": [15.0]}))
        facade = CapitalQueryFacade(capital_store=stub)

        result = facade.get_valuation_metrics(1, date(2024, 1, 15))

        assert len(result) == 1
        assert result["pe"][0] == 15.0


class TestCapitalQueryFacadeAcceptsProtocol:
    """Facade 接受任意满足 CapitalDataPort 的对象."""

    def test_magic_mock_satisfies_protocol(self) -> None:
        """MagicMock 满足 Protocol（鸭子类型）."""
        from unittest.mock import MagicMock

        spec = ["get_margin_trading", "get_valuation_metrics"]
        mock_store = MagicMock(spec=spec)
        mock_store.get_margin_trading.return_value = pl.DataFrame(
            {"rzye": [50.0]},
        )

        facade = CapitalQueryFacade(capital_store=mock_store)
        result = facade.get_margin_trading(1, date(2024, 1, 15))

        assert len(result) == 1
        mock_store.get_margin_trading.assert_called_once_with(
            1,
            date(2024, 1, 15),
        )
