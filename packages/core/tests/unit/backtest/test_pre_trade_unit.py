"""PreTrade V3 — 全部规则单元测试。"""

from types import MappingProxyType

import pytest
from ditto_core.accounting.account import AccountView
from ditto_core.accounting.buying_power import CashAccountBuyingPower
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import (
    Order,
    OrderBookReadOnly,
    OrderDirection,
    OrderStatus,
    OrderTicket,
    OrderType,
)
from ditto_core.backtest.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    ConcentrationPreCheck,
    DailyTurnoverPreCheck,
    Decision,
    LotSizeCheck,
    NoShortSellCheck,
    OrderCheckResult,
    PreTradeContext,
    PreTradeRiskCheck,
    PriceValidityCheck,
)
from ditto_core.execution.reality import SimpleFeeModel
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_core.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instrument_rules(
    instrument_id: str = "ETF-001",
    lot_size: int = 100,
) -> InstrumentRules:
    """构造 InstrumentRules 元组。"""
    definition = InstrumentDefinition(
        instrument_id=instrument_id,
        asset_class="etf",
        exchange="XSHE",
        currency="CNY",
        tick_size=0.01,
        lot_size=lot_size,
        multiplier=1.0,
        board_segment="main",
        lifecycle_state="normal",
    )
    trading_rule = TradingRuleSet(
        instrument_id=instrument_id,
        as_of_date="2026-01-01",
        settlement_cycle=1,
        fund_settlement_cycle=1,
        price_limit_pct=0.10,
        order_types_supported=("market", "limit"),
        call_auction_sessions=("open", "close"),
    )
    fee_schedule = FeeSchedule(
        instrument_id=instrument_id,
        as_of_date="2026-01-01",
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
    )
    return (definition, trading_rule, fee_schedule)


def _make_snapshot(
    instrument_id: str = "ETF-001",
    close: float = 10.0,
    prev_close: float = 10.0,
    limit_up: float | None = 11.0,
    limit_down: float | None = 9.0,
) -> MarketSnapshot:
    """构造 MarketSnapshot。"""
    return MarketSnapshot(
        trade_date="2026-01-01",
        instrument_id=instrument_id,
        open=close,
        high=close,
        low=close,
        close=close,
        prev_close=prev_close,
        volume=100000.0,
        amount=1_000_000.0,
        limit_up=limit_up,
        limit_down=limit_down,
    )


@pytest.fixture
def rules() -> dict[str, InstrumentRules]:
    return {
        "ETF-001": _make_instrument_rules("ETF-001"),
        "ETF-002": _make_instrument_rules("ETF-002", lot_size=200),
    }


@pytest.fixture
def snapshots() -> dict[str, MarketSnapshot]:
    return {
        "ETF-001": _make_snapshot(
            "ETF-001",
            close=10.0,
            limit_up=11.0,
            limit_down=9.0,
        ),
        "ETF-002": _make_snapshot(
            "ETF-002",
            close=20.0,
            limit_up=22.0,
            limit_down=18.0,
        ),
    }


@pytest.fixture
def cash_book() -> CashBook:
    return CashBook(available=500_000.0, settled=500_000.0, frozen=0.0)


@pytest.fixture
def account_view(cash_book: CashBook) -> AccountView:
    return AccountView(
        positions=MappingProxyType({}),
        cash=cash_book,
        total_value=1_000_000.0,
        nav=1_000_000.0,
        exposure=0.0,
        pending_buy_value=0.0,
        order_book=OrderBookReadOnly({}),
    )


@pytest.fixture
def fee_model() -> SimpleFeeModel:
    return SimpleFeeModel()


@pytest.fixture
def buying_power_model() -> CashAccountBuyingPower:
    return CashAccountBuyingPower()


@pytest.fixture
def empty_context(
    account_view: AccountView,
    rules: dict[str, InstrumentRules],
    snapshots: dict[str, MarketSnapshot],
    fee_model: SimpleFeeModel,
    buying_power_model: CashAccountBuyingPower,
) -> PreTradeContext:
    return PreTradeContext(
        account_view=account_view,
        rules=rules,
        market_snapshots=snapshots,
        fee_model=fee_model,
        buying_power_model=buying_power_model,
    )


