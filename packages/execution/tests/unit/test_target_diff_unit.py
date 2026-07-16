"""compute_diff / DiffContext 单元测试 — 直接覆盖 target_diff 模块."""

from collections.abc import Callable
from types import MappingProxyType

import pytest
from ditto_execution._planner_types import BlockedOrder
from ditto_execution.market_precheck import pre_check
from ditto_execution.orders.book import OrderBookReadOnly
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.target_diff import DiffContext, compute_diff, compute_pending_delta
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    MarketSnapshot,
    TradingRuleSet,
)
from ditto_portfolio.accounting import (
    AccountView,
    CashBook,
    Position,
)
from ditto_strategy.alpha.models import TargetPortfolio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PreCheckFn = Callable[
    [InstrumentId, int, dict[InstrumentId, MarketSnapshot]],
    BlockedOrder | None,
]


def _iid(n: int) -> InstrumentId:
    return InstrumentId(n)


def _position(
    instrument_id: int,
    quantity: int = 100,
    market_value: float = 10000.0,
    available_quantity: int | None = None,
) -> Position:
    avg_cost = market_value / quantity if quantity > 0 else 0.0
    return Position(
        instrument_id=_iid(instrument_id),
        quantity=quantity,
        available_quantity=(
            available_quantity if available_quantity is not None else quantity
        ),
        average_cost=avg_cost,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _account_view(
    positions: dict[int, Position] | None = None,
    nav: float = 100_000.0,
) -> AccountView:
    pos = positions or {}
    return AccountView(
        positions=MappingProxyType({_iid(k): v for k, v in pos.items()}),
        cash=CashBook(available=nav, settled=nav, frozen=0.0),
        total_value=nav,
        nav=nav,
        exposure=0.0,
    )


def _target(positions: dict[int, float]) -> TargetPortfolio:
    return TargetPortfolio(
        trade_date="2026-05-10",
        strategy_id="test",
        run_id="run-001",
        positions={_iid(k): v for k, v in positions.items()},
    )


def _make_order(iid: InstrumentId, direction: OrderSide, quantity: int) -> Order:
    return Order(
        client_id=ClientOrderId(value=f"test-{iid}-{direction.value}-{quantity}"),
        instrument_id=iid,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
    )


def _snap(
    instrument_id: int = 1,
    close: float = 10.0,
    limit_up: float | None = None,
    limit_down: float | None = None,
    is_suspended: bool = False,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-05-10",
        instrument_id=_iid(instrument_id),
        open=close,
        high=close,
        low=close,
        close=close,
        prev_close=close,
        volume=1_000_000,
        amount=close * 1_000_000,
        is_suspended=is_suspended,
        limit_up=limit_up,
        limit_down=limit_down,
    )


def _definition(
    instrument_id: int = 1,
    lot_size: int = 100,
) -> InstrumentDefinition:
    return InstrumentDefinition(
        instrument_id=_iid(instrument_id),
        asset_class="etf",
        exchange="XSHE",
        currency="CNY",
        tick_size=0.001,
        lot_size=lot_size,
        multiplier=1.0,
        board_segment="main",
        lifecycle_state="normal",
    )


def _trading_rule(
    instrument_id: int = 1,
    settlement_cycle: int = 0,
) -> TradingRuleSet:
    return TradingRuleSet(
        instrument_id=_iid(instrument_id),
        as_of_date="2026-05-10",
        settlement_cycle=settlement_cycle,
        fund_settlement_cycle=settlement_cycle,
        price_limit_pct=0.10,
        order_types_supported=("market", "limit"),
        call_auction_sessions=("open", "close"),
    )


def _fee_schedule(
    instrument_id: int = 1,
) -> FeeSchedule:
    return FeeSchedule(
        instrument_id=_iid(instrument_id),
        as_of_date="2026-05-10",
        commission_rate=0.0,
        min_commission=0.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
    )


def _instrument_rules(
    instrument_id: int = 1,
    lot_size: int = 100,
    settlement_cycle: int = 0,
) -> InstrumentRules:
    return (
        _definition(instrument_id, lot_size),
        _trading_rule(instrument_id, settlement_cycle),
        _fee_schedule(instrument_id),
    )


def _no_pre_check(
    iid: InstrumentId, qty: int, snaps: dict[InstrumentId, MarketSnapshot]
) -> BlockedOrder | None:
    return None


def _ctx(
    target_positions: dict[int, float] | None = None,
    account_positions: dict[int, Position] | None = None,
    pending_delta: dict[int, int] | None = None,
    locked: set[int] | None = None,
    instruments: set[int] | None = None,
    rules_map: dict[int, InstrumentRules] | None = None,
    snaps_map: dict[int, MarketSnapshot] | None = None,
    lot_size: int = 100,
    pre_check_fn: _PreCheckFn | None = None,
    nav: float = 100_000.0,
) -> DiffContext:
    """构建测试用 DiffContext."""
    target = _target(target_positions or {})
    account = _account_view(account_positions, nav=nav)
    delta = {_iid(k): v for k, v in (pending_delta or {}).items()}

    all_iids = set(target.positions.keys()) | {
        _iid(k) for k in (account_positions or {})
    }
    if instruments:
        all_iids |= {_iid(k) for k in instruments}

    inst_rules = {_iid(k): v for k, v in (rules_map or {}).items()}
    market_snaps = {_iid(k): v for k, v in (snaps_map or {}).items()}

    locked_set = {_iid(k) for k in (locked or set())}
    check_fn: _PreCheckFn = pre_check_fn if pre_check_fn is not None else _no_pre_check

    return DiffContext(
        target=target,
        account_view=account,
        pending_delta=delta,
        all_instruments=all_iids,
        instrument_rules=inst_rules,
        market_snapshots=market_snaps,
        default_lot_size=lot_size,
        locked_instruments=locked_set,
        pre_check_fn=check_fn,
    )


# ---------------------------------------------------------------------------
# DiffContext frozen tests
# ---------------------------------------------------------------------------


class TestDiffContextFrozen:
    def test_immutable(self) -> None:
        ctx = _ctx()
        with pytest.raises(AttributeError):
            ctx.default_lot_size = 200  # type: ignore[misc]

    def test_is_frozen_dataclass(self) -> None:
        import dataclasses

        assert dataclasses.is_dataclass(DiffContext)
        fields = {f.name for f in dataclasses.fields(DiffContext)}
        assert "target" in fields
        assert "pre_check_fn" in fields


# ---------------------------------------------------------------------------
# compute_diff — basic scenarios
# ---------------------------------------------------------------------------


class TestComputeDiffBasic:
    def test_empty_target_no_positions(self) -> None:
        """空目标 + 空持仓 → 无订单."""
        ctx = _ctx()
        orders, blocked = compute_diff(ctx, _make_order)
        assert orders == []
        assert blocked == []

    def test_single_buy(self) -> None:
        """新建仓位 — 买入."""
        ctx = _ctx(
            target_positions={1: 0.5},
            instruments={1},
            snaps_map={1: _snap(1, close=10.0)},
        )
        orders, _ = compute_diff(ctx, _make_order)
        assert len(orders) == 1
        assert orders[0].direction == OrderSide.BUY
        assert orders[0].instrument_id == _iid(1)

    def test_single_sell(self) -> None:
        """减仓 — 卖出."""
        ctx = _ctx(
            target_positions={},
            account_positions={1: _position(1, quantity=500)},
            instruments={1},
            snaps_map={1: _snap(1, close=10.0)},
        )
        orders, _ = compute_diff(ctx, _make_order)
        assert len(orders) >= 1
        assert all(o.direction == OrderSide.SELL for o in orders)
        assert all(o.instrument_id == _iid(1) for o in orders)

    def test_current_price_reversal_uses_exact_target_shares_for_sell(self) -> None:
        """D 日价格重估后，100 股到目标 62 股应只卖出 38 股。"""
        ctx = _ctx(
            target_positions={1: 0.5},
            account_positions={1: _position(1, quantity=100, market_value=1_000.0)},
            instruments={1},
            snaps_map={1: _snap(1, close=80.0)},
            nav=10_000.0,
        )

        orders, blocked = compute_diff(ctx, _make_order)

        assert blocked == []
        assert [(order.direction, order.quantity) for order in orders] == [
            (OrderSide.SELL, 38)
        ]


# ---------------------------------------------------------------------------
# compute_diff — pending delta
# ---------------------------------------------------------------------------


class TestComputeDiffPendingDelta:
    def test_pending_buy_reduces_order(self) -> None:
        """已有 pending buy → 新买单数量减少."""
        ctx_no_pending = _ctx(
            target_positions={1: 0.5},
            instruments={1},
            snaps_map={1: _snap(1, close=10.0)},
        )
        ctx_with_pending = _ctx(
            target_positions={1: 0.5},
            instruments={1},
            snaps_map={1: _snap(1, close=10.0)},
            pending_delta={1: 300},
        )
        orders_normal, _ = compute_diff(ctx_no_pending, _make_order)
        orders_pending, _ = compute_diff(ctx_with_pending, _make_order)
        assert sum(o.quantity for o in orders_pending) < sum(
            o.quantity for o in orders_normal
        )


# ---------------------------------------------------------------------------
# compute_diff — locked instruments
# ---------------------------------------------------------------------------


class TestComputeDiffLocked:
    def test_locked_instrument_blocks_buy(self) -> None:
        """锁定标的 → 买入被阻止."""
        ctx = _ctx(
            target_positions={1: 0.5},
            instruments={1},
            snaps_map={1: _snap(1, close=10.0)},
            locked={1},
        )
        orders, blocked = compute_diff(ctx, _make_order)
        assert len(orders) == 0
        assert len(blocked) == 1
        assert blocked[0].reason == "risk_locked"
        assert blocked[0].instrument_id == _iid(1)


# ---------------------------------------------------------------------------
# compute_diff — pre_check integration
# ---------------------------------------------------------------------------


class TestComputeDiffPreCheck:
    def test_pre_check_suspended_blocks(self) -> None:
        """停牌 → pre_check 返回 BlockedOrder."""
        ctx = _ctx(
            target_positions={1: 0.5},
            instruments={1},
            snaps_map={1: _snap(1, close=10.0, is_suspended=True)},
            pre_check_fn=pre_check,
        )
        orders, blocked = compute_diff(ctx, _make_order)
        assert len(orders) == 0
        assert len(blocked) >= 1
        assert blocked[0].reason == "suspended"

    def test_pre_check_limit_up_defers_buy(self) -> None:
        """涨停 → 买入被 defer."""
        ctx = _ctx(
            target_positions={1: 0.5},
            instruments={1},
            snaps_map={1: _snap(1, close=11.0, limit_up=11.0)},
            pre_check_fn=pre_check,
        )
        orders, blocked = compute_diff(ctx, _make_order)
        assert len(orders) == 0
        assert any(b.reason == "limit_up_no_buy" for b in blocked)


# ---------------------------------------------------------------------------
# compute_diff — T+1 settlement
# ---------------------------------------------------------------------------


class TestComputeDiffSettlement:
    def test_t_plus1_limits_sell(self) -> None:
        """T+1 规则限制可卖出数量."""
        ctx = _ctx(
            target_positions={},
            account_positions={1: _position(1, quantity=500, available_quantity=200)},
            instruments={1},
            snaps_map={1: _snap(1, close=10.0)},
            rules_map={1: _instrument_rules(1, lot_size=100, settlement_cycle=1)},
        )
        orders, blocked = compute_diff(ctx, _make_order)
        sell_qty = sum(o.quantity for o in orders if o.direction == OrderSide.SELL)
        assert sell_qty <= 200
        t_plus1_blocked = [b for b in blocked if b.reason == "t_plus1_not_sellable"]
        assert len(t_plus1_blocked) > 0


# ---------------------------------------------------------------------------
# compute_pending_delta
# ---------------------------------------------------------------------------


class TestComputePendingDelta:
    def test_empty(self) -> None:
        ob = OrderBookReadOnly({})
        assert compute_pending_delta(ob) == {}

    def test_buy_and_sell(self) -> None:
        buy = OrderTicket(
            order=Order(
                client_id=ClientOrderId(value="b1"),
                instrument_id=_iid(1),
                order_type=OrderType.MARKET,
                direction=OrderSide.BUY,
                quantity=100,
            ),
            status=OrderStatus.SUBMITTED,
        )
        sell = OrderTicket(
            order=Order(
                client_id=ClientOrderId(value="s1"),
                instrument_id=_iid(2),
                order_type=OrderType.MARKET,
                direction=OrderSide.SELL,
                quantity=200,
            ),
            status=OrderStatus.SUBMITTED,
        )
        delta = compute_pending_delta(OrderBookReadOnly({"b1": buy, "s1": sell}))
        assert delta[_iid(1)] == 100
        assert delta[_iid(2)] == -200


def test_buy_below_board_lot_is_deferred_with_reason() -> None:
    """不足一手的买入差额不生成订单，并保留可解释原因。"""
    ctx = _ctx(
        target_positions={1: 0.01},
        account_positions={1: _position(1, quantity=50, market_value=500.0)},
        snaps_map={1: _snap(close=10.0)},
        nav=100_000.0,
    )

    orders, blocked = compute_diff(ctx, _make_order)

    assert orders == []
    assert len(blocked) == 1
    assert blocked[0].reason == "below_board_lot"
    assert blocked[0].intended_quantity == 50
