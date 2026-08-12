"""Pure continuous RiskGate state machine for live, paper, and backtest use."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from enum import StrEnum
from hashlib import sha256

from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_risk._turnover import pending_order_notional
from ditto_risk.constraints.context import Decision, PreTradeContext
from ditto_risk.contracts import PreTradeOrder
from ditto_risk.pre_trade import PreTradeRiskCheck

__all__ = [
    "ContinuousRiskGate",
    "DailyRiskInput",
    "DailyRiskReport",
    "FillApplicationResult",
    "FillRiskContext",
    "RiskDecision",
    "RiskDecisionKind",
    "RiskEvent",
    "RiskGateContext",
    "RiskStateError",
    "RiskStateSnapshot",
]

_RISK_STATE_SCHEMA_VERSION = 1


class RiskStateError(ValueError):
    """Raised for corrupt, out-of-order, or identity-inconsistent risk state."""


class RiskDecisionKind(StrEnum):
    """Binary publication decision returned by the continuous gate."""

    ALLOW = "allow"
    REJECT = "reject"


@dataclass(frozen=True)
class RiskGateContext:
    """Account and authoritative position context for one order decision."""

    account_id: str
    sleeve_id: str
    trade_date: str
    account_view: AccountView
    position_fingerprint: str
    pre_trade_context: PreTradeContext | None = None


@dataclass(frozen=True)
class FillRiskContext:
    """Ordered, post-fill authoritative state supplied by orchestration."""

    account_id: str
    sleeve_id: str
    trade_date: str
    account_view: AccountView
    position_fingerprint: str
    event_sequence: int


@dataclass(frozen=True)
class DailyRiskInput:
    """Pure daily scan input with an explicitly valued account NAV."""

    context: RiskGateContext
    nav: float
    external_block_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskDecision:
    """Auditable allow/reject result; cancellation always returns ALLOW."""

    kind: RiskDecisionKind
    reason_code: str | None = None
    reason: str | None = None
    adjusted_order: PreTradeOrder | None = None
    triggered_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class FillApplicationResult:
    """Whether a fill event changed state or was an idempotent replay."""

    applied: bool
    idempotent: bool
    event_sequence: int


@dataclass(frozen=True)
class DailyRiskReport:
    """Daily gate health projected from risk-owned state only."""

    account_id: str
    sleeve_id: str
    trade_date: str
    readiness: str
    block_reasons: tuple[str, ...]
    peak_nav: float
    current_drawdown: float
    daily_turnover_notional: float
    position_fingerprint: str
    event_sequence: int


@dataclass(frozen=True)
class RiskEvent:
    """In-memory append-only audit event emitted for each gate transition."""

    audit_sequence: int
    event_type: str
    trade_date: str
    detail: Mapping[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class RiskStateSnapshot:
    """Versioned, integrity-protected checkpoint of risk-owned state."""

    schema_version: int
    account_id: str
    sleeve_id: str
    trade_date: str | None
    peak_nav: float
    current_drawdown: float
    daily_turnover_notional: float
    locked: bool
    lock_reasons: tuple[str, ...]
    event_sequence: int
    processed_event_ids: tuple[str, ...]
    processed_event_digests: tuple[tuple[str, str], ...]
    position_fingerprint: str | None
    integrity_hash: str


@dataclass
class _RiskState:
    trade_date: str | None = None
    peak_nav: float = 0.0
    current_drawdown: float = 0.0
    daily_turnover_notional: float = 0.0
    locked: bool = False
    lock_reasons: tuple[str, ...] = ()
    event_sequence: int = 0
    processed_event_ids: tuple[str, ...] = ()
    processed_event_digests: tuple[tuple[str, str], ...] = ()
    position_fingerprint: str | None = None


class ContinuousRiskGate:
    """Fail-closed state owner for pre-trade, fill, daily, and recovery checks."""

    def __init__(
        self,
        *,
        account_id: str,
        sleeve_id: str,
        pre_trade_checks: tuple[PreTradeRiskCheck, ...] = (),
        max_drawdown: float = 1.0,
        max_concentration: float = 1.0,
        max_daily_turnover: float = 1.0,
    ) -> None:
        """Create an empty gate for exactly one account and sleeve."""
        if not account_id.strip() or not sleeve_id.strip():
            raise ValueError("account_id and sleeve_id must be non-empty")
        for name, value in (
            ("max_drawdown", max_drawdown),
            ("max_concentration", max_concentration),
            ("max_daily_turnover", max_daily_turnover),
        ):
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        self._account_id = account_id
        self._sleeve_id = sleeve_id
        self._pre_trade_checks = pre_trade_checks
        self._max_drawdown = max_drawdown
        self._max_concentration = max_concentration
        self._max_daily_turnover = max_daily_turnover
        self._state = _RiskState()
        self._events: list[RiskEvent] = []

    @property
    def events(self) -> tuple[RiskEvent, ...]:
        """Return an immutable view of append-only transition evidence."""
        return tuple(self._events)

    def pre_trade(
        self,
        order: PreTradeOrder,
        context: RiskGateContext,
    ) -> RiskDecision:
        """Allow an order only when identity, state, and every rule are valid."""
        initial_rejection = self._initial_pre_trade_rejection(context)
        if initial_rejection is not None:
            return initial_rejection
        adjusted, triggered, rule_rejection = self._apply_pre_trade_rules(
            order,
            context,
        )
        if rule_rejection is not None:
            return rule_rejection
        numeric_rejection = self._numeric_pre_trade_rejection(adjusted, context)
        if numeric_rejection is not None:
            return numeric_rejection
        self._append_event(
            "order_allowed",
            context.trade_date,
            {"order_id": order.order_id},
        )
        return RiskDecision(
            kind=RiskDecisionKind.ALLOW,
            adjusted_order=adjusted,
            triggered_checks=triggered,
        )

    def _numeric_pre_trade_rejection(
        self,
        adjusted: PreTradeOrder,
        context: RiskGateContext,
    ) -> RiskDecision | None:
        """Reject invalid economics and configured turnover breaches."""
        if type(adjusted.quantity) is not int or adjusted.quantity <= 0:
            return self._reject(
                context.trade_date,
                "order_quantity_invalid",
                "order quantity must be a positive integer",
            )
        price = adjusted.price
        if price is None and context.pre_trade_context is not None:
            price = context.pre_trade_context.price_for(adjusted.instrument_id)
        if price is None:
            return self._reject(
                context.trade_date,
                "order_price_missing",
                "order price is required for turnover risk",
            )
        if not math.isfinite(price) or price <= 0.0:
            return self._reject(
                context.trade_date,
                "order_price_invalid",
                "order price must be finite and positive",
            )
        return self._turnover_rejection(adjusted, context, price)

    def _turnover_rejection(
        self,
        order: PreTradeOrder,
        context: RiskGateContext,
        price: float,
    ) -> RiskDecision | None:
        """Reject incomplete pending evidence or a projected turnover breach."""
        pending_notional = pending_order_notional(context.pre_trade_context)
        if pending_notional is None:
            return self._reject(
                context.trade_date,
                "pending_order_evidence_invalid",
                "pending orders require finite positive prices and quantities",
            )
        projected_turnover = self._projected_daily_turnover(
            order,
            context,
            price=price,
            pending_notional=pending_notional,
        )
        if projected_turnover is None:
            return self._reject(
                context.trade_date,
                "account_nav_invalid",
                "account NAV must be finite and positive",
            )
        if projected_turnover > self._max_daily_turnover:
            return self._reject(
                context.trade_date,
                "daily_turnover_limit",
                "projected daily turnover exceeds configured limit",
            )
        return None

    def _apply_pre_trade_rules(
        self,
        order: PreTradeOrder,
        context: RiskGateContext,
    ) -> tuple[PreTradeOrder, tuple[str, ...], RiskDecision | None]:
        """Apply configured pure rules and preserve resize/check evidence."""
        adjusted = order
        triggered: list[str] = []
        pre_trade_context = context.pre_trade_context
        if pre_trade_context is None:
            return adjusted, (), None
        for check in self._pre_trade_checks:
            result = check.check_order(adjusted, pre_trade_context)
            triggered.extend(result.triggered_checks)
            if result.decision is Decision.REJECT:
                return (
                    adjusted,
                    tuple(triggered),
                    self._reject(
                        context.trade_date,
                        "pre_trade_rule_rejected",
                        result.reason or "pre-trade rule rejected",
                        triggered=tuple(triggered),
                    ),
                )
            if result.resized_quantity is not None:
                adjusted = adjusted.with_quantity(result.resized_quantity)
        return adjusted, tuple(triggered), None

    def _initial_pre_trade_rejection(
        self,
        context: RiskGateContext,
    ) -> RiskDecision | None:
        """Return an identity/state rejection before evaluating order rules."""
        mismatch = self._context_mismatch(context)
        if mismatch is not None:
            self._lock(mismatch)
            return self._reject(context.trade_date, mismatch, mismatch)
        if self._state.locked:
            reason = ",".join(self._state.lock_reasons) or "risk gate locked"
            return self._reject(
                context.trade_date,
                "risk_gate_locked",
                reason,
            )
        trade_date_failure = self._advance_trade_date_or_lock(context.trade_date)
        if trade_date_failure is not None:
            return self._reject(
                context.trade_date,
                trade_date_failure,
                "trade date is invalid or precedes current risk state",
            )
        if self._pre_trade_checks and context.pre_trade_context is None:
            self._lock("pre_trade_context_missing")
            return self._reject(
                context.trade_date,
                "pre_trade_context_missing",
                "configured pre-trade rules require PreTradeContext",
            )
        return None

    def pre_cancel(
        self,
        order_id: str,
        context: RiskGateContext,
    ) -> RiskDecision:
        """Always allow cancellation while retaining identity diagnostics."""
        mismatch = self._context_mismatch(context)
        if mismatch is not None:
            self._lock(mismatch)
        self._append_event(
            "cancel_allowed",
            context.trade_date,
            {"order_id": order_id, "context_mismatch": mismatch},
        )
        return RiskDecision(kind=RiskDecisionKind.ALLOW)

    def post_fill(
        self,
        fill: FillEvent,
        context: FillRiskContext,
        event_id: str,
    ) -> FillApplicationResult:
        """Apply a unique next-sequence fill or fail closed on inconsistency."""
        if not event_id.strip():
            raise RiskStateError("event_id must be non-empty")
        if not _valid_fill_payload(fill):
            self._lock("fill_payload_invalid")
            raise RiskStateError("invalid fill payload")
        mismatch = self._identity_mismatch(context.account_id, context.sleeve_id)
        if mismatch is not None:
            self._lock(mismatch)
            raise RiskStateError(mismatch)
        if not context.position_fingerprint:
            self._lock("position_fingerprint_missing")
            raise RiskStateError("position fingerprint is missing")
        event_digest = _fill_event_digest(fill, context)
        prior_digest = dict(self._state.processed_event_digests).get(event_id)
        if prior_digest is not None:
            if prior_digest != event_digest:
                self._lock("fill_event_idempotency_conflict")
                raise RiskStateError("fill event idempotency conflict")
            if context.position_fingerprint != self._state.position_fingerprint:
                self._lock("position_fingerprint_mismatch")
                raise RiskStateError("position fingerprint mismatch")
            return FillApplicationResult(
                applied=False,
                idempotent=True,
                event_sequence=self._state.event_sequence,
            )
        expected = self._state.event_sequence + 1
        if context.event_sequence != expected:
            reason = f"expected event sequence {expected}, got {context.event_sequence}"
            self._lock("fill_event_out_of_order")
            raise RiskStateError(reason)
        trade_date_failure = self._advance_trade_date_or_lock(context.trade_date)
        if trade_date_failure is not None:
            raise RiskStateError(trade_date_failure)
        self._state.event_sequence = context.event_sequence
        self._state.daily_turnover_notional += abs(
            fill.fill_price * fill.filled_quantity
        )
        self._state.processed_event_ids = (
            *self._state.processed_event_ids,
            event_id,
        )
        self._state.processed_event_digests = (
            *self._state.processed_event_digests,
            (event_id, event_digest),
        )
        self._state.position_fingerprint = context.position_fingerprint
        self._append_event(
            "fill_applied",
            context.trade_date,
            {
                "event_id": event_id,
                "fill_id": fill.fill_id,
                "event_sequence": context.event_sequence,
            },
        )
        return FillApplicationResult(
            applied=True,
            idempotent=False,
            event_sequence=context.event_sequence,
        )

    def daily_scan(self, input_: DailyRiskInput) -> DailyRiskReport:
        """Update drawdown/concentration state and return readiness evidence."""
        context = input_.context
        mismatch = self._context_mismatch(context)
        if mismatch is not None:
            self._lock(mismatch)
        valid_nav = math.isfinite(input_.nav) and input_.nav > 0.0
        if not valid_nav:
            self._lock("invalid_nav")
        self._advance_trade_date_or_lock(context.trade_date)
        if valid_nav:
            self._state.peak_nav = max(self._state.peak_nav, input_.nav)
            self._state.current_drawdown = (
                0.0
                if self._state.peak_nav <= 0.0
                else max(0.0, 1.0 - input_.nav / self._state.peak_nav)
            )
        if self._state.current_drawdown > self._max_drawdown:
            self._lock("max_drawdown_exceeded")
        maximum_position_weight = _maximum_position_weight(context.account_view)
        if maximum_position_weight is None:
            self._lock("invalid_position_value")
        elif maximum_position_weight > self._max_concentration:
            self._lock("max_concentration_exceeded")
        if input_.external_block_reasons:
            for reason in input_.external_block_reasons:
                self._lock(reason)
        if mismatch is None:
            self._state.position_fingerprint = context.position_fingerprint
        self._append_event(
            "daily_scan",
            context.trade_date,
            {"readiness": "blocked" if self._state.locked else "ready"},
        )
        return DailyRiskReport(
            account_id=self._account_id,
            sleeve_id=self._sleeve_id,
            trade_date=context.trade_date,
            readiness="blocked" if self._state.locked else "ready",
            block_reasons=self._state.lock_reasons,
            peak_nav=self._state.peak_nav,
            current_drawdown=self._state.current_drawdown,
            daily_turnover_notional=self._state.daily_turnover_notional,
            position_fingerprint=context.position_fingerprint,
            event_sequence=self._state.event_sequence,
        )

    def snapshot_state(self) -> RiskStateSnapshot:
        """Capture a deterministic integrity-protected state snapshot."""
        snapshot = RiskStateSnapshot(
            schema_version=_RISK_STATE_SCHEMA_VERSION,
            account_id=self._account_id,
            sleeve_id=self._sleeve_id,
            trade_date=self._state.trade_date,
            peak_nav=self._state.peak_nav,
            current_drawdown=self._state.current_drawdown,
            daily_turnover_notional=self._state.daily_turnover_notional,
            locked=self._state.locked,
            lock_reasons=self._state.lock_reasons,
            event_sequence=self._state.event_sequence,
            processed_event_ids=self._state.processed_event_ids,
            processed_event_digests=self._state.processed_event_digests,
            position_fingerprint=self._state.position_fingerprint,
            integrity_hash="",
        )
        return replace(snapshot, integrity_hash=_snapshot_hash(snapshot))

    def restore_state(
        self,
        snapshot: RiskStateSnapshot,
        *,
        expected_position_fingerprint: str,
    ) -> None:
        """Restore only an intact state matching identity and authoritative ledger."""
        if snapshot.schema_version != _RISK_STATE_SCHEMA_VERSION:
            self._lock("risk_state_schema_mismatch")
            raise RiskStateError("risk state schema version mismatch")
        if not _valid_snapshot_values(snapshot):
            self._lock("risk_state_values_invalid")
            raise RiskStateError("risk state values are invalid")
        mismatch = self._identity_mismatch(snapshot.account_id, snapshot.sleeve_id)
        if mismatch is not None:
            self._lock(mismatch)
            raise RiskStateError(mismatch)
        if snapshot.integrity_hash != _snapshot_hash(snapshot):
            self._lock("risk_state_integrity_failure")
            raise RiskStateError("risk state integrity hash mismatch")
        if snapshot.position_fingerprint != expected_position_fingerprint:
            self._lock("position_fingerprint_mismatch")
            raise RiskStateError("position fingerprint mismatch")
        if len(set(snapshot.processed_event_ids)) != len(snapshot.processed_event_ids):
            self._lock("duplicate_processed_event_id")
            raise RiskStateError("processed event ids must be unique")
        digest_ids = tuple(event_id for event_id, _ in snapshot.processed_event_digests)
        if (
            digest_ids != snapshot.processed_event_ids
            or snapshot.event_sequence != len(snapshot.processed_event_ids)
            or any(
                not digest.startswith("sha256:")
                for _, digest in snapshot.processed_event_digests
            )
        ):
            self._lock("processed_event_digest_mismatch")
            raise RiskStateError("processed event digests must match event ids")
        self._state = _RiskState(
            trade_date=snapshot.trade_date,
            peak_nav=snapshot.peak_nav,
            current_drawdown=snapshot.current_drawdown,
            daily_turnover_notional=snapshot.daily_turnover_notional,
            locked=snapshot.locked,
            lock_reasons=snapshot.lock_reasons,
            event_sequence=snapshot.event_sequence,
            processed_event_ids=snapshot.processed_event_ids,
            processed_event_digests=snapshot.processed_event_digests,
            position_fingerprint=snapshot.position_fingerprint,
        )

    def _context_mismatch(
        self,
        context: RiskGateContext,
        *,
        check_fingerprint: bool = True,
    ) -> str | None:
        mismatch = self._identity_mismatch(context.account_id, context.sleeve_id)
        if mismatch is not None:
            return mismatch
        if not context.position_fingerprint:
            return "position_fingerprint_missing"
        if (
            check_fingerprint
            and self._state.position_fingerprint is not None
            and context.position_fingerprint != self._state.position_fingerprint
        ):
            return "position_fingerprint_mismatch"
        return None

    def _identity_mismatch(self, account_id: str, sleeve_id: str) -> str | None:
        if account_id != self._account_id or sleeve_id != self._sleeve_id:
            return "context_identity_mismatch"
        return None

    def _projected_daily_turnover(
        self,
        order: PreTradeOrder,
        context: RiskGateContext,
        *,
        price: float,
        pending_notional: float,
    ) -> float | None:
        if (
            not math.isfinite(context.account_view.nav)
            or context.account_view.nav <= 0.0
        ):
            return None
        projected = (
            self._state.daily_turnover_notional
            + pending_notional
            + price * order.quantity
        )
        return projected / context.account_view.nav

    def _advance_trade_date(self, trade_date: str) -> str | None:
        """Advance the daily bucket, rejecting invalid or backward time."""
        parsed = _parse_trade_date(trade_date)
        if parsed is None:
            return "trade_date_invalid"
        current_value = self._state.trade_date
        if current_value is not None:
            current = _parse_trade_date(current_value)
            if current is None:
                return "trade_date_invalid"
            if parsed < current:
                return "trade_date_out_of_order"
        if current_value != trade_date:
            self._state.trade_date = trade_date
            self._state.daily_turnover_notional = 0.0
        return None

    def _advance_trade_date_or_lock(self, trade_date: str) -> str | None:
        failure = self._advance_trade_date(trade_date)
        if failure is not None:
            self._lock(failure)
        return failure

    def _lock(self, reason: str) -> None:
        self._state.locked = True
        if reason not in self._state.lock_reasons:
            self._state.lock_reasons = (*self._state.lock_reasons, reason)

    def _reject(
        self,
        trade_date: str,
        code: str,
        reason: str,
        *,
        triggered: tuple[str, ...] = (),
    ) -> RiskDecision:
        self._append_event(
            "order_rejected",
            trade_date,
            {"reason_code": code, "reason": reason},
        )
        return RiskDecision(
            kind=RiskDecisionKind.REJECT,
            reason_code=code,
            reason=reason,
            triggered_checks=triggered,
        )

    def _append_event(
        self,
        event_type: str,
        trade_date: str,
        detail: Mapping[str, object],
    ) -> None:
        self._events.append(
            RiskEvent(
                audit_sequence=len(self._events) + 1,
                event_type=event_type,
                trade_date=trade_date,
                detail=dict(detail),
            )
        )


def _maximum_position_weight(account: AccountView) -> float | None:
    if any(
        not math.isfinite(position.market_value) or position.market_value < 0.0
        for position in account.positions.values()
    ):
        return None
    if account.nav <= 0.0:
        return 1.0 if account.positions else 0.0
    return max(
        (
            position.market_value / account.nav
            for position in account.positions.values()
        ),
        default=0.0,
    )


def _snapshot_hash(snapshot: RiskStateSnapshot) -> str:
    payload = asdict(replace(snapshot, integrity_hash=""))
    serialized = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{sha256(serialized.encode()).hexdigest()}"


def _parse_trade_date(value: str) -> date | None:
    if not value or len(value) != len("YYYY-MM-DD"):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _valid_snapshot_values(snapshot: RiskStateSnapshot) -> bool:
    """Validate restored domain values independently of integrity evidence."""
    numeric_values = (
        snapshot.peak_nav,
        snapshot.current_drawdown,
        snapshot.daily_turnover_notional,
    )
    return (
        all(_is_finite_number(value) for value in numeric_values)
        and snapshot.peak_nav >= 0.0
        and 0.0 <= snapshot.current_drawdown <= 1.0
        and snapshot.daily_turnover_notional >= 0.0
        and type(snapshot.event_sequence) is int
        and snapshot.event_sequence >= 0
        and type(snapshot.locked) is bool
        and (snapshot.trade_date is None or _parse_trade_date(snapshot.trade_date))
        is not None
        and all(reason.strip() for reason in snapshot.lock_reasons)
        and all(event_id.strip() for event_id in snapshot.processed_event_ids)
        and all(
            event_id.strip() and digest.strip()
            for event_id, digest in snapshot.processed_event_digests
        )
        and (
            snapshot.position_fingerprint is None
            or bool(snapshot.position_fingerprint.strip())
        )
    )


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _valid_fill_payload(fill: FillEvent) -> bool:
    """Validate accounting inputs before hashing or mutating risk state."""
    return (
        bool(fill.fill_id.strip())
        and bool(fill.order_id.strip())
        and type(fill.filled_quantity) is int
        and fill.filled_quantity > 0
        and type(fill.cumulative_quantity) is int
        and fill.cumulative_quantity >= fill.filled_quantity
        and type(fill.leaves_quantity) is int
        and fill.leaves_quantity >= 0
        and math.isfinite(fill.fill_price)
        and fill.fill_price > 0.0
        and math.isfinite(fill.fee)
        and fill.fee >= 0.0
        and math.isfinite(fill.slippage)
        and fill.slippage >= 0.0
    )


def _fill_event_digest(fill: FillEvent, context: FillRiskContext) -> str:
    payload = {
        "account_id": context.account_id,
        "cumulative_quantity": fill.cumulative_quantity,
        "direction": fill.direction.value,
        "event_sequence": context.event_sequence,
        "event_time": fill.event_time.isoformat(),
        "fee": fill.fee,
        "fill_id": fill.fill_id,
        "fill_price": fill.fill_price,
        "filled_quantity": fill.filled_quantity,
        "instrument_id": int(fill.instrument_id),
        "leaves_quantity": fill.leaves_quantity,
        "order_id": fill.order_id,
        "sleeve_id": context.sleeve_id,
        "slippage": fill.slippage,
        "trade_date": context.trade_date,
    }
    serialized = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{sha256(serialized.encode()).hexdigest()}"
