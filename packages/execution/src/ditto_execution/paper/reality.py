"""Deterministic A-share reality rules for formal paper execution."""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import InstrumentRules

from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperFill,
    PaperOrder,
    PaperRealityContext,
    PaperRealityResult,
    PaperRealityStatus,
)

__all__ = ["ASharePaperReality"]

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class ASharePaperReality:
    """Apply point-in-time A-share constraints and a versioned fill assumption."""

    def execute(
        self,
        *,
        paper_order: PaperOrder,
        lineage: MarketSnapshotLineage,
        rules: InstrumentRules,
        assumption: FillAssumption,
        context: PaperRealityContext,
    ) -> PaperRealityResult:
        """Return a deterministic fill, defer, or rejection with exact evidence."""
        lineage.assert_visible_at(context.execution_at)
        self._validate_exact_inputs(paper_order, lineage, rules, context)
        order_outcome = self._order_constraint_outcome(
            paper_order=paper_order,
            rules=rules,
            context=context,
        )
        if order_outcome is not None:
            return order_outcome
        market_outcome = self._market_outcome(paper_order, lineage)
        if market_outcome is not None:
            return market_outcome
        return self._fill(
            paper_order=paper_order,
            lineage=lineage,
            rules=rules,
            assumption=assumption,
            context=context,
        )

    def _order_constraint_outcome(
        self,
        *,
        paper_order: PaperOrder,
        rules: InstrumentRules,
        context: PaperRealityContext,
    ) -> PaperRealityResult | None:
        """Apply quantity, position, and T+1 constraints."""
        definition, trading_rules, _fee_schedule = rules
        order = paper_order.order
        lot_reason = self._lot_reason(
            side=order.direction,
            quantity=order.quantity,
            lot_size=definition.lot_size,
            position_quantity=context.position_quantity,
        )
        if lot_reason is not None:
            return self._reject(paper_order, lot_reason, context.execution_at)
        if (
            order.direction is OrderSide.SELL
            and order.quantity > context.position_quantity
        ):
            return self._reject(
                paper_order,
                "insufficient_position",
                context.execution_at,
            )
        if (
            order.direction is OrderSide.SELL
            and trading_rules.settlement_cycle > 0
            and order.quantity > context.available_quantity
        ):
            return PaperRealityResult(
                status=PaperRealityStatus.DEFERRED,
                order=paper_order,
                reason="t_plus1_not_sellable",
            )
        return None

    @staticmethod
    def _market_outcome(
        paper_order: PaperOrder,
        lineage: MarketSnapshotLineage,
    ) -> PaperRealityResult | None:
        """Apply suspension and directional price-limit constraints."""
        order = paper_order.order
        snapshot = lineage.snapshot
        if snapshot.is_suspended:
            return PaperRealityResult(
                status=PaperRealityStatus.DEFERRED,
                order=paper_order,
                reason="suspended",
            )
        if (
            order.direction is OrderSide.BUY
            and snapshot.limit_up is not None
            and snapshot.close >= snapshot.limit_up
        ):
            return PaperRealityResult(
                status=PaperRealityStatus.DEFERRED,
                order=paper_order,
                reason="limit_up_no_buy",
            )
        if (
            order.direction is OrderSide.SELL
            and snapshot.limit_down is not None
            and snapshot.close <= snapshot.limit_down
        ):
            return PaperRealityResult(
                status=PaperRealityStatus.DEFERRED,
                order=paper_order,
                reason="limit_down_no_sell",
            )
        return None

    @staticmethod
    def _fill(
        *,
        paper_order: PaperOrder,
        lineage: MarketSnapshotLineage,
        rules: InstrumentRules,
        assumption: FillAssumption,
        context: PaperRealityContext,
    ) -> PaperRealityResult:
        """Price one marketable order and attach complete cost evidence."""
        definition, _trading_rules, fee_schedule = rules
        order = paper_order.order
        snapshot = lineage.snapshot
        reference = float(getattr(snapshot, assumption.reference_price_field))
        slip_multiplier = assumption.slippage_bps / 10_000.0
        raw_fill = reference * (
            1.0 + slip_multiplier
            if order.direction is OrderSide.BUY
            else 1.0 - slip_multiplier
        )
        fill_price = _round_to_tick(raw_fill, definition.tick_size)
        limit_outcome = _limit_order_outcome(paper_order, fill_price)
        if limit_outcome is not None:
            return limit_outcome
        amount = fill_price * order.quantity
        commission = max(
            fee_schedule.min_commission,
            amount * fee_schedule.commission_rate,
        )
        transfer_fee = amount * fee_schedule.transfer_fee_rate
        tax = (
            amount * fee_schedule.stamp_duty_rate
            if order.direction is OrderSide.SELL
            else 0.0
        )
        total_cost = commission + transfer_fee + tax
        fill = PaperFill(
            fill_id=_fill_id(
                paper_order.order_id,
                lineage.lineage_hash,
                assumption.assumption_hash,
            ),
            session_id=paper_order.session_id,
            account_id=paper_order.account_id,
            order_id=paper_order.order_id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            quantity=order.quantity,
            trade_date=snapshot.trade_date,
            settlement_date=context.settlement_date,
            event_time=context.execution_at,
            reference_price=reference,
            fill_price=fill_price,
            slippage=assumption.slippage_bps,
            commission=commission,
            transfer_fee=transfer_fee,
            tax=tax,
            total_cost=total_cost,
            assumption_hash=assumption.assumption_hash,
            market_snapshot_hash=lineage.snapshot_hash,
            market_lineage_hash=lineage.lineage_hash,
        )
        return PaperRealityResult(
            status=PaperRealityStatus.FILLED,
            order=paper_order.record_fill(fill),
            fill=fill,
        )

    @staticmethod
    def _validate_exact_inputs(
        paper_order: PaperOrder,
        lineage: MarketSnapshotLineage,
        rules: InstrumentRules,
        context: PaperRealityContext,
    ) -> None:
        """Validate exact identity, PIT rules, dates, and position invariants."""
        _validate_order_and_snapshot(paper_order, lineage)
        _validate_rule_identity(
            paper_order.order.instrument_id,
            paper_order.order.trade_date,
            rules,
        )
        _validate_dates_and_positions(
            paper_order.order.trade_date,
            rules[1].settlement_cycle,
            context,
        )

    @staticmethod
    def _lot_reason(
        *,
        side: OrderSide,
        quantity: int,
        lot_size: int,
        position_quantity: int,
    ) -> str | None:
        """Return a precise board-lot rejection reason, when applicable."""
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if side is OrderSide.BUY and quantity % lot_size != 0:
            return "buy_quantity_not_board_lot"
        if (
            side is OrderSide.SELL
            and quantity % lot_size != 0
            and quantity != position_quantity
        ):
            return "sell_odd_lot_requires_full_liquidation"
        return None

    @staticmethod
    def _reject(
        paper_order: PaperOrder,
        reason: str,
        decision_at: datetime,
    ) -> PaperRealityResult:
        """Return a rejected result with the shared order FSM advanced."""
        return PaperRealityResult(
            status=PaperRealityStatus.REJECTED,
            order=paper_order.reject(reason=reason, timestamp=decision_at),
            reason=reason,
        )


