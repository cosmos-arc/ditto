"""Reachable fail-closed edges for manual fill command orchestration."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_application.commands import trade
from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppNotFoundError,
)
from ditto_execution.errors import FillNotFoundError
from ditto_execution.models import FillAdjustmentRecord, FillRecord, SignalRecord


def _intent(
    *,
    status: str = "pending",
    strategy_id: str = "strategy-a",
    instrument_id: int = 1,
    direction: str = "buy",
) -> SignalRecord:
    return SignalRecord(
        intent_id="intent-a",
        strategy_id=strategy_id,
        signal_date="2025-01-01",
        instrument_id=instrument_id,
        direction=direction,
        target_weight=0.2,
        current_weight=0.1,
        delta_weight=0.1,
        quantity=100,
        status=status,
        created_at="2025-01-01T08:00:00Z",
    )


def _fill(
    *,
    fill_id: str = "fill-a",
    trade_date: str = "2025-01-02",
    strategy_id: str = "strategy-a",
    instrument_id: int = 1,
    direction: str = "buy",
    quantity: int = 100,
    fill_price: float = 10.0,
    fee: float = 1.0,
    slippage: float = 0.1,
    notes: str = "manual",
) -> FillRecord:
    return FillRecord(
        fill_id=fill_id,
        intent_id="intent-a",
        strategy_id=strategy_id,
        trade_date=trade_date,
        instrument_id=instrument_id,
        direction=direction,
        quantity=quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=slippage,
        notes=notes,
        settlement_date="2025-01-03",
        created_at="2025-01-02T08:00:00Z",
    )


def _adjustment(
    *,
    adjustment_id: str = "adjustment-a",
    fill_id: str = "fill-a",
    replacement_fill_id: str | None = "replacement-a",
    reason: str = "broker correction",
) -> FillAdjustmentRecord:
    return FillAdjustmentRecord(
        adjustment_id=adjustment_id,
        fill_id=fill_id,
        adjustment_type="replace",
        replacement_fill_id=replacement_fill_id,
        reason=reason,
        created_at="2025-01-02T09:00:00Z",
    )


def _record_command() -> trade.RecordFillCommand:
    return trade.RecordFillCommand(
        fill_id="fill-a",
        intent_id="intent-a",
        strategy_id="strategy-a",
        trade_date="2025-01-02",
        instrument_id=1,
        direction="buy",
        quantity=100,
        fill_price=10.0,
        fee=1.0,
        slippage=0.1,
        notes="manual",
    )


def _replace_command() -> trade.ReplaceFillCommand:
    return trade.ReplaceFillCommand(
        adjustment_id="adjustment-a",
        fill_id="fill-a",
        replacement_fill_id="replacement-a",
        trade_date="2025-01-03",
        quantity=80,
        fill_price=10.5,
        reason="broker correction",
        fee=0.8,
        slippage=0.2,
        notes="corrected",
    )


def _dependencies() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    intent_port = MagicMock(
        spec=["get_intent", "update_intent_status", "save_intent", "list_intents"]
    )
    fill_port = MagicMock(
        spec=[
            "apply_fill_adjustment",
            "get_fill",
            "get_fill_adjustment",
            "ledger_transaction",
            "list_effective_fills",
            "list_fill_adjustments",
            "list_fills",
            "save_fill",
        ]
    )
    position_port = MagicMock(
        spec=["list_positions", "replace_position_snapshot", "save_position"]
    )
    tracker = MagicMock(spec=["compute_positions", "compute_settlement_date"])
    baseline = MagicMock(spec=["resolve"])

    intent_port.get_intent.return_value = _intent()
    intent_port.update_intent_status.return_value = True
    fill_port.get_fill.return_value = None
    fill_port.get_fill_adjustment.return_value = None
    fill_port.ledger_transaction.return_value = nullcontext()
    fill_port.list_effective_fills.return_value = []
    fill_port.list_fills.return_value = []
    fill_port.save_fill.return_value = True
    fill_port.apply_fill_adjustment.return_value = True
    position_port.list_positions.return_value = []
    tracker.compute_positions.return_value = []
    tracker.compute_settlement_date.return_value = "2025-01-03"
    baseline.resolve.return_value = SimpleNamespace(
        account=SimpleNamespace(snapshot_date="2025-01-01"),
        positions=(),
    )
    return intent_port, fill_port, position_port, tracker, baseline


def _append_adapter(
    dependencies: tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock],
) -> trade.ProjectedFillAppendAdapter:
    intent_port, fill_port, position_port, tracker, baseline = dependencies
    return trade.ProjectedFillAppendAdapter(
        intent_port,
        fill_port,
        position_port,
        tracker,
        baseline,
    )


def _void_handler(
    dependencies: tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock],
) -> trade.VoidFillHandler:
    intent_port, fill_port, position_port, tracker, baseline = dependencies
    return trade.VoidFillHandler(
        intent_port,
        fill_port,
        position_port,
        tracker,
        baseline,
    )


def _replace_handler(
    dependencies: tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock],
) -> trade.ReplaceFillHandler:
    intent_port, fill_port, position_port, tracker, baseline = dependencies
    return trade.ReplaceFillHandler(
        intent_port,
        fill_port,
        position_port,
        tracker,
        baseline,
    )


@pytest.mark.unit
def test_append_fails_closed_when_intent_status_update_loses_race() -> None:
    dependencies = _dependencies()
    intent_port, fill_port, position_port, _, _ = dependencies
    intent_port.get_intent.side_effect = [_intent(), _intent()]
    intent_port.update_intent_status.return_value = False

    with pytest.raises(AppConflictError, match="Concurrent fill update conflict"):
        _append_adapter(dependencies).append_projected_fill(_fill())

    fill_port.save_fill.assert_called_once()
    position_port.replace_position_snapshot.assert_not_called()


@pytest.mark.unit
def test_append_translates_storage_not_found_at_application_boundary() -> None:
    dependencies = _dependencies()
    _, fill_port, _, _, _ = dependencies
    fill_port.save_fill.side_effect = FillNotFoundError("fill disappeared")

    with pytest.raises(AppNotFoundError, match="fill disappeared"):
        _append_adapter(dependencies).append_projected_fill(_fill())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("intent", "error_type", "message"),
    [
        (None, AppNotFoundError, "Intent not found"),
        (_intent(strategy_id="other"), AppCommandError, "Fill identity mismatch"),
        (_intent(status="cancelled"), AppCommandError, "expected 'pending'"),
    ],
)
def test_append_validates_intent_identity_and_open_status_before_writing(
    intent: SignalRecord | None,
    error_type: type[AppCommandError],
    message: str,
) -> None:
    dependencies = _dependencies()
    intent_port, fill_port, _, _, _ = dependencies
    intent_port.get_intent.return_value = intent

    with pytest.raises(error_type, match=message):
        _append_adapter(dependencies).append_projected_fill(_fill())

    fill_port.save_fill.assert_not_called()


@pytest.mark.unit
def test_record_fill_rejects_conflicting_idempotency_payload() -> None:
    dependencies = _dependencies()
    intent_port, fill_port, position_port, tracker, baseline = dependencies
    fill_port.get_fill.return_value = _fill(quantity=99)
    handler = trade.RecordFillHandler(
        intent_port,
        fill_port,
        position_port,
        tracker,
        baseline,
    )

    with pytest.raises(AppConflictError, match="Fill ID conflict"):
        handler.handle(_record_command())


@pytest.mark.unit
def test_record_fill_replay_requires_canonical_persisted_fill() -> None:
    dependencies = _dependencies()
    intent_port, fill_port, position_port, tracker, baseline = dependencies
    projected = MagicMock(spec=["append_projected_fill"])
    projected.append_projected_fill.return_value = False
    handler = trade.RecordFillHandler(
        intent_port,
        fill_port,
        position_port,
        tracker,
        baseline,
        projected,
    )

    with pytest.raises(AppNotFoundError, match="Fill not found after replay"):
        handler.handle(_record_command())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "intent", "message"),
    [
        (None, _intent(), "Fill not found"),
        (_fill(), None, "Intent not found"),
        (_fill(), _intent(instrument_id=2), "Fill identity mismatch"),
    ],
)
def test_void_requires_source_fill_and_matching_intent(
    source: FillRecord | None,
    intent: SignalRecord | None,
    message: str,
) -> None:
    dependencies = _dependencies()
    intent_port, fill_port, _, _, _ = dependencies
    fill_port.get_fill.return_value = source
    intent_port.get_intent.return_value = intent

    with pytest.raises(AppCommandError, match=message):
        _void_handler(dependencies).handle(
            trade.VoidFillCommand("adjustment-a", "fill-a", "duplicate")
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("failure", "error_type", "message"),
    [
        ("locked_missing", AppNotFoundError, "Intent not found"),
        ("locked_mismatch", AppCommandError, "Fill identity mismatch"),
        ("status_conflict", AppConflictError, "Concurrent fill adjustment conflict"),
        ("storage_missing", AppNotFoundError, "adjustment disappeared"),
    ],
)
def test_void_fails_closed_when_locked_state_or_storage_changes(
    failure: str,
    error_type: type[AppCommandError],
    message: str,
) -> None:
    dependencies = _dependencies()
    intent_port, fill_port, _, _, _ = dependencies
    fill_port.get_fill.return_value = _fill()
    if failure == "locked_missing":
        intent_port.get_intent.side_effect = [_intent(), None]
    elif failure == "locked_mismatch":
        intent_port.get_intent.side_effect = [_intent(), _intent(direction="sell")]
    elif failure == "status_conflict":
        intent_port.get_intent.side_effect = [_intent(), _intent()]
        intent_port.update_intent_status.return_value = False
    else:
        fill_port.apply_fill_adjustment.side_effect = FillNotFoundError(
            "adjustment disappeared"
        )

    with pytest.raises(error_type, match=message):
        _void_handler(dependencies).handle(
            trade.VoidFillCommand("adjustment-a", "fill-a", "duplicate")
        )


@pytest.mark.unit
def test_projected_correction_validates_adjustment_kind_and_replacement_id() -> None:
    dependencies = _dependencies()
    adapter = trade.ProjectedFillCorrectionAdapter(*dependencies)
    wrong_kind = FillAdjustmentRecord(
        "adjustment-a",
        "fill-a",
        "void",
        None,
        "duplicate",
        "2025-01-02T09:00:00Z",
    )

    with pytest.raises(AppCommandError, match="requires replace adjustment"):
        adapter.apply_projected_fill_replacement(
            adjustment=wrong_kind,
            replacement_fill=_fill(fill_id="replacement-a"),
        )
    with pytest.raises(AppCommandError, match="does not match adjustment"):
        adapter.apply_projected_fill_replacement(
            adjustment=_adjustment(replacement_fill_id="replacement-other"),
            replacement_fill=_fill(fill_id="replacement-a"),
        )


@pytest.mark.unit
def test_void_rejects_idempotency_conflict_and_blank_reason() -> None:
    dependencies = _dependencies()
    _, fill_port, _, _, _ = dependencies
    fill_port.get_fill_adjustment.return_value = FillAdjustmentRecord(
        "adjustment-a",
        "fill-a",
        "void",
        None,
        "original reason",
        "2025-01-02T09:00:00Z",
    )
    with pytest.raises(AppConflictError, match="adjustment ID conflict"):
        _void_handler(dependencies).handle(
            trade.VoidFillCommand("adjustment-a", "fill-a", "different reason")
        )

    fill_port.get_fill_adjustment.return_value = None
    with pytest.raises(AppCommandError, match="reason is required"):
        _void_handler(dependencies).handle(
            trade.VoidFillCommand("adjustment-b", "fill-a", "  ")
        )


@pytest.mark.unit
def test_void_replay_requires_canonical_adjustment() -> None:
    dependencies = _dependencies()
    intent_port, fill_port, _, _, _ = dependencies
    fill_port.get_fill_adjustment.side_effect = [None, None]
    fill_port.get_fill.return_value = _fill()
    fill_port.apply_fill_adjustment.return_value = False
    intent_port.get_intent.return_value = _intent()

    with pytest.raises(AppNotFoundError, match="adjustment not found after replay"):
        _void_handler(dependencies).handle(
            trade.VoidFillCommand("adjustment-a", "fill-a", "duplicate")
        )


@pytest.mark.unit
def test_replace_exact_replay_returns_canonical_adjustment() -> None:
    dependencies = _dependencies()
    _, fill_port, _, _, _ = dependencies
    existing = _adjustment()
    fill_port.get_fill_adjustment.return_value = existing
    fill_port.get_fill.return_value = _fill(
        fill_id="replacement-a",
        trade_date="2025-01-03",
        quantity=80,
        fill_price=10.5,
        fee=0.8,
        slippage=0.2,
        notes="corrected",
    )

    result = _replace_handler(dependencies).handle(_replace_command())

    assert result.adjustment_id == existing.adjustment_id
    fill_port.apply_fill_adjustment.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("replacement_exists", [False, True])
def test_replace_rejects_existing_adjustment_payload_drift(
    replacement_exists: bool,
) -> None:
    dependencies = _dependencies()
    _, fill_port, _, _, _ = dependencies
    fill_port.get_fill_adjustment.return_value = _adjustment(
        reason=("broker correction" if replacement_exists else "different reason")
    )
    fill_port.get_fill.return_value = (
        _fill(fill_id="replacement-a") if replacement_exists else None
    )

    with pytest.raises(AppConflictError, match="adjustment ID conflict"):
        _replace_handler(dependencies).handle(_replace_command())


@pytest.mark.unit
@pytest.mark.parametrize("canonical", [None, _adjustment()])
def test_replace_storage_replay_requires_and_returns_canonical_adjustment(
    canonical: FillAdjustmentRecord | None,
) -> None:
    dependencies = _dependencies()
    intent_port, fill_port, _, _, _ = dependencies
    fill_port.get_fill_adjustment.side_effect = [None, canonical]
    fill_port.get_fill.return_value = _fill()
    fill_port.apply_fill_adjustment.return_value = False
    intent_port.get_intent.return_value = _intent()
    handler = _replace_handler(dependencies)

    if canonical is None:
        with pytest.raises(
            AppNotFoundError,
            match="adjustment not found after replay",
        ):
            handler.handle(_replace_command())
    else:
        assert (
            handler.handle(_replace_command()).adjustment_id == canonical.adjustment_id
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("command", "message"),
    [
        (replace(_replace_command(), reason=" "), "reason is required"),
        (replace(_replace_command(), quantity=0), "quantity must be positive"),
        (
            replace(_replace_command(), fill_price=float("inf")),
            "price must be positive",
        ),
        (replace(_replace_command(), fee=-1.0), "fee must be non-negative"),
        (replace(_replace_command(), slippage=float("nan")), "slippage must be finite"),
    ],
)
def test_replace_rejects_invalid_financial_correction_values(
    command: trade.ReplaceFillCommand,
    message: str,
) -> None:
    dependencies = _dependencies()

    with pytest.raises(AppCommandError, match=message):
        _replace_handler(dependencies).handle(command)


@pytest.mark.unit
@pytest.mark.pit
@pytest.mark.parametrize("trade_date", ["2025-01-01", "2024-12-31"])
def test_position_rebuild_rejects_fill_at_or_before_opening_baseline(
    trade_date: str,
) -> None:
    dependencies = _dependencies()
    intent_port, _, position_port, _, _ = dependencies
    intent_port.get_intent.side_effect = [_intent(), _intent()]

    with pytest.raises(AppCommandError, match="later than its opening baseline"):
        _append_adapter(dependencies).append_projected_fill(
            _fill(trade_date=trade_date)
        )

    position_port.replace_position_snapshot.assert_not_called()


@pytest.mark.unit
def test_status_update_fails_closed_when_compare_and_swap_loses_race() -> None:
    intent_port, _, _, _, _ = _dependencies()
    intent_port.update_intent_status.return_value = False
    handler = trade.UpdateIntentStatusHandler(intent_port)

    with pytest.raises(AppCommandError, match="Concurrent status conflict"):
        handler.handle(trade.UpdateIntentStatusCommand("intent-a", "cancelled"))
