"""Tests for _build_actual_navs — NAV 重建."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.execution_dto import ManualExecutionFill
from ditto_application.query.comparison import _build_actual_navs


def _make_fill(
    fill_id: str = "fill-001",
    fee: float = 100.0,
    trade_date: str = "2024-01-03",
    instrument_id: int = 510300,
    direction: str = "buy",
    quantity: int = 1000,
    fill_price: float = 4.0,
) -> ManualExecutionFill:
    """构造测试用 ManualExecutionFill."""
    return ManualExecutionFill(
        fill_id=fill_id,
        intent_id="intent-001",
        strategy_id="strat-001",
        trade_date=trade_date,
        instrument_id=instrument_id,
        direction=direction,
        quantity=quantity,
        fill_price=fill_price,
        fee=fee,
    )


def _make_price_df(rows: list[tuple[int, str, float]]) -> pl.DataFrame:
    """构造 mock 行情 DataFrame: (instrument_id, trade_date, close)."""
    if rows:
        return pl.DataFrame(
            {
                "instrument_id": [r[0] for r in rows],
                "trade_date": [r[1] for r in rows],
                "close": [r[2] for r in rows],
            },
        )
    return pl.DataFrame(
        {
            "instrument_id": pl.Series([], dtype=pl.Int64),
            "trade_date": pl.Series([], dtype=pl.Utf8),
            "close": pl.Series([], dtype=pl.Float64),
        },
    )


# ========== 空输入 ==========


class TestBuildActualNavsEmpty:
    """_build_actual_navs — 空输入边界."""

    def test_empty_fills_returns_empty(self) -> None:
        """空 fills 返回空序列."""
        market = MagicMock()
        result = _build_actual_navs([], 1_000_000.0, price_query=market)
        assert result == []


# ========== NAV 重建 ==========


class TestBuildActualNavsFull:
    """_build_actual_navs — NAV 重建（逐日现金/持仓台账 + 收盘价）."""

    def test_buy_only_reduces_cash_adds_position(self) -> None:
        """纯买入: 现金减少，持仓增加，NAV = 现金 + 持仓市值."""
        fills = [
            _make_fill(
                trade_date="2024-01-02",
                instrument_id=510300,
                quantity=1000,
                fill_price=4.0,
                fee=100.0,
            ),
        ]
        price_df = _make_price_df(
            [
                (510300, "2024-01-02", 4.1),
            ]
        )
        market = MagicMock()
        market.find_bars.return_value = price_df

        result = _build_actual_navs(fills, 1_000_000.0, price_query=market)

        assert len(result) == 1
        dt, nav = result[0]
        assert dt == "2024-01-02"
        # cash = 1_000_000 - 4000 - 100 = 995_900
        # position_value = 1000 * 4.1 = 4100
        # nav = 995_900 + 4100 = 1_000_000
        assert nav == pytest.approx(1_000_000.0, abs=1.0)

    def test_buy_then_sell_nav_consistency(self) -> None:
        """买入后卖出: 现金增减正确，NAV 始终反映市值."""
        fills = [
            _make_fill(
                fill_id="f1",
                trade_date="2024-01-02",
                instrument_id=510300,
                quantity=1000,
                fill_price=4.0,
                fee=100.0,
            ),
            _make_fill(
                fill_id="f2",
                trade_date="2024-01-03",
                instrument_id=510300,
                direction="sell",
                quantity=1000,
                fill_price=4.2,
                fee=100.0,
            ),
        ]
        price_df = _make_price_df(
            [
                (510300, "2024-01-02", 4.1),
                (510300, "2024-01-03", 4.2),
            ]
        )
        market = MagicMock()
        market.find_bars.return_value = price_df

        result = _build_actual_navs(fills, 1_000_000.0, price_query=market)

        assert len(result) == 2
        # Day 1: cash=995_900, position=1000*4.1=4100, nav=1_000_000
        assert result[0][1] == pytest.approx(1_000_000.0, abs=1.0)
        # Day 2: sell → cash=995_900+4200-100=1_000_000, position=0
        assert result[1][1] == pytest.approx(1_000_000.0, abs=1.0)

    def test_multi_instrument_nav(self) -> None:
        """多标的: 不同 instrument 的持仓独立计算."""
        fills = [
            _make_fill(
                fill_id="f1",
                trade_date="2024-01-02",
                instrument_id=510300,
                quantity=500,
                fill_price=4.0,
                fee=50.0,
            ),
            _make_fill(
                fill_id="f2",
                trade_date="2024-01-02",
                instrument_id=159915,
                quantity=300,
                fill_price=1.0,
                fee=30.0,
            ),
        ]
        price_df = _make_price_df(
            [
                (510300, "2024-01-02", 4.1),
                (159915, "2024-01-02", 1.05),
            ]
        )
        market = MagicMock()
        market.find_bars.return_value = price_df

        result = _build_actual_navs(fills, 1_000_000.0, price_query=market)

        assert len(result) == 1
        _, nav = result[0]
        # cash = 1_000_000 - 2000 - 50 - 300 - 30 = 997_620
        # position_value = 500*4.1 + 300*1.05 = 2050 + 315 = 2365
        # nav = 997_620 + 2365 = 999_985
        assert nav == pytest.approx(999_985.0)

    def test_falls_back_to_fill_price_when_no_close_data(self) -> None:
        """无行情价格时回退到成交价."""
        fills = [
            _make_fill(
                trade_date="2024-01-02",
                instrument_id=510300,
                quantity=1000,
                fill_price=4.0,
                fee=100.0,
            ),
        ]
        price_df = _make_price_df([])
        market = MagicMock()
        market.find_bars.return_value = price_df

        result = _build_actual_navs(fills, 1_000_000.0, price_query=market)

        assert len(result) == 1
        # cash = 1_000_000 - 4000 - 100 = 995_900
        # position_value = 1000 * 4.0 (fallback to fill_price) = 4000
        # nav = 995_900 + 4000 = 999_900
        assert result[0][1] == pytest.approx(999_900.0)

    def test_partial_sell_reduces_position(self) -> None:
        """部分卖出: 持仓数量减少但未清零."""
        fills = [
            _make_fill(
                fill_id="f1",
                trade_date="2024-01-02",
                instrument_id=510300,
                quantity=1000,
                fill_price=4.0,
                fee=100.0,
            ),
            _make_fill(
                fill_id="f2",
                trade_date="2024-01-03",
                instrument_id=510300,
                direction="sell",
                quantity=400,
                fill_price=4.2,
                fee=50.0,
            ),
        ]
        price_df = _make_price_df(
            [
                (510300, "2024-01-02", 4.1),
                (510300, "2024-01-03", 4.3),
            ]
        )
        market = MagicMock()
        market.find_bars.return_value = price_df

        result = _build_actual_navs(fills, 1_000_000.0, price_query=market)

        assert len(result) == 2
        # Day 1: cash=995_900, position=1000*4.1=4100, nav=1_000_000
        assert result[0][1] == pytest.approx(1_000_000.0, abs=1.0)
        # Day 2: cash=995_900+1680-50=997_530, position=600*4.3=2580
        # nav = 997_530 + 2580 = 1_000_110
        assert result[1][1] == pytest.approx(1_000_110.0)
