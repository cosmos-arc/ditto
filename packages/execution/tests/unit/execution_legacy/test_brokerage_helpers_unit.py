"""撮合辅助函数单元测试.

测试覆盖:
- _is_order_executable: 判断订单是否可执行的纯函数
- BacktestBrokerage._process_single_ticket: 处理单个委托单的方法
"""

from datetime import datetime
from unittest.mock import MagicMock

from ditto_execution.brokerage import BacktestBrokerage, _is_order_executable
from ditto_execution.fills import Filled, NoFill
from ditto_execution.reality.brokerage import BrokerageModel
from ditto_execution.reality.market import MarketSnapshot
from ditto_execution.reality.settlement import (
    SettlementModel,
    SimpleSettlementModel,
)
from ditto_execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    TradingRuleSet,
)
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.order_book import (
    Order,
    OrderSide,
    OrderStatus,
    OrderTicket,
    OrderType,
)
from ditto_portfolio.accounting.position import Position

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _order(
    order_id: str = "ORD-001",
    instrument_id: int = 1,
    order_type: OrderType = OrderType.MARKET,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 1000,
    price: float | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        instrument_id=InstrumentId(instrument_id),
        order_type=order_type,
        direction=direction,
        quantity=quantity,
        price=price,
        created_at=datetime(2026, 3, 1),
    )


def _ticket(
    order_id: str = "ORD-001",
    instrument_id: int = 1,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 1000,
) -> OrderTicket:
    return OrderTicket(
        order=_order(
            order_id=order_id,
            instrument_id=instrument_id,
            direction=direction,
            quantity=quantity,
        ),
        status=OrderStatus.SUBMITTED,
    )


def _trading_rule(instrument_id: int = 1) -> TradingRuleSet:
    return TradingRuleSet(
        instrument_id=InstrumentId(instrument_id),
        as_of_date="2026-01-01",
        settlement_cycle=0,
        fund_settlement_cycle=0,
        price_limit_pct=None,
        order_types_supported=("market", "limit"),
        call_auction_sessions=(),
    )


