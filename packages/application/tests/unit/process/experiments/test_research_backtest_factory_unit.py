"""Closed audit-bound construction tests for the R3 research backtest path."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from inspect import signature
from io import BytesIO

import orjson
import polars as pl
import pytest
from ditto_application.builders.research_backtest_factory import (
    FrozenAuditResearchBacktestFactory,
)
from ditto_application.builders.research_factor_registry import (
    ResearchFactorBinding,
    ResearchFactorRegistry,
    analysis_execution_hash,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportEvidence,
    backtest_report_content_hash,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ExactBenchmarkBinding,
    ExecutionEvidenceSource,
    PolicyModelEvidenceBinding,
    ResearchExecutionAudit,
    ResearchExecutionSemantics,
    ResearchFactorExecutionBinding,
    ResearchFillMode,
    ResearchSnapshotBinding,
    StrategyExecutionBinding,
    VersionedExecutionComponent,
    canonical_payload,
    research_data_feed_manifest_hash,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    ExactUniverseIdentity,
    default_stock_execution_policy,
)
from ditto_application.processes.experiments.research_data_feed import (
    FrozenResearchDataFrames,
    ResearchDataFeed,
    ResearchFrameKind,
    VerifiedResearchFrame,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_application.processes.experiments.worker import (
    ExistingBacktestResearchFoldRunner,
    ResearchBacktestBuildAttestation,
    ResearchCandidateExecutionError,
    ResearchFoldRunState,
    VerifiedResearchBacktestBuild,
)
from ditto_backtest.audit.state import ExecutionAuditStateSnapshot
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestFrozenQuantitySnapshot,
    BacktestPendingOrderSnapshot,
    BacktestPositionSnapshot,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
)
from ditto_backtest.simulation import (
    AShareFillModel,
    AShareSettlementModel,
    BrokerageModel,
)
from ditto_backtest.statistics import BacktestReport
from ditto_execution.orders.book import OrderBook
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_execution.trade_builder import (
    TradeBuilderStateSnapshot,
    TradeMatchingMethod,
)
from ditto_features.expression.contracts import (
    Analysis,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import InstrumentRules, RulesGetter
from ditto_portfolio.accounting import Account, CashBook, FillEvent
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
    canonical_parameter_hash,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import (
    ExecutionSpec,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.runs.models import StrategyRunCheckpointRecord

_NOW = datetime(2026, 7, 20, 9, tzinfo=UTC)
_DATES = ("2026-01-02", "2026-01-05")
_MEMBER_ID = 2_000_001
_BENCHMARK_ID = 3_000_001
_SOURCE = "research-source-v1"


class _FloatSubclass(float):
    pass


class _IntSubclass(int):
    pass


class _StrSubclass(str):
    pass


class _TupleSubclass(tuple[str, ...]):
    pass


def _never_stop() -> bool:
    return False


def _sha(character: str) -> str:
    return character * 64


def _parquet_bytes(frame: pl.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def _schema_hash(frame: pl.DataFrame) -> str:
    fields = tuple((name, str(dtype)) for name, dtype in frame.schema.items())
    return hashlib.sha256(orjson.dumps(fields)).hexdigest()


def _verified(kind: ResearchFrameKind, frame: pl.DataFrame) -> VerifiedResearchFrame:
    artifact_bytes = _parquet_bytes(frame)
    return VerifiedResearchFrame(
        input_evidence=ContentAddressedResearchInput(
            input_id=f"{kind.value}.parquet",
            artifact_kind=kind.value,
            content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
            schema_hash=_schema_hash(frame),
        ),
        source_snapshot_ids=(_SOURCE,),
        artifact_bytes=artifact_bytes,
    )


def _bars() -> pl.DataFrame:
    rows = tuple(
        (trade_date, instrument_id, close)
        for trade_date, member_close, benchmark_close in (
            (_DATES[0], 10.0, 4_000.0),
            (_DATES[1], 10.5, 4_050.0),
        )
        for instrument_id, close in (
            (_MEMBER_ID, member_close),
            (_BENCHMARK_ID, benchmark_close),
        )
    )
    return pl.DataFrame(
        {
            "trade_date": [item[0] for item in rows],
            "instrument_id": [item[1] for item in rows],
            "open": [item[2] for item in rows],
            "high": [item[2] * 1.01 for item in rows],
            "low": [item[2] * 0.99 for item in rows],
            "close": [item[2] for item in rows],
            "prev_close": [item[2] for item in rows],
            "volume": [1_000_000.0] * len(rows),
            "amount": [item[2] * 1_000_000.0 for item in rows],
            "is_suspended": [False] * len(rows),
            "limit_up": [item[2] * 1.1 for item in rows],
            "limit_down": [item[2] * 0.9 for item in rows],
            "avg_volume_20d": [1_000_000.0] * len(rows),
            "source_snapshot_id": [_SOURCE] * len(rows),
        }
    )


def _frames() -> FrozenResearchDataFrames:
    return FrozenResearchDataFrames(
        bars=_verified(ResearchFrameKind.BARS, _bars()),
        calendar=_verified(
            ResearchFrameKind.CALENDAR,
            pl.DataFrame(
                {
                    "trade_date": list(_DATES),
                    "is_open": [True, True],
                    "source_snapshot_id": [_SOURCE, _SOURCE],
                }
            ),
        ),
        membership=_verified(
            ResearchFrameKind.MEMBERSHIP,
            pl.DataFrame(
                {
                    "trade_date": list(_DATES),
                    "instrument_id": [_MEMBER_ID, _MEMBER_ID],
                    "is_member": [True, True],
                    "known_at": ["2026-01-01", "2026-01-04"],
                    "source_snapshot_id": [_SOURCE, _SOURCE],
                }
            ),
        ),
    )


_RULE_SCHEMA: dict[str, pl.DataType] = {
    "instrument_code": pl.String,
    "instrument_id": pl.Int64,
    "asset_class": pl.String,
    "exchange": pl.String,
    "currency": pl.String,
    "tick_size": pl.Float64,
    "lot_size": pl.Int64,
    "multiplier": pl.Float64,
    "board_segment": pl.String,
    "lifecycle_state": pl.String,
    "ipo_date": pl.Date,
    "delisting_date": pl.Date,
    "as_of_date": pl.Date,
    "known_at": pl.Date,
    "settlement_cycle": pl.Int64,
    "fund_settlement_cycle": pl.Int64,
    "price_limit_pct": pl.Float64,
    "order_types_supported": pl.List(pl.String),
    "call_auction_sessions": pl.List(pl.String),
    "commission_rate": pl.Float64,
    "min_commission": pl.Float64,
    "stamp_duty_rate": pl.Float64,
    "transfer_fee_rate": pl.Float64,
    "source_snapshot_id": pl.String,
}


def _rules(
    *,
    member_lifecycle_state: str = "normal",
    member_delisting_date: date | None = None,
    benchmark_as_of_date: date = date(2026, 1, 1),
    benchmark_known_at_date: date = date(2025, 12, 31),
) -> VerifiedInstrumentRulesArtifact:
    frame = pl.DataFrame(
        {
            "instrument_code": ["000001.SZ", "000001.SZ", "000300.SH"],
            "instrument_id": [_MEMBER_ID, _MEMBER_ID, _BENCHMARK_ID],
            "asset_class": ["stock", "stock", "stock"],
            "exchange": ["XSHE", "XSHE", "XSHG"],
            "currency": ["CNY", "CNY", "CNY"],
            "tick_size": [0.01, 0.01, 0.01],
            "lot_size": [100, 100, 100],
            "multiplier": [1.0, 1.0, 1.0],
            "board_segment": ["main", "main", "index"],
            "lifecycle_state": [
                member_lifecycle_state,
                member_lifecycle_state,
                "normal",
            ],
            "ipo_date": [
                date(1991, 4, 3),
                date(1991, 4, 3),
                date(2005, 4, 8),
            ],
            "delisting_date": [
                member_delisting_date,
                member_delisting_date,
                None,
            ],
            "as_of_date": [
                date(2026, 1, 1),
                date(2026, 1, 2),
                benchmark_as_of_date,
            ],
            "known_at": [
                date(2025, 12, 31),
                date(2026, 1, 2),
                benchmark_known_at_date,
            ],
            "settlement_cycle": [1, 1, 1],
            "fund_settlement_cycle": [0, 0, 0],
            "price_limit_pct": [0.1, 0.2, 0.1],
            "order_types_supported": [
                ["market", "limit"],
                ["market", "limit"],
                ["market", "limit"],
            ],
            "call_auction_sessions": [
                ["open", "close"],
                ["open", "close"],
                ["open", "close"],
            ],
            "commission_rate": [0.0003, 0.0009, 0.0003],
            "min_commission": [5.0, 9.0, 5.0],
            "stamp_duty_rate": [0.001, 0.001, 0.001],
            "transfer_fee_rate": [0.00001, 0.00001, 0.00001],
            "source_snapshot_id": [_SOURCE, _SOURCE, _SOURCE],
        },
        schema=_RULE_SCHEMA,
    )
    artifact_bytes = _parquet_bytes(frame)
    return VerifiedInstrumentRulesArtifact(
        input_evidence=ContentAddressedResearchInput(
            input_id="instrument_rules.parquet",
            artifact_kind="instrument_rules",
            content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
            schema_hash=_schema_hash(frame),
        ),
        artifact_bytes=artifact_bytes,
    )


def _snapshot(
    frames: FrozenResearchDataFrames,
    rules: VerifiedInstrumentRulesArtifact,
) -> ResearchSnapshotBinding:
    return ResearchSnapshotBinding(
        exact_snapshot=ExactResearchSnapshot("snapshot-v1", _sha("a")),
        dataset_id="a-share-daily-v1",
        source_snapshot_ids=(_SOURCE,),
        known_at_policy="sample_time",
        builder_version="research-fixture-v1",
        inputs=(
            *(item.input_evidence for _, item in frames.items()),
            rules.input_evidence,
        ),
    )


def _benchmark(
    snapshot: ResearchSnapshotBinding,
    rules: VerifiedInstrumentRulesArtifact,
) -> ExactBenchmarkBinding:
    bars = next(item for item in snapshot.inputs if item.artifact_kind == "bars")
    identity = str(
        canonical_payload(
            {
                "instrument_code": "000300.SH",
                "instrument_id": _BENCHMARK_ID,
                "mapping_input": rules.input_evidence.as_payload(),
            }
        ).content_hash
    )
    return ExactBenchmarkBinding(
        instrument_id=_BENCHMARK_ID,
        instrument_identity_hash=identity,
        mapping_input=rules.input_evidence,
        bars_input=bars,
    )


def _backtest(
    snapshot: ResearchSnapshotBinding,
    rules: VerifiedInstrumentRulesArtifact,
) -> BacktestExecutionConfigBinding:
    policy = default_stock_execution_policy()
    frozen = ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=100_000_000,
        currency="CNY",
        engine=VersionedExecutionComponent("ditto_backtest.engine_loop", 1),
        engine_version="0.1.0",
        rebalance_policy=VersionedExecutionComponent(
            "ditto_backtest.rebalance.daily",
            1,
        ),
        rebalance_frequency="daily",
        participation_rate_ppm=50_000,
        fill_mode=ResearchFillMode.PARTIAL,
        fill_model=VersionedExecutionComponent(
            "ditto_backtest.a_share_fill.partial",
            1,
        ),
        brokerage_model=VersionedExecutionComponent(
            "ditto_backtest.backtest_brokerage",
            1,
        ),
        execution_planner=VersionedExecutionComponent(
            "ditto_execution.simple_execution_planner.market",
            1,
        ),
        slippage_basis_points=1,
        benchmark=_benchmark(snapshot, rules),
        policy_hash=policy.canonical_hash,
        policy_model_evidence=(
            PolicyModelEvidenceBinding(
                "fees",
                VersionedExecutionComponent(policy.fees.model_key, 1),
                frozen,
                (rules.input_evidence,),
            ),
            PolicyModelEvidenceBinding(
                "rules",
                VersionedExecutionComponent(policy.rules.contract_key, 1),
                frozen,
                (rules.input_evidence,),
            ),
            PolicyModelEvidenceBinding(
                "settlement",
                VersionedExecutionComponent(policy.settlement.model_key, 1),
                frozen,
                (rules.input_evidence,),
            ),
            PolicyModelEvidenceBinding(
                "slippage",
                VersionedExecutionComponent(policy.slippage.model_key, 1),
                ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY,
                (),
            ),
        ),
        pre_trade_checks=(
            VersionedExecutionComponent("ditto_risk.lot_size_check", 1),
            VersionedExecutionComponent("ditto_risk.buying_power_check", 1),
        ),
        post_trade_guard=None,
        data_feed_manifest_hash=research_data_feed_manifest_hash(snapshot),
    )


def _strategy_record() -> StrategySpecRecord:
    spec = StrategySpec(
        strategy_id="stock-alpha",
        name="stock alpha",
        template="stock_selection",
        universe="all_a_shares",
        asset_class="equity",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 20}),
        params={"top_k": 20, "allocation_method": "equal_weight"},
        required_datasets=("stock_daily",),
        benchmark="000300.SH",
        execution=ExecutionSpec(frequency="D"),
    )
    return StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=3,
    )


def _binding(runtime: ResearchStrategyRuntime) -> StrategyExecutionBinding:
    return StrategyExecutionBinding(
        exact_strategy=ExactStrategyIdentity(
            runtime.strategy_id,
            runtime.strategy_version,
            runtime.base_spec_hash,
        ),
        resolved_spec_hash=runtime.resolved_spec_hash,
        parameter_hash=runtime.parameter_hash,
        node_registry_manifest_hash=runtime.node_registry_manifest_hash,
        pipeline_execution_hash=runtime.pipeline_execution_hash,
        factor_registry_manifest_hash=runtime.factor_registry_manifest_hash,
        compiled_factor_set_hash=compiled_expressions_execution_hash(
            runtime.compiled_expressions
        ),
        factor_bindings=(),
        candidate_parameters=(),
    )


def _compile_identity() -> CompileIdentity:
    return CompileIdentity(
        compile_input_hash=_sha("1"),
        operator_fingerprint=_sha("2"),
        compiler_fingerprint=_sha("3"),
        cache_key=_sha("4"),
        engine_codegen_version="polars-codegen-v1",
        analysis_version="factor-analysis-v1",
        polars_version="1.0.0",
        expr_serialization_format="polars-expr-v1",
        operator_versions=(("rank", "1"),),
        global_compile_flags=("grain=1d",),
    )


def _audit(
    binding: StrategyExecutionBinding,
    snapshot: ResearchSnapshotBinding,
    backtest: BacktestExecutionConfigBinding,
) -> ResearchExecutionAudit:
    semantics = ResearchExecutionSemantics(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        fold_id="fold-1",
        fold_role="walk_forward",
        is_baseline=False,
        plan_hash=_sha("1"),
        launch_spec_hash=_sha("2"),
        fold_spec_hash=_sha("3"),
        strategy=binding,
        backtest=backtest,
        snapshot=snapshot,
        membership_hash=_sha("4"),
        membership_projection_hash=_sha("5"),
        train_start=date(2025, 1, 2),
        train_end=date(2025, 12, 31),
        test_start=date.fromisoformat(_DATES[0]),
        test_end=date.fromisoformat(_DATES[-1]),
        purge_sessions=5,
        embargo_sessions=2,
        seed=42,
        knowledge_lag_days=1,
        execution_delay_sessions=0,
        baseline_registry_manifest_hash=_sha("6"),
        baseline_plan=None,
        policy=default_stock_execution_policy(),
        environment=CodeEnvironmentLock("commit-abc", _sha("7")),
    )
    return ResearchExecutionAudit.create(
        semantics=semantics,
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="backtest-run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )


class _Reader:
    def __init__(
        self, record: StrategySpecRecord, version_state: str = "draft"
    ) -> None:
        self.record = record
        self.version_state = version_state
        self.calls: list[tuple[str, int]] = []

    def get_spec(self, strategy_id: str, version: int) -> StrategySpecRecord:
        self.calls.append((strategy_id, version))
        return self.record

    def get_version_state(self, strategy_id: str, version: int) -> str | None:
        del strategy_id, version
        return self.version_state


class _Builder:
    def __init__(self, runtime: ResearchStrategyRuntime) -> None:
        self.runtime = runtime
        self.calls = 0

    def build(self, **_kwargs: object) -> ResearchStrategyRuntime:
        self.calls += 1
        return self.runtime


class _Loader:
    def __init__(
        self,
        frames: FrozenResearchDataFrames,
        rules: VerifiedInstrumentRulesArtifact,
    ) -> None:
        self.frames = {item.input_evidence: item for _, item in frames.items()}
        self.rules = rules
        self.frame_calls: list[ContentAddressedResearchInput] = []
        self.rules_calls: list[ContentAddressedResearchInput] = []

    def load_frame(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedResearchFrame:
        self.frame_calls.append(evidence)
        return self.frames[evidence]

    def load_instrument_rules(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedInstrumentRulesArtifact:
        self.rules_calls.append(evidence)
        return self.rules


class _CheckpointStore:
    def __init__(
        self,
        checkpoints: tuple[StrategyRunCheckpointRecord, ...] = (),
    ) -> None:
        self._checkpoints = {item.run_id: item for item in checkpoints}
        self.read_calls: list[str] = []
        self.saved: list[StrategyRunCheckpointRecord] = []

    def get_latest_checkpoint(
        self,
        run_id: str,
    ) -> StrategyRunCheckpointRecord | None:
        self.read_calls.append(run_id)
        return self._checkpoints.get(run_id)

    def list_checkpoints_by_strategy(
        self,
        strategy_id: str,
    ) -> list[StrategyRunCheckpointRecord]:
        return [
            item
            for item in self._checkpoints.values()
            if item.strategy_id == strategy_id
        ]

    def save_checkpoint(self, record: StrategyRunCheckpointRecord) -> None:
        self.saved.append(record)
        self._checkpoints[record.run_id] = record


def _fixture(
    *,
    rules: VerifiedInstrumentRulesArtifact | None = None,
    checkpoint_store: _CheckpointStore | None = None,
) -> tuple[
    FrozenAuditResearchBacktestFactory,
    ResearchExecutionAudit,
    _Reader,
    _Builder,
    _Loader,
]:
    frames = _frames()
    rules = _rules() if rules is None else rules
    snapshot = _snapshot(frames, rules)
    registry = ResearchFactorRegistry()
    record = _strategy_record()
    runtime = ResearchRuntimeBuilder(factor_registry=registry).build(
        record=record,
        candidate_parameters=(),
        snapshot_identity=ResearchSnapshotIdentity(
            snapshot.exact_snapshot.snapshot_id,
            snapshot.exact_snapshot.manifest_hash,
        ),
        version_status="draft",
    )
    binding = _binding(runtime)
    reader = _Reader(record)
    builder = _Builder(runtime)
    loader = _Loader(frames, rules)
    checkpoints = checkpoint_store or _CheckpointStore()
    audit = _audit(binding, snapshot, _backtest(snapshot, rules))
    return (
        FrozenAuditResearchBacktestFactory(
            strategy_reader=reader,
            runtime_builder=builder,
            artifact_loader=loader,
            environment=audit.semantics.environment,
            checkpoint_reader=checkpoints,
            checkpoint_writer=checkpoints,
        ),
        audit,
        reader,
        builder,
        loader,
    )


def _resumable_checkpoint(audit: ResearchExecutionAudit) -> StrategyRunCheckpointRecord:
    account = BacktestAccountStateSnapshot(
        cash_available=900_000.0,
        cash_settled=900_000.0,
        cash_frozen=0.0,
        total_value=1_000_000.0,
        nav=1_000_000.0,
        exposure=100_000.0,
        positions=(
            BacktestPositionSnapshot(
                instrument_id=InstrumentId(_MEMBER_ID),
                quantity=10_000,
                available_quantity=9_900,
                average_cost=10.0,
                market_value=100_000.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                total_fees=0.0,
            ),
        ),
    )
    settlement = BacktestSettlementStateSnapshot(
        frozen_quantities=(
            BacktestFrozenQuantitySnapshot(
                instrument_id=InstrumentId(_MEMBER_ID),
                settle_date=_DATES[1],
                quantity=100,
            ),
        ),
    )
    runtime = BacktestRuntimeStateSnapshot(
        pending_orders=(
            BacktestPendingOrderSnapshot(
                client_order_id="plan-order-9",
                instrument_id=InstrumentId(_MEMBER_ID),
                order_type="market",
                direction="buy",
                quantity=100,
                price=None,
                stop_price=None,
                trade_date=_DATES[0],
                status="submitted",
                filled_quantity=0,
                leaves_quantity=100,
                filled_price=None,
                average_fill_price=None,
            ),
        ),
        planner_id_counter=9,
        brokerage_fill_counter=1,
        trade_builder_state=TradeBuilderStateSnapshot(
            method=TradeMatchingMethod.FIFO,
            counter=0,
        ),
        rebalance_calendar_start=_DATES[0],
        audit_state_json=ExecutionAuditStateSnapshot(
            fills=(
                FillEvent(
                    fill_id="fill-1",
                    order_id="plan-order-9",
                    instrument_id=InstrumentId(_MEMBER_ID),
                    direction=OrderSide.BUY,
                    filled_quantity=100,
                    fill_price=10.0,
                    fee=0.0,
                    slippage=0.0,
                    event_time=_NOW,
                    cumulative_quantity=100,
                    leaves_quantity=0,
                ),
            ),
            daily_snapshots=((_DATES[0], account),),
        ).to_json(),
        runtime_state_version=2,
    )
    strategy = audit.semantics.strategy
    assert type(strategy) is StrategyExecutionBinding
    return StrategyRunCheckpointRecord(
        run_id=audit.backtest_run_id,
        strategy_id=strategy.exact_strategy.strategy_id,
        strategy_version=str(strategy.exact_strategy.version),
        mode="backtest",
        completed_trade_date=_DATES[0],
        resume_from=_DATES[1],
        completed_days=1,
        total_days=len(_DATES),
        nav=account.nav,
        order_count=1,
        fill_count=1,
        account_state_json=account.to_json(),
        account_state_hash=account.state_hash,
        settlement_state_json=settlement.to_json(),
        settlement_state_hash=settlement.state_hash,
        runtime_state_json=runtime.to_json(),
        runtime_state_hash=runtime.state_hash,
        updated_at=_NOW.isoformat(),
    )


def _resume_audit(audit: ResearchExecutionAudit) -> ResearchExecutionAudit:
    return ResearchExecutionAudit.create(
        semantics=audit.semantics,
        attempt_id="attempt-2",
        attempt_ordinal=2,
        backtest_run_id="backtest-run-2",
        parent_attempt_id=audit.attempt_id,
        resume_from_run_id=audit.backtest_run_id,
        created_at=_NOW,
    )


def _assert_post_build_mutation_rejected(
    mutate: Callable[[VerifiedResearchBacktestBuild], None],
    *,
    reason: str,
) -> None:
    concrete, audit, *_ = _fixture()

    class _MutationFactory:
        def build(
            self,
            audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            build = concrete.build(
                audit,
                external_should_stop=external_should_stop,
            )
            mutate(build)
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_MutationFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == reason


def test_factory_build_surface_accepts_only_the_frozen_audit() -> None:
    assert tuple(signature(FrozenAuditResearchBacktestFactory.build).parameters) == (
        "self",
        "audit",
        "external_should_stop",
    )


def test_factory_builds_real_service_and_attests_constructed_objects() -> None:
    factory, audit, reader, builder, loader = _fixture()
    stop_calls = 0

    def _stop() -> bool:
        nonlocal stop_calls
        stop_calls += 1
        return False

    result = factory.build(audit, external_should_stop=_stop)

    assert type(result.service) is BacktestService
    assert result.attestation == ResearchBacktestBuildAttestation.from_audit(audit)
    assert result.service._options.external_should_stop is _stop
    assert stop_calls == 0
    assert result.service._config.run_id == audit.backtest_run_id
    assert result.service._config.random_seed == audit.semantics.seed
    assert (
        result.service._data_feed.evidence_manifest.canonical_hash
        == audit.semantics.backtest.data_feed_manifest_hash
    )
    assert reader.calls == [("stock-alpha", 3)]
    assert builder.calls == 1
    assert {item.artifact_kind for item in loader.frame_calls} == {
        "bars",
        "calendar",
        "membership",
    }
    assert loader.rules_calls == [
        next(
            item
            for item in audit.semantics.snapshot.inputs
            if item.artifact_kind == "instrument_rules"
        )
    ]


def test_factory_publishes_only_resumable_strategy_checkpoints() -> None:
    checkpoints = _CheckpointStore()
    factory, audit, *_ = _fixture(checkpoint_store=checkpoints)

    factory.build(audit, external_should_stop=_never_stop).service.run()

    assert [item.completed_trade_date for item in checkpoints.saved] == list(
        _DATES[:-1]
    )
    assert [item.run_id for item in checkpoints.saved] == [
        audit.backtest_run_id,
    ]
    assert checkpoints.saved[-1].resume_from == _DATES[-1]


def test_factory_resumes_exact_parent_checkpoint_with_full_runtime_state() -> None:
    _, parent_audit, *_ = _fixture()
    checkpoint = _resumable_checkpoint(parent_audit)
    checkpoints = _CheckpointStore((checkpoint,))
    factory, parent_audit, *_ = _fixture(checkpoint_store=checkpoints)
    audit = _resume_audit(parent_audit)

    result = factory.build(audit, external_should_stop=_never_stop)

    config = result.service._config
    assert checkpoints.read_calls == [parent_audit.backtest_run_id]
    assert config.start_date == checkpoint.resume_from
    assert config.end_date == parent_audit.semantics.test_end.isoformat()
    assert config.parent_run_id == parent_audit.backtest_run_id
    assert config.resume_from_run_id == parent_audit.backtest_run_id
    assert config.resume_checkpoint_trade_date == checkpoint.completed_trade_date
    assert config.resume_checkpoint_completed_days == checkpoint.completed_days
    assert config.resume_checkpoint_total_days == checkpoint.total_days
    assert config.resume_account_state_json == checkpoint.account_state_json
    assert config.resume_settlement_state_json == checkpoint.settlement_state_json
    assert config.resume_runtime_state_json == checkpoint.runtime_state_json
    assert result.service._options.checkpoint_writer is checkpoints
    expected_runtime = BacktestRuntimeStateSnapshot.from_json(
        checkpoint.runtime_state_json
    )
    assert result.service._options.restore_runtime_state == expected_runtime
    # Exact V2 runtime evidence carries the actual monotonic counters; aggregate
    # order counts cannot reconstruct IDs consumed by both plans and orders.
    assert expected_runtime.resolved_planner_id_counter == 9
    assert expected_runtime.brokerage_fill_counter == 1
    assert result.graph.components.account.get_view().nav == checkpoint.nav
    assert (
        result.graph.components.brokerage.get_settlement_state_snapshot()
        == BacktestSettlementStateSnapshot.from_json(checkpoint.settlement_state_json)
    )
    assert tuple(
        item.order.client_id.value
        for item in result.graph.components.order_book.get_pending()
    ) == ("plan-order-9",)
    assert result.attestation == ResearchBacktestBuildAttestation.from_audit(audit)
    assert result.attestation.reproduction_fingerprint == (
        parent_audit.reproduction_fingerprint
    )


def test_factory_rejects_v1_runtime_without_exact_monotonic_state() -> None:
    """Aggregate order counts cannot reconstruct planner IDs consumed by plans."""
    _, parent_audit, *_ = _fixture()
    legacy_runtime = BacktestRuntimeStateSnapshot.from_json(
        '{"delayed_signals":[],"pending_orders":[]}',
    )
    checkpoint = replace(
        _resumable_checkpoint(parent_audit),
        order_count=2,
        runtime_state_json=legacy_runtime.to_json(),
        runtime_state_hash=legacy_runtime.state_hash,
    )
    checkpoints = _CheckpointStore((checkpoint,))
    factory, parent_audit, *_ = _fixture(checkpoint_store=checkpoints)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(
            _resume_audit(parent_audit),
            external_should_stop=_never_stop,
        )

    assert (
        exc_info.value.details["reason"]
        == "research_resume_checkpoint_state_incomplete"
    )


@pytest.mark.parametrize(
    "drift",
    [
        "account",
        "audit-order-id",
        "calendar-anchor",
        "daily-date",
        "fill-id",
        "planner-counter",
    ],
)
def test_factory_rejects_cross_field_runtime_audit_drift(drift: str) -> None:
    """Individually valid hashes cannot hide a broken checkpoint boundary."""
    _, parent_audit, *_ = _fixture()
    checkpoint = _resumable_checkpoint(parent_audit)
    runtime = BacktestRuntimeStateSnapshot.from_json(checkpoint.runtime_state_json)
    audit_state = ExecutionAuditStateSnapshot.from_json(runtime.audit_state_json or "")
    if drift == "account":
        trade_date, account = audit_state.daily_snapshots[-1]
        audit_state = replace(
            audit_state,
            daily_snapshots=(
                (
                    trade_date,
                    replace(account, cash_available=account.cash_available - 1.0),
                ),
            ),
        )
    elif drift == "audit-order-id":
        audit_state = replace(
            audit_state,
            fills=(replace(audit_state.fills[0], order_id="plan-order-10"),),
        )
    elif drift == "daily-date":
        _, account = audit_state.daily_snapshots[-1]
        audit_state = replace(
            audit_state,
            daily_snapshots=((_DATES[1], account),),
        )
    elif drift == "fill-id":
        audit_state = replace(
            audit_state,
            fills=(replace(audit_state.fills[0], fill_id="fill-2"),),
        )
    elif drift == "planner-counter":
        audit_state = replace(audit_state, fills=())
    runtime = replace(
        runtime,
        audit_state_json=audit_state.to_json(),
        pending_orders=() if drift == "planner-counter" else runtime.pending_orders,
        planner_id_counter=0
        if drift == "planner-counter"
        else runtime.planner_id_counter,
        brokerage_fill_counter=(
            0 if drift == "planner-counter" else runtime.brokerage_fill_counter
        ),
        rebalance_calendar_start=(
            _DATES[1]
            if drift == "calendar-anchor"
            else runtime.rebalance_calendar_start
        ),
    )
    checkpoint = replace(
        checkpoint,
        fill_count=0 if drift == "planner-counter" else checkpoint.fill_count,
        runtime_state_json=runtime.to_json(),
        runtime_state_hash=runtime.state_hash,
    )
    checkpoints = _CheckpointStore((checkpoint,))
    factory, parent_audit, *_ = _fixture(checkpoint_store=checkpoints)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(
            _resume_audit(parent_audit),
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == "research_resume_checkpoint_state_drift"


def test_factory_rejects_cross_field_settlement_account_drift() -> None:
    """Individually hashed settlement state must match unavailable positions."""
    _, parent_audit, *_ = _fixture()
    checkpoint = _resumable_checkpoint(parent_audit)
    settlement = BacktestSettlementStateSnapshot(
        frozen_quantities=(
            BacktestFrozenQuantitySnapshot(
                instrument_id=InstrumentId(_MEMBER_ID),
                settle_date=_DATES[1],
                quantity=99,
            ),
        ),
    )
    checkpoint = replace(
        checkpoint,
        settlement_state_json=settlement.to_json(),
        settlement_state_hash=settlement.state_hash,
    )
    checkpoints = _CheckpointStore((checkpoint,))
    factory, parent_audit, *_ = _fixture(checkpoint_store=checkpoints)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(
            _resume_audit(parent_audit),
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == "research_resume_checkpoint_state_drift"


@pytest.mark.parametrize(
    ("checkpoint", "expected_reason"),
    [
        pytest.param(None, "research_resume_checkpoint_missing", id="missing"),
        pytest.param(
            "wrong-parent",
            "research_resume_checkpoint_identity_drift",
            id="wrong-parent",
        ),
        pytest.param(
            "incomplete-state",
            "research_resume_checkpoint_state_incomplete",
            id="incomplete-state",
        ),
    ],
)
def test_factory_rejects_non_exact_parent_checkpoint(
    checkpoint: str | None,
    expected_reason: str,
) -> None:
    _, parent_audit, *_ = _fixture()
    resolved: StrategyRunCheckpointRecord | None
    if checkpoint is None:
        resolved = None
    elif checkpoint == "wrong-parent":
        resolved = replace(_resumable_checkpoint(parent_audit), run_id="other-run")
    else:
        resolved = replace(
            _resumable_checkpoint(parent_audit),
            runtime_state_json="",
            runtime_state_hash="",
        )
    checkpoints = _CheckpointStore(
        () if resolved is None else (resolved,),
    )
    if resolved is not None and resolved.run_id != parent_audit.backtest_run_id:
        checkpoints._checkpoints[parent_audit.backtest_run_id] = resolved
    factory, parent_audit, *_ = _fixture(checkpoint_store=checkpoints)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(
            _resume_audit(parent_audit),
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == expected_reason


def test_existing_runner_returns_exact_report_evidence_from_concrete_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    reports: list[BacktestReport] = []
    original_run = BacktestService.run

    def capture_report(service: BacktestService) -> BacktestReport:
        report = original_run(service)
        reports.append(report)
        return report

    monkeypatch.setattr(BacktestService, "run", capture_report)

    outcome = ExistingBacktestResearchFoldRunner(factory).run(
        audit,
        external_should_stop=_never_stop,
    )

    assert outcome.state is ResearchFoldRunState.COMPLETED
    assert type(outcome.report_evidence) is BacktestReportEvidence
    assert outcome.report_evidence == BacktestReportEvidence.from_report(reports[0])
    assert outcome.report_evidence.content_hash == backtest_report_content_hash(
        reports[0]
    )


def test_existing_runner_maps_real_strategy_failure_to_candidate_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The concrete numerical path must make candidate-local isolation reachable."""
    factory, audit, *_ = _fixture()
    strategy_error = StrategySpecError("candidate pipeline rejected its input")

    def _fail_candidate(_service: BacktestService) -> object:
        raise strategy_error

    monkeypatch.setattr(BacktestService, "run", _fail_candidate)

    with pytest.raises(ResearchCandidateExecutionError) as exc_info:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.__cause__ is strategy_error


