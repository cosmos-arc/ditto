"""Adversarial edge coverage for the continuous risk-gate contract."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from types import MappingProxyType

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting import (
    AccountView,
    CashAccountBuyingPower,
    CashBook,
    FillEvent,
    Position,
)
from ditto_risk.constraints.context import Decision, OrderCheckResult, PreTradeContext
from ditto_risk.continuous_gate import (
    ContinuousRiskGate,
    DailyRiskInput,
    FillRiskContext,
    RiskDecisionKind,
    RiskGateContext,
    RiskStateError,
    RiskStateSnapshot,
)
from ditto_risk.contracts import PreTradeOrder

_INSTRUMENT_ID = InstrumentId(1)


@dataclass(frozen=True)
class _Order:
    instrument_id: InstrumentId = _INSTRUMENT_ID
    quantity: int = 100
    direction: OrderSide = OrderSide.BUY
    order_id: str = "order-1"
    order_type: OrderType = OrderType.MARKET
    price: float | None = 10.0

    def with_quantity(self, qty: int) -> _Order:
        return replace(self, quantity=qty)


@dataclass(frozen=True)
class _Ticket:
    order: _Order
    leaves_quantity: int


@dataclass(frozen=True)
class _Rule:
    decision: Decision
    resized_quantity: int | None = None
    reason: str | None = None

    def check_order(
        self,
        order: PreTradeOrder,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        del context
        return OrderCheckResult(
            decision=self.decision,
            order_id=order.order_id,
            resized_quantity=self.resized_quantity,
            reason=self.reason,
            triggered_checks=("edge-rule",),
        )


def _account_view(
    *,
    nav: float = 100_000.0,
    positions: dict[InstrumentId, Position] | None = None,
) -> AccountView:
    return AccountView(
        positions=MappingProxyType(positions or {}),
        cash=CashBook(available=nav, settled=nav, frozen=0.0),
        total_value=nav,
        nav=nav,
        exposure=0.0,
    )


def _pre_trade_context(
    *,
    account_view: AccountView | None = None,
    snapshots: dict[InstrumentId, MarketSnapshot] | None = None,
    pending_tickets: tuple[_Ticket, ...] = (),
) -> PreTradeContext:
    return PreTradeContext(
        account_view=account_view or _account_view(),
        rules={},
        market_snapshots=snapshots or {},
        buying_power_model=CashAccountBuyingPower(),
        pending_tickets=pending_tickets,
    )


def _context(
    *,
    account_view: AccountView | None = None,
    fingerprint: str = "positions:empty",
    trade_date: str = "2026-09-05",
    pre_trade_context: PreTradeContext | None = None,
) -> RiskGateContext:
    return RiskGateContext(
        account_id="paper-1",
        sleeve_id="core",
        trade_date=trade_date,
        account_view=account_view or _account_view(),
        position_fingerprint=fingerprint,
        pre_trade_context=pre_trade_context,
    )


def _fill(*, fill_id: str = "fill-1") -> FillEvent:
    return FillEvent(
        fill_id=fill_id,
        order_id="order-1",
        instrument_id=_INSTRUMENT_ID,
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=10.0,
        fee=1.0,
        slippage=0.0,
        event_time=datetime(2026, 9, 5, 2, tzinfo=UTC),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def _fill_context(
    sequence: int,
    *,
    trade_date: str = "2026-09-05",
    account_id: str = "paper-1",
) -> FillRiskContext:
    return FillRiskContext(
        account_id=account_id,
        sleeve_id="core",
        trade_date=trade_date,
        account_view=_account_view(),
        position_fingerprint=f"positions:{sequence}",
        event_sequence=sequence,
    )


def _seal(snapshot: RiskStateSnapshot) -> RiskStateSnapshot:
    payload = asdict(replace(snapshot, integrity_hash=""))
    serialized = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = sha256(serialized.encode()).hexdigest()
    return replace(snapshot, integrity_hash=f"sha256:{digest}")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: ContinuousRiskGate(account_id=" ", sleeve_id="core"),
            "account_id and sleeve_id",
        ),
        (
            lambda: ContinuousRiskGate(account_id="paper-1", sleeve_id=""),
            "account_id and sleeve_id",
        ),
        (
            lambda: ContinuousRiskGate(
                account_id="paper-1", sleeve_id="core", max_drawdown=0.0
            ),
            "max_drawdown",
        ),
        (
            lambda: ContinuousRiskGate(
                account_id="paper-1", sleeve_id="core", max_concentration=1.1
            ),
            "max_concentration",
        ),
        (
            lambda: ContinuousRiskGate(
                account_id="paper-1", sleeve_id="core", max_daily_turnover=-0.1
            ),
            "max_daily_turnover",
        ),
    ],
)
def test_constructor_rejects_invalid_identity_and_limits(
    factory: Callable[[], ContinuousRiskGate],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_configured_rules_require_context_and_preserve_resize_evidence() -> None:
    missing_context = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        pre_trade_checks=(_Rule(Decision.ACCEPT),),
    ).pre_trade(_Order(), _context())
    assert missing_context.reason_code == "pre_trade_context_missing"

    pre_trade = _pre_trade_context()
    resized = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        pre_trade_checks=(
            _Rule(Decision.RESIZE, resized_quantity=50),
            _Rule(Decision.ACCEPT),
        ),
    ).pre_trade(_Order(), _context(pre_trade_context=pre_trade))

    assert resized.kind is RiskDecisionKind.ALLOW
    assert resized.adjusted_order is not None
    assert resized.adjusted_order.quantity == 50
    assert resized.triggered_checks == ("edge-rule", "edge-rule")


def test_rule_rejection_supplies_default_reason_and_audit_evidence() -> None:
    gate = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        pre_trade_checks=(_Rule(Decision.REJECT),),
    )

    decision = gate.pre_trade(
        _Order(),
        _context(pre_trade_context=_pre_trade_context()),
    )

    assert decision.kind is RiskDecisionKind.REJECT
    assert decision.reason == "pre-trade rule rejected"
    assert decision.triggered_checks == ("edge-rule",)


def test_market_snapshot_supplies_price_and_invalid_pending_evidence_rejects() -> None:
    snapshot = MarketSnapshot(
        trade_date="2026-09-05",
        instrument_id=_INSTRUMENT_ID,
        open=10.0,
        high=10.0,
        low=10.0,
        close=10.0,
        prev_close=10.0,
        volume=1_000.0,
        amount=10_000.0,
    )
    market_context = _pre_trade_context(snapshots={_INSTRUMENT_ID: snapshot})
    allowed = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").pre_trade(
        replace(_Order(), price=None),
        _context(pre_trade_context=market_context),
    )
    assert allowed.kind is RiskDecisionKind.ALLOW

    invalid_pending = _pre_trade_context(
        pending_tickets=(_Ticket(order=_Order(), leaves_quantity=-1),)
    )
    rejected = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").pre_trade(
        _Order(),
        _context(pre_trade_context=invalid_pending),
    )
    assert rejected.reason_code == "pending_order_evidence_invalid"


def test_zero_nav_rejects_turnover_and_position_concentration_is_fail_closed() -> None:
    zero_nav = _account_view(nav=0.0)
    decision = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").pre_trade(
        _Order(),
        _context(
            account_view=zero_nav,
            pre_trade_context=_pre_trade_context(account_view=zero_nav),
        ),
    )
    assert decision.reason_code == "account_nav_invalid"

    position = Position(
        instrument_id=_INSTRUMENT_ID,
        quantity=10,
        available_quantity=10,
        average_cost=9.0,
        market_value=90.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )
    concentrated = _account_view(
        nav=100.0,
        positions={_INSTRUMENT_ID: position},
    )
    report = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        max_concentration=0.5,
    ).daily_scan(
        DailyRiskInput(
            context=_context(account_view=concentrated),
            nav=100.0,
        )
    )
    assert "max_concentration_exceeded" in report.block_reasons


def test_external_blocks_and_cancel_identity_drift_are_audited() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    first = gate.daily_scan(
        DailyRiskInput(
            context=_context(),
            nav=100_000.0,
            external_block_reasons=("feed_stale", "feed_stale"),
        )
    )
    second = gate.daily_scan(
        DailyRiskInput(
            context=_context(),
            nav=100_000.0,
            external_block_reasons=("feed_stale",),
        )
    )
    wrong = replace(_context(), account_id="paper-2")
    cancel = gate.pre_cancel("order-1", wrong)

    assert first.block_reasons == ("feed_stale",)
    assert second.block_reasons == ("feed_stale",)
    assert cancel.kind is RiskDecisionKind.ALLOW
    assert gate.events[-1].detail["context_mismatch"] == "context_identity_mismatch"


@pytest.mark.parametrize("event_id", ["", " "])
def test_fill_requires_nonempty_event_identity(event_id: str) -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    with pytest.raises(RiskStateError, match="event_id must be non-empty"):
        gate.post_fill(_fill(), _fill_context(1), event_id)


def test_fill_identity_and_trade_date_failures_lock_without_applying() -> None:
    identity_gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    with pytest.raises(RiskStateError, match="context_identity_mismatch"):
        identity_gate.post_fill(
            _fill(),
            _fill_context(1, account_id="paper-2"),
            "event-1",
        )
    assert identity_gate.snapshot_state().event_sequence == 0

    date_gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    with pytest.raises(RiskStateError, match="trade_date_invalid"):
        date_gate.post_fill(
            _fill(),
            _fill_context(1, trade_date="2026-02-30"),
            "event-1",
        )
    assert date_gate.snapshot_state().event_sequence == 0


def test_missing_fingerprint_and_invalid_dates_reject_pre_trade() -> None:
    missing = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").pre_trade(
        _Order(),
        _context(fingerprint=""),
    )
    malformed = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").pre_trade(
        _Order(),
        _context(trade_date="2026/09/05"),
    )
    short = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").pre_trade(
        _Order(),
        _context(trade_date="bad"),
    )
    impossible = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").pre_trade(
        _Order(),
        _context(trade_date="2026-02-30"),
    )

    assert missing.reason_code == "position_fingerprint_missing"
    assert malformed.reason_code == "trade_date_invalid"
    assert short.reason_code == "trade_date_invalid"
    assert impossible.reason_code == "trade_date_invalid"


def test_restore_rejects_schema_identity_and_duplicate_event_evidence() -> None:
    source = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    source.post_fill(_fill(), _fill_context(1), "event-1")
    snapshot = source.snapshot_state()

    for invalid, message in (
        (replace(snapshot, schema_version=2), "schema version"),
        (replace(snapshot, account_id="paper-2"), "context_identity_mismatch"),
        (
            _seal(
                replace(
                    snapshot,
                    processed_event_ids=("event-1", "event-1"),
                    event_sequence=2,
                )
            ),
            "processed event ids must be unique",
        ),
    ):
        restored = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
        with pytest.raises(RiskStateError, match=message):
            restored.restore_state(
                invalid,
                expected_position_fingerprint="positions:1",
            )


@pytest.mark.parametrize(
    "changes",
    [
        {"processed_event_digests": (("other-event", "sha256:valid"),)},
        {"event_sequence": 2},
        {"processed_event_digests": (("event-1", "invalid-digest"),)},
    ],
)
def test_restore_rejects_digest_membership_sequence_and_shape(
    changes: dict[str, object],
) -> None:
    source = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    source.post_fill(_fill(), _fill_context(1), "event-1")
    invalid = _seal(replace(source.snapshot_state(), **changes))

    restored = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    with pytest.raises(RiskStateError, match="digests must match"):
        restored.restore_state(
            invalid,
            expected_position_fingerprint="positions:1",
        )


def test_zero_nav_position_weight_handles_empty_and_invested_accounts() -> None:
    empty = ContinuousRiskGate(account_id="paper-1", sleeve_id="core").daily_scan(
        DailyRiskInput(context=_context(account_view=_account_view(nav=0.0)), nav=1.0)
    )
    assert "max_concentration_exceeded" not in empty.block_reasons

    position = Position(
        instrument_id=_INSTRUMENT_ID,
        quantity=1,
        available_quantity=1,
        average_cost=1.0,
        market_value=0.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )
    invested = _account_view(nav=0.0, positions={_INSTRUMENT_ID: position})
    blocked = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        max_concentration=0.5,
    ).daily_scan(DailyRiskInput(context=_context(account_view=invested), nav=1.0))
    assert "max_concentration_exceeded" in blocked.block_reasons
