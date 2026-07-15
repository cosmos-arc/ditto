"""基于账户基线与 A 股交易规则计算可解释的人工建议数量。"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Literal

from ditto_execution.quantity_rounding import round_buy_qty

from ditto_application.execution_dto import TradeIntent

__all__ = [
    "ManualSizingContext",
    "ManualSizingRequest",
    "ManualSizingResult",
    "ManualSizingService",
]


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
    lot_size: int = 100
    risk_quantity_limit: int | None = None
    is_suspended: bool = False
    at_price_limit: bool = False


@dataclass(frozen=True)
class ManualSizingContext:
    """SignalSnapshotProcess 可按标的提供的账户和行情上下文。"""

    nav: float
    current_quantity: int
    available_quantity: int
    cash_available: float
    reference_price: float | None
    lot_size: int = 100
    risk_quantity_limit: int | None = None
    is_suspended: bool = False
    at_price_limit: bool = False


@dataclass(frozen=True)
class ManualSizingResult:
    """建议数量以及审阅所需的取整解释。"""

    raw_quantity: int
    rounded_quantity: int
    lot_size: int
    reference_price: float | None
    cash_impact: float
    reason: str
    readiness: Literal["ready", "review", "blocked"]


class ManualSizingService:
    """确定性计算建议数量，并执行现金、风险和 T+1 上限。"""

    def size(self, request: ManualSizingRequest) -> ManualSizingResult:
        """计算建议数量；行情不可交易时不伪造数量。"""
        if request.reference_price is None or request.reference_price <= 0:
            return _zero(request, "missing_reference_price", "blocked")
        if request.is_suspended:
            return _zero(request, "suspended", "blocked")
        if request.at_price_limit:
            return _zero(request, "price_limit", "review")

        target_quantity = floor(
            request.target_weight * request.nav / request.reference_price
        )
        delta = target_quantity - request.current_quantity
        raw_quantity = max(0, delta if request.direction == "buy" else -delta)

        if request.direction == "buy":
            return self._size_buy(request, raw_quantity)
        return self._size_sell(request, raw_quantity)

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
                lot_size=context.lot_size,
                risk_quantity_limit=context.risk_quantity_limit,
                is_suspended=context.is_suspended,
                at_price_limit=context.at_price_limit,
            )
        )

    def _size_buy(
        self,
        request: ManualSizingRequest,
        raw_quantity: int,
    ) -> ManualSizingResult:
        price = request.reference_price or 0.0
        cash_cap = floor(request.cash_available / price)
        capped = min(raw_quantity, cash_cap)
        caps: list[str] = []
        if cash_cap < raw_quantity:
            caps.append("cash")
        if request.risk_quantity_limit is not None:
            if request.risk_quantity_limit < capped:
                caps.append("risk_limit")
            capped = min(capped, request.risk_quantity_limit)
        rounded = round_buy_qty(capped, request.lot_size)
        if rounded == 0:
            reason = "below_board_lot"
            readiness: Literal["ready", "review", "blocked"] = "review"
        elif caps:
            reason = f"capped_by_{'_and_'.join(caps)}"
            readiness = "ready"
        elif rounded != raw_quantity:
            reason = "rounded_down_to_board_lot"
            readiness = "ready"
        else:
            reason = "exact_board_lot"
            readiness = "ready"
        return ManualSizingResult(
            raw_quantity=raw_quantity,
            rounded_quantity=rounded,
            lot_size=request.lot_size,
            reference_price=price,
            cash_impact=-(rounded * price),
            reason=reason,
            readiness=readiness,
        )

    def _size_sell(
        self,
        request: ManualSizingRequest,
        raw_quantity: int,
    ) -> ManualSizingResult:
        price = request.reference_price or 0.0
        rounded = min(raw_quantity, request.available_quantity)
        reason = (
            "t_plus1_available_quantity_cap"
            if rounded < raw_quantity
            else "sell_quantity_available"
        )
        readiness: Literal["ready", "review", "blocked"] = (
            "review" if rounded == 0 and raw_quantity > 0 else "ready"
        )
        return ManualSizingResult(
            raw_quantity=raw_quantity,
            rounded_quantity=rounded,
            lot_size=request.lot_size,
            reference_price=price,
            cash_impact=rounded * price,
            reason=reason,
            readiness=readiness,
        )


def _zero(
    request: ManualSizingRequest,
    reason: str,
    readiness: Literal["review", "blocked"],
) -> ManualSizingResult:
    return ManualSizingResult(
        raw_quantity=0,
        rounded_quantity=0,
        lot_size=request.lot_size,
        reference_price=request.reference_price,
        cash_impact=0.0,
        reason=reason,
        readiness=readiness,
    )