def _buy_order(
    order_id: str = "o-1",
    instrument_id: str = "ETF-001",
    quantity: int = 100,
    price: float | None = None,
    order_type: OrderType = OrderType.MARKET,
) -> Order:
    return Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=order_type,
        direction=OrderDirection.BUY,
        quantity=quantity,
        price=price,
    )


def _sell_order(
    order_id: str = "o-sell",
    instrument_id: str = "ETF-001",
    quantity: int = 100,
) -> Order:
    return Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=OrderDirection.SELL,
        quantity=quantity,
    )


# ---------------------------------------------------------------------------
# OrderCheckResult
# ---------------------------------------------------------------------------


class TestOrderCheckResult:
    def test_frozen(self) -> None:
        result = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="o-1",
        )
        with pytest.raises(AttributeError):
            result.decision = Decision.REJECT  # type: ignore[misc]

    def test_resize_result(self) -> None:
        result = OrderCheckResult(
            decision=Decision.RESIZE,
            order_id="o-1",
            resized_quantity=200,
            reason="lot_size",
            triggered_checks=("lot_size",),
        )
        assert result.resized_quantity == 200
        assert result.triggered_checks == ("lot_size",)


# ---------------------------------------------------------------------------
# PreTradeContext V3 — 辅助方法
# ---------------------------------------------------------------------------


