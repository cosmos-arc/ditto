"""
BacktestBrokerage — 回测经纪商.

BacktestBrokerage 是 state owner, 持有可变 Account 实例,
通过 fill / slippage / fee 模型处理订单成交。
"""

from __future__ import annotations

from datetime import datetime

from ditto_execution.brokerage import ProcessInput
from ditto_execution.errors import FillProcessingError
from ditto_execution.fills import Filled, NoFill
from ditto_execution.orders.book import OrderBook, OrderBookReadOnly
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.fsm import OrderStateError, transition
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger
from ditto_execution.reality.order import daily_buy_rejection, minimum_order_rejection
from ditto_execution.reality.price import round_to_tick
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    MarketSnapshot,
    RulesGetter,
    TradingRuleSet,
)
from ditto_portfolio.accounting import Account, AccountView, FillEvent, Position
from ditto_portfolio.accounting.conversions import ShareConversion

from ditto_backtest.result import BacktestSettlementStateSnapshot
from ditto_backtest.simulation import BrokerageModel
from ditto_backtest.simulation.settlement import SettlementModel

__all__ = ["BacktestBrokerage"]


# ---------------------------------------------------------------------------
# Default helpers
# ---------------------------------------------------------------------------


def _default_rules_getter(
    instrument_id: InstrumentId,
    trade_date: str,
) -> InstrumentRules:
    """默认规则获取 — 用于无 rules_getter 时的 fallback。"""
    return (
        InstrumentDefinition(
            instrument_id=instrument_id,
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=DEFAULT_LOT_SIZE,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        ),
        TradingRuleSet(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            settlement_cycle=0,
            fund_settlement_cycle=0,
            price_limit_pct=None,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        ),
        FeeSchedule(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            commission_rate=DEFAULT_COMMISSION_RATE,
            min_commission=DEFAULT_MIN_COMMISSION,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        ),
    )


def _is_order_executable(
    ticket: OrderTicket,
    position: Position | None,
    settlement_model: SettlementModel,
    instrument_id: InstrumentId,
    trade_date: str,
    trading_rule: TradingRuleSet,
) -> bool:
    """
    检查订单是否可执行 — 结算可交易性 + 卖出可用份额检查。

    Args:
        ticket: 待检查的订单票据
        position: 当前持仓（可为 None）
        settlement_model: 结算模型（需支持 is_tradable）
        instrument_id: 标的 ID
        trade_date: 交易日
        trading_rule: 交易规则

    Returns:
        True 表示订单可以继续执行流程

    """
    # Settlement check
    if not settlement_model.is_tradable(
        instrument_id,
        trade_date,
        ticket.order.direction,
        position,
        trading_rule,
    ):
        return False

    # 卖出时检查可用份额（position 存在时）
    return not (
        ticket.order.direction == OrderSide.SELL
        and position is not None
        and ticket.leaves_quantity > position.available_quantity
    )


# ---------------------------------------------------------------------------
# BacktestBrokerage
# ---------------------------------------------------------------------------


