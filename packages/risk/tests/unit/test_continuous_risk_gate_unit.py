"""Continuous R4 RiskGate state and recovery contract tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import (
    Account,
    CashAccountBuyingPower,
    CashBook,
    FillEvent,
    Position,
)
from ditto_risk.constraints.context import PreTradeContext
from ditto_risk.continuous_gate import (
    ContinuousRiskGate,
    DailyRiskInput,
    FillRiskContext,
    RiskDecisionKind,
    RiskGateContext,
    RiskStateError,
)


@dataclass(frozen=True)
class _Order:
    instrument_id: int = 1
    quantity: int = 100
    direction: OrderSide = OrderSide.BUY
    order_id: str = "order-1"
    order_type: OrderType = OrderType.MARKET
    price: float | None = None

    def with_quantity(self, qty: int) -> _Order:
        return replace(self, quantity=qty)


@dataclass(frozen=True)
class _Ticket:
    order: _Order
    leaves_quantity: int


def _account_view(nav: float = 100_000.0):
    return Account(cash=CashBook(available=nav, settled=nav, frozen=0.0)).get_view()


def _context(*, fingerprint: str = "positions:empty") -> RiskGateContext:
    return RiskGateContext(
        account_id="paper-1",
        sleeve_id="core",
        trade_date="2026-04-01",
        account_view=_account_view(),
        position_fingerprint=fingerprint,
    )


def _fill_context(sequence: int, *, fingerprint: str) -> FillRiskContext:
    return FillRiskContext(
        account_id="paper-1",
        sleeve_id="core",
        trade_date="2026-04-01",
        account_view=_account_view(),
        position_fingerprint=fingerprint,
        event_sequence=sequence,
    )


def _fill() -> FillEvent:
    return FillEvent(
        fill_id="fill-1",
        order_id="order-1",
        instrument_id=1,
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=10.0,
        fee=1.0,
        slippage=0.0,
        event_time=datetime(2026, 4, 1, 2, tzinfo=UTC),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def test_daily_drawdown_lock_rejects_new_orders_but_cancel_is_audited() -> None:
    gate = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        max_drawdown=0.10,
    )
    gate.daily_scan(
        DailyRiskInput(
            context=_context(),
            nav=100_000.0,
        )
    )
    report = gate.daily_scan(
        DailyRiskInput(
            context=_context(),
            nav=89_000.0,
        )
    )

    decision = gate.pre_trade(_Order(), _context())
    cancel = gate.pre_cancel("order-1", _context())

    assert report.readiness == "blocked"
    assert decision.kind is RiskDecisionKind.REJECT
    assert decision.reason_code == "risk_gate_locked"
    assert cancel.kind is RiskDecisionKind.ALLOW
    assert gate.events[-1].event_type == "cancel_allowed"


def test_daily_scan_fails_closed_on_unexplained_position_fingerprint_drift() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    gate.daily_scan(DailyRiskInput(context=_context(), nav=100_000.0))

    report = gate.daily_scan(
        DailyRiskInput(
            context=_context(fingerprint="positions:unreconciled-drift"),
            nav=100_000.0,
        )
    )

    assert report.readiness == "blocked"
    assert "position_fingerprint_mismatch" in report.block_reasons
    assert gate.snapshot_state().position_fingerprint == "positions:empty"


def test_duplicate_fill_is_idempotent_and_out_of_order_fill_fails_closed() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")

    first = gate.post_fill(
        _fill(),
        _fill_context(1, fingerprint="positions:after-fill-1"),
        "fill-event-1",
    )
    duplicate = gate.post_fill(
        _fill(),
        _fill_context(1, fingerprint="positions:after-fill-1"),
        "fill-event-1",
    )

    assert first.applied is True
    assert duplicate.applied is False
    assert duplicate.idempotent is True
    assert gate.snapshot_state().event_sequence == 1
    assert gate.snapshot_state().daily_turnover_notional == pytest.approx(1_000.0)

    with pytest.raises(RiskStateError, match="expected event sequence 2"):
        gate.post_fill(
            replace(_fill(), fill_id="fill-2"),
            _fill_context(3, fingerprint="positions:after-fill-2"),
            "fill-event-2",
        )

    assert gate.snapshot_state().locked is True


def test_restore_rejects_tampered_hash_and_position_fingerprint_mismatch() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    gate.daily_scan(DailyRiskInput(context=_context(), nav=100_000.0))
    snapshot = gate.snapshot_state()

    restored = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    restored.restore_state(
        snapshot,
        expected_position_fingerprint="positions:empty",
    )
    assert restored.snapshot_state() == snapshot

    with pytest.raises(RiskStateError, match="integrity hash"):
        restored.restore_state(
            replace(snapshot, peak_nav=123.0),
            expected_position_fingerprint="positions:empty",
        )

    with pytest.raises(RiskStateError, match="position fingerprint"):
        restored.restore_state(
            snapshot,
            expected_position_fingerprint="positions:different",
        )


def test_context_identity_mismatch_locks_gate_and_rejects_order() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    wrong = replace(_context(), account_id="paper-2")

    decision = gate.pre_trade(_Order(), wrong)

    assert decision.kind is RiskDecisionKind.REJECT
    assert decision.reason_code == "context_identity_mismatch"
    assert gate.snapshot_state().locked is True


def test_daily_turnover_applies_to_sells_and_missing_price_fails_closed() -> None:
    gate = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        max_daily_turnover=0.005,
    )
    gate.daily_scan(DailyRiskInput(context=_context(), nav=100_000.0))

    sell = gate.pre_trade(
        replace(_Order(), direction=OrderSide.SELL, price=10.0),
        _context(),
    )
    missing_price = gate.pre_trade(_Order(), _context())

    assert sell.kind is RiskDecisionKind.REJECT
    assert sell.reason_code == "daily_turnover_limit"
    assert missing_price.kind is RiskDecisionKind.REJECT
    assert missing_price.reason_code == "order_price_missing"


def test_daily_turnover_includes_orders_already_accepted_in_same_batch() -> None:
    gate = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        max_daily_turnover=0.015,
    )
    account_view = _account_view()
    accepted = replace(_Order(), order_id="accepted-1", price=10.0)
    rolling_context = PreTradeContext(
        account_view=account_view,
        rules={},
        market_snapshots={},
        buying_power_model=CashAccountBuyingPower(),
    ).with_order_accepted(accepted)

    decision = gate.pre_trade(
        replace(_Order(), order_id="order-2", price=10.0),
        replace(
            _context(),
            account_view=account_view,
            pre_trade_context=rolling_context,
        ),
    )

    assert decision.kind is RiskDecisionKind.REJECT
    assert decision.reason_code == "daily_turnover_limit"


def test_duplicate_event_id_with_different_fill_fails_closed() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    gate.post_fill(
        _fill(),
        _fill_context(1, fingerprint="positions:after-fill-1"),
        "fill-event-1",
    )

    with pytest.raises(RiskStateError, match="idempotency conflict"):
        gate.post_fill(
            replace(_fill(), filled_quantity=99),
            _fill_context(1, fingerprint="positions:after-fill-1"),
            "fill-event-1",
        )

    assert gate.snapshot_state().locked is True


def test_duplicate_fill_replay_rejects_current_position_fingerprint_drift() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    gate.post_fill(
        _fill(),
        _fill_context(1, fingerprint="positions:after-fill-1"),
        "fill-event-1",
    )

    with pytest.raises(RiskStateError, match="position fingerprint"):
        gate.post_fill(
            _fill(),
            _fill_context(1, fingerprint="positions:unreconciled-drift"),
            "fill-event-1",
        )

    assert gate.snapshot_state().locked is True


def test_fill_with_missing_position_fingerprint_fails_closed() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")

    with pytest.raises(RiskStateError, match="position fingerprint is missing"):
        gate.post_fill(
            _fill(),
            _fill_context(1, fingerprint=""),
            "fill-event-1",
        )

    snapshot = gate.snapshot_state()
    assert snapshot.locked is True
    assert snapshot.event_sequence == 0


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1.0, 0.0])
def test_non_finite_or_non_positive_order_price_fails_closed(price: float) -> None:
    decision = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
    ).pre_trade(replace(_Order(), price=price), _context())

    assert decision.kind is RiskDecisionKind.REJECT
    assert decision.reason_code == "order_price_invalid"


def test_non_positive_quantity_and_non_finite_daily_nav_fail_closed() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")

    quantity_decision = gate.pre_trade(
        replace(_Order(), quantity=0, price=10.0), _context()
    )
    report = gate.daily_scan(DailyRiskInput(context=_context(), nav=float("nan")))

    assert quantity_decision.kind is RiskDecisionKind.REJECT
    assert quantity_decision.reason_code == "order_quantity_invalid"
    assert report.readiness == "blocked"
    assert "invalid_nav" in report.block_reasons


@pytest.mark.parametrize("market_value", [float("nan"), float("inf"), -1.0])
def test_daily_scan_fails_closed_on_invalid_position_value(
    market_value: float,
) -> None:
    position = Position(
        instrument_id=1,
        quantity=100,
        available_quantity=100,
        average_cost=10.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )
    account_view = Account(
        positions={1: position},
        cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
    ).get_view()
    context = replace(_context(), account_view=account_view)

    report = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
    ).daily_scan(DailyRiskInput(context=context, nav=100_000.0))

    assert report.readiness == "blocked"
    assert "invalid_position_value" in report.block_reasons


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("filled_quantity", 0),
        ("fill_price", float("nan")),
        ("fill_price", 0.0),
        ("fee", float("nan")),
        ("fee", -1.0),
        ("slippage", float("inf")),
        ("slippage", -1.0),
    ],
)
def test_invalid_fill_payload_fails_closed_without_advancing_state(
    field: str,
    value: float,
) -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")

    with pytest.raises(RiskStateError, match="invalid fill payload"):
        gate.post_fill(
            replace(_fill(), **{field: value}),
            _fill_context(1, fingerprint="positions:after-fill-1"),
            "fill-event-1",
        )

    snapshot = gate.snapshot_state()
    assert snapshot.locked is True
    assert snapshot.event_sequence == 0
    assert snapshot.daily_turnover_notional == 0.0
    assert snapshot.processed_event_ids == ()


def test_pre_trade_rolls_daily_turnover_before_first_order_of_new_day() -> None:
    gate = ContinuousRiskGate(
        account_id="paper-1",
        sleeve_id="core",
        max_daily_turnover=0.02,
    )
    gate.post_fill(
        _fill(),
        _fill_context(1, fingerprint="positions:after-fill-1"),
        "fill-event-1",
    )
    next_day = replace(
        _context(fingerprint="positions:after-fill-1"),
        trade_date="2026-04-02",
    )

    decision = gate.pre_trade(replace(_Order(), price=10.0), next_day)

    assert decision.kind is RiskDecisionKind.ALLOW
    assert gate.snapshot_state().trade_date == "2026-04-02"
    assert gate.snapshot_state().daily_turnover_notional == 0.0


def test_backward_trade_date_locks_gate_instead_of_resetting_turnover() -> None:
    gate = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    gate.daily_scan(DailyRiskInput(context=_context(), nav=100_000.0))
    backward = replace(_context(), trade_date="2026-03-31")

    decision = gate.pre_trade(replace(_Order(), price=10.0), backward)

    assert decision.kind is RiskDecisionKind.REJECT
    assert decision.reason_code == "trade_date_out_of_order"
    assert gate.snapshot_state().trade_date == "2026-04-01"
    assert gate.snapshot_state().locked is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("peak_nav", float("nan")),
        ("current_drawdown", -0.1),
        ("daily_turnover_notional", -1.0),
        ("event_sequence", -1),
    ],
)
def test_restore_rejects_invalid_state_values_before_accepting_snapshot(
    field: str,
    value: float,
) -> None:
    source = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    source.daily_scan(DailyRiskInput(context=_context(), nav=100_000.0))
    invalid = replace(source.snapshot_state(), **{field: value})

    restored = ContinuousRiskGate(account_id="paper-1", sleeve_id="core")
    with pytest.raises(RiskStateError, match="risk state values"):
        restored.restore_state(
            invalid,
            expected_position_fingerprint="positions:empty",
        )

    assert restored.snapshot_state().locked is True
