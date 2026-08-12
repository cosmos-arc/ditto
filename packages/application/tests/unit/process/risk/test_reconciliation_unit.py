"""R4 three-layer EOD reconciliation tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.risk.reconciliation import (
    PlannedOrder,
    ReconciliationFill,
    ReconciliationInput,
    reconcile_eod,
)


def test_three_layer_reconciliation_matches_orders_positions_and_fingerprint() -> None:
    report = reconcile_eod(
        ReconciliationInput(
            account_id="paper-1",
            sleeve_id="core",
            trade_date="2026-04-01",
            planned_orders=(PlannedOrder("o1", 1, "buy", 100),),
            fills=(ReconciliationFill("f1", "o1", 1, "buy", 100),),
            opening_positions={1: 0},
            actual_positions={1: 100},
            risk_position_fingerprint="sha256:actual",
            actual_position_fingerprint="sha256:actual",
        )
    )

    assert report.status == "reconciled"
    assert report.differences == ()
    assert report.suggestion_allowed is True


def test_any_reconciliation_difference_blocks_and_has_stable_alert_key() -> None:
    input_ = ReconciliationInput(
        account_id="paper-1",
        sleeve_id="core",
        trade_date="2026-04-01",
        planned_orders=(PlannedOrder("o1", 1, "buy", 100),),
        fills=(ReconciliationFill("f1", "unknown", 1, "buy", 80),),
        opening_positions={1: 0},
        actual_positions={1: 70},
        risk_position_fingerprint="sha256:risk",
        actual_position_fingerprint="sha256:actual",
    )

    first = reconcile_eod(input_)
    second = reconcile_eod(input_)

    assert first.status == "mismatch"
    assert first.suggestion_allowed is False
    assert "unplanned_fill:unknown" in first.differences
    assert "position_quantity:1:rebuilt=80:actual=70" in first.differences
    assert "risk_position_fingerprint" in first.differences
    assert first.alert_idempotency_key == second.alert_idempotency_key


def test_reconciliation_is_read_only_and_exposes_no_auto_fix() -> None:
    report = reconcile_eod(
        ReconciliationInput(
            account_id="paper-1",
            sleeve_id="core",
            trade_date="2026-04-01",
            planned_orders=(),
            fills=(),
            opening_positions={},
            actual_positions={},
            risk_position_fingerprint="sha256:empty",
            actual_position_fingerprint="sha256:empty",
        )
    )

    assert not hasattr(report, "repair")
    assert not hasattr(report, "corrected_positions")


@pytest.mark.parametrize(
    "invalid_input",
    [
        {"trade_date": ""},
        {"risk_position_fingerprint": ""},
        {"actual_position_fingerprint": ""},
        {"actual_positions": {1: -1}},
    ],
)
def test_reconciliation_rejects_incomplete_or_invalid_authoritative_evidence(
    invalid_input: dict[str, object],
) -> None:
    valid = ReconciliationInput(
        account_id="paper-1",
        sleeve_id="core",
        trade_date="2026-04-01",
        planned_orders=(),
        fills=(),
        opening_positions={},
        actual_positions={},
        risk_position_fingerprint="sha256:risk",
        actual_position_fingerprint="sha256:actual",
    )

    with pytest.raises(AppProcessError):
        reconcile_eod(replace(valid, **invalid_input))
