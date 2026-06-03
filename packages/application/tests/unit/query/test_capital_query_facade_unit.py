"""Tests for CapitalQueryFacade — 封装 CapitalDataPort Protocol."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.capital import CapitalDataPort, CapitalQueryFacade
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

        result = facade.get_margin_trading(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert len(result) == 1
        assert result["rzye"][0] == 100.0


class TestCapitalQueryFacadeGetValuationMetrics:
    """CapitalQueryFacade.get_valuation_metrics — 委托到端口."""

    def test_delegates_to_port(self) -> None:
        stub = _StubCapitalData(valuation=pl.DataFrame({"pe": [15.0]}))
        facade = CapitalQueryFacade(capital_store=stub)

        result = facade.get_valuation_metrics(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert len(result) == 1
        assert result["pe"][0] == 15.0


class TestCapitalQueryFacadeMaturityGate:
    """CapitalQueryFacade — 显式数据集 maturity read gate."""

    @pytest.mark.parametrize(
        ("method_name", "dataset_id"),
        [
            ("get_margin_trading", "margin_trading"),
            ("get_valuation_metrics", "valuation_metrics"),
        ],
    )
    def test_experimental_datasets_require_explicit_research_opt_in(
        self,
        method_name: str,
        dataset_id: str,
    ) -> None:
        store = MagicMock(spec=["get_margin_trading", "get_valuation_metrics"])
        facade = CapitalQueryFacade(capital_store=store)

        with pytest.raises(AppQueryError, match="allow_experimental_data=True") as exc:
            getattr(facade, method_name)(1, date(2026, 6, 1))

        getattr(store, method_name).assert_not_called()
        assert dataset_id in str(exc.value)

    def test_allow_experimental_data_delegates_to_port(self) -> None:
        store = MagicMock(spec=["get_margin_trading"])
        store.get_margin_trading.return_value = pl.DataFrame({"rzye": [100.0]})
        facade = CapitalQueryFacade(capital_store=store)

        result = facade.get_margin_trading(
            1,
            date(2026, 6, 1),
            allow_experimental_data=True,
        )

        assert len(result) == 1
        store.get_margin_trading.assert_called_once_with(1, date(2026, 6, 1))

    def test_promoted_dataset_does_not_need_research_opt_in(self) -> None:
        store = MagicMock(spec=["get_margin_trading"])
        store.get_margin_trading.return_value = pl.DataFrame({"rzye": [100.0]})
        facade = CapitalQueryFacade(
            capital_store=store,
            maturity_promotion_reader=_MaturityPromotionReader(
                {
                    "margin_trading": DatasetMaturityPromotion(
                        dataset_id="margin_trading",
                        previous_maturity="experimental",
                        promoted_maturity="initial-focus",
                        promoted_by="architecture-review",
                    )
                }
            ),
        )

        result = facade.get_margin_trading(1, date(2026, 6, 1))

        assert len(result) == 1
        store.get_margin_trading.assert_called_once_with(1, date(2026, 6, 1))


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
        result = facade.get_margin_trading(
            1,
            date(2024, 1, 15),
            allow_experimental_data=True,
        )

        assert len(result) == 1
        mock_store.get_margin_trading.assert_called_once_with(
            1,
            date(2024, 1, 15),
        )
