"""FillModel unit tests — SimpleFill, AShare, ClosingAuction."""

from dataclasses import dataclass

import pytest
from ditto_backtest.simulation.fill import (
    AShareFillModel,
    ClosingAuctionFillModel,
    SimpleFillModel,
)
from ditto_execution.fills import Filled, FillOutcome, NoFill
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import InstrumentDefinition, MarketSnapshot, TradingRuleSet

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _order(
    order_type: OrderType = OrderType.MARKET,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 100,
    price: float | None = None,
    instrument_id: InstrumentId = InstrumentId(1),
    order_id: str = "ORD-001",
) -> Order:
    return Order(
        client_id=ClientOrderId(order_id),
        instrument_id=instrument_id,
        order_type=order_type,
        direction=direction,
        quantity=quantity,
        price=price,
    )


def _market_snapshot(
    close: float = 10.5,
    low: float = 10.0,
    high: float = 11.0,
    instrument_id: int = 1,
    limit_up: float | None = None,
    limit_down: float | None = None,
    is_suspended: bool = False,
    avg_volume_20d: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-03-01",
        instrument_id=instrument_id,
        open=10.2,
        high=high,
        low=low,
        close=close,
        prev_close=10.0,
        volume=1_000_000,
        amount=10_500_000,
        limit_up=limit_up,
        limit_down=limit_down,
        is_suspended=is_suspended,
        avg_volume_20d=avg_volume_20d,
    )


_DEFINITION = InstrumentDefinition(
    instrument_id=1,
    asset_class="etf",
    exchange="XSHE",
    currency="CNY",
    tick_size=0.001,
    lot_size=100,
    multiplier=1.0,
    board_segment="main",
    lifecycle_state="normal",
)

_TRADING_RULE = TradingRuleSet(
    instrument_id=1,
    as_of_date="2026-03-01",
    settlement_cycle=1,
    fund_settlement_cycle=1,
    price_limit_pct=0.10,
    order_types_supported=("market", "limit"),
    call_auction_sessions=("open", "close"),
)


# ---------------------------------------------------------------------------
# SimpleFillModel
# ---------------------------------------------------------------------------


