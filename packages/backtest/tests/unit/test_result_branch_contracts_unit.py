"""Checkpoint projection behavior for absent and captured runtime state."""

from __future__ import annotations

from ditto_backtest._account_checkpoint import BacktestAccountStateSnapshot
from ditto_backtest.result import (
    BacktestCheckpoint,
    BacktestSettlementStateSnapshot,
)
from ditto_backtest.runtime_state import BacktestRuntimeStateSnapshot
from ditto_kernel.identity import InstrumentId


def _checkpoint(
    *,
    account_state: BacktestAccountStateSnapshot | None = None,
    settlement_state: BacktestSettlementStateSnapshot | None = None,
    runtime_state: BacktestRuntimeStateSnapshot | None = None,
) -> BacktestCheckpoint:
    return BacktestCheckpoint(
        run_id="run-1",
        strategy_id="strategy-1",
        completed_trade_date="2026-09-04",
        resume_from=None,
        completed_days=1,
        total_days=1,
        nav=1.0,
        fill_count=0,
        order_count=0,
        account_state=account_state,
        settlement_state=settlement_state,
        runtime_state=runtime_state,
    )


def test_checkpoint_absent_state_has_unambiguous_empty_evidence() -> None:
    checkpoint = _checkpoint()

    assert checkpoint.can_resume is False
    assert checkpoint.account_state_json == ""
    assert checkpoint.account_state_hash == ""
    assert checkpoint.settlement_state_json == ""
    assert checkpoint.settlement_state_hash == ""
    assert checkpoint.runtime_state_json == ""
    assert checkpoint.runtime_state_hash == ""


def test_checkpoint_captured_state_exposes_json_and_content_hashes() -> None:
    account = BacktestAccountStateSnapshot(
        cash_available=1.0,
        cash_settled=1.0,
        cash_frozen=0.0,
        total_value=1.0,
        nav=1.0,
        exposure=0.0,
    )
    settlement = BacktestSettlementStateSnapshot.from_frozen_quantities(
        {
            InstrumentId(2): {"2026-09-05": 0},
            InstrumentId(1): {"2026-09-05": 100},
        }
    )
    runtime = BacktestRuntimeStateSnapshot()
    checkpoint = _checkpoint(
        account_state=account,
        settlement_state=settlement,
        runtime_state=runtime,
    )

    assert checkpoint.account_state_json == account.to_json()
    assert checkpoint.account_state_hash == account.state_hash
    assert checkpoint.settlement_state_json == settlement.to_json()
    assert checkpoint.settlement_state_hash == settlement.state_hash
    assert checkpoint.runtime_state_json == runtime.to_json()
    assert checkpoint.runtime_state_hash == runtime.state_hash
    assert [int(item.instrument_id) for item in settlement.frozen_quantities] == [1]