class BacktestBrokerage:
    """
    回测经纪商 -- state owner, 持有 Account 并处理订单成交。

    Args:
        account: 可变账户实例
        order_book: 执行层订单簿（OMS）
        model: 模型组合包 (fill / slippage / fee / settlement)
        rules_getter: 规则获取函数 (instrument_id, trade_date) → 三层规则

    """

    def __init__(
        self,
        account: Account,
        order_book: OrderBook,
        model: BrokerageModel | None = None,
        rules_getter: RulesGetter | None = None,
    ) -> None:
        self._account = account
        self._order_book = order_book
        self._model = model or BrokerageModel()
        self._rules_getter = rules_getter or _default_rules_getter
        self._fill_counter = 0
        # T+1 冻结: {instrument_id: {settle_date: frozen_qty}}
        self._frozen_quantities: dict[InstrumentId, dict[str, int]] = {}
        # 最近一次 process_pending 的 trade_date (用于 T+0 即时解冻)
        self._current_trade_date: str = ""

    # -- Brokerage interface ------------------------------------------------

    def connect(self) -> None:
        """回测环境无需连接。"""

    def get_account(self) -> AccountView:
        """获取只读账户快照。"""
        return self._account.get_view()

    def settle(self, trade_date: str) -> None:
        """Make due quantities available before the day's account snapshot."""
        self._current_trade_date = trade_date
        self._thaw_frozen(trade_date)
        self._account.settle_dividends(trade_date)
        for conversion in self._account.apply_share_conversions(trade_date):
            self._scale_frozen_shares(conversion)

    def _scale_frozen_shares(self, conversion: ShareConversion) -> None:
        """Rescale pending settlement quantities to the converted share scale."""
        by_date = self._frozen_quantities.get(conversion.instrument_id)
        if not by_date:
            return
        self._frozen_quantities[conversion.instrument_id] = {
            settle_date: conversion.converted(quantity)
            for settle_date, quantity in by_date.items()
        }

    def get_order_book(self) -> OrderBookReadOnly:
        """获取订单簿只读快照。"""
        return self._order_book.readonly_view()

    def get_settlement_state_snapshot(self) -> BacktestSettlementStateSnapshot:
        """获取 settlement/frozen queue checkpoint 快照。"""
        return BacktestSettlementStateSnapshot.from_frozen_quantities(
            self._frozen_quantities
        )

    def restore_settlement_state(
        self,
        snapshot: BacktestSettlementStateSnapshot,
    ) -> None:
        """从 checkpoint 恢复 settlement/frozen queue 状态。"""
        restored: dict[InstrumentId, dict[str, int]] = {}
        for frozen in snapshot.frozen_quantities:
            if frozen.quantity <= 0:
                continue
            by_date = restored.setdefault(frozen.instrument_id, {})
            by_date[frozen.settle_date] = (
                by_date.get(frozen.settle_date, 0) + frozen.quantity
            )
        self._frozen_quantities = restored

    def snapshot_fill_counter(self) -> int:
        """Capture the monotonic fill ID counter for checkpointing."""
        return self._fill_counter

    def restore_fill_counter(self, counter: int) -> None:
        """Restore the monotonic fill ID counter from a verified checkpoint."""
        if type(counter) is not int or counter < 0:
            msg = "brokerage fill counter must be a non-negative integer"
            raise ValueError(msg)
        self._fill_counter = counter

    def place_order(self, order: Order) -> OrderTicket:
        """提交订单，返回 OrderTicket (SUBMITTED)。"""
        return self._order_book.submit(order)

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单。终态不可撤销。"""
        try:
            self._order_book.cancel(ClientOrderId(value=order_id))
            return True
        except (KeyError, OrderStateError):
            return False

    def process_pending(
        self,
        process_input: ProcessInput,
    ) -> tuple[FillEvent, ...]:
        """处理所有待成交订单。"""
        step_time = process_input.step_time
        trade_date = process_input.trade_date
        bars = process_input.bars
        events: list[FillEvent] = []

        self.settle(trade_date)

        for ticket in self._order_book.get_pending():
            fill = self._process_single_ticket(
                ticket,
                bars,
                trade_date,
                step_time,
            )
            if fill is not None:
                events.append(fill)

        self._account.mark_to_market(
            {iid: market.close for iid, market in bars.items()}
        )
        self._account.close_dividend_day(trade_date)
        return tuple(events)

    def _process_single_ticket(
        self,
        ticket: OrderTicket,
        bars: dict[InstrumentId, MarketSnapshot],
        trade_date: str,
        step_time: datetime,
    ) -> FillEvent | None:
        """
        处理单个待成交订单，返回成交事件或 None。

        封装了规则获取、可执行性检查、滑点计算、成交尝试、
        成交后处理的完整流程。
        """
        iid = ticket.order.instrument_id
        market = bars.get(iid)
        if market is None:
            return None

        # 获取三层规则
        definition, trading_rule, fee_schedule = self._rules_getter(
            iid,
            trade_date,
        )

        # 可执行性检查（结算 + 卖出可用份额）
        position = self._account.positions.get(iid)
        if not _is_order_executable(
            ticket,
            position,
            self._model.settlement_model,
            iid,
            trade_date,
            trading_rule,
        ):
            return None

        # Retryable partial fills must model only the still-open quantity.  The
        # immutable ticket retains the original order for cumulative accounting.
        remaining_order = ticket.order.with_quantity(ticket.leaves_quantity)

        # Compute slippage
        slippage = self._model.slippage_model.estimate(
            remaining_order,
            market,
            definition,
        )

        # The minimum applies to the original submission, not a residual fill.
        reason = (
            minimum_order_rejection(
                ticket.order,
                trading_rule,
                position_quantity=position.quantity if position else 0,
            )
            if ticket.filled_quantity == 0
            else None
        )
        reason = reason or daily_buy_rejection(
            remaining_order,
            trading_rule,
            bought_quantity=position.quantity
            - position.available_quantity
            - self._account.get_view().dividends.unlisted_shares(iid)
            if position
            else 0,
            pending_quantity=0,
        )
        outcome = (
            NoFill(reason=reason, can_retry=False)
            if reason
            else self._model.fill_model.try_fill(
                remaining_order, market, definition, trading_rule
            )
        )

        if isinstance(outcome, Filled):
            fill_event = self._build_fill_event(
                ticket,
                outcome,
                slippage,
                step_time,
                fee_schedule,
                definition,
                market,
            )
            settle_date = self._model.settlement_model.settle_date(
                trade_date,
                trading_rule,
            )
            self._apply_fill(ticket, fill_event, settle_date)
            return fill_event

        if isinstance(outcome, NoFill) and not outcome.can_retry:
            order_evt = OrderEvent(
                client_id=ticket.order.client_id,
                trigger=OrderTrigger.INVALIDATE,
                status=OrderStatus.INVALID,
                message=outcome.reason,
                timestamp=step_time,
            )
            self._order_book.update(ticket.with_invalid(order_evt), event=order_evt)
        # can_retry=True: 保持 SUBMITTED, 下 step 再试

        return None

    # -- internals ----------------------------------------------------------

    def _build_fill_event(
        self,
        ticket: OrderTicket,
        filled: Filled,
        slippage: float,
        step_time: datetime,
        fee_schedule: FeeSchedule,
        definition: InstrumentDefinition,
        market: MarketSnapshot,
    ) -> FillEvent:
        """构建 FillEvent，补全所有字段。"""
        order = ticket.order

        model_qty = filled.fill_event.filled_quantity
        if model_qty <= 0:
            raise FillProcessingError(
                f"Fill model returned non-positive qty {model_qty} "
                + f"for order {order.order_id}. Fill models must return NoFill "
                + "when no quantity can be executed.",
                order_id=order.order_id,
                model_quantity=model_qty,
                leaves_quantity=ticket.leaves_quantity,
            )
        if model_qty > ticket.leaves_quantity:
            raise FillProcessingError(
                f"Fill model returned qty {model_qty} > leaves qty "
                + f"{ticket.leaves_quantity} for order {order.order_id}.",
                order_id=order.order_id,
                model_quantity=model_qty,
                leaves_quantity=ticket.leaves_quantity,
            )
        fill_qty = model_qty
        cumulative = ticket.filled_quantity + fill_qty
        leaves = order.quantity - cumulative
        self._fill_counter += 1

        # 基准成交价 (FillModel 返回) + 滑点
        base_price = filled.fill_event.fill_price
        fill_price = round_to_tick(base_price + slippage, definition.tick_size)
        if market.limit_up is not None:
            fill_price = min(fill_price, market.limit_up)
        if market.limit_down is not None:
            fill_price = max(fill_price, market.limit_down)
        if order.order_type == OrderType.LIMIT and order.price is not None:
            fill_price = (
                min(fill_price, order.price)
                if order.direction == OrderSide.BUY
                else max(fill_price, order.price)
            )
        slippage = fill_price - base_price

        fee = self._model.fee_model.calculate(
            order,
            fill_price,
            fill_qty,
            fee_schedule,
        )

        # 重新构建 FillEvent, 使用 fill_price + slippage
        return FillEvent(
            fill_id=f"fill-{self._fill_counter}",
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            filled_quantity=fill_qty,
            fill_price=fill_price,
            fee=fee,
            slippage=slippage,
            event_time=step_time,
            cumulative_quantity=cumulative,
            leaves_quantity=leaves,
        )

    def _apply_fill(
        self,
        ticket: OrderTicket,
        fill: FillEvent,
        settle_date: str,
    ) -> None:
        """成交后更新 OrderTicket + Account 仓位/现金。"""
        order = ticket.order
        # FSM 单一状态来源: transition() 决定 FILLED / PARTIALLY_FILLED
        new_status = transition(
            ticket.status,
            OrderTrigger.FILL,
            fill_qty=fill.filled_quantity,
            leaves_qty=ticket.leaves_quantity,
        )
        order_evt = OrderEvent(
            client_id=order.client_id,
            trigger=OrderTrigger.FILL,
            status=new_status,
            fill_price=fill.fill_price,
            fill_quantity=fill.filled_quantity,
            fee=fill.fee,
            timestamp=fill.event_time,
        )
        updated_ticket = ticket.with_fill(
            quantity=fill.filled_quantity,
            price=fill.fill_price,
            event=order_evt,
        )
        # 入账先于订单簿 FILLED 落笔：模型层拒绝（#681 裸卖/超卖）时
        # 抛错在任何簿记变更之前，不留下"已成交未入账"的幻影票
        # （#684 批B correctness F2）。
        self._account.apply_fill(fill, settle_date, on_frozen=self._register_frozen)
        self._order_book.update(updated_ticket, event=order_evt)

    def _register_frozen(
        self,
        instrument_id: InstrumentId,
        settle_date: str,
        quantity: int,
    ) -> None:
        """
        注册冻结份额 — settle_date 到期后通过 _thaw_frozen 解冻。

        T+0 (settle_date == current_trade_date) 时直接增加 available_quantity。
        """
        if settle_date <= self._current_trade_date:
            # T+0 交收: 当日即解冻, 直接增加 available_quantity
            self._account.thaw_position(instrument_id, quantity)
            return

        frozen_for_iid = self._frozen_quantities.setdefault(instrument_id, {})
        frozen_for_iid[settle_date] = frozen_for_iid.get(settle_date, 0) + quantity

    def _thaw_frozen(self, trade_date: str) -> None:
        """解冻 settle_date <= trade_date 的份额, 加回 available_quantity。"""
        for iid, date_qty_map in list(self._frozen_quantities.items()):
            pos = self._account.positions.get(iid)
            if pos is None:
                # 仓位已清空, 移除残留冻结记录
                del self._frozen_quantities[iid]
                continue

            thaw_total = 0
            expired_dates: list[str] = []
            for settle_date, qty in date_qty_map.items():
                if settle_date <= trade_date:
                    thaw_total += qty
                    expired_dates.append(settle_date)

            if thaw_total > 0:
                for d in expired_dates:
                    del date_qty_map[d]
                if not date_qty_map:
                    del self._frozen_quantities[iid]
                self._account.thaw_position(iid, thaw_total)