class TestSimpleFillModel:
    def test_market_order_fills(self) -> None:
        model = SimpleFillModel()
        order = _order()
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(10.5)

    def test_limit_order_in_range_fills(self) -> None:
        model = SimpleFillModel()
        order = _order(order_type=OrderType.LIMIT, price=10.3)
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(10.3)

    def test_limit_order_at_low_boundary(self) -> None:
        model = SimpleFillModel()
        order = _order(order_type=OrderType.LIMIT, price=10.0)
        market = _market_snapshot(close=10.5, low=10.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(10.0)

    def test_limit_order_at_high_boundary(self) -> None:
        model = SimpleFillModel()
        order = _order(order_type=OrderType.LIMIT, price=11.0)
        market = _market_snapshot(close=10.5, high=11.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(11.0)

    def test_limit_order_below_range_no_fill(self) -> None:
        model = SimpleFillModel()
        order = _order(order_type=OrderType.LIMIT, price=9.5)
        market = _market_snapshot(close=10.5, low=10.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "price_out_of_range"
        assert result.can_retry is False

    def test_limit_order_above_range_no_fill(self) -> None:
        model = SimpleFillModel()
        order = _order(order_type=OrderType.LIMIT, price=12.0)
        market = _market_snapshot(close=10.5, high=11.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "price_out_of_range"

    def test_limit_order_no_price_no_fill(self) -> None:
        """LIMIT 单无价格 -> price_out_of_range。"""
        model = SimpleFillModel()
        order = _order(order_type=OrderType.LIMIT, price=None)
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "price_out_of_range"

    def test_unsupported_order_type_no_fill(self) -> None:
        """不支持的订单类型 -> NoFill。"""
        model = SimpleFillModel()
        order = _order(order_type=OrderType.STOP_MARKET)
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "unsupported_order_type"

    def test_result_is_fill_outcome(self) -> None:
        model = SimpleFillModel()
        order = _order()
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, FillOutcome)

    def test_market_sell_fills_at_close(self) -> None:
        """SELL 方向: MARKET 单也以 close 成交 (无滑点)。"""
        model = SimpleFillModel()
        order = _order(direction=OrderSide.SELL)
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(10.5)


# ---------------------------------------------------------------------------
# AShareFillModel
# ---------------------------------------------------------------------------


class TestAShareFillModel:
    def test_suspended_no_fill_can_retry(self) -> None:
        model = AShareFillModel()
        order = _order()
        market = _market_snapshot(is_suspended=True)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "suspended"
        assert result.can_retry is True

    def test_limit_up_buy_no_fill(self) -> None:
        model = AShareFillModel()
        order = _order(direction=OrderSide.BUY)
        market = _market_snapshot(close=11.0, high=11.0, limit_up=11.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "limit_up_no_buy"
        assert result.can_retry is True

    def test_limit_down_sell_no_fill(self) -> None:
        model = AShareFillModel()
        order = _order(direction=OrderSide.SELL)
        market = _market_snapshot(close=10.0, low=10.0, limit_down=10.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "limit_down_no_sell"
        assert result.can_retry is True

    def test_limit_up_sell_fills(self) -> None:
        model = AShareFillModel()
        order = _order(direction=OrderSide.SELL)
        market = _market_snapshot(close=11.0, high=11.0, limit_up=11.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(11.0)

    def test_limit_down_buy_fills(self) -> None:
        model = AShareFillModel()
        order = _order(direction=OrderSide.BUY)
        market = _market_snapshot(close=10.0, low=10.0, limit_down=10.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(10.0)

    def test_market_order_normal_fills(self) -> None:
        model = AShareFillModel()
        order = _order()
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(10.5)

    def test_limit_order_in_range_fills(self) -> None:
        model = AShareFillModel()
        order = _order(order_type=OrderType.LIMIT, price=10.3)
        market = _market_snapshot(close=10.5)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.fill_price == pytest.approx(10.3)

    def test_limit_order_out_of_range_no_fill(self) -> None:
        model = AShareFillModel()
        order = _order(order_type=OrderType.LIMIT, price=12.0)
        market = _market_snapshot(close=10.5, high=11.0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "price_out_of_range"

    def test_market_on_close_delegates_to_auction(self) -> None:
        model = AShareFillModel()
        order = _order(order_type=OrderType.MARKET_ON_CLOSE, quantity=100)
        market = _market_snapshot(close=10.5, avg_volume_20d=1_000_000)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)

    def test_no_limit_up_info_treats_as_normal(self) -> None:
        """limit_up=None 视为正常, 不触发涨停规则。"""
        model = AShareFillModel()
        order = _order(direction=OrderSide.BUY)
        market = _market_snapshot(close=11.0, high=11.0, limit_up=None)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)

    def test_no_limit_down_info_treats_as_normal(self) -> None:
        """limit_down=None 视为正常, 不触发跌停规则。"""
        model = AShareFillModel()
        order = _order(direction=OrderSide.SELL)
        market = _market_snapshot(close=10.0, low=10.0, limit_down=None)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)


# ---------------------------------------------------------------------------
# ClosingAuctionFillModel
# ---------------------------------------------------------------------------


class TestClosingAuctionFillModel:
    def test_small_order_full_fill(self) -> None:
        model = ClosingAuctionFillModel()
        order = _order(order_type=OrderType.MARKET_ON_CLOSE, quantity=100)
        market = _market_snapshot(close=10.5, avg_volume_20d=1_000_000)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.filled_quantity == 100

    def test_large_order_partial_fill(self) -> None:
        model = ClosingAuctionFillModel(participation_rate_threshold=0.05)
        # max_acceptable = 1_000_000 * 0.05 = 50_000
        order = _order(order_type=OrderType.MARKET_ON_CLOSE, quantity=100_000)
        market = _market_snapshot(close=10.5, avg_volume_20d=1_000_000)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.filled_quantity == 50_000

    def test_extremely_large_order_zero_fill(self) -> None:
        model = ClosingAuctionFillModel(participation_rate_threshold=0.05)
        # max_acceptable = 100 * 0.05 = 5 → int(5) = 5, but qty=100
        # filled_qty = max(0, int(100 * 5/100)) = 5
        # Actually need to test when filled_qty rounds to 0
        # With qty=1, max_acceptable=0 → filled_qty = max(0, int(1*0/1)) = 0
        order = _order(order_type=OrderType.MARKET_ON_CLOSE, quantity=1)
        market = _market_snapshot(close=10.5, avg_volume_20d=0.0001)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, NoFill)
        assert result.reason == "insufficient_auction"
        assert result.can_retry is False

    def test_no_avg_volume_fallback_full_fill(self) -> None:
        model = ClosingAuctionFillModel()
        order = _order(order_type=OrderType.MARKET_ON_CLOSE, quantity=100)
        market = _market_snapshot(close=10.5, avg_volume_20d=None)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.filled_quantity == 100

    def test_zero_avg_volume_fallback_full_fill(self) -> None:
        model = ClosingAuctionFillModel()
        order = _order(order_type=OrderType.MARKET_ON_CLOSE, quantity=100)
        market = _market_snapshot(close=10.5, avg_volume_20d=0)
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)
        assert isinstance(result, Filled)
        assert result.fill_event.filled_quantity == 100


# ---------------------------------------------------------------------------
# AShareFillModel — Parametrized scenario matrix (v3 §5.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FillScenario:
    """Declarative fill scenario for parametrized testing."""

    name: str
    order_type: OrderType
    direction: OrderSide
    is_suspended: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    close: float = 10.5
    high: float = 11.0
    low: float = 10.0
    order_price: float | None = None
    should_fill: bool = True
    expected_reason: str | None = None
    expected_can_retry: bool = True


A_SHARE_FILL_SCENARIOS: list[FillScenario] = [
    # ── Core scenarios (v3 §5.3) ──────────────────────────────────────
    FillScenario(
        name="normal_market_buy_fills",
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        should_fill=True,
    ),
    FillScenario(
        name="suspended_market_buy_no_fill",
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        is_suspended=True,
        should_fill=False,
        expected_reason="suspended",
        expected_can_retry=True,
    ),
    FillScenario(
        name="limit_up_market_buy_no_fill",
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        close=11.0,
        high=11.0,
        limit_up=11.0,
        should_fill=False,
        expected_reason="limit_up_no_buy",
        expected_can_retry=True,
    ),
    FillScenario(
        name="limit_down_market_sell_no_fill",
        order_type=OrderType.MARKET,
        direction=OrderSide.SELL,
        close=10.0,
        low=10.0,
        limit_down=10.0,
        should_fill=False,
        expected_reason="limit_down_no_sell",
        expected_can_retry=True,
    ),
    FillScenario(
        name="limit_up_market_sell_fills",
        order_type=OrderType.MARKET,
        direction=OrderSide.SELL,
        close=11.0,
        high=11.0,
        limit_up=11.0,
        should_fill=True,
    ),
    FillScenario(
        name="limit_down_market_buy_fills",
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        close=10.0,
        low=10.0,
        limit_down=10.0,
        should_fill=True,
    ),
    # ── Edge cases ────────────────────────────────────────────────────
    FillScenario(
        name="limit_buy_at_exact_low_boundary_fills",
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        order_price=10.0,
        should_fill=True,
    ),
    FillScenario(
        name="limit_buy_below_low_no_fill",
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        order_price=9.5,
        should_fill=False,
        expected_reason="price_out_of_range",
        expected_can_retry=False,
    ),
    FillScenario(
        name="stop_market_unsupported_no_fill",
        order_type=OrderType.STOP_MARKET,
        direction=OrderSide.BUY,
        should_fill=False,
        expected_reason="unsupported_order_type",
        expected_can_retry=False,
    ),
]


class TestAShareFillScenarios:
    """Parametrized AShareFillModel scenario matrix."""

    @pytest.mark.parametrize("scenario", A_SHARE_FILL_SCENARIOS, ids=lambda s: s.name)
    def test_fill_scenario(self, scenario: FillScenario) -> None:
        model = AShareFillModel()
        order = _order(
            order_type=scenario.order_type,
            direction=scenario.direction,
            price=scenario.order_price,
        )
        market = _market_snapshot(
            close=scenario.close,
            high=scenario.high,
            low=scenario.low,
            limit_up=scenario.limit_up,
            limit_down=scenario.limit_down,
            is_suspended=scenario.is_suspended,
        )
        result = model.try_fill(order, market, _DEFINITION, _TRADING_RULE)

        if scenario.should_fill:
            assert isinstance(result, Filled), (
                f"Expected Filled but got {type(result).__name__}"
            )
            assert isinstance(result, FillOutcome)
        else:
            assert isinstance(result, NoFill), "Expected NoFill but got Filled"
            assert result.reason == scenario.expected_reason
            assert result.can_retry is scenario.expected_can_retry
