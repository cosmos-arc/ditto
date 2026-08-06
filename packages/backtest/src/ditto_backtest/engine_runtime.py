"""Capture and restore result-determining EngineLoop checkpoint state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ditto_execution.brokerage import Brokerage
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.planner import ExecutionPlanner
from ditto_execution.trade_builder import TradeBuilder
from ditto_strategy.alpha.context import StrategyContext

from ditto_backtest.audit.collector import ExecutionAuditCollector
from ditto_backtest.audit.state import ExecutionAuditStateSnapshot
from ditto_backtest.runtime_state import (
    BacktestRuntimeStateCapture,
    BacktestRuntimeStateSnapshot,
)

__all__ = [
    "BrokerageCheckpointStateOwner",
    "EngineRuntimeCapture",
    "PlannerCheckpointStateOwner",
    "capture_runtime_state",
    "restore_runtime_collaborators",
    "strategy_context_from_runtime",
]


@runtime_checkable
class PlannerCheckpointStateOwner(Protocol):
    """Optional planner capability required only by exact checkpoint resume."""

    def snapshot_id_counter(self) -> int:
        """Return the monotonic planner identifier counter."""
        ...

    def restore_id_counter(self, counter: int) -> None:
        """Restore the monotonic planner identifier counter."""
        ...


@runtime_checkable
class BrokerageCheckpointStateOwner(Protocol):
    """Optional brokerage capability required only by exact checkpoint resume."""

    def snapshot_fill_counter(self) -> int:
        """Return the monotonic brokerage fill counter."""
        ...

    def restore_fill_counter(self, counter: int) -> None:
        """Restore the monotonic brokerage fill counter."""
        ...


@dataclass(frozen=True)
class EngineRuntimeCapture:
    """State owners and values sampled atomically at one engine boundary."""

    pending_tickets: tuple[OrderTicket, ...]
    delayed_signals: tuple[object, ...]
    strategy_context: StrategyContext
    planner: ExecutionPlanner
    brokerage: Brokerage
    trade_builder: TradeBuilder
    rebalance_calendar_start: str | None
    audit_collector: ExecutionAuditCollector | None


def strategy_context_from_runtime(
    state: BacktestRuntimeStateSnapshot | None,
) -> StrategyContext:
    """Create StrategyContext from a checkpoint or a pristine default."""
    if state is None:
        return StrategyContext()
    _require_exact_versioned_state(state)
    return StrategyContext.from_snapshot(state.to_strategy_context_snapshot())


def restore_runtime_collaborators(
    state: BacktestRuntimeStateSnapshot | None,
    *,
    planner: ExecutionPlanner,
    brokerage: Brokerage,
    trade_builder: TradeBuilder,
    audit_collector: ExecutionAuditCollector | None,
) -> None:
    """Restore public state-owner APIs after all collaborators exist."""
    if state is None:
        return
    _require_exact_versioned_state(state)
    audit_state = _decode_audit_state(state)
    if audit_state is not None and audit_collector is None:
        raise ValueError("checkpoint audit history requires an audit collector")
    require_checkpoint_api = state.runtime_state_version is not None
    _restore_planner_counter(
        planner,
        state.resolved_planner_id_counter,
        required=require_checkpoint_api,
    )
    _restore_brokerage_counter(
        brokerage,
        state.brokerage_fill_counter,
        required=require_checkpoint_api,
    )
    if state.trade_builder_state is not None:
        trade_builder.restore_state(state.trade_builder_state)
    if audit_state is not None:
        if audit_collector is None:
            raise ValueError("checkpoint audit history requires an audit collector")
        audit_collector.restore_state(audit_state)


def capture_runtime_state(
    capture: EngineRuntimeCapture,
) -> BacktestRuntimeStateSnapshot:
    """Capture all mutable state that affects a resumed research backtest."""
    # Research construction currently rejects post_trade_guard, so stateful
    # MaxDrawdownRule peak state is not reachable on this Task's resume path.
    planner_counter = _snapshot_planner_counter(capture.planner)
    brokerage_counter = _snapshot_brokerage_counter(capture.brokerage)
    audit_state_json = (
        None
        if capture.audit_collector is None
        else capture.audit_collector.snapshot_state().to_json()
    )
    return BacktestRuntimeStateSnapshot.from_state(
        BacktestRuntimeStateCapture(
            pending_tickets=capture.pending_tickets,
            delayed_signals=capture.delayed_signals,
            strategy_context=capture.strategy_context.to_snapshot(),
            planner_id_counter=planner_counter or 0,
            brokerage_fill_counter=brokerage_counter or 0,
            trade_builder_state=capture.trade_builder.snapshot_state(),
            rebalance_calendar_start=capture.rebalance_calendar_start,
            audit_state_json=audit_state_json,
            attest_exact=(
                planner_counter is not None
                and brokerage_counter is not None
                and capture.rebalance_calendar_start is not None
                and audit_state_json is not None
            ),
        )
    )


def _snapshot_planner_counter(owner: ExecutionPlanner) -> int | None:
    if not isinstance(owner, PlannerCheckpointStateOwner):
        return None
    value = owner.snapshot_id_counter()
    return value if type(value) is int and value >= 0 else None


def _snapshot_brokerage_counter(owner: Brokerage) -> int | None:
    if not isinstance(owner, BrokerageCheckpointStateOwner):
        return None
    value = owner.snapshot_fill_counter()
    return value if type(value) is int and value >= 0 else None


def _restore_planner_counter(
    owner: ExecutionPlanner,
    counter: int,
    *,
    required: bool,
) -> None:
    if not isinstance(owner, PlannerCheckpointStateOwner):
        if not required and counter == 0:
            return
        raise ValueError("planner cannot restore checkpoint ID counter")
    if counter == 0 and not required:
        return
    owner.restore_id_counter(counter)


def _restore_brokerage_counter(
    owner: Brokerage,
    counter: int,
    *,
    required: bool,
) -> None:
    if not isinstance(owner, BrokerageCheckpointStateOwner):
        if not required and counter == 0:
            return
        raise ValueError("brokerage cannot restore checkpoint ID counter")
    if counter == 0 and not required:
        return
    owner.restore_fill_counter(counter)


def _require_exact_versioned_state(state: BacktestRuntimeStateSnapshot) -> None:
    if state.runtime_state_version is not None and not state.is_exact_resume_state:
        raise ValueError("versioned checkpoint runtime state is incomplete")


def _decode_audit_state(
    state: BacktestRuntimeStateSnapshot,
) -> ExecutionAuditStateSnapshot | None:
    if state.audit_state_json is None:
        return None
    return ExecutionAuditStateSnapshot.from_canonical_json(state.audit_state_json)