def _validate_order_and_snapshot(
    paper_order: PaperOrder,
    lineage: MarketSnapshotLineage,
) -> None:
    order = paper_order.order
    snapshot = lineage.snapshot
    if paper_order.status.value != "submitted":
        raise ValueError("paper order must be submitted before execution")
    if order.trade_date is None:
        raise ValueError("paper order trade_date is required")
    if snapshot.trade_date != order.trade_date:
        raise ValueError("market snapshot trade_date does not match order")
    if snapshot.instrument_id != order.instrument_id:
        raise ValueError("market snapshot instrument does not match order")


def _validate_rule_identity(
    instrument_id: InstrumentId,
    trade_date: str | None,
    rules: InstrumentRules,
) -> None:
    definition, trading_rules, fee_schedule = rules
    if any(
        item != instrument_id
        for item in (
            definition.instrument_id,
            trading_rules.instrument_id,
            fee_schedule.instrument_id,
        )
    ):
        raise ValueError("instrument rules do not match order")
    if trading_rules.as_of_date != trade_date or fee_schedule.as_of_date != trade_date:
        raise ValueError("paper execution requires exact trade-date rules")


def _validate_dates_and_positions(
    trade_date: str | None,
    settlement_cycle: int,
    context: PaperRealityContext,
) -> None:
    if trade_date is None:
        raise ValueError("paper order trade_date is required")
    try:
        trade_day = date.fromisoformat(trade_date)
        settle_day = date.fromisoformat(context.settlement_date)
    except ValueError as exc:
        raise ValueError("paper trade and settlement dates must be valid") from exc
    if settle_day < trade_day:
        raise ValueError("settlement_date cannot precede trade_date")
    if trade_day > context.execution_at.astimezone(_SHANGHAI).date():
        raise ValueError("paper trade_date is after execution date")
    if settlement_cycle > 0 and settle_day == trade_day:
        raise ValueError("T+1 instrument requires later settlement_date")
    if context.position_quantity < 0 or context.available_quantity < 0:
        raise ValueError("position quantities must be non-negative")
    if context.available_quantity > context.position_quantity:
        raise ValueError("available_quantity cannot exceed position_quantity")


def _limit_order_outcome(
    paper_order: PaperOrder,
    fill_price: float,
) -> PaperRealityResult | None:
    order = paper_order.order
    if order.order_type is not OrderType.LIMIT or order.price is None:
        return None
    not_marketable = (
        order.direction is OrderSide.BUY and fill_price > order.price
    ) or (order.direction is OrderSide.SELL and fill_price < order.price)
    if not_marketable:
        return PaperRealityResult(
            status=PaperRealityStatus.DEFERRED,
            order=paper_order,
            reason="limit_price_not_marketable",
        )
    return None


def _round_to_tick(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    price_decimal = Decimal(str(price))
    tick_decimal = Decimal(str(tick_size))
    ticks = (price_decimal / tick_decimal).quantize(Decimal("1"), ROUND_HALF_UP)
    return float(ticks * tick_decimal)


def _fill_id(order_id: str, lineage_hash: str, assumption_hash: str) -> str:
    digest = sha256(
        f"{order_id}\x00{lineage_hash}\x00{assumption_hash}".encode()
    ).hexdigest()
    return f"paper-fill:{digest[:32]}"
