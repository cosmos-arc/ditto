"""ditto_datahub.query.market 单元测试."""

from unittest.mock import MagicMock

import polars as pl
from ditto_datahub.query.market import MarketQuerist


class TestMarketQuerist:
    """MarketQuerist 门面测试."""

    def _make_querist(self) -> tuple[MarketQuerist, MagicMock]:
        service = MagicMock(spec=["find_bars", "list_bars"])
        return MarketQuerist(market_service=service), service

    def test_get_bars_delegates(self) -> None:
        """应委托给 MarketService.find_bars."""
        querist, service = self._make_querist()
        expected = pl.DataFrame({"trade_date": ["2024-01-02"], "close": [10.0]})
        service.find_bars.return_value = expected
        result = querist.get_bars(
            instrument_ids=[1, 2],
            start="2024-01-01",
            end="2024-12-31",
        )
        assert result.equals(expected)
        assert service.find_bars.call_count == 1

    def test_get_bars_with_adj(self) -> None:
        """应正确传递复权参数."""
        querist, service = self._make_querist()
        service.find_bars.return_value = pl.DataFrame()
        querist.get_bars(
            instrument_ids=[1],
            start="2024-01-01",
            end="2024-12-31",
            adj="qfq",
        )
        call_args = service.find_bars.call_args
        query = call_args[0][0]
        assert query.adj.value == "qfq"
        assert query.instrument_ids == [1]

    def test_get_bars_default_adj_none(self) -> None:
        """默认 adj 应为 none."""
        querist, service = self._make_querist()
        service.find_bars.return_value = pl.DataFrame()
        querist.get_bars(instrument_ids=[1], start="2024-01-01", end="2024-12-31")
        call_args = service.find_bars.call_args
        query = call_args[0][0]
        assert query.adj.value == "none"
