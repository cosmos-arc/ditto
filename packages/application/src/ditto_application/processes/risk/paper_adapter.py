"""Application adapter for continuous risk in paper trading."""

from __future__ import annotations

from ditto_execution.orders.model import Order
from ditto_portfolio.accounting import FillEvent
from ditto_risk.continuous_gate import (
    ContinuousRiskGate,
    FillRiskContext,
    RiskDecisionKind,
    RiskGateContext,
)

from ditto_application.processes.execution.paper_trading_process import (
    PaperRiskContext,
    PaperRiskDecision,
)
from ditto_application.processes.risk.fingerprint import position_fingerprint

__all__ = ["ContinuousRiskPaperAdapter"]


class ContinuousRiskPaperAdapter:
    """Bind a pure continuous gate to one paper account and sleeve."""

    def __init__(
        self,
        *,
        gate: ContinuousRiskGate,
        account_id: str,
        sleeve_id: str,
    ) -> None:
        self._gate = gate
        self._account_id = account_id
        self._sleeve_id = sleeve_id

    def pre_trade(
        self,
        order: Order,
        context: PaperRiskContext,
    ) -> PaperRiskDecision:
        """Run the main pre-trade gate before the paper broker is called."""
        result = self._gate.pre_trade(order, self._gate_context(context))
        adjusted = result.adjusted_order
        adjusted_order = adjusted if isinstance(adjusted, Order) else None
        return PaperRiskDecision(
            allow=result.kind is RiskDecisionKind.ALLOW and adjusted_order is not None,
            adjusted_order=adjusted_order,
            reason_code=result.reason_code,
            reason=result.reason,
        )

    def post_fill(
        self,
        fill: FillEvent,
        context: PaperRiskContext,
        event_id: str,
    ) -> None:
        """Apply the broker fill using risk-owned monotonic sequencing."""
        snapshot = self._gate.snapshot_state()
        sequence = (
            snapshot.processed_event_ids.index(event_id) + 1
            if event_id in snapshot.processed_event_ids
            else snapshot.event_sequence + 1
        )
        self._gate.post_fill(
            fill,
            FillRiskContext(
                account_id=self._account_id,
                sleeve_id=self._sleeve_id,
                trade_date=context.trade_date,
                account_view=context.account_view,
                position_fingerprint=position_fingerprint(context.account_view),
                event_sequence=sequence,
            ),
            event_id,
        )

    def _gate_context(self, context: PaperRiskContext) -> RiskGateContext:
        return RiskGateContext(
            account_id=self._account_id,
            sleeve_id=self._sleeve_id,
            trade_date=context.trade_date,
            account_view=context.account_view,
            position_fingerprint=position_fingerprint(context.account_view),
            pre_trade_context=context.pre_trade_context,
        )
