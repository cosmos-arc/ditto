"""基于账户基线与 A 股交易规则计算可解释的人工建议数量。"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from types import MappingProxyType
from typing import Literal

from ditto_execution.orders.model import Order
from ditto_execution.planner import (
    BlockedOrder,
    ExecutionPlanner,
    SimpleExecutionPlanner,
)
from ditto_execution.quantity_rounding import round_buy_qty
from ditto_execution.reality.fee import AShareFeeModel
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_MIN_COMMISSION,
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    MarketSnapshot,
    TradingRuleSet,
)
from ditto_portfolio.accounting import AccountView, CashBook, Position

from ditto_application.exceptions import AppProcessError
from ditto_application.execution_dto import TradeIntent
from ditto_application.processes.execution.manual_sizing_context import (
    ManualSizingContext,
    ManualSizingContextBuilder,
    ManualSizingContexts,
)

__all__ = [
    "AShareTradeDateResolver",
    "ManualSizingContext",
    "ManualSizingContextBuilder",
    "ManualSizingContexts",
    "ManualSizingRequest",
    "ManualSizingResult",
    "ManualSizingService",
    "ManualTradeDates",
]


@dataclass(frozen=True)
class ManualTradeDates:
    """一个 D 日信号包对应的决策日与正式下一交易日。"""

    signal_date: str
    decision_date: str
    intended_trade_date: str


class AShareTradeDateResolver:
    """只从已注入的 A 股交易日历解析 D+1，禁止自然日推算。"""

    def __init__(self, *, trading_days: tuple[str, ...]) -> None:
        self._trading_days = tuple(sorted(set(trading_days)))

    def resolve(self, *, signal_date: str, decision_date: str) -> ManualTradeDates:
        """解析信号日后的下一开市日。"""
        if decision_date < signal_date:
            raise AppProcessError("decision_date cannot precede signal_date")
        try:
            index = self._trading_days.index(signal_date)
        except ValueError as exc:
            raise AppProcessError(
                f"signal_date is absent from A-share trading calendar: {signal_date}"
            ) from exc
        if index + 1 >= len(self._trading_days):
            message = "next A-share trading date is unavailable for signal_date: {}"
            raise AppProcessError(message.format(signal_date))
        return ManualTradeDates(
            signal_date=signal_date,
            decision_date=decision_date,
            intended_trade_date=self._trading_days[index + 1],
        )

    def validate(
        self,
        *,
        signal_date: str,
        decision_date: str,
        intended_trade_date: str,
    ) -> None:
        """验证调用者传入的建议交易日确为交易日历 D+1。"""
        expected = self.resolve(
            signal_date=signal_date,
            decision_date=decision_date,
        )
        if intended_trade_date != expected.intended_trade_date:
            message = " ".join(
                (
                    "intended_trade_date must equal the next A-share trading date",
                    "({expected}), got {actual}",
                )
            )
            raise AppProcessError(
                message.format(
                    expected=expected.intended_trade_date,
                    actual=intended_trade_date,
                )
            )


@dataclass(frozen=True)
class ManualSizingRequest:
    """计算单个建议数量所需的完整事实。"""

    direction: Literal["buy", "sell"]
    target_weight: float
    nav: float
    current_quantity: int
    available_quantity: int
    cash_available: float
    reference_price: float | None
    instrument_id: int = 0
    trade_date: str = ""
    lot_size: int = 100
    risk_quantity_limit: int | None = None
    commission_rate: float = DEFAULT_COMMISSION_RATE
    min_commission: float = DEFAULT_MIN_COMMISSION
    settlement_cycle: int = 1
    is_suspended: bool = False
    at_price_limit: bool = False
    is_limit_up: bool = False
    is_limit_down: bool = False
    is_risk_locked: bool = False
    tradability_reason: Literal["tradability_unverified"] | None = None


@dataclass(frozen=True)
class ManualSizingResult:
    """建议数量以及审阅所需的取整解释。"""

    direction: Literal["buy", "sell"] | None
    raw_quantity: int
    rounded_quantity: int
    lot_size: int
    reference_price: float | None
    cash_impact: float
    estimated_fee: float
    cash_required: float
    reason: str
    readiness: Literal["ready", "review", "blocked"]


@dataclass(frozen=True)
class _SizingTarget:
    positions: dict[InstrumentId, float]


class ManualSizingService:
    """组合 ExecutionPlanner 生成建议，再执行人工账户现金与风险上限。"""

    def __init__(
        self,
        *,
        planner: ExecutionPlanner | None = None,
        fee_model: AShareFeeModel | None = None,
    ) -> None:
        self._planner = planner or SimpleExecutionPlanner()
        self._fee_model = fee_model or AShareFeeModel()

    def size(self, request: ManualSizingRequest) -> ManualSizingResult:
        """以 planner 的订单方向和数量为权威生成可解释建议。"""
        if request.reference_price is None or request.reference_price <= 0:
            return _zero(request, "missing_reference_price", "blocked")
        if request.tradability_reason is not None:
            return _zero(request, request.tradability_reason, "blocked")
        plan = self._planner.plan(
            target=_sizing_target(request),
            account_view=_account_view(request),
            trade_date=request.trade_date,
            rules={_instrument_id(request): _instrument_rules(request)},
            market_snapshots={_instrument_id(request): _market_snapshot(request)},
            locked_instruments=(
                {_instrument_id(request)} if request.is_risk_locked else set()
            ),
        )
        return self._from_plan(request, plan.orders, plan.blocked_orders)

    def size_intent(
        self,
        intent: TradeIntent,
        context: ManualSizingContext,
    ) -> ManualSizingResult:
        """使用 intent 与对应账户/行情上下文计算建议数量。"""
        return self.size(
            ManualSizingRequest(
                direction="buy" if intent.direction == "buy" else "sell",
                target_weight=intent.target_weight,
                nav=context.nav,
                current_quantity=context.current_quantity,
                available_quantity=context.available_quantity,
                cash_available=context.cash_available,
                reference_price=context.reference_price,
                instrument_id=intent.instrument_id,
                trade_date=intent.signal_date,
                lot_size=context.lot_size,
                risk_quantity_limit=context.risk_quantity_limit,
                commission_rate=context.commission_rate,
                min_commission=context.min_commission,
                settlement_cycle=context.settlement_cycle,
                is_suspended=context.is_suspended,
                at_price_limit=context.at_price_limit,
                is_limit_up=context.is_limit_up,
                is_limit_down=context.is_limit_down,
                is_risk_locked=context.is_risk_locked,
                tradability_reason=context.tradability_reason,
            )
        )

    def _from_plan(
        self,
        request: ManualSizingRequest,
        orders: tuple[Order, ...],
        blocked_orders: tuple[BlockedOrder, ...],
    ) -> ManualSizingResult:
        direction = _planned_direction(orders, blocked_orders)
        raw_quantity = _raw_quantity(request)
        reasons = tuple(blocked.reason for blocked in blocked_orders)
        if direction is None:
            return _result(
                request,
                direction=None,
                raw_quantity=raw_quantity,
                rounded_quantity=0,
                reason="no_rebalance",
                readiness="ready",
            )
        planned_quantity = sum(order.quantity for order in orders)
        if direction == "buy" and planned_quantity > 0:
            return self._size_planned_buy(
                request,
                orders[0],
                raw_quantity=raw_quantity,
                planned_quantity=planned_quantity,
            )
        if direction == "sell" and planned_quantity > 0:
            reason = (
                "t_plus1_available_quantity_cap"
                if "t_plus1_not_sellable" in reasons
                else "sell_quantity_available"
            )
            return _result(
                request,
                direction=direction,
                raw_quantity=raw_quantity,
                rounded_quantity=planned_quantity,
                estimated_fee=_estimated_sell_fee(
                    self._fee_model,
                    orders,
                    request,
                ),
                reason=reason,
                readiness="ready",
            )
        return _blocked_result(request, direction, raw_quantity, reasons)

    def _size_planned_buy(
        self,
        request: ManualSizingRequest,
        order: Order,
        *,
        raw_quantity: int,
        planned_quantity: int,
    ) -> ManualSizingResult:
        affordable, _ = _affordable_buy_quantity(
            fee_model=self._fee_model,
            order=order,
            request=request,
            maximum=planned_quantity,
        )
        risk_cap = planned_quantity
        if request.risk_quantity_limit is not None:
            risk_cap = round_buy_qty(
                max(0, request.risk_quantity_limit),
                request.lot_size,
            )
        caps: list[str] = []
        if affordable < planned_quantity:
            caps.append("cash")
        if risk_cap < min(planned_quantity, affordable):
            caps.append("risk_limit")
        rounded = min(planned_quantity, affordable, risk_cap)
        estimated_fee = _estimated_buy_fee(
            self._fee_model,
            order,
            request,
            rounded,
        )
        if caps:
            reason = f"capped_by_{'_and_'.join(caps)}"
            readiness: Literal["ready", "review", "blocked"] = (
                "ready" if rounded > 0 else "review"
            )
        elif rounded != raw_quantity:
            reason = "rounded_down_to_board_lot"
            readiness = "ready"
        else:
            reason = "exact_board_lot"
            readiness = "ready"
        return _result(
            request,
            direction="buy",
            raw_quantity=raw_quantity,
            rounded_quantity=rounded,
            estimated_fee=estimated_fee,
            reason=reason,
            readiness=readiness,
        )


def _zero(
    request: ManualSizingRequest,
    reason: str,
    readiness: Literal["review", "blocked"],
) -> ManualSizingResult:
    return _result(
        request,
        direction=request.direction,
        raw_quantity=0,
        rounded_quantity=0,
        reason=reason,
        readiness=readiness,
    )


def _instrument_id(request: ManualSizingRequest) -> InstrumentId:
    return InstrumentId(request.instrument_id)


def _sizing_target(request: ManualSizingRequest) -> _SizingTarget:
    return _SizingTarget(
        positions={_instrument_id(request): request.target_weight},
    )


def _account_view(request: ManualSizingRequest) -> AccountView:
    iid = _instrument_id(request)
    price = request.reference_price or 0.0
    positions: dict[InstrumentId, Position] = {}
    if request.current_quantity > 0:
        positions[iid] = Position(
            instrument_id=iid,
            quantity=request.current_quantity,
            available_quantity=request.available_quantity,
            average_cost=price,
            market_value=request.current_quantity * price,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
    return AccountView(
        positions=MappingProxyType(positions),
        cash=CashBook(
            available=request.cash_available,
            settled=request.cash_available,
            frozen=0.0,
        ),
        total_value=request.nav,
        nav=request.nav,
        exposure=request.current_quantity * price,
    )


def _instrument_rules(request: ManualSizingRequest) -> InstrumentRules:
    iid = _instrument_id(request)
    return (
        InstrumentDefinition(
            instrument_id=iid,
            asset_class="fund",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.001,
            lot_size=request.lot_size,
            multiplier=1.0,
            board_segment="fund",
            lifecycle_state="normal",
        ),
        TradingRuleSet(
            instrument_id=iid,
            as_of_date=request.trade_date,
            settlement_cycle=request.settlement_cycle,
            fund_settlement_cycle=request.settlement_cycle,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
        ),
        FeeSchedule(
            instrument_id=iid,
            as_of_date=request.trade_date,
            commission_rate=request.commission_rate,
            min_commission=request.min_commission,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        ),
    )


def _market_snapshot(request: ManualSizingRequest) -> MarketSnapshot:
    iid = _instrument_id(request)
    price = request.reference_price or 0.0
    # ``at_price_limit`` predates directional market facts.  Preserve that
    # fail-closed fallback only when the authoritative limit side is unknown;
    # otherwise the planner must still permit sells at limit-up and buys at
    # limit-down.
    generic_limit = (
        request.at_price_limit and not request.is_limit_up and not request.is_limit_down
    )
    return MarketSnapshot(
        trade_date=request.trade_date,
        instrument_id=iid,
        open=price,
        high=price,
        low=price,
        close=price,
        prev_close=price,
        volume=0.0 if request.is_suspended else 1.0,
        amount=0.0 if request.is_suspended else price,
        is_suspended=request.is_suspended,
        limit_up=price if request.is_limit_up or generic_limit else None,
        limit_down=price if request.is_limit_down or generic_limit else None,
    )


def _raw_quantity(request: ManualSizingRequest) -> int:
    price = request.reference_price or 0.0
    target_quantity = floor(request.target_weight * request.nav / price)
    return abs(target_quantity - request.current_quantity)


def _planned_direction(
    orders: tuple[Order, ...],
    blocked_orders: tuple[BlockedOrder, ...],
) -> Literal["buy", "sell"] | None:
    sides = {order.direction for order in orders}
    sides.update(blocked.direction for blocked in blocked_orders)
    if len(sides) > 1:
        raise AppProcessError("Execution planner returned conflicting order sides")
    if not sides:
        return None
    return "buy" if sides.pop() == OrderSide.BUY else "sell"


def _blocked_result(
    request: ManualSizingRequest,
    direction: Literal["buy", "sell"],
    raw_quantity: int,
    reasons: tuple[str, ...],
) -> ManualSizingResult:
    reason = reasons[0] if reasons else "planner_no_order"
    if (
        request.at_price_limit
        and not request.is_limit_up
        and not request.is_limit_down
        and reason.startswith("limit_")
    ):
        reason = "price_limit"
    readiness: Literal["review", "blocked"] = (
        "blocked" if reason in {"risk_locked", "suspended"} else "review"
    )
    return _result(
        request,
        direction=direction,
        raw_quantity=raw_quantity,
        rounded_quantity=0,
        reason=reason,
        readiness=readiness,
    )


def _affordable_buy_quantity(
    *,
    fee_model: AShareFeeModel,
    order: Order,
    request: ManualSizingRequest,
    maximum: int,
) -> tuple[int, float]:
    price = request.reference_price or 0.0
    candidate = round_buy_qty(
        min(maximum, floor(request.cash_available / price)),
        request.lot_size,
    )
    while candidate > 0:
        fee = _estimated_buy_fee(fee_model, order, request, candidate)
        if candidate * price + fee <= request.cash_available:
            return candidate, fee
        candidate -= request.lot_size
    return 0, 0.0


def _estimated_buy_fee(
    fee_model: AShareFeeModel,
    order: Order,
    request: ManualSizingRequest,
    quantity: int,
) -> float:
    if quantity <= 0:
        return 0.0
    return fee_model.estimate(
        order.with_quantity(quantity),
        request.reference_price or 0.0,
        _instrument_rules(request)[2],
    )


def _estimated_sell_fee(
    fee_model: AShareFeeModel,
    orders: tuple[Order, ...],
    request: ManualSizingRequest,
) -> float:
    price = request.reference_price or 0.0
    schedule = _instrument_rules(request)[2]
    return sum(fee_model.estimate(order, price, schedule) for order in orders)


def _result(
    request: ManualSizingRequest,
    *,
    direction: Literal["buy", "sell"] | None,
    raw_quantity: int,
    rounded_quantity: int,
    reason: str,
    readiness: Literal["ready", "review", "blocked"],
    estimated_fee: float = 0.0,
) -> ManualSizingResult:
    price = request.reference_price or 0.0
    notional = rounded_quantity * price
    cash_impact = -notional if direction == "buy" else notional
    cash_required = notional + estimated_fee if direction == "buy" else 0.0
    return ManualSizingResult(
        direction=direction,
        raw_quantity=raw_quantity,
        rounded_quantity=rounded_quantity,
        lot_size=request.lot_size,
        reference_price=request.reference_price,
        cash_impact=cash_impact,
        estimated_fee=estimated_fee,
        cash_required=cash_required,
        reason=reason,
        readiness=readiness,
    )
