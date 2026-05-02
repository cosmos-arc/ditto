"""
Brokerage Protocol + BacktestBrokerage — 回测经纪商.

BacktestBrokerage 是 state owner, 持有可变 Account 实例,
通过 fill / slippage / fee 模型处理订单成交。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import Account, AccountView
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.order_book import (
    Order,
    OrderEvent,
    OrderStatus,
    OrderTicket,
    StateTransitionError,
)
from ditto_portfolio.accounting.position import Position

from ditto_execution.errors import EngineError
from ditto_execution.fills import Filled, NoFill
from ditto_execution.reality import BrokerageModel
from ditto_execution.reality.constants import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
)
from ditto_execution.reality.market import MarketSnapshot
from ditto_execution.reality.settlement import SettlementModel
from ditto_execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    RulesGetter,
    TradingRuleSet,
)

__all__ = ["BacktestBrokerage", "Brokerage", "ProcessInput"]


# ---------------------------------------------------------------------------
# ProcessInput
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessInput:
    """
    process_pending 的输入 — 包含完整 MarketSnapshot。

    Attributes:
        step_time: 当前步骤时间
        trade_date: 交易日（YYYY-MM-DD 格式）
        bars: 标的行情快照映射（instrument_id → MarketSnapshot）

    """

    step_time: datetime
    trade_date: str
    bars: dict[InstrumentId, MarketSnapshot]


# ---------------------------------------------------------------------------
# Brokerage Protocol
# ---------------------------------------------------------------------------


class Brokerage(Protocol):
    """经纪商协议 -- 统一实盘/回测接口。"""

    def connect(self) -> None:
        """建立连接。"""
        ...

    def get_account(self) -> AccountView:
        """获取只读账户快照。"""
        ...

    def place_order(self, order: Order) -> OrderTicket:
        """提交订单。"""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单，返回是否成功。"""
        ...

    def process_pending(self, process_input: ProcessInput) -> tuple[FillEvent, ...]:
        """处理所有待成交订单，返回成交事件列表。"""
        ...


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
        model: 模型组合包 (fill / slippage / fee / settlement)
        rules_getter: 规则获取函数 (instrument_id, trade_date) → 三层规则

    """

    def __init__(
        self,
        account: Account,
        model: BrokerageModel | None = None,
        rules_getter: RulesGetter | None = None,
    ) -> None:
        self._account = account
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

    def place_order(self, order: Order) -> OrderTicket:
        """提交订单，创建 OrderTicket (SUBMITTED)。"""
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)
        self._account.order_book.submit(ticket)
        return ticket

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单。终态不可撤销。"""
        try:
            self._account.order_book.cancel(order_id)
            return True
        except (KeyError, StateTransitionError):
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

        self._current_trade_date = trade_date
        # 解冻到期份额
        self._thaw_frozen(trade_date)

        for ticket in self._account.order_book.get_pending():
            fill = self._process_single_ticket(
                ticket,
                bars,
                trade_date,
                step_time,
            )
            if fill is not None:
                events.append(fill)

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

        # Compute slippage
        slippage = self._model.slippage_model.estimate(
            ticket.order,
            market,
            definition,
        )

        # Try fill
        outcome = self._model.fill_model.try_fill(
            ticket.order,
            market,
            definition,
            trading_rule,
        )

        if isinstance(outcome, Filled):
            fill_event = self._build_fill_event(
                ticket,
                outcome,
                slippage,
                step_time,
                fee_schedule,
            )
            settle_date = self._model.settlement_model.settle_date(
                trade_date,
                trading_rule,
            )
            self._apply_fill(ticket, fill_event, settle_date)
            return fill_event

        if isinstance(outcome, NoFill) and not outcome.can_retry:
            order_evt = OrderEvent(
                order_id=ticket.order.order_id,
                status=OrderStatus.INVALID,
                message=outcome.reason,
                timestamp=step_time,
            )
            self._account.order_book.update(ticket.with_invalid(order_evt))
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
    ) -> FillEvent:
        """构建 FillEvent，补全所有字段。"""
        self._fill_counter += 1
        order = ticket.order

        fill_qty = ticket.leaves_quantity

        # 防御性检查：V1 fill model 合约为 all-or-nothing，
        # filled.fill_event.filled_quantity 应等于 leaves_quantity。
        # 如 V2 引入部分成交模型，需重构 fill model contract。
        model_qty = filled.fill_event.filled_quantity
        if model_qty != fill_qty:
            raise EngineError(
                f"Fill model returned qty {model_qty} != leaves qty {fill_qty} "
                + f"for order {order.order_id}. V1 fill model is all-or-nothing; "
                + "partial fills require fill model contract refactoring."
            )
        cumulative = ticket.filled_quantity + fill_qty
        leaves = order.quantity - cumulative

        # 基准成交价 (FillModel 返回) + 滑点
        base_price = filled.fill_event.fill_price
        fill_price = base_price + slippage

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
        order_evt = OrderEvent(
            order_id=order.order_id,
            status=OrderStatus.FILLED
            if fill.leaves_quantity == 0
            else OrderStatus.PARTIALLY_FILLED,
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
        self._account.order_book.update(updated_ticket)
        self._account.apply_fill(fill, settle_date, on_frozen=self._register_frozen)

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
            pos = self._account.positions.get(instrument_id)
            if pos is not None:
                self._account.positions[instrument_id] = replace(
                    pos,
                    available_quantity=pos.available_quantity + quantity,
                )
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
                self._account.positions[iid] = replace(
                    pos,
                    available_quantity=pos.available_quantity + thaw_total,
                )
