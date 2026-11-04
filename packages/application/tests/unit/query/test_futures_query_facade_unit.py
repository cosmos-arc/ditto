"""FuturesQueryFacade 单元测试 — experimental 门与端口委托（#658 批次4c）."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.futures import FuturesDataPort, FuturesQueryFacade


class TestFuturesQueryFacadeMaturityGate:
    """experimental 数据集须显式 opt-in 才可读."""

    @pytest.mark.parametrize(
        ("method_name", "call", "dataset_id"),
        [
            (
                "get_futures_daily",
                lambda f: f("2026-01-01", "2026-01-31"),
                "futures_daily",
            ),
            ("get_futures_contracts", lambda f: f(), "futures_basic"),
        ],
    )
    def test_experimental_datasets_require_explicit_research_opt_in(
        self,
        method_name: str,
        call: Callable[[object], object],
        dataset_id: str,
    ) -> None:
        store = MagicMock(spec=["get_futures_daily", "get_futures_contracts"])
        facade = FuturesQueryFacade(futures_data=store)
        method = getattr(facade, method_name)

        with pytest.raises(AppQueryError, match="allow_experimental_data=True") as exc:
            call(method)

        getattr(store, method_name).assert_not_called()
        assert dataset_id in str(exc.value)

    def test_allow_experimental_data_delegates_to_port(self) -> None:
        store = MagicMock(spec=["get_futures_daily", "get_futures_contracts"])
        store.get_futures_daily.return_value = pl.DataFrame({"close": [3470.0]})
        store.get_futures_contracts.return_value = pl.DataFrame({"symbol": ["RB2410"]})
        facade = FuturesQueryFacade(futures_data=store)

        daily = facade.get_futures_daily(
            "2026-10-01",
            "2026-10-31",
            ["RB2410.SHF"],
            allow_experimental_data=True,
        )
        assert len(daily) == 1
        store.get_futures_daily.assert_called_once_with(
            "2026-10-01", "2026-10-31", ["RB2410.SHF"]
        )

        contracts = facade.get_futures_contracts(
            "SHFE",
            "RB",
            allow_experimental_data=True,
        )
        assert len(contracts) == 1
        store.get_futures_contracts.assert_called_once_with("SHFE", "RB")


class TestFuturesQueryFacadeAcceptsProtocol:
    """Facade 接受任意满足 FuturesDataPort 的对象."""

    def test_magic_mock_satisfies_protocol(self) -> None:
        port: FuturesDataPort = MagicMock(
            spec=["get_futures_daily", "get_futures_contracts"]
        )
        facade = FuturesQueryFacade(futures_data=port)
        assert facade is not None