def test_existing_runner_keeps_unexpected_execution_failure_system_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected implementation failures must still reach worker fail-fast mapping."""
    factory, audit, *_ = _fixture()
    system_error = RuntimeError("engine implementation failed")

    def _fail_system(_service: BacktestService) -> object:
        raise system_error

    monkeypatch.setattr(BacktestService, "run", _fail_system)

    with pytest.raises(RuntimeError) as exc_info:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value is system_error


def test_existing_runner_propagates_cooperative_stop_into_real_service() -> None:
    factory, audit, *_ = _fixture()
    stop_checks = 0

    def _stop_during_engine() -> bool:
        nonlocal stop_checks
        stop_checks += 1
        # Runner checks twice before numerical execution.  The third check is
        # BacktestService/EngineLoop's first cooperative cancellation poll.
        return stop_checks >= 3

    outcome = ExistingBacktestResearchFoldRunner(factory).run(
        audit,
        external_should_stop=_stop_during_engine,
    )

    assert outcome.state is ResearchFoldRunState.STOPPED
    assert outcome.report_evidence is None
    assert stop_checks == 3


def test_existing_runner_rejects_factory_that_substitutes_stop_callback() -> None:
    concrete, audit, *_ = _fixture()

    class _WrongCallbackFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            del external_should_stop
            return concrete.build(
                requested_audit,
                external_should_stop=_never_stop,
            )

    stop_checks = 0

    def _leased_stop() -> bool:
        nonlocal stop_checks
        stop_checks += 1
        return stop_checks >= 3

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_WrongCallbackFactory()).run(
            audit,
            external_should_stop=_leased_stop,
        )

    assert exc_info.value.details["reason"] == "external_stop_callback_drift"
    assert stop_checks == 2


def test_existing_runner_rejects_audit_graph_substitution() -> None:
    concrete, audit_a, *_ = _fixture()
    semantics_b = replace(audit_a.semantics, seed=audit_a.semantics.seed + 1)
    audit_b = ResearchExecutionAudit.create(
        semantics=semantics_b,
        attempt_id="attempt-b",
        attempt_ordinal=1,
        backtest_run_id="backtest-b",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )

    class _MixedAuditFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            del requested_audit
            build = concrete.build(
                audit_b,
                external_should_stop=external_should_stop,
            )
            object.__setattr__(
                build,
                "attestation",
                ResearchBacktestBuildAttestation.from_audit(audit_a),
            )
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_MixedAuditFactory()).run(
            audit_a,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == "research_backtest_audit_drift"


def test_existing_runner_rejects_planner_method_shadow_after_official_build() -> None:
    concrete, audit, *_ = _fixture()
    poisoned_calls = 0

    def _poisoned_plan(*_args: object, **_kwargs: object) -> object:
        nonlocal poisoned_calls
        poisoned_calls += 1
        raise AssertionError("shadowed planner must not be reached")

    class _PlannerShadowFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            build = concrete.build(
                requested_audit,
                external_should_stop=external_should_stop,
            )
            object.__setattr__(build.graph.planner, "plan", _poisoned_plan)
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_PlannerShadowFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert (
        exc_info.value.details["reason"] == "constructed_execution_planner_state_drift"
    )
    assert poisoned_calls == 0


@pytest.mark.parametrize(
    ("target_name", "method_name", "reason"),
    [
        (
            "pipeline",
            "run",
            "constructed_strategy_pipeline_state_drift",
        ),
        (
            "feed",
            "get_slice",
            "research_data_feed_state_drift",
        ),
    ],
)
def test_existing_runner_rejects_execution_method_shadow_after_official_build(
    target_name: str,
    method_name: str,
    reason: str,
) -> None:
    concrete, audit, *_ = _fixture()
    poisoned_calls = 0

    def _poisoned(*_args: object, **_kwargs: object) -> object:
        nonlocal poisoned_calls
        poisoned_calls += 1
        raise AssertionError("shadowed execution method must not be reached")

    class _MethodShadowFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            build = concrete.build(
                requested_audit,
                external_should_stop=external_should_stop,
            )
            target = getattr(build.graph, target_name)
            object.__setattr__(target, method_name, _poisoned)
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_MethodShadowFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == reason
    assert poisoned_calls == 0


def test_existing_runner_rejects_mutated_rule_provider_after_official_build() -> None:
    concrete, audit, *_ = _fixture()

    class _RulePoisonFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            build = concrete.build(
                requested_audit,
                external_should_stop=external_should_stop,
            )
            build.graph.rule_provider.inner._definitions.clear()
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_RulePoisonFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == "constructed_rule_provider_state_drift"


def test_existing_runner_rejects_slippage_value_mutation_after_official_build() -> None:
    concrete, audit, *_ = _fixture()

    class _SlippagePoisonFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            build = concrete.build(
                requested_audit,
                external_should_stop=external_should_stop,
            )
            object.__setattr__(build.graph.slippage_model, "bps", 9_999.0)
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_SlippagePoisonFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == (
        "constructed_slippage_model_parameter_drift"
    )


def test_existing_runner_rejects_coherent_audit_mutation_after_official_build() -> None:
    concrete, audit, *_ = _fixture()

    class _AuditPoisonFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            build = concrete.build(
                requested_audit,
                external_should_stop=external_should_stop,
            )
            object.__setattr__(
                requested_audit.semantics.backtest,
                "slippage_basis_points",
                9_999,
            )
            object.__setattr__(build.graph.slippage_model, "bps", 9_999.0)
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_AuditPoisonFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == "research_backtest_attestation_drift"


def test_existing_runner_derives_planner_order_type_from_audit() -> None:
    concrete, audit, *_ = _fixture()

    class _PlannerIdentityPoisonFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            build = concrete.build(
                requested_audit,
                external_should_stop=external_should_stop,
            )
            object.__setattr__(
                build.graph.planner,
                "_default_order_type",
                OrderType.LIMIT,
            )
            return build

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_PlannerIdentityPoisonFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == (
        "constructed_execution_planner_parameter_drift"
    )


def test_existing_runner_rejects_unsealed_exact_build() -> None:
    concrete, audit, *_ = _fixture()

    class _UnsealedFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            sealed = concrete.build(
                requested_audit,
                external_should_stop=external_should_stop,
            )
            return VerifiedResearchBacktestBuild(
                sealed.service,
                sealed.attestation,
                sealed.graph,
            )

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_UnsealedFactory()).run(
            audit,
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == "unsealed_research_backtest_build"


def test_factory_rebuilds_typed_parameters_and_actual_compiled_factor_hash() -> None:
    factory, audit, _reader, builder, _loader = _fixture()
    declared = audit.semantics.strategy
    assert type(declared) is StrategyExecutionBinding
    parameter = CandidateParameter(
        "/pipeline/nodes/allocation/config/top_k",
        20,
    )
    effective = EffectiveParameter(parameter.path, parameter.value)
    artifact = ContentAddressedResearchInput(
        input_id="momentum_1m@1",
        artifact_kind="factor",
        content_hash=_sha("8"),
        schema_hash=_sha("9"),
    )
    unused_artifact = ContentAddressedResearchInput(
        input_id="value_quality@1",
        artifact_kind="factor",
        content_hash=_sha("6"),
        schema_hash=_sha("7"),
    )
    compiled_expression = CompiledDerivedExpression(
        derived_id="momentum_1m",
        version=1,
        expr=pl.col("close"),
        analysis=Analysis(
            dependencies=("close",),
            operator_names=(),
            lookback=0,
            requires_full_day=False,
            scope="instrument",
        ),
        compile_identity=_compile_identity(),
    )
    serialized = compiled_expression.expr.meta.serialize()
    assert type(serialized) is bytes
    runtime_factor = ResearchFactorBinding(
        factor_id="momentum_1m",
        version=1,
        spec_hash=_sha("a"),
        compiled_expression_hash=hashlib.sha256(serialized).hexdigest(),
        analysis_execution_hash=analysis_execution_hash(compiled_expression.analysis),
        compile_identity=_compile_identity(),
    )
    execution_factor = ResearchFactorExecutionBinding(
        factor_id=runtime_factor.factor_id,
        version=runtime_factor.version,
        spec_hash=runtime_factor.spec_hash,
        compiled_expression_hash=runtime_factor.compiled_expression_hash,
        analysis_execution_hash=runtime_factor.analysis_execution_hash,
        compile_identity=runtime_factor.compile_identity,
        artifact=artifact,
    )
    snapshot = replace(
        audit.semantics.snapshot,
        inputs=(*audit.semantics.snapshot.inputs, artifact, unused_artifact),
    )
    compiled = CompiledExpressions(
        expressions=(compiled_expression,),
        weights=(1.0,),
    )
    binding = replace(
        declared,
        parameter_hash=canonical_parameter_hash((effective,)),
        compiled_factor_set_hash=compiled_expressions_execution_hash(compiled),
        factor_bindings=(execution_factor,),
        candidate_parameters=(parameter,),
    )
    builder.runtime = replace(
        builder.runtime,
        legacy_spec=replace(
            builder.runtime.legacy_spec,
            signal_expressions=("momentum_1m",),
            signal_weights=(1.0,),
        ),
        snapshot_identity=ResearchSnapshotIdentity(
            snapshot.exact_snapshot.snapshot_id,
            snapshot.exact_snapshot.manifest_hash,
        ),
        parameter_hash=binding.parameter_hash,
        effective_parameters=(effective,),
        used_factor_bindings=(runtime_factor,),
        compiled_expressions=compiled,
    )
    semantics = replace(
        audit.semantics,
        strategy=binding,
        snapshot=snapshot,
    )
    exact_audit = ResearchExecutionAudit.create(
        semantics=semantics,
        attempt_id=audit.attempt_id,
        attempt_ordinal=audit.attempt_ordinal,
        backtest_run_id=audit.backtest_run_id,
        parent_attempt_id=audit.parent_attempt_id,
        resume_from_run_id=audit.resume_from_run_id,
        created_at=audit.created_at,
    )

    result = factory.build(exact_audit, external_should_stop=_never_stop)

    assert result.attestation == ResearchBacktestBuildAttestation.from_audit(
        exact_audit
    )
    assert result.attestation.strategy.factor_bindings == (execution_factor,)

    class _CompiledPoisonFactory:
        def build(
            self,
            requested_audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            assert requested_audit is exact_audit
            assert external_should_stop is _never_stop
            assert result.graph.compiled_expressions is not None
            object.__setattr__(
                result.graph.compiled_expressions,
                "weights",
                (0.5,),
            )
            return result

    with pytest.raises(AppProcessError) as exc_info:
        ExistingBacktestResearchFoldRunner(_CompiledPoisonFactory()).run(
            exact_audit,
            external_should_stop=_never_stop,
        )
    assert exc_info.value.details["reason"] == "compiled_factor_set_execution_drift"

    builder.runtime = replace(
        builder.runtime,
        compiled_expressions=CompiledExpressions(
            expressions=(replace(compiled_expression, expr=pl.col("open")),),
            weights=(1.0,),
        ),
    )
    with pytest.raises(AppProcessError) as exc_info:
        factory.build(exact_audit, external_should_stop=_never_stop)
    assert exc_info.value.details["reason"] == "compiled_factor_runtime_drift"

    builder.runtime = replace(
        builder.runtime,
        compiled_expressions=CompiledExpressions(
            expressions=(
                replace(
                    compiled_expression,
                    analysis=replace(compiled_expression.analysis, lookback=1),
                ),
            ),
            weights=(1.0,),
        ),
    )
    with pytest.raises(AppProcessError) as exc_info:
        factory.build(exact_audit, external_should_stop=_never_stop)
    assert exc_info.value.details["reason"] == "compiled_factor_runtime_drift"

    poisoned_factor = replace(
        runtime_factor,
        compiled_expression_hash=_sha("c"),
    )
    builder.runtime = replace(
        builder.runtime,
        used_factor_bindings=(poisoned_factor,),
        compiled_expressions=CompiledExpressions(
            expressions=(compiled_expression,),
            weights=(1.0,),
        ),
    )
    with pytest.raises(AppProcessError) as exc_info:
        factory.build(exact_audit, external_should_stop=_never_stop)
    assert exc_info.value.details["reason"] == "compiled_factor_runtime_drift"


def test_factory_applies_audit_knowledge_lag_to_rules_and_fees() -> None:
    factory, audit, *_ = _fixture()

    result = factory.build(audit, external_should_stop=_never_stop)
    provider = result.service._options.rule_provider
    assert provider is not None
    member_id = InstrumentId(_MEMBER_ID)
    same_day_rule = provider.get_trading_rule(
        member_id,
        "2026-01-02",
    )
    same_day_fee = provider.get_fee_schedule(
        member_id,
        "2026-01-02",
    )
    next_day_rule = provider.get_trading_rule(
        member_id,
        "2026-01-03",
    )
    next_day_fee = provider.get_fee_schedule(
        member_id,
        "2026-01-03",
    )

    assert same_day_rule is not None
    assert same_day_rule.as_of_date == "2026-01-01"
    assert same_day_rule.price_limit_pct == 0.1
    assert same_day_fee is not None
    assert same_day_fee.min_commission == 5.0
    assert next_day_rule is not None
    assert next_day_rule.as_of_date == "2026-01-02"
    assert next_day_rule.price_limit_pct == 0.2
    assert next_day_fee is not None
    assert next_day_fee.min_commission == 9.0


def test_factory_builds_synthetic_baseline_without_catalog_runtime_lookup() -> None:
    factory, candidate_audit, reader, builder, _loader = _fixture()
    snapshot = candidate_audit.semantics.snapshot
    registry = default_baseline_registry()
    universe = ExactUniverseIdentity("stock-pit-universe", _sha("4"))
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=BaselineRef("stock_universe_equal_weight", 1),
            snapshot=snapshot.exact_snapshot,
            universe=universe,
            exact_strategy=None,
        )
    )
    binding = BaselineExecutorBinding(
        baseline_ref=plan.baseline_ref.identity,
        kind=plan.kind,
        descriptor_hash=plan.descriptor_hash,
        implementation_key=plan.implementation_key,
        executor_contract_version=plan.executor_contract_version,
        registry_manifest_hash=registry.manifest_hash,
        factor_versions=(),
    )
    backtest = replace(
        candidate_audit.semantics.backtest,
        rebalance_policy=VersionedExecutionComponent(
            "research.baseline.fold_schedule",
            1,
        ),
        rebalance_frequency="fold_schedule",
        benchmark=None,
    )
    semantics = replace(
        candidate_audit.semantics,
        candidate_id="baseline-1",
        is_baseline=True,
        strategy=binding,
        backtest=backtest,
        membership_hash=universe.membership_hash,
        baseline_registry_manifest_hash=registry.manifest_hash,
        baseline_plan=plan,
    )
    audit = ResearchExecutionAudit.create(
        semantics=semantics,
        attempt_id="attempt-baseline-1",
        attempt_ordinal=1,
        backtest_run_id="backtest-baseline-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )

    result = factory.build(audit, external_should_stop=_never_stop)
    report = result.service.run()

    assert result.attestation == ResearchBacktestBuildAttestation.from_audit(audit)
    assert result.service._config.strategy_id == binding.baseline_ref
    assert result.service._config.rebalance_freq == "fold_schedule"
    assert result.service._pipeline._stages == ()
    assert reader.calls == []
    assert builder.calls == 0
    first_day_orders = tuple(
        item for item in report.pre_trade_log if item.trade_date == _DATES[0]
    )
    assert len(first_day_orders) == 1
    assert first_day_orders[0].instrument_id == InstrumentId(_MEMBER_ID)
    # The actual execution plan asks for 100% of first-day NAV in the sole
    # exact-PIT member.  Later pre-trade resizing/fill participation may reduce
    # the executable quantity, so prove the baseline target from original_qty.
    first_day_notional = first_day_orders[0].original_quantity * 10.0
    assert first_day_notional / report.initial_cash == pytest.approx(1.0)


def _poison_component(
    audit: ResearchExecutionAudit,
    field: str,
    value: object,
) -> ResearchExecutionAudit:
    object.__setattr__(audit.semantics.backtest, field, value)
    return audit


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        (
            "fill_model",
            VersionedExecutionComponent("provider.fill.latest", 1),
            "unsupported_backtest_component",
        ),
        (
            "execution_planner",
            VersionedExecutionComponent("provider.planner.latest", 1),
            "unsupported_backtest_component",
        ),
        (
            "pre_trade_checks",
            (
                VersionedExecutionComponent("ditto_risk.buying_power_check", 1),
                VersionedExecutionComponent("ditto_risk.lot_size_check", 1),
            ),
            "pre_trade_check_order_drift",
        ),
        (
            "data_feed_manifest_hash",
            _sha("f"),
            "data_feed_manifest_hash_drift",
        ),
    ],
)
def test_factory_rejects_component_poison_before_service_run(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    reason: str,
) -> None:
    factory, audit, *_ = _fixture()
    run_calls = 0

    def _run(_self: BacktestService) -> object:
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run must not be reached")

    monkeypatch.setattr(BacktestService, "run", _run)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(
            _poison_component(audit, field, value),
            external_should_stop=_never_stop,
        )

    assert exc_info.value.details["reason"] == reason
    assert run_calls == 0


def test_factory_rejects_fee_model_poison_before_service_run() -> None:
    factory, audit, *_ = _fixture()
    models = list(audit.semantics.backtest.policy_model_evidence)
    fee = next(item for item in models if item.role == "fees")
    models[models.index(fee)] = replace(
        fee,
        implementation=VersionedExecutionComponent("provider.fee.latest", 1),
    )
    object.__setattr__(
        audit.semantics.backtest,
        "policy_model_evidence",
        tuple(models),
    )

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "policy_model_evidence_drift"


def test_factory_rejects_coherently_poisoned_policy_model_registry() -> None:
    factory, audit, *_ = _fixture()
    wrong_policy = replace(
        audit.semantics.policy,
        fees=replace(
            audit.semantics.policy.fees,
            model_key="provider.fee.latest",
        ),
    )
    wrong_models = tuple(
        replace(
            item,
            implementation=VersionedExecutionComponent("provider.fee.latest", 1),
        )
        if item.role == "fees"
        else item
        for item in audit.semantics.backtest.policy_model_evidence
    )
    wrong_backtest = replace(
        audit.semantics.backtest,
        policy_hash=wrong_policy.canonical_hash,
        policy_model_evidence=wrong_models,
    )
    wrong_semantics = replace(
        audit.semantics,
        policy=wrong_policy,
        backtest=wrong_backtest,
    )
    wrong_audit = ResearchExecutionAudit.create(
        semantics=wrong_semantics,
        attempt_id=audit.attempt_id,
        attempt_ordinal=audit.attempt_ordinal,
        backtest_run_id=audit.backtest_run_id,
        parent_attempt_id=audit.parent_attempt_id,
        resume_from_run_id=audit.resume_from_run_id,
        created_at=audit.created_at,
    )

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(wrong_audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "unsupported_policy_model_component"


def test_factory_rejects_audit_from_a_different_code_environment() -> None:
    factory, audit, *_ = _fixture()
    wrong_semantics = replace(
        audit.semantics,
        environment=CodeEnvironmentLock("other-commit", _sha("e")),
    )
    wrong_audit = ResearchExecutionAudit.create(
        semantics=wrong_semantics,
        attempt_id=audit.attempt_id,
        attempt_ordinal=audit.attempt_ordinal,
        backtest_run_id=audit.backtest_run_id,
        parent_attempt_id=audit.parent_attempt_id,
        resume_from_run_id=audit.resume_from_run_id,
        created_at=audit.created_at,
    )

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(wrong_audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "actual_code_environment_lock_drift"


def test_factory_rejects_benchmark_identity_poison_before_service_run() -> None:
    factory, audit, *_ = _fixture()
    benchmark = audit.semantics.backtest.benchmark
    assert benchmark is not None
    object.__setattr__(benchmark, "instrument_identity_hash", _sha("e"))

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "benchmark_binding_drift"


def test_factory_rejects_benchmark_mapping_unknown_at_knowledge_cutoff() -> None:
    factory, audit, *_ = _fixture(
        rules=_rules(
            benchmark_as_of_date=date(2026, 1, 2),
            benchmark_known_at_date=date(2026, 1, 2),
        )
    )

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "benchmark_mapping_knowledge_drift"


def test_factory_reverifies_rules_bytes_instead_of_trusting_loader_internals() -> None:
    factory, audit, _reader, _builder, loader = _fixture()
    object.__setattr__(loader.rules, "_definitions", ())
    object.__setattr__(loader.rules, "_trading_rules", ())
    object.__setattr__(loader.rules, "_fee_schedules", ())

    result = factory.build(audit, external_should_stop=_never_stop)

    provider = result.service._options.rule_provider
    assert provider is not None
    assert provider.get_trading_rule(InstrumentId(_MEMBER_ID), _DATES[0]) is not None


def test_factory_rejects_active_member_after_delisting() -> None:
    factory, audit, *_ = _fixture(rules=_rules(member_delisting_date=date(2026, 1, 3)))

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "frozen_instrument_lifecycle_drift"


def test_factory_rejects_non_tradable_member_lifecycle() -> None:
    factory, audit, *_ = _fixture(rules=_rules(member_lifecycle_state="delisted"))

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "frozen_instrument_lifecycle_drift"


def test_factory_rejects_same_type_fill_model_parameter_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = AShareFillModel.__init__

    def _poisoned_init(
        self: AShareFillModel,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        original_init(self)
        self._participation_rate = 0.75

    monkeypatch.setattr(AShareFillModel, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "constructed_fill_model_parameter_drift"


def test_factory_rejects_same_type_planner_parameter_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = SimpleExecutionPlanner.__init__

    def _poisoned_init(
        self: SimpleExecutionPlanner,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        original_init(self)
        self._default_order_type = OrderType.LIMIT

    monkeypatch.setattr(SimpleExecutionPlanner, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert (
        exc_info.value.details["reason"]
        == "constructed_execution_planner_parameter_drift"
    )


def test_factory_rejects_same_type_pre_trade_order_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = CompositePreTradeCheck.__init__

    def _poisoned_init(
        self: CompositePreTradeCheck,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        original_init(self, (BuyingPowerCheck(), LotSizeCheck()))

    monkeypatch.setattr(CompositePreTradeCheck, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "constructed_pre_trade_check_order_drift"


def test_factory_rejects_same_type_brokerage_child_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = BrokerageModel.__init__

    def _poisoned_init(
        self: BrokerageModel,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        original_init(self)

    monkeypatch.setattr(BrokerageModel, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "constructed_brokerage_model_drift"


def test_factory_rejects_same_type_brokerage_rules_getter_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = BacktestBrokerage.__init__

    def _poisoned_rules_getter(
        _instrument_id: InstrumentId,
        _trade_date: str,
    ) -> InstrumentRules:
        raise AssertionError("provider fallback must not be reachable")

    def _poisoned_init(
        self: BacktestBrokerage,
        account: Account,
        order_book: OrderBook,
        model: BrokerageModel | None = None,
        rules_getter: RulesGetter | None = None,
    ) -> None:
        original_init(
            self,
            account=account,
            order_book=order_book,
            model=model,
            rules_getter=rules_getter,
        )
        object.__setattr__(self, "_rules_getter", _poisoned_rules_getter)

    monkeypatch.setattr(BacktestBrokerage, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "constructed_brokerage_state_drift"


def test_factory_rejects_same_type_brokerage_initial_cash_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = BacktestBrokerage.__init__

    def _poisoned_init(
        self: BacktestBrokerage,
        account: Account,
        order_book: OrderBook,
        model: BrokerageModel | None = None,
        rules_getter: RulesGetter | None = None,
    ) -> None:
        original_init(
            self,
            account=account,
            order_book=order_book,
            model=model,
            rules_getter=rules_getter,
        )
        account.cash = CashBook(available=1.0, settled=1.0, frozen=0.0)

    monkeypatch.setattr(BacktestBrokerage, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "constructed_brokerage_account_drift"


def test_factory_rejects_same_type_settlement_calendar_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = AShareSettlementModel.__init__

    def _poisoned_init(
        self: AShareSettlementModel,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        original_init(self)

    monkeypatch.setattr(AShareSettlementModel, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "constructed_settlement_calendar_drift"


@pytest.mark.parametrize(
    "poison_kind",
    ["float_subclass", "tuple_subclass", "tuple_item_subclass"],
)
def test_existing_runner_rejects_config_subclass_after_official_build(
    poison_kind: str,
) -> None:
    def _mutate(build: VerifiedResearchBacktestBuild) -> None:
        config = build.graph.config
        if poison_kind == "float_subclass":
            object.__setattr__(
                config,
                "initial_cash",
                _FloatSubclass(config.initial_cash),
            )
        elif poison_kind == "tuple_subclass":
            object.__setattr__(
                config,
                "data_catalog_identities",
                _TupleSubclass(config.data_catalog_identities),
            )
        else:
            object.__setattr__(
                config,
                "data_catalog_identities",
                tuple(_StrSubclass(value) for value in config.data_catalog_identities),
            )

    _assert_post_build_mutation_rejected(
        _mutate,
        reason="constructed_backtest_service_config_drift",
    )


@pytest.mark.parametrize("field_name", ["_counter", "_default_lot_size"])
def test_existing_runner_rejects_planner_integer_subclass_after_official_build(
    field_name: str,
) -> None:
    def _mutate(build: VerifiedResearchBacktestBuild) -> None:
        planner = build.graph.planner
        object.__setattr__(
            planner,
            field_name,
            _IntSubclass(getattr(planner, field_name)),
        )

    _assert_post_build_mutation_rejected(
        _mutate,
        reason="constructed_execution_planner_parameter_drift",
    )


@pytest.mark.parametrize("field_name", ["available", "settled", "frozen"])
def test_existing_runner_rejects_cash_float_subclass_after_official_build(
    field_name: str,
) -> None:
    def _mutate(build: VerifiedResearchBacktestBuild) -> None:
        cash = build.graph.components.cash
        object.__setattr__(
            cash,
            field_name,
            _FloatSubclass(getattr(cash, field_name)),
        )

    _assert_post_build_mutation_rejected(
        _mutate,
        reason="constructed_brokerage_account_drift",
    )


@pytest.mark.parametrize("poison_kind", ["tuple_subclass", "string_subclass"])
def test_existing_runner_rejects_noncanonical_settlement_calendar_after_build(
    poison_kind: str,
) -> None:
    def _mutate(build: VerifiedResearchBacktestBuild) -> None:
        settlement = build.graph.components.settlement_model
        calendar = settlement.trading_calendar
        poisoned = (
            _TupleSubclass(calendar)
            if poison_kind == "tuple_subclass"
            else tuple(_StrSubclass(value) for value in calendar)
        )
        object.__setattr__(settlement, "trading_calendar", poisoned)

    _assert_post_build_mutation_rejected(
        _mutate,
        reason="constructed_settlement_calendar_drift",
    )


@pytest.mark.parametrize(
    "poisoned_events",
    [
        {},
        defaultdict(set),
        defaultdict(list, {"ghost": []}),
    ],
)
def test_existing_runner_rejects_noncanonical_empty_order_journal_after_build(
    poisoned_events: object,
) -> None:
    def _mutate(build: VerifiedResearchBacktestBuild) -> None:
        object.__setattr__(
            build.graph.components.order_journal,
            "_events",
            poisoned_events,
        )

    _assert_post_build_mutation_rejected(
        _mutate,
        reason="constructed_order_journal_state_drift",
    )


def test_existing_runner_rejects_rule_provider_lookup_semantics_drift_after_build() -> (
    None
):
    def _mutate(build: VerifiedResearchBacktestBuild) -> None:
        provider = build.graph.components.rule_provider.inner
        member_id = InstrumentId(_MEMBER_ID)
        honest_schedules = provider._fee_schedules[member_id]
        drifted_schedules = [
            replace(
                schedule,
                commission_rate=1.0,
                min_commission=999_999.0,
            )
            for schedule in honest_schedules
        ]

        class _LookupDrift(dict):
            def get(self, key, default=None):
                if key == member_id:
                    return drifted_schedules
                return super().get(key, default)

        drifted_store = _LookupDrift(provider._fee_schedules)
        assert drifted_store == provider._fee_schedules
        assert drifted_store.get(member_id)[0].commission_rate == 1.0
        object.__setattr__(provider, "_fee_schedules", drifted_store)

    _assert_post_build_mutation_rejected(
        _mutate,
        reason="constructed_rule_provider_state_drift",
    )


def test_factory_rejects_same_type_service_unauthorized_option_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = BacktestService.__init__

    def _poisoned_init(
        self: BacktestService,
        config: BacktestServiceConfig,
        pipeline: StrategyPipeline,
        planner: SimpleExecutionPlanner,
        brokerage: BacktestBrokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: ResearchDataFeed,
        options: BacktestServiceOptions,
    ) -> None:
        original_init(
            self,
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=options,
        )
        object.__setattr__(options, "allow_experimental_data", True)

    monkeypatch.setattr(BacktestService, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "unauthorized_backtest_service_option"


def test_factory_rejects_same_type_service_dependency_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = BacktestService.__init__

    def _poisoned_init(
        self: BacktestService,
        config: BacktestServiceConfig,
        pipeline: StrategyPipeline,
        planner: SimpleExecutionPlanner,
        brokerage: BacktestBrokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: ResearchDataFeed,
        options: BacktestServiceOptions,
    ) -> None:
        original_init(
            self,
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=options,
        )
        object.__setattr__(self, "_data_feed", object())

    monkeypatch.setattr(BacktestService, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert (
        exc_info.value.details["reason"] == "constructed_backtest_service_wiring_drift"
    )


def test_factory_rejects_same_type_service_callable_shadow_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, audit, *_ = _fixture()
    original_init = BacktestService.__init__

    def _shadowed_run() -> object:
        return object()

    def _poisoned_init(
        self: BacktestService,
        config: BacktestServiceConfig,
        pipeline: StrategyPipeline,
        planner: SimpleExecutionPlanner,
        brokerage: BacktestBrokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: ResearchDataFeed,
        options: BacktestServiceOptions,
    ) -> None:
        original_init(
            self,
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=options,
        )
        object.__setattr__(self, "run", _shadowed_run)

    monkeypatch.setattr(BacktestService, "__init__", _poisoned_init)

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert (
        exc_info.value.details["reason"] == "constructed_backtest_service_wiring_drift"
    )


def test_factory_rejects_rebuilt_strategy_drift_before_service_run() -> None:
    factory, audit, _reader, builder, _loader = _fixture()
    builder.runtime = replace(builder.runtime, resolved_spec_hash=_sha("e"))

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "rebuilt_strategy_binding_drift"


def test_factory_rejects_rebuilt_pipeline_execution_hash_drift() -> None:
    factory, audit, _reader, builder, _loader = _fixture()
    object.__setattr__(
        builder.runtime.attested_pipeline,
        "_execution_hash",
        _sha("f"),
    )

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "rebuilt_pipeline_execution_drift"


def test_factory_rejects_actual_pipeline_poison_with_unchanged_hash() -> None:
    factory, audit, _reader, builder, _loader = _fixture()
    original_hash = builder.runtime.pipeline_execution_hash
    object.__setattr__(
        builder.runtime.attested_pipeline,
        "_pipeline",
        StrategyPipeline(()),
    )

    assert builder.runtime.pipeline_execution_hash == original_hash
    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=_never_stop)

    assert exc_info.value.details["reason"] == "rebuilt_pipeline_execution_drift"