class TestPreTradeContextHelpers:
    def test_price_for_existing(self, empty_context: PreTradeContext) -> None:
        assert empty_context.price_for("ETF-001") == 10.0
        assert empty_context.price_for("ETF-002") == 20.0

    def test_price_for_missing(self, empty_context: PreTradeContext) -> None:
        assert empty_context.price_for("ETF-UNKNOWN") is None

    def test_lot_size_for_existing(self, empty_context: PreTradeContext) -> None:
        assert empty_context.lot_size_for("ETF-001") == 100
        assert empty_context.lot_size_for("ETF-002") == 200

    def test_lot_size_for_missing(self, empty_context: PreTradeContext) -> None:
        assert empty_context.lot_size_for("ETF-UNKNOWN") == 100

    def test_fee_schedule_for_existing(self, empty_context: PreTradeContext) -> None:
        fs = empty_context.fee_schedule_for("ETF-001")
        assert fs.commission_rate == 0.0003
        assert fs.min_commission == 5.0

    def test_fee_schedule_for_missing(self, empty_context: PreTradeContext) -> None:
        fs = empty_context.fee_schedule_for("ETF-UNKNOWN")
        assert fs.commission_rate == 0.0003  # 默认值

    def test_estimate_order_cost(self, empty_context: PreTradeContext) -> None:
        order = _buy_order(quantity=100)
        cost = empty_context.estimate_order_cost(order)
        # 100 * 10.0 = 1000 + fee(5.0 min)
        assert cost == 1005.0

    def test_estimate_order_cost_missing_price(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        order = _buy_order(instrument_id="ETF-UNKNOWN", quantity=100)
        assert empty_context.estimate_order_cost(order) == 0.0

    def test_frozen(self, empty_context: PreTradeContext) -> None:
        with pytest.raises(AttributeError):
            empty_context.account_view = empty_context.account_view  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PreTradeContext — F1 rolling context
# ---------------------------------------------------------------------------


class TestPreTradeContext:
    def test_buy_reduces_available_and_increases_frozen(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """F1: buy order reduces available, increases frozen。"""
        order = _buy_order(quantity=100)
        new_ctx = empty_context.with_order_accepted(order)

        assert (
            new_ctx.account_view.cash.available
            < empty_context.account_view.cash.available
        )
        assert new_ctx.account_view.cash.frozen > empty_context.account_view.cash.frozen
        assert (
            new_ctx.account_view.pending_buy_value
            > empty_context.account_view.pending_buy_value
        )

    def test_sell_decreases_available_quantity(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """B3: sell order decreases available_quantity。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=500,
            available_quantity=500,
            average_cost=10.0,
            market_value=5000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=505_000.0,
            nav=505_000.0,
            exposure=5000.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = PreTradeContext(
            account_view=view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
        )

        sell = _sell_order(quantity=200)
        new_ctx = ctx.with_order_accepted(sell)

        assert new_ctx.account_view.positions["ETF-001"].available_quantity == 300

    def test_sell_does_not_exceed_available(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """B3: sell available_quantity cannot go below 0。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=501_000.0,
            nav=501_000.0,
            exposure=1000.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = PreTradeContext(
            account_view=view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
        )

        sell = _sell_order(quantity=200)
        new_ctx = ctx.with_order_accepted(sell)

        assert new_ctx.account_view.positions["ETF-001"].available_quantity == 0

    def test_rolling_context_second_order_sees_first(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """F1: second buy order sees reserved cash from first。"""
        order1 = _buy_order(order_id="o-1", quantity=100)
        ctx1 = empty_context.with_order_accepted(order1)

        order2 = _buy_order(order_id="o-2", quantity=100)
        ctx2 = ctx1.with_order_accepted(order2)

        assert ctx2.account_view.cash.available < ctx1.account_view.cash.available
        assert ctx2.account_view.cash.frozen > ctx1.account_view.cash.frozen

    def test_no_price_data_returns_same_context(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """Order with no price data -> context unchanged。"""
        order = _buy_order(instrument_id="ETF-UNKNOWN", quantity=100)
        new_ctx = empty_context.with_order_accepted(order)

        assert (
            new_ctx.account_view.cash.available
            == empty_context.account_view.cash.available
        )

    def test_with_order_accepted_preserves_rules_and_snapshots(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """F1: rolling update preserves rules, snapshots, models。"""
        order = _buy_order(quantity=100)
        new_ctx = empty_context.with_order_accepted(order)

        assert new_ctx.rules is empty_context.rules
        assert new_ctx.market_snapshots is empty_context.market_snapshots
        assert new_ctx.fee_model is empty_context.fee_model
        assert new_ctx.buying_power_model is empty_context.buying_power_model
        assert new_ctx.pending_tickets is empty_context.pending_tickets


# ---------------------------------------------------------------------------
# NoShortSellCheck
# ---------------------------------------------------------------------------


class TestNoShortSellCheck:
    def test_buy_always_accepts(self, empty_context: PreTradeContext) -> None:
        check = NoShortSellCheck()
        order = _buy_order(quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_sell_with_position_accepts(self, empty_context: PreTradeContext) -> None:
        """有充足持仓时卖出通过。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=500,
            available_quantity=500,
            average_cost=10.0,
            market_value=5000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=505_000.0,
            nav=505_000.0,
            exposure=5000.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = PreTradeContext(
            account_view=view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
        )

        check = NoShortSellCheck()
        result = check.check_order(_sell_order(quantity=300), ctx)

        assert result.decision == Decision.ACCEPT

    def test_sell_no_position_rejects(self, empty_context: PreTradeContext) -> None:
        """无持仓时卖出拒绝。"""
        check = NoShortSellCheck()
        result = check.check_order(_sell_order(quantity=100), empty_context)

        assert result.decision == Decision.REJECT
        assert "no_short_sell" in result.triggered_checks
        assert "available=0" in (result.reason or "")

    def test_sell_insufficient_quantity_rejects(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """持仓数量不足时卖出拒绝。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=50,
            available_quantity=50,
            average_cost=10.0,
            market_value=500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=500_500.0,
            nav=500_500.0,
            exposure=500.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = PreTradeContext(
            account_view=view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
        )

        check = NoShortSellCheck()
        result = check.check_order(_sell_order(quantity=100), ctx)

        assert result.decision == Decision.REJECT
        assert "available=50" in (result.reason or "")


# ---------------------------------------------------------------------------
# PriceValidityCheck
# ---------------------------------------------------------------------------


class TestPriceValidityCheck:
    def test_market_order_accepts(self, empty_context: PreTradeContext) -> None:
        check = PriceValidityCheck()
        order = _buy_order(order_type=OrderType.MARKET)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_limit_order_in_range_accepts(self, empty_context: PreTradeContext) -> None:
        check = PriceValidityCheck()
        order = _buy_order(order_type=OrderType.LIMIT, price=10.5)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_limit_order_at_boundary_accepts(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """边界值 price == limit_up / limit_down 应通过。"""
        check = PriceValidityCheck()
        order_up = _buy_order(order_type=OrderType.LIMIT, price=11.0)
        order_down = _buy_order(order_type=OrderType.LIMIT, price=9.0)

        assert check.check_order(order_up, empty_context).decision == Decision.ACCEPT
        assert check.check_order(order_down, empty_context).decision == Decision.ACCEPT

    def test_limit_order_above_limit_up_rejects(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        check = PriceValidityCheck()
        order = _buy_order(order_type=OrderType.LIMIT, price=12.0)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "price_validity" in result.triggered_checks

    def test_limit_order_below_limit_down_rejects(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        check = PriceValidityCheck()
        order = _buy_order(order_type=OrderType.LIMIT, price=8.0)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "price_validity" in result.triggered_checks

    def test_no_snapshot_accepts(self, empty_context: PreTradeContext) -> None:
        """无市场快照时直接放行。"""
        check = PriceValidityCheck()
        order = _buy_order(
            instrument_id="ETF-UNKNOWN",
            order_type=OrderType.LIMIT,
            price=100.0,
        )
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_no_price_limit_accepts(self) -> None:
        """无涨跌停信息（如 IPO 前五日）时直接放行。"""
        snapshots = {
            "ETF-001": _make_snapshot(
                "ETF-001",
                close=10.0,
                limit_up=None,
                limit_down=None,
            ),
        }
        ctx = PreTradeContext(
            account_view=AccountView(
                positions=MappingProxyType({}),
                cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
                total_value=1_000_000.0,
                nav=1_000_000.0,
                exposure=0.0,
                pending_buy_value=0.0,
                order_book=OrderBookReadOnly({}),
            ),
            rules={"ETF-001": _make_instrument_rules("ETF-001")},
            market_snapshots=snapshots,
            fee_model=SimpleFeeModel(),
            buying_power_model=CashAccountBuyingPower(),
        )
        check = PriceValidityCheck()
        order = _buy_order(order_type=OrderType.LIMIT, price=100.0)
        result = check.check_order(order, ctx)

        assert result.decision == Decision.ACCEPT


# ---------------------------------------------------------------------------
# LotSizeCheck (V3: 使用 lot_size_for)
# ---------------------------------------------------------------------------


class TestLotSizeCheck:
    def test_exact_lot_passes(self, empty_context: PreTradeContext) -> None:
        check = LotSizeCheck()
        order = _buy_order(quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_multiple_lot_passes(self, empty_context: PreTradeContext) -> None:
        check = LotSizeCheck()
        order = _buy_order(quantity=300)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_below_lot_resizes_up(self, empty_context: PreTradeContext) -> None:
        check = LotSizeCheck()
        order = _buy_order(quantity=50)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.RESIZE
        assert result.resized_quantity == 100
        assert "lot_size" in result.triggered_checks

    def test_zero_quantity_resizes_to_lot(self, empty_context: PreTradeContext) -> None:
        check = LotSizeCheck()
        order = _buy_order(quantity=0)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.RESIZE
        assert result.resized_quantity == 100

    def test_sell_always_passes(self, empty_context: PreTradeContext) -> None:
        check = LotSizeCheck()
        order = _sell_order(quantity=50)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_per_instrument_lot_size(self, empty_context: PreTradeContext) -> None:
        """ETF-002 lot_size=200，50 -> resize to 200。"""
        check = LotSizeCheck()
        order = _buy_order(instrument_id="ETF-002", quantity=50)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.RESIZE
        assert result.resized_quantity == 200

    def test_missing_instrument_defaults_100(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """无规则标的默认 lot_size=100。"""
        check = LotSizeCheck()
        order = _buy_order(instrument_id="ETF-UNKNOWN", quantity=50)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.RESIZE
        assert result.resized_quantity == 100


# ---------------------------------------------------------------------------
# BuyingPowerCheck (V3: 使用 buying_power_model)
# ---------------------------------------------------------------------------


class TestBuyingPowerCheck:
    def test_sufficient_power_accepts(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        check = BuyingPowerCheck()
        order = _buy_order(quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT
        assert result.order_id == "o-1"

    def test_insufficient_power_rejects(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        check = BuyingPowerCheck()
        order = _buy_order(quantity=50000)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "buying_power" in (result.reason or "")

    def test_sell_always_accepts(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        check = BuyingPowerCheck()
        order = _sell_order()
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_triggered_check_id(self) -> None:
        ctx = PreTradeContext(
            account_view=AccountView(
                positions=MappingProxyType({}),
                cash=CashBook(available=1.0, settled=1.0, frozen=0.0),
                total_value=1.0,
                nav=1.0,
                exposure=0.0,
                pending_buy_value=0.0,
                order_book=OrderBookReadOnly({}),
            ),
            rules={"ETF-001": _make_instrument_rules("ETF-001")},
            market_snapshots={
                "ETF-001": _make_snapshot("ETF-001", close=10.0),
            },
            fee_model=SimpleFeeModel(),
            buying_power_model=CashAccountBuyingPower(),
        )
        check = BuyingPowerCheck()
        order = _buy_order(quantity=100)
        result = check.check_order(order, ctx)

        assert result.decision == Decision.REJECT
        assert "buying_power" in result.triggered_checks


# ---------------------------------------------------------------------------
# ConcentrationPreCheck
# ---------------------------------------------------------------------------


class TestConcentrationPreCheck:
    def test_buy_within_limit_accepts(self, empty_context: PreTradeContext) -> None:
        """NAV=1M, buy 100*10=1000 -> 0.1% < 20%。"""
        check = ConcentrationPreCheck(max_weight=0.20)
        order = _buy_order(quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_buy_exceeds_limit_rejects(self, empty_context: PreTradeContext) -> None:
        """NAV=1M, buy 20000*10=200k -> 20% == 20% → should reject (> max)。"""
        check = ConcentrationPreCheck(max_weight=0.20)
        order = _buy_order(quantity=20001)  # 200010 / 1M > 20%
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "concentration" in result.triggered_checks

    def test_buy_at_exact_limit_accepts(self, empty_context: PreTradeContext) -> None:
        """NAV=1M, buy 20000*10=200k -> 20% == 20% → should accept (<=)。"""
        check = ConcentrationPreCheck(max_weight=0.20)
        order = _buy_order(quantity=20000)  # 200000 / 1M = 20%
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_sell_always_accepts(self, empty_context: PreTradeContext) -> None:
        check = ConcentrationPreCheck(max_weight=0.20)
        order = _sell_order(quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_with_existing_position(self, empty_context: PreTradeContext) -> None:
        """已有持仓 150k + 新买 60k = 210k > 200k (20%)。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=15000,
            available_quantity=15000,
            average_cost=10.0,
            market_value=150_000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=850_000.0, settled=850_000.0, frozen=0.0),
            total_value=1_000_000.0,
            nav=1_000_000.0,
            exposure=150_000.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = PreTradeContext(
            account_view=view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
        )
        check = ConcentrationPreCheck(max_weight=0.20)
        # 150k + 6000*10=60k = 210k > 200k
        order = _buy_order(quantity=6000)
        result = check.check_order(order, ctx)

        assert result.decision == Decision.REJECT

    def test_no_position_no_price_accepts(self, empty_context: PreTradeContext) -> None:
        """无价格信息时直接放行。"""
        check = ConcentrationPreCheck(max_weight=0.20)
        order = _buy_order(instrument_id="ETF-UNKNOWN", quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_zero_nav_accepts(self) -> None:
        """NAV=0 时直接放行。"""
        ctx = PreTradeContext(
            account_view=AccountView(
                positions=MappingProxyType({}),
                cash=CashBook(available=0.0, settled=0.0, frozen=0.0),
                total_value=0.0,
                nav=0.0,
                exposure=0.0,
                pending_buy_value=0.0,
                order_book=OrderBookReadOnly({}),
            ),
            rules={"ETF-001": _make_instrument_rules("ETF-001")},
            market_snapshots={"ETF-001": _make_snapshot("ETF-001", close=10.0)},
            fee_model=SimpleFeeModel(),
            buying_power_model=CashAccountBuyingPower(),
        )
        check = ConcentrationPreCheck(max_weight=0.20)
        order = _buy_order(quantity=100)
        result = check.check_order(order, ctx)

        assert result.decision == Decision.ACCEPT

    def test_invalid_max_weight_raises(self) -> None:
        with pytest.raises(ValueError, match="max_weight must be in"):
            ConcentrationPreCheck(max_weight=0.0)
        with pytest.raises(ValueError, match="max_weight must be in"):
            ConcentrationPreCheck(max_weight=1.5)


# ---------------------------------------------------------------------------
# DailyTurnoverPreCheck
# ---------------------------------------------------------------------------


class TestDailyTurnoverPreCheck:
    def test_buy_within_limit_accepts(self, empty_context: PreTradeContext) -> None:
        """NAV=1M, buy 100*10=1000 -> 0.1% < 30%。"""
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        order = _buy_order(quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_buy_exceeds_limit_rejects(self, empty_context: PreTradeContext) -> None:
        """NAV=1M, buy 30001*10=300010 -> 30.001% > 30%。"""
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        order = _buy_order(quantity=30001)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "daily_turnover" in result.triggered_checks

    def test_buy_at_exact_limit_accepts(self, empty_context: PreTradeContext) -> None:
        """NAV=1M, buy 30000*10=300000 -> 30% == 30% -> accept (<=)。"""
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        order = _buy_order(quantity=30000)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_sell_always_accepts(self, empty_context: PreTradeContext) -> None:
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        order = _sell_order(quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_sell_pending_tickets_not_counted(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """SELL 票不计入换手率。"""
        ticket = OrderTicket(
            order=_sell_order(order_id="o-pending", quantity=100),
            status=OrderStatus.NEW,
        )
        ctx = PreTradeContext(
            account_view=empty_context.account_view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
            pending_tickets=(ticket,),
        )
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        # 即使有 pending sell ticket，当前 buy 不受影响
        order = _buy_order(quantity=30000)
        result = check.check_order(order, ctx)

        assert result.decision == Decision.ACCEPT

    def test_pending_buy_tickets_accumulate(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """已有 pending buy 20k + 当前 buy 15k = 35k > 30%。"""
        ticket = OrderTicket(
            order=_buy_order(order_id="o-pending", quantity=2000),
            status=OrderStatus.NEW,
        )
        ctx = PreTradeContext(
            account_view=empty_context.account_view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
            pending_tickets=(ticket,),
        )
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        # 2000*10=20000 + 11000*10=110000 = 130000 < 300000 → accept
        order = _buy_order(quantity=11000)
        result = check.check_order(order, ctx)

        assert result.decision == Decision.ACCEPT

        # 2000*10=20000 + 29000*10=290000 = 310000 > 300000 → reject
        order2 = _buy_order(quantity=29000)
        result2 = check.check_order(order2, ctx)

        assert result2.decision == Decision.REJECT

    def test_no_price_accepts(self, empty_context: PreTradeContext) -> None:
        """无价格信息时直接放行。"""
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        order = _buy_order(instrument_id="ETF-UNKNOWN", quantity=100)
        result = check.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_zero_nav_accepts(self) -> None:
        """NAV=0 时直接放行。"""
        ctx = PreTradeContext(
            account_view=AccountView(
                positions=MappingProxyType({}),
                cash=CashBook(available=0.0, settled=0.0, frozen=0.0),
                total_value=0.0,
                nav=0.0,
                exposure=0.0,
                pending_buy_value=0.0,
                order_book=OrderBookReadOnly({}),
            ),
            rules={"ETF-001": _make_instrument_rules("ETF-001")},
            market_snapshots={"ETF-001": _make_snapshot("ETF-001", close=10.0)},
            fee_model=SimpleFeeModel(),
            buying_power_model=CashAccountBuyingPower(),
        )
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        order = _buy_order(quantity=100)
        result = check.check_order(order, ctx)

        assert result.decision == Decision.ACCEPT

    def test_invalid_max_turnover_raises(self) -> None:
        with pytest.raises(ValueError, match="max_turnover must be in"):
            DailyTurnoverPreCheck(max_turnover=0.0)
        with pytest.raises(ValueError, match="max_turnover must be in"):
            DailyTurnoverPreCheck(max_turnover=1.5)


# ---------------------------------------------------------------------------
# CompositePreTradeCheck — A1 resize recheck
# ---------------------------------------------------------------------------


class TestCompositeResize:
    def test_lot_resize_then_buying_power_rejects(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """350 -> lot_size resize 400 -> buying_power reject (A1 recheck)。"""
        poor_view = AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(available=3_500.0, settled=3_500.0, frozen=0.0),
            total_value=3_500.0,
            nav=3_500.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = PreTradeContext(
            account_view=poor_view,
            rules=empty_context.rules,
            market_snapshots=empty_context.market_snapshots,
            fee_model=empty_context.fee_model,
            buying_power_model=empty_context.buying_power_model,
        )
        composite = CompositePreTradeCheck(
            checks=(
                NoShortSellCheck(),
                PriceValidityCheck(),
                LotSizeCheck(),
                BuyingPowerCheck(),
            ),
        )

        order = _buy_order(quantity=350)
        result = composite.check_order(order, ctx)

        assert result.decision == Decision.REJECT
        assert "buying_power" in (result.reason or "")

    def test_all_pass_accepts(self, empty_context: PreTradeContext) -> None:
        composite = CompositePreTradeCheck(
            checks=(
                NoShortSellCheck(),
                PriceValidityCheck(),
                LotSizeCheck(),
                BuyingPowerCheck(),
                ConcentrationPreCheck(),
                DailyTurnoverPreCheck(),
            ),
        )
        order = _buy_order(quantity=100)
        result = composite.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT

    def test_resize_returns_resized_quantity(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """Accept with resize — resized_quantity should reflect final qty。"""
        composite = CompositePreTradeCheck(
            checks=(
                NoShortSellCheck(),
                PriceValidityCheck(),
                LotSizeCheck(),
                BuyingPowerCheck(),
                ConcentrationPreCheck(),
                DailyTurnoverPreCheck(),
            ),
        )
        order = _buy_order(quantity=150)
        result = composite.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT
        assert result.resized_quantity == 200

    def test_resize_loop_detected(self, empty_context: PreTradeContext) -> None:
        """MAX_RESIZE_ITERATIONS exceeded -> reject。"""

        class LoopCheck(PreTradeRiskCheck):
            """Always resizes, simulating a loop。"""

            def check_order(
                self,
                order: Order,
                context: PreTradeContext,
            ) -> OrderCheckResult:
                return OrderCheckResult(
                    decision=Decision.RESIZE,
                    order_id=order.order_id,
                    resized_quantity=order.quantity + 100,
                    reason="always_resize",
                    triggered_checks=("loop_check",),
                )

        composite = CompositePreTradeCheck(checks=(LoopCheck(),))
        order = _buy_order(quantity=100)
        result = composite.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "resize loop" in (result.reason or "")

    def test_triggered_checks_chain(self, empty_context: PreTradeContext) -> None:
        """R2: triggered_checks records the full check id chain。"""
        composite = CompositePreTradeCheck(
            checks=(
                NoShortSellCheck(),
                PriceValidityCheck(),
                LotSizeCheck(),
                BuyingPowerCheck(),
                ConcentrationPreCheck(),
                DailyTurnoverPreCheck(),
            ),
        )
        order = _buy_order(quantity=50)
        result = composite.check_order(order, empty_context)

        assert result.decision == Decision.ACCEPT
        assert "lot_size" in result.triggered_checks

    def test_no_short_sell_short_circuits(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """NoShortSell 是第一个 check，reject 短路后续。"""
        composite = CompositePreTradeCheck(
            checks=(
                NoShortSellCheck(),
                PriceValidityCheck(),
                LotSizeCheck(),
                BuyingPowerCheck(),
                ConcentrationPreCheck(),
                DailyTurnoverPreCheck(),
            ),
        )
        order = _sell_order(quantity=100)
        result = composite.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "no_short_sell" in result.triggered_checks

    def test_price_validity_short_circuits(
        self,
        empty_context: PreTradeContext,
    ) -> None:
        """PriceValidity reject 短路后续 checks。"""
        composite = CompositePreTradeCheck(
            checks=(
                NoShortSellCheck(),
                PriceValidityCheck(),
                LotSizeCheck(),
                BuyingPowerCheck(),
                ConcentrationPreCheck(),
                DailyTurnoverPreCheck(),
            ),
        )
        # price=12.0 > limit_up=11.0
        order = _buy_order(order_type=OrderType.LIMIT, price=12.0)
        result = composite.check_order(order, empty_context)

        assert result.decision == Decision.REJECT
        assert "price_validity" in result.triggered_checks
