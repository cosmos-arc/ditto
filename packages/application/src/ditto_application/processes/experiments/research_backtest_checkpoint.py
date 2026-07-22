"""Strategy-checkpoint resume contract for frozen research backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ditto_backtest.audit.state import ExecutionAuditStateSnapshot
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestRuntimeStateCapture,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
)
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting import Account, CashBook
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
    canonical_parameter_hash,
)
from ditto_strategy.runs.models import StrategyRunCheckpointRecord
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointReaderProtocol,
    StrategyRunCheckpointWriterProtocol,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import (
    BacktestServiceConfig,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    BaselineExecutorBinding,
)
from ditto_application.processes.experiments.execution_bundle import (
    ExactBenchmarkBinding,
    ResearchExecutionAudit,
    StrategyExecutionBinding,
)

__all__ = [
    "ResearchBacktestCheckpointControl",
    "ResearchBacktestResumeState",
    "ResearchBacktestStrategyConfig",
    "build_research_backtest_config",
    "build_research_backtest_strategy_config",
    "require_research_resume_runtime_state",
    "resolve_research_backtest_resume",
]


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "frozen research backtest construction failed",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


@dataclass(frozen=True, slots=True)
class ResearchBacktestResumeState:
    """Exact parent checkpoint plus its verified restorable state."""

    checkpoint: StrategyRunCheckpointRecord
    account: BacktestAccountStateSnapshot
    settlement: BacktestSettlementStateSnapshot
    runtime: BacktestRuntimeStateSnapshot


@dataclass(frozen=True, slots=True)
class ResearchBacktestCheckpointControl:
    """Existing strategy-run checkpoint ports bound to one research build."""

    writer: StrategyRunCheckpointWriterProtocol
    resume: ResearchBacktestResumeState | None = None


@dataclass(frozen=True, slots=True)
class ResearchBacktestStrategyConfig:
    """Resolved strategy fields needed by the audit-bound service config."""

    strategy_id: str
    strategy_version: str
    base_spec_hash: str
    spec_hash: str
    parameter_hash: str
    candidate_parameters: tuple[CandidateParameter, ...]
    effective_parameters: tuple[EffectiveParameter, ...]
    factor_report_refs: tuple[str, ...]
    rebalance_frequency: str


def build_research_backtest_strategy_config(
    strategy: StrategyExecutionBinding | BaselineExecutorBinding,
    *,
    effective_parameters: tuple[EffectiveParameter, ...],
    rebalance_frequency: str,
) -> ResearchBacktestStrategyConfig:
    """Resolve canonical service fields from one frozen strategy binding."""
    if type(strategy) is StrategyExecutionBinding:
        return ResearchBacktestStrategyConfig(
            strategy_id=strategy.exact_strategy.strategy_id,
            strategy_version=str(strategy.exact_strategy.version),
            base_spec_hash=strategy.exact_strategy.spec_hash,
            spec_hash=strategy.resolved_spec_hash,
            parameter_hash=strategy.parameter_hash,
            candidate_parameters=strategy.candidate_parameters,
            effective_parameters=effective_parameters,
            factor_report_refs=tuple(
                item.binding_hash for item in strategy.factor_bindings
            ),
            rebalance_frequency=rebalance_frequency,
        )
    if type(strategy) is BaselineExecutorBinding and not effective_parameters:
        return ResearchBacktestStrategyConfig(
            strategy_id=strategy.baseline_ref,
            strategy_version=str(strategy.executor_contract_version),
            base_spec_hash=strategy.descriptor_hash,
            spec_hash=strategy.descriptor_hash,
            parameter_hash=canonical_parameter_hash(()),
            candidate_parameters=(),
            effective_parameters=(),
            factor_report_refs=(),
            rebalance_frequency=rebalance_frequency,
        )
    raise _error("invalid_strategy_execution_binding")


def build_research_backtest_config(
    *,
    audit: ResearchExecutionAudit,
    strategy: ResearchBacktestStrategyConfig,
    initial_cash: float,
    benchmark: ExactBenchmarkBinding | None,
    resume: ResearchBacktestResumeState | None,
) -> BacktestServiceConfig:
    """Build the one canonical service config for initial and resumed attempts."""
    semantics = audit.semantics
    snapshot = semantics.snapshot
    checkpoint = None if resume is None else resume.checkpoint
    return BacktestServiceConfig(
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        run_id=audit.backtest_run_id,
        parent_run_id="" if checkpoint is None else checkpoint.run_id,
        start_date=(
            semantics.test_start.isoformat()
            if checkpoint is None
            else checkpoint.resume_from or ""
        ),
        end_date=semantics.test_end.isoformat(),
        initial_cash=initial_cash,
        benchmark_id=(
            None if benchmark is None else InstrumentId(benchmark.instrument_id)
        ),
        candidate_parameters=strategy.candidate_parameters,
        research_snapshot_id=snapshot.exact_snapshot.snapshot_id,
        research_snapshot_manifest_hash=snapshot.exact_snapshot.manifest_hash,
        rebalance_freq=strategy.rebalance_frequency,
        engine_version=semantics.backtest.engine_version,
        random_seed=semantics.seed,
        execution_delay=semantics.execution_delay_sessions,
        knowledge_lag_days=semantics.knowledge_lag_days,
        code_version=semantics.environment.code_version,
        data_catalog_identities=tuple(
            f"{item.input_id}:{item.content_hash}:{item.schema_hash}"
            for item in snapshot.inputs
        ),
        factor_report_refs=strategy.factor_report_refs,
        recommendation_status="research",
        participation_rate=(semantics.backtest.participation_rate_ppm / 1_000_000),
        fill_mode=semantics.backtest.fill_mode.value,
        resume_from_run_id="" if checkpoint is None else checkpoint.run_id,
        resume_checkpoint_trade_date=(
            "" if checkpoint is None else checkpoint.completed_trade_date
        ),
        resume_checkpoint_completed_days=(
            0 if checkpoint is None else checkpoint.completed_days
        ),
        resume_checkpoint_total_days=(
            0 if checkpoint is None else checkpoint.total_days
        ),
        resume_checkpoint_nav=0.0 if checkpoint is None else checkpoint.nav,
        resume_checkpoint_order_count=(
            0 if checkpoint is None else checkpoint.order_count
        ),
        resume_checkpoint_fill_count=(
            0 if checkpoint is None else checkpoint.fill_count
        ),
        resume_account_state_json=(
            "" if checkpoint is None else checkpoint.account_state_json
        ),
        resume_account_state_hash=(
            "" if checkpoint is None else checkpoint.account_state_hash
        ),
        resume_settlement_state_json=(
            "" if checkpoint is None else checkpoint.settlement_state_json
        ),
        resume_settlement_state_hash=(
            "" if checkpoint is None else checkpoint.settlement_state_hash
        ),
        resume_runtime_state_json=(
            "" if checkpoint is None else checkpoint.runtime_state_json
        ),
        resume_runtime_state_hash=(
            "" if checkpoint is None else checkpoint.runtime_state_hash
        ),
        spec_hash=strategy.spec_hash,
        base_spec_hash=strategy.base_spec_hash,
        parameter_hash=strategy.parameter_hash,
        effective_parameters=strategy.effective_parameters,
    )


def resolve_research_backtest_resume(
    *,
    audit: ResearchExecutionAudit,
    strategy: StrategyExecutionBinding | BaselineExecutorBinding,
    trading_days: tuple[str, ...],
    checkpoint_reader: StrategyRunCheckpointReaderProtocol,
) -> ResearchBacktestResumeState | None:
    """Load and verify only the exact parent run checkpoint named by the audit."""
    parent_run_id = audit.resume_from_run_id
    if parent_run_id is None:
        return None
    checkpoint = checkpoint_reader.get_latest_checkpoint(parent_run_id)
    if checkpoint is None:
        raise _error("research_resume_checkpoint_missing")
    expected_strategy_id, expected_strategy_version = _run_identity(strategy)
    if (
        type(checkpoint) is not StrategyRunCheckpointRecord
        or checkpoint.run_id != parent_run_id
        or checkpoint.run_id == audit.backtest_run_id
        or checkpoint.strategy_id != expected_strategy_id
        or checkpoint.strategy_version != expected_strategy_version
        or checkpoint.mode != "backtest"
        or not checkpoint.can_resume
    ):
        raise _error("research_resume_checkpoint_identity_drift")
    _require_resume_boundary(checkpoint, trading_days)
    account, settlement, runtime = _decode_resume_state(checkpoint, trading_days)
    if (
        checkpoint.nav != account.nav
        or not trading_days
        or runtime.rebalance_calendar_start != trading_days[0]
    ):
        raise _error("research_resume_checkpoint_state_drift")
    return ResearchBacktestResumeState(checkpoint, account, settlement, runtime)


def require_research_resume_runtime_state(
    resume: ResearchBacktestResumeState,
    *,
    account: Account,
    cash: CashBook,
    brokerage: BacktestBrokerage,
    order_book: OrderBook,
    order_journal: InMemoryOrderEventJournal,
) -> None:
    """Verify the constructed mutable graph exactly matches resume evidence."""
    account_state = vars(account)
    if (
        account_state.get("_cash") is not cash
        or account_state.get("_event_bus") is not None
        or BacktestAccountStateSnapshot.from_account_view(account.get_view())
        != resume.account
    ):
        raise _error("constructed_brokerage_account_drift")
    if brokerage.get_settlement_state_snapshot() != resume.settlement:
        raise _error("constructed_brokerage_state_drift")
    pending = BacktestRuntimeStateSnapshot.from_state(
        BacktestRuntimeStateCapture(pending_tickets=order_book.get_pending())
    ).pending_orders
    if pending != resume.runtime.pending_orders or order_journal.all_events():
        raise _error("constructed_order_book_state_drift")


def _run_identity(
    strategy: StrategyExecutionBinding | BaselineExecutorBinding,
) -> tuple[str, str]:
    if type(strategy) is StrategyExecutionBinding:
        return strategy.exact_strategy.strategy_id, str(strategy.exact_strategy.version)
    if type(strategy) is BaselineExecutorBinding:
        return strategy.baseline_ref, str(strategy.executor_contract_version)
    raise _error("invalid_strategy_execution_binding")


def _require_resume_boundary(
    checkpoint: StrategyRunCheckpointRecord,
    trading_days: tuple[str, ...],
) -> None:
    try:
        completed_index = trading_days.index(checkpoint.completed_trade_date)
        resume_index = trading_days.index(checkpoint.resume_from or "")
    except ValueError:
        raise _error("research_resume_checkpoint_boundary_drift") from None
    if (
        resume_index != completed_index + 1
        or checkpoint.completed_days != resume_index
        or checkpoint.total_days != len(trading_days)
        or type(checkpoint.order_count) is not int
        or checkpoint.order_count < 0
        or type(checkpoint.fill_count) is not int
        or checkpoint.fill_count < 0
    ):
        raise _error("research_resume_checkpoint_boundary_drift")


def _decode_resume_state(
    checkpoint: StrategyRunCheckpointRecord,
    trading_days: tuple[str, ...],
) -> tuple[
    BacktestAccountStateSnapshot,
    BacktestSettlementStateSnapshot,
    BacktestRuntimeStateSnapshot,
]:
    state_fields = (
        checkpoint.account_state_json,
        checkpoint.account_state_hash,
        checkpoint.settlement_state_json,
        checkpoint.settlement_state_hash,
        checkpoint.runtime_state_json,
        checkpoint.runtime_state_hash,
    )
    if any(type(value) is not str or not value for value in state_fields):
        raise _error("research_resume_checkpoint_state_incomplete")
    try:
        account = BacktestAccountStateSnapshot.from_json(checkpoint.account_state_json)
        settlement = BacktestSettlementStateSnapshot.from_json(
            checkpoint.settlement_state_json
        )
        runtime = BacktestRuntimeStateSnapshot.from_json(checkpoint.runtime_state_json)
    except ValueError:
        raise _error("research_resume_checkpoint_state_drift") from None
    if (
        checkpoint.account_state_hash != account.state_hash
        or checkpoint.settlement_state_hash != settlement.state_hash
        or checkpoint.runtime_state_hash != runtime.state_hash
        or not _settlement_matches_account(
            account,
            settlement,
            checkpoint.completed_trade_date,
        )
    ):
        raise _error("research_resume_checkpoint_state_drift")
    # Aggregate order counts cannot reconstruct planner IDs because the planner
    # consumes the same counter for plans and orders. V1 payloads also cannot
    # distinguish genuinely empty state from omitted state, so exact research
    # resume is deliberately fail-closed unless the complete V2 marker exists.
    if not runtime.is_exact_resume_state:
        raise _error("research_resume_checkpoint_state_incomplete")
    try:
        audit_state = ExecutionAuditStateSnapshot.from_canonical_json(
            runtime.audit_state_json or "",
        )
    except ValueError:
        raise _error("research_resume_checkpoint_state_drift") from None
    if (
        runtime.brokerage_fill_counter != checkpoint.fill_count
        or runtime.planner_id_counter < checkpoint.order_count
        or len(audit_state.fills) != checkpoint.fill_count
        or tuple(item[0] for item in audit_state.daily_snapshots)
        != trading_days[: checkpoint.completed_days]
        or audit_state.daily_snapshots[-1][1] != account
        or not _audit_runtime_ids_are_consistent(audit_state, runtime)
    ):
        raise _error("research_resume_checkpoint_state_drift")
    return account, settlement, runtime


def _settlement_matches_account(
    account: BacktestAccountStateSnapshot,
    settlement: BacktestSettlementStateSnapshot,
    completed_trade_date: str,
) -> bool:
    positions = {item.instrument_id: item for item in account.positions}
    if len(positions) != len(account.positions):
        return False
    frozen_totals: dict[InstrumentId, int] = {}
    queue_keys: set[tuple[InstrumentId, str]] = set()
    try:
        boundary = date.fromisoformat(completed_trade_date)
        for item in settlement.frozen_quantities:
            queue_key = (item.instrument_id, item.settle_date)
            if (
                item.quantity <= 0
                or item.instrument_id not in positions
                or queue_key in queue_keys
                or date.fromisoformat(item.settle_date) <= boundary
            ):
                return False
            queue_keys.add(queue_key)
            frozen_totals[item.instrument_id] = (
                frozen_totals.get(item.instrument_id, 0) + item.quantity
            )
    except ValueError:
        return False
    return all(
        item.quantity >= item.available_quantity >= 0
        and item.quantity - item.available_quantity
        == frozen_totals.get(item.instrument_id, 0)
        for item in account.positions
    )


def _audit_runtime_ids_are_consistent(
    audit: ExecutionAuditStateSnapshot,
    runtime: BacktestRuntimeStateSnapshot,
) -> bool:
    fill_ids = tuple(item.fill_id for item in audit.fills)
    if len(set(fill_ids)) != len(fill_ids) or not _ids_fit_counter(
        fill_ids,
        prefix="fill",
        counter=runtime.brokerage_fill_counter,
    ):
        return False
    pending_order_ids = tuple(item.client_order_id for item in runtime.pending_orders)
    audit_order_ids = tuple(item.order_id for item in audit.fills) + tuple(
        order_id
        for trade in audit.closed_trades
        for order_id in trade.entry_order_ids + trade.exit_order_ids
    )
    audit_order_ids += tuple(item.order_id for item in audit.pre_trade_log)
    trade_state = runtime.trade_builder_state
    if trade_state is None:
        return False
    if trade_state.method.value == "fifo":
        open_order_ids = tuple(
            item.entry_order_id for item in trade_state.fifo_open_entries
        )
    else:
        open_order_ids = tuple(
            order_id
            for item in trade_state.flat_to_flat_accumulators
            for order_id in item.entry_order_ids + item.exit_order_ids
        )
    if len(set(pending_order_ids)) != len(pending_order_ids) or not _ids_fit_counter(
        pending_order_ids + audit_order_ids + open_order_ids,
        prefix="plan-order",
        counter=runtime.planner_id_counter,
    ):
        return False
    closed_trade_ids = tuple(item.trade_id for item in audit.closed_trades)
    open_trade_ids = tuple(item.trade_id for item in trade_state.fifo_open_entries)
    visible_trade_ids = closed_trade_ids + open_trade_ids
    return len(set(visible_trade_ids)) == len(visible_trade_ids) and _ids_fit_counter(
        visible_trade_ids,
        prefix="trade",
        counter=trade_state.counter,
    )


def _ids_fit_counter(
    values: tuple[str, ...],
    *,
    prefix: str,
    counter: int,
) -> bool:
    for value in values:
        actual_prefix, separator, suffix = value.rpartition("-")
        if (
            actual_prefix != prefix
            or not separator
            or not suffix.isdigit()
            or not 1 <= int(suffix) <= counter
        ):
            return False
    return True
