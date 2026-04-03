"""SettlementModel unit tests — SimpleSettlementModel + AShareSettlementModel."""

import pytest
from ditto_engine.accounting.position import Position
from ditto_engine.execution.reality.settlement import (
    AShareSettlementModel,
    SimpleSettlementModel,
)
from ditto_engine.execution.rules import TradingRuleSet
from ditto_kernel.enums import OrderSide

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_CALENDAR = (
    "2026-03-02",
    "2026-03-03",
    "2026-03-04",
    "2026-03-05",
    "2026-03-06",
    "2026-03-09",
    "2026-03-10",
    "2026-03-11",
    "2026-03-12",
    "2026-03-13",
)

_T1_RULE = TradingRuleSet(
    instrument_id=1,
    as_of_date="2026-03-02",
    settlement_cycle=1,
    fund_settlement_cycle=1,
    price_limit_pct=0.10,
    order_types_supported=("market", "limit"),
    call_auction_sessions=("open", "close"),
)

_T0_RULE = TradingRuleSet(
    instrument_id=99,
    as_of_date="2026-03-02",
    settlement_cycle=0,
    fund_settlement_cycle=0,
    price_limit_pct=0.10,
    order_types_supported=("market", "limit"),
    call_auction_sessions=("open", "close"),
)

_POSITION = Position(
    instrument_id=1,
    quantity=1000,
    available_quantity=500,
    average_cost=10.0,
    market_value=10500.0,
    unrealized_pnl=500.0,
    realized_pnl=0.0,
    total_fees=15.0,
)


# ---------------------------------------------------------------------------
# SimpleSettlementModel
# ---------------------------------------------------------------------------


class TestSimpleSettlementModel:
    def test_always_tradable(self) -> None:
        model = SimpleSettlementModel()
        assert model.is_tradable(
            1,
            "2026-03-01",
            OrderSide.BUY,
            _POSITION,
            _T1_RULE,
        )
        assert model.is_tradable(
            1,
            "2026-03-01",
            OrderSide.SELL,
            _POSITION,
            _T1_RULE,
        )

    def test_settle_date_same_day(self) -> None:
        model = SimpleSettlementModel()
        assert model.settle_date("2026-03-01", _T1_RULE) == "2026-03-01"
        assert model.settle_date("2026-03-01", _T0_RULE) == "2026-03-01"


# ---------------------------------------------------------------------------
# AShareSettlementModel
# ---------------------------------------------------------------------------


class TestAShareSettlementModel:
    def test_buy_always_tradable(self) -> None:
        model = AShareSettlementModel()
        assert model.is_tradable(
            1,
            "2026-03-02",
            OrderSide.BUY,
            _POSITION,
            _T1_RULE,
        )

    def test_t0_sell_tradable(self) -> None:
        model = AShareSettlementModel()
        assert model.is_tradable(
            99,
            "2026-03-02",
            OrderSide.SELL,
            _POSITION,
            _T0_RULE,
        )

    def test_t1_sell_tradable(self) -> None:
        """SettlementModel 总是返回 True, 冻结逻辑在 Brokerage 层。"""
        model = AShareSettlementModel()
        assert model.is_tradable(
            1,
            "2026-03-02",
            OrderSide.SELL,
            _POSITION,
            _T1_RULE,
        )

    def test_no_position_sell_tradable(self) -> None:
        model = AShareSettlementModel()
        assert model.is_tradable(
            1,
            "2026-03-02",
            OrderSide.SELL,
            None,
            _T1_RULE,
        )

    def test_t0_settle_date_same_day(self) -> None:
        model = AShareSettlementModel()
        assert model.settle_date("2026-03-02", _T0_RULE) == "2026-03-02"

    def test_t1_settle_date_next_trading_day(self) -> None:
        model = AShareSettlementModel(trading_calendar=_CALENDAR)
        result = model.settle_date("2026-03-02", _T1_RULE)
        assert result == "2026-03-03"

    def test_t1_settle_date_skips_weekend(self) -> None:
        """周五 → 下周一 (跳过周六周日)。"""
        model = AShareSettlementModel(trading_calendar=_CALENDAR)
        result = model.settle_date("2026-03-06", _T1_RULE)
        assert result == "2026-03-09"

    def test_empty_calendar_fallback(self) -> None:
        """无日历时简单加 N 天。"""
        model = AShareSettlementModel()
        result = model.settle_date("2026-03-02", _T1_RULE)
        assert result == "2026-03-03"

    def test_date_not_in_calendar_fallback(self) -> None:
        """trade_date 不在日历中, fallback。"""
        model = AShareSettlementModel(trading_calendar=_CALENDAR)
        result = model.settle_date("2026-03-01", _T1_RULE)
        assert result == "2026-03-02"

    def test_frozen(self) -> None:
        model = AShareSettlementModel(trading_calendar=_CALENDAR)
        with pytest.raises(AttributeError):
            model.trading_calendar = ()  # type: ignore[misc]