def _position(
    instrument_id: int = 1,
    quantity: int = 1000,
    available_quantity: int = 1000,
) -> Position:
    """构造仅包含 _is_order_executable 所需字段的 Position."""
    return Position(
        instrument_id=InstrumentId(instrument_id),
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=0.0,
        market_value=0.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


# ---------------------------------------------------------------------------
# _is_order_executable
# ---------------------------------------------------------------------------


class TestIsOrderExecutable:
    """_is_order_executable 模块级函数测试."""

    _IID = InstrumentId(1)
    _TRADE_DATE = "2026-01-01"

    def test_buy_always_executable_when_tradable(self) -> None:
        """买单在结算模型允许时可执行."""
        ticket = _ticket(direction=OrderSide.BUY)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()

        assert (
            _is_order_executable(
                ticket,
                None,
                settlement,
                self._IID,
                self._TRADE_DATE,
                rule,
            )
            is True
        )

    def test_sell_executable_with_sufficient_available(self) -> None:
        """卖单在可用数量 >= 剩余数量时可执行."""
        ticket = _ticket(direction=OrderSide.SELL, quantity=500)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=500)

        assert (
            _is_order_executable(
                ticket,
                position,
                settlement,
                self._IID,
                self._TRADE_DATE,
                rule,
            )
            is True
        )

    def test_sell_blocked_when_insufficient_available(self) -> None:
        """卖单在可用数量 < 剩余数量时被阻止."""
        ticket = _ticket(direction=OrderSide.SELL, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=500)

        assert (
            _is_order_executable(
                ticket,
                position,
                settlement,
                self._IID,
                self._TRADE_DATE,
                rule,
            )
            is False
        )

    def test_sell_with_no_position_passes_check(self) -> None:
        """无持仓的卖单通过 _is_order_executable.

        当 position 为 None 时，跳过可用数量检查。
        保留原始行为 — 下游撮合模型仍可拒绝该订单.
        """
        ticket = _ticket(direction=OrderSide.SELL, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()

        assert (
            _is_order_executable(
                ticket,
                None,
                settlement,
                self._IID,
                self._TRADE_DATE,
                rule,
            )
            is True
        )

    def test_not_tradable_by_settlement_model(self) -> None:
        """结算模型返回不可交易时返回 False."""
        ticket = _ticket(direction=OrderSide.BUY)
        settlement = MagicMock(spec=SettlementModel)
        settlement.is_tradable.return_value = False
        rule = _trading_rule()

        assert (
            _is_order_executable(
                ticket,
                None,
                settlement,
                self._IID,
                self._TRADE_DATE,
                rule,
            )
            is False
        )

    def test_sell_exact_available_executable(self) -> None:
        """卖单在可用数量等于剩余数量时可执行."""
        ticket = _ticket(direction=OrderSide.SELL, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=1000)

        assert (
            _is_order_executable(
                ticket,
                position,
                settlement,
                self._IID,
                self._TRADE_DATE,
                rule,
            )
            is True
        )

    def test_buy_with_position_ignores_available(self) -> None:
        """买单忽略可用数量检查."""
        ticket = _ticket(direction=OrderSide.BUY, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=0)

        assert (
            _is_order_executable(
                ticket,
                position,
                settlement,
                self._IID,
                self._TRADE_DATE,
                rule,
            )
            is True
        )


# ---------------------------------------------------------------------------
# 辅助函数 — _process_single_ticket
# ---------------------------------------------------------------------------


def _market_snapshot(
    instrument_id: int = 1,
    close: float = 10.0,
    is_suspended: bool = False,
) -> MarketSnapshot:
    """构造测试用 MarketSnapshot."""
    return MarketSnapshot(
        trade_date="2026-01-01",
        instrument_id=InstrumentId(instrument_id),
        open=close,
        high=close,
        low=close,
        close=close,
        prev_close=close,
        volume=1_000_000.0,
        amount=10_000_000.0,
        is_suspended=is_suspended,
    )


def _instrument_definition(instrument_id: int = 1) -> InstrumentDefinition:
    """构造最小化 InstrumentDefinition."""
    return InstrumentDefinition(
        instrument_id=InstrumentId(instrument_id),
        asset_class="etf",
        exchange="XSHE",
        currency="CNY",
        tick_size=0.001,
        lot_size=100,
        multiplier=1.0,
        board_segment="main",
        lifecycle_state="normal",
    )


def _fee_schedule(instrument_id: int = 1) -> FeeSchedule:
    """构造最小化 FeeSchedule."""
    return FeeSchedule(
        instrument_id=InstrumentId(instrument_id),
        as_of_date="2026-01-01",
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
    )


def _make_brokerage(
    account: Account | None = None,
) -> BacktestBrokerage:
    """构造带合理默认值的 BacktestBrokerage."""
    if account is None:
        account = Account(
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
    return BacktestBrokerage(account=account)


# ---------------------------------------------------------------------------
# _process_single_ticket
# ---------------------------------------------------------------------------


class TestProcessSingleTicket:
    """BacktestBrokerage._process_single_ticket 测试."""

    def test_returns_none_when_no_market_snapshot(self) -> None:
        """bars 字典无对应 instrument_id 时返回 None."""
        brokerage = _make_brokerage()
        ticket = _ticket(instrument_id=1)
        bars: dict[InstrumentId, MarketSnapshot] = {}  # 空 — iid=1 无快照

        result = brokerage._process_single_ticket(
            ticket=ticket,
            bars=bars,
            trade_date="2026-01-01",
            step_time=datetime(2026, 1, 1, 15, 0),
        )

        assert result is None

    def test_returns_none_when_settlement_model_says_not_tradable(self) -> None:
        """结算模型返回不可交易时返回 None."""
        account = Account(
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        brokerage = _make_brokerage(account=account)

        # 替换结算模型以拒绝所有交易
        brokerage._model = MagicMock(spec=BrokerageModel)
        brokerage._model.settlement_model = MagicMock()
        brokerage._model.settlement_model.is_tradable.return_value = False

        ticket = _ticket(instrument_id=1)
        market = _market_snapshot(instrument_id=1)
        bars = {InstrumentId(1): market}

        # rules_getter 仍需返回有效的三层规则
        defn = _instrument_definition(1)
        rule = _trading_rule(1)
        fee = _fee_schedule(1)
        brokerage._rules_getter = lambda _iid, _td: (defn, rule, fee)

        result = brokerage._process_single_ticket(
            ticket=ticket,
            bars=bars,
            trade_date="2026-01-01",
            step_time=datetime(2026, 1, 1, 15, 0),
        )

        assert result is None

    def test_returns_none_when_order_not_executable(self) -> None:
        """_is_order_executable 返回 False 时返回 None.

        测试可用数量不足的卖单.
        """
        account = Account(
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        # 为账户添加可用数量不足的持仓
        account.positions[InstrumentId(1)] = _position(
            instrument_id=1,
            quantity=1000,
            available_quantity=100,
        )

        brokerage = _make_brokerage(account=account)

        ticket = _ticket(instrument_id=1, direction=OrderSide.SELL, quantity=500)
        market = _market_snapshot(instrument_id=1)
        bars = {InstrumentId(1): market}

        result = brokerage._process_single_ticket(
            ticket=ticket,
            bars=bars,
            trade_date="2026-01-01",
            step_time=datetime(2026, 1, 1, 15, 0),
        )

        assert result is None

    def test_returns_fill_event_on_successful_fill(self) -> None:
        """正常路径: 撮合模型返回 Filled，返回 FillEvent."""
        account = Account(
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        brokerage = _make_brokerage(account=account)

        # 提交委托单使 order_book 跟踪
        ticket = _ticket(instrument_id=1, quantity=1000)
        account.order_book.submit(ticket)

        market = _market_snapshot(instrument_id=1, close=10.0)
        bars = {InstrumentId(1): market}

        # 配置模型 mock
        model = MagicMock(spec=BrokerageModel)
        model.settlement_model = MagicMock()
        model.slippage_model = MagicMock()
        model.fee_model = MagicMock()
        model.fill_model = MagicMock()
        model.settlement_model.is_tradable.return_value = True
        model.settlement_model.settle_date.return_value = "2026-01-01"
        model.slippage_model.estimate.return_value = 0.01
        model.fee_model.calculate.return_value = 5.0

        # 撮合模型返回与委托数量匹配的 Filled
        inner_fill_event = FillEvent(
            fill_id="fill-inner",
            order_id="ORD-001",
            instrument_id=InstrumentId(1),
            direction=OrderSide.BUY,
            filled_quantity=1000,
            fill_price=10.0,
            fee=5.0,
            slippage=0.0,
            event_time=datetime(2026, 1, 1, 15, 0),
            cumulative_quantity=1000,
            leaves_quantity=0,
        )
        model.fill_model.try_fill.return_value = Filled(fill_event=inner_fill_event)

        brokerage._model = model

        defn = _instrument_definition(1)
        rule = _trading_rule(1)
        fee = _fee_schedule(1)
        brokerage._rules_getter = lambda _iid, _td: (defn, rule, fee)

        result = brokerage._process_single_ticket(
            ticket=ticket,
            bars=bars,
            trade_date="2026-01-01",
            step_time=datetime(2026, 1, 1, 15, 0),
        )

        assert result is not None
        assert isinstance(result, FillEvent)
        assert result.order_id == "ORD-001"
        assert result.instrument_id == 1
        assert result.filled_quantity == 1000
        # 成交价应为基准价 + 滑点
        assert result.fill_price == 10.0 + 0.01
        assert result.fee == 5.0

    def test_marks_invalid_on_nofill_without_retry(self) -> None:
        """NoFill 且 can_retry=False 时委托单转为 INVALID."""
        account = Account(
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        brokerage = _make_brokerage(account=account)

        # 提交委托单使 order_book 跟踪
        ticket = _ticket(instrument_id=1)
        account.order_book.submit(ticket)

        market = _market_snapshot(instrument_id=1)
        bars = {InstrumentId(1): market}

        model = MagicMock(spec=BrokerageModel)
        model.settlement_model = MagicMock()
        model.slippage_model = MagicMock()
        model.fill_model = MagicMock()
        model.settlement_model.is_tradable.return_value = True
        model.slippage_model.estimate.return_value = 0.0
        model.fill_model.try_fill.return_value = NoFill(
            reason="suspended",
            can_retry=False,
        )
        brokerage._model = model

        defn = _instrument_definition(1)
        rule = _trading_rule(1)
        fee = _fee_schedule(1)
        brokerage._rules_getter = lambda _iid, _td: (defn, rule, fee)

        result = brokerage._process_single_ticket(
            ticket=ticket,
            bars=bars,
            trade_date="2026-01-01",
            step_time=datetime(2026, 1, 1, 15, 0),
        )

        assert result is None

        # 验证委托单在 order_book 中被标记为 INVALID
        updated_ticket = account.order_book.get("ORD-001")
        assert updated_ticket is not None
        assert updated_ticket.status == OrderStatus.INVALID

    def test_returns_none_but_keeps_submitted_on_nofill_with_retry(self) -> None:
        """NoFill 且 can_retry=True 时返回 None 但委托单保持 SUBMITTED."""
        account = Account(
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        brokerage = _make_brokerage(account=account)

        ticket = _ticket(instrument_id=1)
        account.order_book.submit(ticket)

        market = _market_snapshot(instrument_id=1)
        bars = {InstrumentId(1): market}

        model = MagicMock(spec=BrokerageModel)
        model.settlement_model = MagicMock()
        model.slippage_model = MagicMock()
        model.fill_model = MagicMock()
        model.settlement_model.is_tradable.return_value = True
        model.slippage_model.estimate.return_value = 0.0
        model.fill_model.try_fill.return_value = NoFill(
            reason="limit_up_deferred",
            can_retry=True,
        )
        brokerage._model = model

        defn = _instrument_definition(1)
        rule = _trading_rule(1)
        fee = _fee_schedule(1)
        brokerage._rules_getter = lambda _iid, _td: (defn, rule, fee)

        result = brokerage._process_single_ticket(
            ticket=ticket,
            bars=bars,
            trade_date="2026-01-01",
            step_time=datetime(2026, 1, 1, 15, 0),
        )

        assert result is None

        # 委托单应保持 SUBMITTED（非 INVALID，非 FILLED）
        updated_ticket = account.order_book.get("ORD-001")
        assert updated_ticket is not None
        assert updated_ticket.status == OrderStatus.SUBMITTED
