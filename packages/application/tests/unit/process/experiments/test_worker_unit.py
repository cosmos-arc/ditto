"""Fail-closed execution tests for one durably claimed research fold."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from threading import Event, Lock
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    AttemptView,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
    LeaseFence,
    SchedulerLease,
    canonical_payload,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.research.artifact_measurement import (
    measure_json_bytes,
    measure_parquet_bytes,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import BacktestService
from ditto_application.processes.execution.backtest_serialization import (
    serialize_selection_evidence,
)
from ditto_application.processes.experiments import worker as worker_module
from ditto_application.processes.experiments._execution_resolution_evidence import (
    research_execution_error,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
    FoldSelectionTraceArtifactPublisher,
    FoldSelectionTraceArtifactReceipt,
    fold_selection_trace_table_name,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportArtifactIdentity,
    BacktestReportArtifactPublisher,
    BacktestReportEvidence,
)
from ditto_application.processes.experiments.backtest_service_wiring import (
    ClosedBacktestServiceGraph,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentDispatch,
    PersistedAttemptStart,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
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
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    default_stock_execution_policy,
)
from ditto_application.processes.experiments.research_data_feed import (
    research_data_feed_manifest_hash,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentExecutionControlChanged,
    ResearchExecutionDirective,
)
from ditto_application.processes.experiments.worker import (
    ExecutionBundleFirstAttemptFactory,
    ExistingBacktestResearchFoldRunner,
    ResearchBacktestBuildAttestation,
    ResearchBacktestBuildSource,
    ResearchCandidateExecutionError,
    ResearchExecutionSemanticsResolver,
    ResearchExperimentWorker,
    ResearchFoldRunner,
    ResearchFoldRunResult,
    ResearchFoldRunState,
    ResearchWorkerCoordinator,
    ResearchWorkerState,
    VerifiedResearchBacktestBuild,
)
from ditto_backtest.statistics import BacktestReport
from ditto_features.expression.contracts import CompileIdentity
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceLog

_NOW = datetime(2026, 7, 20, 9, tzinfo=UTC)


def _sha(character: str) -> str:
    return character * 64


def _forged_graph(service: BacktestService) -> ClosedBacktestServiceGraph:
    """Claim an arbitrary service graph without providing verified components."""
    return ClosedBacktestServiceGraph(
        service=service,
        audit=MagicMock(),
        config=MagicMock(),
        pipeline=MagicMock(),
        selection_evidence_collector=MagicMock(),
        planner=MagicMock(),
        brokerage=MagicMock(),
        pre_trade=MagicMock(),
        feed=MagicMock(),
        options=MagicMock(),
        fee_model=MagicMock(),
        slippage_model=MagicMock(),
        rule_provider=MagicMock(),
        compiled_expressions=None,
        pipeline_attestation=None,
        external_should_stop=lambda: False,
        components=MagicMock(),
    )


def _factor_binding() -> ResearchFactorExecutionBinding:
    return ResearchFactorExecutionBinding(
        factor_id="momentum_1m",
        version=1,
        spec_hash=_sha("8"),
        compile_identity=CompileIdentity(
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
        ),
        compiled_expression_hash="8" * 64,
        analysis_execution_hash="7" * 64,
        artifact=ContentAddressedResearchInput(
            input_id="momentum_1m@1",
            artifact_kind="factor",
            content_hash=_sha("8"),
            schema_hash=_sha("9"),
        ),
    )


def _backtest_binding() -> BacktestExecutionConfigBinding:
    fee_schedule = ContentAddressedResearchInput(
        input_id="fee_schedule",
        artifact_kind="parquet",
        content_hash=_sha("9"),
        schema_hash=_sha("a"),
    )
    instrument_rules = ContentAddressedResearchInput(
        input_id="instrument_rules",
        artifact_kind="instrument_rules",
        content_hash=_sha("b"),
        schema_hash=_sha("c"),
    )
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=100_000_000,
        currency="CNY",
        engine=VersionedExecutionComponent("ditto_backtest.engine", 1),
        engine_version="0.1.0",
        rebalance_policy=VersionedExecutionComponent(
            "ditto_strategy.rebalance_schedule",
            1,
        ),
        rebalance_frequency="daily",
        participation_rate_ppm=50_000,
        fill_mode=ResearchFillMode.PARTIAL,
        fill_model=VersionedExecutionComponent("ditto_backtest.a_share_fill", 1),
        brokerage_model=VersionedExecutionComponent(
            "ditto_backtest.brokerage",
            1,
        ),
        execution_planner=VersionedExecutionComponent(
            "ditto_execution.simple_planner",
            1,
        ),
        slippage_basis_points=1,
        benchmark=ExactBenchmarkBinding(
            instrument_id=3_000_001,
            instrument_identity_hash=_sha("d"),
            mapping_input=instrument_rules,
            bars_input=ContentAddressedResearchInput(
                input_id="benchmark_bars",
                artifact_kind="bars",
                content_hash=_sha("f"),
                schema_hash=_sha("0"),
            ),
        ),
        policy_hash=default_stock_execution_policy().canonical_hash,
        policy_model_evidence=(
            PolicyModelEvidenceBinding(
                role="fees",
                implementation=VersionedExecutionComponent(
                    "ditto_execution.a_share_fee",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                inputs=(fee_schedule,),
            ),
            PolicyModelEvidenceBinding(
                role="rules",
                implementation=VersionedExecutionComponent(
                    "ditto_kernel.instrument_rules",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                inputs=(instrument_rules,),
            ),
            PolicyModelEvidenceBinding(
                role="settlement",
                implementation=VersionedExecutionComponent(
                    "ditto_backtest.a_share_settlement",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                inputs=(instrument_rules,),
            ),
            PolicyModelEvidenceBinding(
                role="slippage",
                implementation=VersionedExecutionComponent(
                    "ditto_backtest.fixed_bps_slippage",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY,
                inputs=(),
            ),
        ),
        pre_trade_checks=(
            VersionedExecutionComponent("ditto_risk.lot_size", 1),
            VersionedExecutionComponent("ditto_risk.buying_power", 1),
        ),
        post_trade_guard=None,
        data_feed_manifest_hash=_sha("1"),
    )


def _backtest_inputs(
    binding: BacktestExecutionConfigBinding,
) -> tuple[ContentAddressedResearchInput, ...]:
    inputs = {
        item.input_id: item
        for model in binding.policy_model_evidence
        for item in model.inputs
    }
    if binding.benchmark is not None:
        inputs[binding.benchmark.bars_input.input_id] = binding.benchmark.bars_input
    return tuple(sorted(inputs.values(), key=lambda item: item.input_id))


def _fold(
    status: ExperimentStatus = ExperimentStatus.RUNNING,
    *,
    role: FoldRole = FoldRole.WALK_FORWARD,
) -> FoldView:
    key = FoldKey(
        ExperimentId("experiment-1"),
        CandidateId("candidate-1"),
        FoldId("fold-1"),
    )
    spec = FoldPersistenceSpec.create(
        key,
        2,
        role,
        DateWindow(date(2018, 1, 1), date(2023, 12, 31)),
        DateWindow(date(2024, 1, 1), date(2024, 12, 31)),
        5,
        5,
    )
    return FoldView(
        spec,
        FoldProjection(
            key=key,
            status=status,
            claim_owner_token=(
                "worker-owner" if status is ExperimentStatus.RUNNING else None
            ),
            created_at=_NOW,
            updated_at=_NOW,
            revision=1,
        ),
    )


def _semantics(
    *,
    role: FoldRole = FoldRole.WALK_FORWARD,
) -> ResearchExecutionSemantics:
    bars_input = ContentAddressedResearchInput(
        input_id="bars",
        artifact_kind="bars",
        content_hash=_sha("3"),
        schema_hash=_sha("4"),
    )
    base_backtest = _backtest_binding()
    assert base_backtest.benchmark is not None
    declared_backtest = replace(
        base_backtest,
        benchmark=replace(base_backtest.benchmark, bars_input=bars_input),
    )
    factor_binding = _factor_binding()
    snapshot = ResearchSnapshotBinding(
        exact_snapshot=ExactResearchSnapshot("snapshot-1", _sha("2")),
        dataset_id="research-stock-selection",
        source_snapshot_ids=("provider-snapshot-1",),
        known_at_policy="sample_time",
        builder_version="research-builder-v1",
        inputs=(
            ContentAddressedResearchInput(
                input_id="calendar",
                artifact_kind="calendar",
                content_hash=_sha("6"),
                schema_hash=_sha("7"),
            ),
            ContentAddressedResearchInput(
                input_id="membership",
                artifact_kind="membership",
                content_hash=_sha("5"),
                schema_hash=_sha("6"),
            ),
            factor_binding.artifact,
            *_backtest_inputs(declared_backtest),
        ),
    )
    backtest = replace(
        declared_backtest,
        data_feed_manifest_hash=research_data_feed_manifest_hash(snapshot),
    )
    return ResearchExecutionSemantics(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        fold_id="fold-1",
        fold_role=role.value,
        is_baseline=False,
        plan_hash=_sha("a"),
        launch_spec_hash=_sha("b"),
        fold_spec_hash=str(_fold(role=role).spec.payload_hash),
        strategy=StrategyExecutionBinding(
            exact_strategy=ExactStrategyIdentity("stock-selection", 3, _sha("d")),
            resolved_spec_hash=_sha("e"),
            parameter_hash=_sha("f"),
            node_registry_manifest_hash=_sha("1"),
            pipeline_execution_hash=_sha("9"),
            factor_registry_manifest_hash=_sha("0"),
            compiled_factor_set_hash=_sha("a"),
            factor_bindings=(factor_binding,),
        ),
        backtest=backtest,
        snapshot=snapshot,
        membership_hash=_sha("5"),
        membership_projection_hash=_sha("6"),
        train_start=date(2018, 1, 1),
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2024, 12, 31),
        purge_sessions=5,
        embargo_sessions=5,
        seed=17,
        knowledge_lag_days=1,
        execution_delay_sessions=1,
        baseline_registry_manifest_hash=_sha("7"),
        baseline_plan=None,
        policy=default_stock_execution_policy(),
        environment=CodeEnvironmentLock("git:abc123", _sha("8")),
    )


def _report_evidence(
    *,
    run_id: str = "research-run-persisted",
) -> BacktestReportEvidence:
    return BacktestReportEvidence(
        run_id=run_id,
        period=("2024-01-01", "2024-12-31"),
        initial_cash=100_000.0,
        final_nav=101_000.0,
        nav_series=(
            ("2024-01-01", 100_000.0),
            ("2024-12-31", 101_000.0),
        ),
        fill_log=(),
    )


def _artifact_receipt(
    identity: BacktestReportArtifactIdentity,
    evidence: BacktestReportEvidence,
) -> ArtifactRecord:
    measurement = measure_json_bytes(
        canonical_payload(evidence.canonical_payload()).json_bytes
    )
    return ArtifactManifest.create(
        spec=ArtifactPublicationSpec(
            artifact_id=identity.artifact_id,
            experiment_id=identity.experiment_id,
            candidate_id=identity.candidate_id,
            fold_id=identity.fold_id,
            attempt_id=identity.attempt_id,
            artifact_kind=identity.artifact_kind,
            relative_path=identity.relative_path,
            reproduction_fingerprint=identity.reproduction_fingerprint,
            audit={
                "attempt_id": str(identity.attempt_id),
                "created_at": identity.attempt_created_at.isoformat(),
                "run_id": str(identity.run_id),
            },
            created_at=identity.attempt_created_at,
        ),
        artifact_format=ArtifactFormat.JSON,
        content_hash=measurement.content_hash,
        schema_hash=measurement.schema_hash,
        row_count=measurement.row_count,
        byte_size=measurement.byte_size,
    ).to_record()


def _fold_selection_trace_receipt(
    identity: FoldSelectionTraceArtifactIdentity,
    evidence: SelectionEvidenceLog,
) -> FoldSelectionTraceArtifactReceipt:
    tables = serialize_selection_evidence(str(identity.run_id), evidence)
    records: list[ArtifactRecord] = []
    for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
        buffer = BytesIO()
        tables[fold_selection_trace_table_name(kind)].write_parquet(buffer)
        measurement = measure_parquet_bytes(buffer.getvalue())
        records.append(
            ArtifactManifest.create(
                spec=ArtifactPublicationSpec(
                    artifact_id=identity.artifact_id(kind),
                    experiment_id=identity.experiment_id,
                    candidate_id=identity.candidate_id,
                    fold_id=identity.fold_id,
                    attempt_id=identity.attempt_id,
                    artifact_kind=kind.value,
                    relative_path=identity.relative_path(kind),
                    reproduction_fingerprint=identity.reproduction_fingerprint,
                    audit=identity.audit(kind),
                    created_at=identity.attempt_created_at,
                ),
                artifact_format=ArtifactFormat.PARQUET,
                content_hash=measurement.content_hash,
                schema_hash=measurement.schema_hash,
                row_count=measurement.row_count,
                byte_size=measurement.byte_size,
            ).to_record()
        )
    return FoldSelectionTraceArtifactReceipt(*records)


class _FoldSelectionTracePublisher:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                FoldSelectionTraceArtifactIdentity,
                SelectionEvidenceLog,
                LeaseFence,
                int,
            ]
        ] = []

    def publish(
        self,
        identity: FoldSelectionTraceArtifactIdentity,
        evidence: SelectionEvidenceLog,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> FoldSelectionTraceArtifactReceipt:
        self.calls.append((identity, evidence, lease_fence, now_epoch_us))
        return _fold_selection_trace_receipt(identity, evidence)


_DEFAULT_TRACE_PUBLISHER = object()


def _make_worker(
    *,
    coordinator: ResearchWorkerCoordinator,
    semantics_resolver: ResearchExecutionSemanticsResolver,
    runner: ResearchFoldRunner,
    report_publisher: BacktestReportArtifactPublisher,
    fold_selection_trace_publisher: (
        FoldSelectionTraceArtifactPublisher | None | object
    ) = _DEFAULT_TRACE_PUBLISHER,
    checkpoint_available: Callable[[str], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ResearchExperimentWorker:
    trace_publisher = (
        _FoldSelectionTracePublisher()
        if fold_selection_trace_publisher is _DEFAULT_TRACE_PUBLISHER
        else cast(
            "FoldSelectionTraceArtifactPublisher | None",
            fold_selection_trace_publisher,
        )
    )
    return ResearchExperimentWorker(
        coordinator=coordinator,
        semantics_resolver=semantics_resolver,
        runner=runner,
        report_publisher=report_publisher,
        fold_selection_trace_publisher=trace_publisher,
        checkpoint_available=checkpoint_available,
        clock=clock,
    )


@pytest.mark.parametrize(
    ("state", "evidence"),
    [
        (ResearchFoldRunState.COMPLETED, None),
        (ResearchFoldRunState.STOPPED, _report_evidence()),
        (cast("ResearchFoldRunState", object()), None),
    ],
)
def test_fold_run_result_rejects_state_evidence_mismatch(
    state: ResearchFoldRunState,
    evidence: BacktestReportEvidence | None,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        worker_module.ResearchFoldRunResult(state, evidence)

    assert exc_info.value.details["reason"] == "invalid_research_fold_run_result"


def test_fold_run_result_rejects_stopped_selection_evidence() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        ResearchFoldRunResult(
            ResearchFoldRunState.STOPPED,
            None,
            SelectionEvidenceLog(),
        )

    assert exc_info.value.details["reason"] == "invalid_research_fold_run_result"


class _Resolver:
    def __init__(self, semantics: ResearchExecutionSemantics | Exception) -> None:
        self.value = semantics
        self.calls = 0

    def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
        _ = fold
        self.calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_first_attempt_factory_freezes_semantics_before_atomic_claim() -> None:
    resolver = _Resolver(_semantics())

    fold = _fold(ExperimentStatus.QUEUED)
    first = ExecutionBundleFirstAttemptFactory(resolver).create(fold, _NOW)

    assert resolver.calls == 1
    assert first.spec.fold_key == fold.spec.key
    assert first.spec.ordinal == 1
    assert first.spec.reproduction_fingerprint == _semantics().reproduction_fingerprint
    assert first.projection.status is ExperimentStatus.QUEUED
    assert first.projection.backtest_run_id is None
    assert first.spec.attempt_id == AttemptId(
        "attempt-9faccd3ec1168c57c9821def208e4a6ec4c852dadb4212fea6e92e51c9bcb0da"
    )


def test_first_attempt_factory_rejects_fold_semantic_lineage_drift() -> None:
    resolver = _Resolver(replace(_semantics(), fold_id="different-fold"))

    with pytest.raises(AppProcessError) as captured:
        ExecutionBundleFirstAttemptFactory(resolver).create(
            _fold(ExperimentStatus.QUEUED),
            _NOW,
        )

    assert captured.value.details["code"] == "REPRODUCIBILITY_FAILED"
    assert captured.value.details["reason"] == "execution_fold_lineage_mismatch"


def test_research_runner_rejects_unverified_graph_before_numerics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Factory:
        def __init__(self, service: BacktestService) -> None:
            self.service = service
            self.audits: list[ResearchExecutionAudit] = []
            self.stop_callbacks: list[Callable[[], bool]] = []

        def build(
            self,
            audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> VerifiedResearchBacktestBuild:
            self.audits.append(audit)
            self.stop_callbacks.append(external_should_stop)
            return VerifiedResearchBacktestBuild(
                service=self.service,
                attestation=ResearchBacktestBuildAttestation.from_audit(audit),
                graph=_forged_graph(self.service),
            )

    run_calls = 0

    def _run(_self: BacktestService) -> BacktestReport:
        nonlocal run_calls
        run_calls += 1
        return cast("BacktestReport", object())

    monkeypatch.setattr(BacktestService, "run", _run)
    semantics = _semantics()
    audit = ResearchExecutionAudit.create(
        semantics=semantics,
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    service = object.__new__(BacktestService)
    object.__setattr__(service, "_last_run_cancelled", False)
    factory = _Factory(service)

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert (
        captured.value.details["reason"] == "constructed_backtest_service_wiring_drift"
    )
    assert factory.audits == [audit]
    assert len(factory.stop_callbacks) == 1
    assert run_calls == 0


def test_research_runner_rejects_backtest_subclass_with_forged_attestation() -> None:
    class _PoisonedBacktestService(BacktestService):
        def __init__(self) -> None:
            self.called = False

        @property
        def last_run_cancelled(self) -> bool:
            return False

        def run(self) -> BacktestReport:
            self.called = True
            return cast("BacktestReport", object())

    audit = ResearchExecutionAudit.create(
        semantics=_semantics(),
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    service = _PoisonedBacktestService()
    factory = MagicMock()
    factory.build.return_value = VerifiedResearchBacktestBuild(
        service=service,
        attestation=ResearchBacktestBuildAttestation.from_audit(audit),
        graph=_forged_graph(service),
    )

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert captured.value.details["reason"] == "invalid_research_backtest_service"
    assert service.called is False


def test_research_runner_rejects_exact_service_callable_shadow_from_fake_factory() -> (
    None
):
    called = False

    def _shadowed_run() -> BacktestReport:
        nonlocal called
        called = True
        return cast("BacktestReport", object())

    audit = ResearchExecutionAudit.create(
        semantics=_semantics(),
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    service = object.__new__(BacktestService)
    object.__setattr__(service, "run", _shadowed_run)
    object.__setattr__(service, "_last_run_cancelled", False)
    factory = MagicMock()
    factory.build.return_value = VerifiedResearchBacktestBuild(
        service=service,
        attestation=ResearchBacktestBuildAttestation.from_audit(audit),
        graph=_forged_graph(service),
    )

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert (
        captured.value.details["reason"] == "constructed_backtest_service_wiring_drift"
    )
    assert called is False


def test_research_runner_rejects_unverified_graph_before_cooperative_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(service: BacktestService) -> BacktestReport:
        object.__setattr__(service, "_last_run_cancelled", True)
        return cast("BacktestReport", object())

    monkeypatch.setattr(BacktestService, "run", _run)
    audit = ResearchExecutionAudit.create(
        semantics=_semantics(),
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    service = object.__new__(BacktestService)
    object.__setattr__(service, "_last_run_cancelled", None)
    factory = MagicMock()
    factory.build.return_value = VerifiedResearchBacktestBuild(
        service=service,
        attestation=ResearchBacktestBuildAttestation.from_audit(audit),
        graph=_forged_graph(service),
    )

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert (
        captured.value.details["reason"] == "constructed_backtest_service_wiring_drift"
    )


def test_research_runner_checks_authority_before_factory_build() -> None:
    audit = ResearchExecutionAudit.create(
        semantics=_semantics(),
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    factory = MagicMock()

    result = ExistingBacktestResearchFoldRunner(factory).run(
        audit,
        external_should_stop=lambda: True,
    )

    assert result.state is ResearchFoldRunState.STOPPED
    assert result.report_evidence is None
    factory.build.assert_not_called()


def test_research_runner_checks_authority_after_build_before_service_run() -> None:
    audit = ResearchExecutionAudit.create(
        semantics=_semantics(),
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    service = MagicMock(spec=BacktestService)
    factory = MagicMock()
    factory.build.return_value = VerifiedResearchBacktestBuild(
        service=service,
        attestation=ResearchBacktestBuildAttestation.from_audit(audit),
        graph=_forged_graph(cast("BacktestService", service)),
    )
    checks = iter((False, True))

    result = ExistingBacktestResearchFoldRunner(factory).run(
        audit,
        external_should_stop=lambda: next(checks),
    )

    assert result.state is ResearchFoldRunState.STOPPED
    assert result.report_evidence is None
    factory.build.assert_called_once()
    service.run.assert_not_called()


@pytest.mark.parametrize(
    "source",
    [
        ResearchBacktestBuildSource.PROVIDER_LATEST,
        ResearchBacktestBuildSource.CATALOG_LATEST,
    ],
)
def test_research_runner_rejects_moving_factory_resolution(
    source: ResearchBacktestBuildSource,
) -> None:
    audit = ResearchExecutionAudit.create(
        semantics=_semantics(),
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    service = MagicMock(spec=BacktestService)
    attestation = replace(
        ResearchBacktestBuildAttestation.from_audit(audit),
        source=source,
    )
    factory = MagicMock()
    factory.build.return_value = VerifiedResearchBacktestBuild(
        service=service,
        attestation=attestation,
        graph=_forged_graph(cast("BacktestService", service)),
    )

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert captured.value.details["reason"] == "research_backtest_attestation_drift"
    service.run.assert_not_called()


@pytest.mark.parametrize(
    "drifted_attestation",
    [
        lambda audit: replace(
            ResearchBacktestBuildAttestation.from_audit(audit),
            reproduction_fingerprint=ContentHash(_sha("0")),
        ),
        lambda audit: replace(
            ResearchBacktestBuildAttestation.from_audit(audit),
            strategy=replace(audit.semantics.strategy, parameter_hash=_sha("0")),
        ),
        lambda audit: replace(
            ResearchBacktestBuildAttestation.from_audit(audit),
            snapshot=replace(audit.semantics.snapshot, dataset_id="other-dataset"),
        ),
        lambda audit: replace(
            ResearchBacktestBuildAttestation.from_audit(audit),
            execution_config=replace(
                audit.semantics.backtest,
                participation_rate_ppm=100_000,
            ),
        ),
        lambda audit: replace(
            ResearchBacktestBuildAttestation.from_audit(audit),
            policy_hash=_sha("0"),
        ),
        lambda audit: replace(
            ResearchBacktestBuildAttestation.from_audit(audit),
            environment=CodeEnvironmentLock("git:drift", _sha("0")),
        ),
    ],
)
def test_research_runner_rejects_any_attestation_drift(
    drifted_attestation: Callable[
        [ResearchExecutionAudit], ResearchBacktestBuildAttestation
    ],
) -> None:
    audit = ResearchExecutionAudit.create(
        semantics=_semantics(),
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=_NOW,
    )
    service = MagicMock(spec=BacktestService)
    factory = MagicMock()
    factory.build.return_value = VerifiedResearchBacktestBuild(
        service=service,
        attestation=drifted_attestation(audit),
        graph=_forged_graph(cast("BacktestService", service)),
    )

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(factory).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert captured.value.details["reason"] == "research_backtest_attestation_drift"
    service.run.assert_not_called()


def test_research_runner_rejects_factory_coherent_audit_rewrite_before_numerics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from packages.application.tests.unit.process.experiments import (
        test_research_backtest_factory_unit as factory_tests,
    )

    concrete, audit, *_ = factory_tests._fixture()
    numerical_runs = 0

    def _run(_service: BacktestService) -> BacktestReport:
        nonlocal numerical_runs
        numerical_runs += 1
        return cast("BacktestReport", object())

    monkeypatch.setattr(BacktestService, "run", _run)

    class _CoherentAuditRewriteFactory:
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
            rewritten_semantics = replace(
                requested_audit.semantics,
                seed=9_999,
            )
            rewritten_audit = ResearchExecutionAudit.create(
                semantics=rewritten_semantics,
                attempt_id=requested_audit.attempt_id,
                attempt_ordinal=requested_audit.attempt_ordinal,
                backtest_run_id=requested_audit.backtest_run_id,
                parent_attempt_id=requested_audit.parent_attempt_id,
                resume_from_run_id=requested_audit.resume_from_run_id,
                created_at=requested_audit.created_at,
            )
            object.__setattr__(
                requested_audit,
                "semantics",
                rewritten_audit.semantics,
            )
            object.__setattr__(
                requested_audit,
                "canonical_payload",
                rewritten_audit.canonical_payload,
            )
            object.__setattr__(
                requested_audit,
                "bundle_hash",
                rewritten_audit.bundle_hash,
            )
            object.__setattr__(build.graph.config, "random_seed", 9_999)
            object.__setattr__(
                build,
                "attestation",
                ResearchBacktestBuildAttestation.from_audit(requested_audit),
            )
            return build

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(_CoherentAuditRewriteFactory()).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert captured.value.details["reason"] == "research_execution_audit_drift"
    assert numerical_runs == 0


@pytest.mark.parametrize("derived_hash", ["execution_config", "benchmark"])
def test_research_runner_rejects_factory_derived_hash_rewrite_before_numerics(
    monkeypatch: pytest.MonkeyPatch,
    derived_hash: str,
) -> None:
    from packages.application.tests.unit.process.experiments import (
        test_research_backtest_factory_unit as factory_tests,
    )

    concrete, audit, *_ = factory_tests._fixture()
    numerical_runs = 0

    def _run(_service: BacktestService) -> BacktestReport:
        nonlocal numerical_runs
        numerical_runs += 1
        return cast("BacktestReport", object())

    monkeypatch.setattr(BacktestService, "run", _run)

    class _DerivedHashRewriteFactory:
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
            if derived_hash == "execution_config":
                target = requested_audit.semantics.backtest
            else:
                target = requested_audit.semantics.backtest.benchmark
                assert target is not None
            object.__setattr__(target, "canonical_hash", ContentHash(_sha("0")))
            object.__setattr__(
                build,
                "attestation",
                ResearchBacktestBuildAttestation.from_audit(requested_audit),
            )
            return build

    with pytest.raises(AppProcessError) as captured:
        ExistingBacktestResearchFoldRunner(_DerivedHashRewriteFactory()).run(
            audit,
            external_should_stop=lambda: False,
        )

    assert captured.value.details["reason"] == "research_execution_audit_drift"
    assert numerical_runs == 0


class _Coordinator:
    def __init__(
        self,
        renew_error_on_call: int | None = None,
        *,
        renew_error_code: str = "LEASE_LOST",
        started_now: bool = True,
        start_transform: Callable[[PersistedAttemptStart], PersistedAttemptStart]
        | None = None,
    ) -> None:
        self.calls: list[tuple[str, object]] = []
        self.renew_error_on_call = renew_error_on_call
        self.renew_error_code = renew_error_code
        self.renew_calls = 0
        self.started_now = started_now
        self.start_transform = start_transform

    def renew_lease(self, *, occurred_at: datetime) -> SchedulerLease:
        self.calls.append(("renew", occurred_at))
        self.renew_calls += 1
        if self.renew_calls == self.renew_error_on_call:
            raise AppProcessError(
                "lease fence rejected",
                details={"code": self.renew_error_code, "reason": "lease_expired"},
            )
        return cast("SchedulerLease", object())

    def start_attempt(self, dispatch, *, occurred_at):
        self.calls.append(("start", (dispatch, occurred_at)))
        attempt = replace(
            dispatch.attempt,
            projection=replace(
                dispatch.attempt.projection,
                status=ExperimentStatus.RUNNING,
                backtest_run_id=BacktestRunId("research-run-persisted"),
                revision=dispatch.attempt.projection.revision + 1,
                updated_at=occurred_at,
            ),
        )
        persisted = PersistedAttemptStart(
            attempt=attempt,
            fold=dispatch.fold,
            started_now=self.started_now,
        )
        if self.start_transform is not None:
            return self.start_transform(persisted)
        return persisted

    def complete_attempt(self, attempt_id, *, occurred_at):
        self.calls.append(("complete", (attempt_id, occurred_at)))
        return cast("object", object())

    def publish_attempt_artifact(self, operation):
        fence = LeaseFence(
            experiment_id=ExperimentId("experiment-1"),
            owner_token="worker-owner",
            revision=17,
            lease_until_epoch_us=int(_NOW.timestamp() * 1_000_000) + 300_000_000,
        )
        now_epoch_us = int(_NOW.timestamp() * 1_000_000)
        self.calls.append(("publish", (fence, now_epoch_us)))
        return operation(fence, now_epoch_us)

    def fail_attempt(self, attempt_id, failure_code, *, occurred_at):
        self.calls.append(("fail", (attempt_id, failure_code, occurred_at)))
        return cast("object", object())

    def poll_execution_directive(self, attempt_id, *, occurred_at):
        _ = (attempt_id, occurred_at)
        return ResearchExecutionDirective.RUN

    def record_checkpoint(self, attempt_id, checkpoint_ref, *, occurred_at):
        self.calls.append(("checkpoint", (attempt_id, checkpoint_ref, occurred_at)))
        return cast("object", object())

    def cooperative_stop_attempt(self, attempt_id, directive, *, occurred_at):
        self.calls.append(("stop", (attempt_id, directive, occurred_at)))
        return cast("object", object())


_DEFAULT_RUNNER_SELECTION_EVIDENCE = object()


class _Runner:
    def __init__(
        self,
        error: Exception | None = None,
        *,
        state: ResearchFoldRunState = ResearchFoldRunState.COMPLETED,
        poll_control: bool = False,
        selection_evidence: (
            SelectionEvidenceLog | None | object
        ) = _DEFAULT_RUNNER_SELECTION_EVIDENCE,
    ) -> None:
        self.error = error
        self.state = state
        self.poll_control = poll_control
        self.selection_evidence = (
            SelectionEvidenceLog()
            if selection_evidence is _DEFAULT_RUNNER_SELECTION_EVIDENCE
            else cast("SelectionEvidenceLog | None", selection_evidence)
        )
        self.audits: list[ResearchExecutionAudit] = []

    def run(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> ResearchFoldRunResult:
        self.audits.append(audit)
        if self.error is not None:
            raise self.error
        if self.poll_control and external_should_stop():
            return ResearchFoldRunResult(ResearchFoldRunState.STOPPED, None)
        if self.state is ResearchFoldRunState.STOPPED:
            return ResearchFoldRunResult(ResearchFoldRunState.STOPPED, None)
        return ResearchFoldRunResult(
            ResearchFoldRunState.COMPLETED,
            _report_evidence(run_id=audit.backtest_run_id),
            self.selection_evidence,
        )


class _Publisher:
    def __init__(
        self,
        error: Exception | None = None,
        *,
        receipt_factory: (
            Callable[
                [BacktestReportArtifactIdentity, BacktestReportEvidence],
                object,
            ]
            | None
        ) = None,
    ) -> None:
        self.error = error
        self._receipt_factory = receipt_factory or _artifact_receipt
        self.calls: list[
            tuple[
                BacktestReportArtifactIdentity,
                BacktestReportEvidence,
                LeaseFence,
                int,
            ]
        ] = []

    def publish(
        self,
        identity: BacktestReportArtifactIdentity,
        evidence: BacktestReportEvidence,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        self.calls.append((identity, evidence, lease_fence, now_epoch_us))
        if self.error is not None:
            raise self.error
        return cast("ArtifactRecord", self._receipt_factory(identity, evidence))


class _MemoryArtifactIndex:
    """Minimal tmp_path index for worker-to-real-adapter integration."""

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root.resolve()
        self.records: dict[str, ArtifactRecord] = {}
        self.add_calls: list[tuple[LeaseFence, int]] = []

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.relative_path == relative_path
            ),
            None,
        )

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        commit_guard()
        self.add_calls.append((lease_fence, now_epoch_us))
        assert self.get_artifact(record.artifact_id) is None
        assert self.get_artifact_by_relative_path(record.relative_path) is None
        self.records[record.artifact_id] = record

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        _ = (artifact_id, expected_revision, pinned_at, commit_guard)
        raise AssertionError("pin is outside worker publication")


def _dispatch(
    *,
    stage: ExperimentStage = ExperimentStage.WALK_FORWARD,
    role: FoldRole = FoldRole.WALK_FORWARD,
) -> ExperimentDispatch:
    queued = _fold(ExperimentStatus.QUEUED, role=role)
    first = ExecutionBundleFirstAttemptFactory(_Resolver(_semantics(role=role))).create(
        queued,
        _NOW,
    )
    attempt = AttemptView(first.spec, first.projection)
    fold = _fold(role=role)
    return ExperimentDispatch(stage, fold, attempt)


def _resumed_dispatch() -> ExperimentDispatch:
    dispatch = _dispatch()
    attempt_id = AttemptId("attempt-resumed-2")
    attempt = replace(
        dispatch.attempt,
        spec=replace(
            dispatch.attempt.spec,
            attempt_id=attempt_id,
            ordinal=2,
            parent_attempt_id=dispatch.attempt.spec.attempt_id,
            resume_from_run_id=BacktestRunId("research-run-checkpoint"),
        ),
        projection=replace(
            dispatch.attempt.projection,
            attempt_id=attempt_id,
        ),
    )
    return replace(dispatch, attempt=attempt)


def _replace_persisted_attempt_id(
    start: PersistedAttemptStart,
) -> PersistedAttemptStart:
    attempt_id = AttemptId("attempt-durable-drift")
    return replace(
        start,
        attempt=replace(
            start.attempt,
            spec=replace(start.attempt.spec, attempt_id=attempt_id),
            projection=replace(start.attempt.projection, attempt_id=attempt_id),
        ),
    )


def _replace_persisted_fold_key(
    start: PersistedAttemptStart,
) -> PersistedAttemptStart:
    key = FoldKey(
        ExperimentId("experiment-1"),
        CandidateId("candidate-1"),
        FoldId("fold-durable-drift"),
    )
    return replace(
        start,
        attempt=replace(
            start.attempt,
            spec=replace(start.attempt.spec, fold_key=key),
        ),
        fold=replace(
            start.fold,
            spec=replace(start.fold.spec, key=key),
            projection=replace(start.fold.projection, key=key),
        ),
    )


@pytest.mark.parametrize(
    ("stage", "role"),
    [
        (ExperimentStage.WALK_FORWARD, FoldRole.WALK_FORWARD),
        (ExperimentStage.HOLDOUT, FoldRole.HOLDOUT),
    ],
)
def test_worker_runs_existing_fold_runner_and_completes_under_renewed_fence(
    tmp_path: Path,
    stage: ExperimentStage,
    role: FoldRole,
) -> None:
    from ditto_analysis.research.artifact_service import ResearchArtifactService
    from ditto_application.builders.fold_selection_trace_artifact_adapter import (
        IndexedFoldSelectionTraceArtifactAdapter,
    )

    coordinator = _Coordinator()
    runner = _Runner(selection_evidence=SelectionEvidenceLog())
    publisher = _Publisher()
    trace_index = _MemoryArtifactIndex(tmp_path)
    trace_publisher = IndexedFoldSelectionTraceArtifactAdapter(
        artifact_service=ResearchArtifactService(
            artifact_root=tmp_path,
            artifact_reader=trace_index,
            artifact_writer=trace_index,
        ),
        artifact_index_reader=trace_index,
    )
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics(role=role)),
        runner=runner,
        report_publisher=publisher,
        fold_selection_trace_publisher=trace_publisher,
        clock=lambda: _NOW,
    )

    dispatch = _dispatch(stage=stage, role=role)
    result = worker.execute(dispatch, occurred_at=_NOW)

    assert result.state is ResearchWorkerState.COMPLETED
    assert result.failure_code is None
    assert result.reproduction_fingerprint == ContentHash(
        str(_semantics(role=role).reproduction_fingerprint)
    )
    assert [name for name, _ in coordinator.calls] == [
        "renew",
        "start",
        "renew",
        "renew",
        "renew",
        "publish",
        "renew",
        "complete",
    ]
    assert len(publisher.calls) == 1
    identity, evidence, fence, now_epoch_us = publisher.calls[0]
    persisted = dispatch
    assert identity.experiment_id == persisted.fold.spec.key.experiment_id
    assert identity.candidate_id == persisted.fold.spec.key.candidate_id
    assert identity.fold_id == persisted.fold.spec.key.fold_id
    assert identity.attempt_id == persisted.attempt.spec.attempt_id
    assert identity.attempt_created_at == persisted.attempt.spec.created_at
    assert identity.run_id == BacktestRunId("research-run-persisted")
    assert identity.test_window == persisted.fold.spec.test_window
    assert identity.reproduction_fingerprint == (
        persisted.attempt.spec.reproduction_fingerprint
    )
    assert evidence == _report_evidence()
    assert fence.revision == 17
    assert now_epoch_us == int(_NOW.timestamp() * 1_000_000)
    assert len(trace_index.records) == 5
    assert trace_index.add_calls == [
        (fence, now_epoch_us),
        (fence, now_epoch_us),
        (fence, now_epoch_us),
        (fence, now_epoch_us),
        (fence, now_epoch_us),
    ]
    assert len(runner.audits) == 1
    assert runner.audits[0].attempt_id == str(dispatch.attempt.spec.attempt_id)
    assert runner.audits[0].reproduction_fingerprint == (
        dispatch.attempt.spec.reproduction_fingerprint
    )
    assert runner.audits[0].backtest_run_id == "research-run-persisted"


def test_worker_fails_closed_when_selection_log_has_no_trace_publisher() -> None:
    coordinator = _Coordinator()
    report_publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(selection_evidence=SelectionEvidenceLog()),
        report_publisher=report_publisher,
        fold_selection_trace_publisher=None,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.SYSTEM_FAILED
    assert result.failure_code is ExperimentFailureCode.SYSTEM_ERROR
    assert result.error_type == "AppProcessError"
    assert report_publisher.calls == []
    assert all(name != "publish" for name, _ in coordinator.calls)
    assert [name for name, _ in coordinator.calls][-2:] == ["renew", "fail"]
    assert all(name != "complete" for name, _ in coordinator.calls)


def test_worker_does_not_publish_fake_trace_for_resume_none() -> None:
    class _UnexpectedTracePublisher:
        calls = 0

        def publish(self, *args, **kwargs):
            _ = (args, kwargs)
            self.calls += 1
            raise AssertionError("None trace must remain objectively absent")

    trace_publisher = _UnexpectedTracePublisher()
    coordinator = _Coordinator()
    runner = _Runner(selection_evidence=None)
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=runner,
        report_publisher=_Publisher(),
        fold_selection_trace_publisher=trace_publisher,
        clock=lambda: _NOW,
    )
    dispatch = _resumed_dispatch()
    assert dispatch.attempt.spec.resume_from_run_id == BacktestRunId(
        "research-run-checkpoint"
    )

    result = worker.execute(dispatch, occurred_at=_NOW)

    assert result.state is ResearchWorkerState.COMPLETED
    assert trace_publisher.calls == 0
    assert runner.audits[0].resume_from_run_id == "research-run-checkpoint"


def test_worker_rejects_fresh_none_trace_before_any_artifact_write() -> None:
    coordinator = _Coordinator()
    report_publisher = _Publisher()
    trace_publisher = _FoldSelectionTracePublisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(selection_evidence=None),
        report_publisher=report_publisher,
        fold_selection_trace_publisher=trace_publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.SYSTEM_FAILED
    assert result.failure_code is ExperimentFailureCode.SYSTEM_ERROR
    assert report_publisher.calls == []
    assert trace_publisher.calls == []
    assert all(name != "publish" for name, _ in coordinator.calls)
    assert all(name != "complete" for name, _ in coordinator.calls)


def test_worker_rejects_resumed_suffix_trace_without_checkpoint_continuity() -> None:
    coordinator = _Coordinator()
    report_publisher = _Publisher()
    trace_publisher = _FoldSelectionTracePublisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(selection_evidence=SelectionEvidenceLog()),
        report_publisher=report_publisher,
        fold_selection_trace_publisher=trace_publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_resumed_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.SYSTEM_FAILED
    assert result.failure_code is ExperimentFailureCode.SYSTEM_ERROR
    assert report_publisher.calls == []
    assert trace_publisher.calls == []
    assert all(name != "publish" for name, _ in coordinator.calls)
    assert all(name != "complete" for name, _ in coordinator.calls)


def test_worker_rejects_wrong_fold_selection_trace_receipt() -> None:
    class _WrongReceiptTracePublisher:
        calls = 0

        def publish(self, *args, **kwargs):
            _ = (args, kwargs)
            self.calls += 1
            return object()

    trace_publisher = _WrongReceiptTracePublisher()
    coordinator = _Coordinator()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(selection_evidence=SelectionEvidenceLog()),
        report_publisher=_Publisher(),
        fold_selection_trace_publisher=trace_publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.SYSTEM_FAILED
    assert result.failure_code is ExperimentFailureCode.SYSTEM_ERROR
    assert result.error_type == "ExperimentIntegrityError"
    assert trace_publisher.calls == 1
    assert all(name != "complete" for name, _ in coordinator.calls)


def test_worker_publishes_real_indexed_artifact_before_completion(
    tmp_path: Path,
) -> None:
    from ditto_analysis.research.artifact_service import ResearchArtifactService
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    index = _MemoryArtifactIndex(tmp_path)
    artifact_service = ResearchArtifactService(
        artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )
    adapter = IndexedBacktestReportArtifactAdapter(
        artifact_service=artifact_service,
        artifact_index_reader=index,
    )

    class _ArtifactAwareCoordinator(_Coordinator):
        artifact_visible_before_complete = False

        def complete_attempt(self, attempt_id, *, occurred_at):
            self.artifact_visible_before_complete = len(index.records) == 1 and all(
                (tmp_path / record.relative_path).is_file()
                for record in index.records.values()
            )
            return super().complete_attempt(attempt_id, occurred_at=occurred_at)

    coordinator = _ArtifactAwareCoordinator()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(),
        report_publisher=adapter,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.COMPLETED
    assert coordinator.artifact_visible_before_complete is True
    assert len(index.records) == 1
    record = next(iter(index.records.values()))
    assert (tmp_path / record.relative_path).is_file()


def test_worker_turns_recoverable_publication_error_into_system_failure() -> None:
    coordinator = _Coordinator()
    publisher = _Publisher(RuntimeError("artifact fsync failed"))
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.SYSTEM_FAILED
    assert result.failure_code is ExperimentFailureCode.SYSTEM_ERROR
    assert result.error_type == "RuntimeError"
    assert len(publisher.calls) == 1
    assert [name for name, _ in coordinator.calls] == [
        "renew",
        "start",
        "renew",
        "renew",
        "renew",
        "publish",
        "renew",
        "fail",
    ]


@pytest.mark.parametrize(
    "receipt_transform",
    [
        pytest.param(lambda _record: object(), id="object"),
        pytest.param(lambda _record: None, id="none"),
        pytest.param(
            lambda record: replace(
                record,
                content_hash=ContentHash(_sha("0")),
            ),
            id="content-drift",
        ),
        pytest.param(
            lambda record: replace(
                record,
                attempt_id=AttemptId("attempt-receipt-drift"),
            ),
            id="lineage-drift",
        ),
        pytest.param(
            lambda record: replace(
                record,
                schema_hash=cast("ContentHash", _sha("e")),
            ),
            id="non-nominal-schema-hash",
        ),
        pytest.param(
            lambda record: replace(record, row_count=0),
            id="row-count",
        ),
        pytest.param(
            lambda record: replace(record, byte_size=0),
            id="byte-size",
        ),
    ],
)
def test_worker_rejects_invalid_artifact_publication_receipt(
    receipt_transform: Callable[[ArtifactRecord], object],
) -> None:
    class _IntegrityNormalizingCoordinator(_Coordinator):
        publication_authority_invalidated = False

        def publish_attempt_artifact(self, operation):
            try:
                return super().publish_attempt_artifact(operation)
            except ExperimentIntegrityError as error:
                self.publication_authority_invalidated = True
                raise AppProcessError(
                    "artifact publication integrity failed",
                    details={
                        "code": "EXPERIMENT_INTEGRITY_FAILED",
                        "reason": "scheduler_persistence_integrity_failed",
                    },
                ) from error

    coordinator = _IntegrityNormalizingCoordinator()
    publisher = _Publisher(
        receipt_factory=lambda identity, evidence: receipt_transform(
            _artifact_receipt(identity, evidence)
        )
    )
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as exc_info:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    integrity_error = exc_info.value.__cause__
    assert isinstance(integrity_error, ExperimentIntegrityError)
    assert (
        integrity_error.details["reason_code"]
        == "backtest_report_artifact_receipt_drift"
    )
    assert coordinator.publication_authority_invalidated is True
    assert len(publisher.calls) == 1
    assert [name for name, _payload in coordinator.calls][-1] == "publish"
    assert all(name not in {"complete", "fail"} for name, _payload in coordinator.calls)


@pytest.mark.parametrize(
    "code",
    ["LEASE_LOST", "EXPERIMENT_INTEGRITY_FAILED"],
)
def test_worker_rethrows_terminal_publication_error_without_terminal_write(
    code: str,
) -> None:
    class _TerminalPublicationCoordinator(_Coordinator):
        def publish_attempt_artifact(self, operation):
            _ = operation
            self.calls.append(("publish", code))
            raise AppProcessError(
                "attempt artifact authority failed",
                details={"code": code, "reason": "artifact_publication_failed"},
            )

    coordinator = _TerminalPublicationCoordinator()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as exc_info:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert exc_info.value.details["code"] == code
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls][-1] == "publish"
    assert all(name not in {"fail", "complete"} for name, _payload in coordinator.calls)


def test_worker_does_not_turn_complete_error_into_reverse_failure() -> None:
    complete_error = RuntimeError("complete persistence failed")

    class _CompleteFailureCoordinator(_Coordinator):
        def complete_attempt(self, attempt_id, *, occurred_at):
            self.calls.append(("complete", (attempt_id, occurred_at)))
            raise complete_error

    coordinator = _CompleteFailureCoordinator()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    with pytest.raises(RuntimeError) as exc_info:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert exc_info.value is complete_error
    assert len(publisher.calls) == 1
    assert [name for name, _ in coordinator.calls][-2:] == ["renew", "complete"]
    assert all(name != "fail" for name, _payload in coordinator.calls)


def test_worker_rejects_non_exact_runner_result_before_publication() -> None:
    class _InvalidRunner:
        def run(
            self,
            audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> ResearchFoldRunResult:
            _ = (audit, external_should_stop)
            return cast("ResearchFoldRunResult", object())

    coordinator = _Coordinator()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_InvalidRunner(),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.SYSTEM_FAILED
    assert result.failure_code is ExperimentFailureCode.SYSTEM_ERROR
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls][-2:] == ["renew", "fail"]


@pytest.mark.parametrize(
    ("directive", "expected_state"),
    [
        (ResearchExecutionDirective.PAUSE, ResearchWorkerState.PAUSED),
        (ResearchExecutionDirective.CANCEL, ResearchWorkerState.CANCELLED),
    ],
)
def test_worker_treats_control_winning_start_race_as_normal_stop(
    directive: ResearchExecutionDirective,
    expected_state: ResearchWorkerState,
) -> None:
    class _ControlRaceCoordinator(_Coordinator):
        def __init__(self) -> None:
            super().__init__()
            self._directives = iter((ResearchExecutionDirective.RUN, directive))

        def poll_execution_directive(self, attempt_id, *, occurred_at):
            self.calls.append(("directive", (attempt_id, occurred_at)))
            return next(self._directives)

        def start_attempt(self, dispatch, *, occurred_at):
            self.calls.append(("start", (dispatch, occurred_at)))
            raise ExperimentExecutionControlChanged(
                "control won attempt start race",
                details={
                    "code": "CONTROL_CHANGED",
                    "reason": "execution_control_changed_before_start",
                },
            )

    coordinator = _ControlRaceCoordinator()
    runner = _Runner()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=runner,
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is expected_state
    assert result.failure_code is None
    assert result.error_type is None
    assert runner.audits == []
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls] == [
        "renew",
        "directive",
        "start",
        "directive",
        "renew",
        "stop",
    ]


def test_worker_rejects_control_change_with_run_intent() -> None:
    class _FalseControlRaceCoordinator(_Coordinator):
        def start_attempt(self, dispatch, *, occurred_at):
            self.calls.append(("start", (dispatch, occurred_at)))
            raise ExperimentExecutionControlChanged(
                "control won attempt start race",
                details={
                    "code": "CONTROL_CHANGED",
                    "reason": "execution_control_changed_before_start",
                },
            )

    coordinator = _FalseControlRaceCoordinator()
    runner = _Runner()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=runner,
        report_publisher=_Publisher(),
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as captured:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert captured.value.details == {
        "code": "EXPERIMENT_INTEGRITY_FAILED",
        "reason": "execution_control_change_without_stop_intent",
    }
    assert runner.audits == []
    assert [name for name, _ in coordinator.calls] == ["renew", "start"]


@pytest.mark.parametrize(
    ("start_transform", "reason"),
    [
        (_replace_persisted_attempt_id, "persisted_attempt_identity_drift"),
        (_replace_persisted_fold_key, "persisted_attempt_identity_drift"),
        (
            lambda start: replace(
                start,
                attempt=replace(
                    start.attempt,
                    spec=replace(
                        start.attempt.spec,
                        reproduction_fingerprint=ContentHash(_sha("0")),
                    ),
                ),
            ),
            "persisted_attempt_identity_drift",
        ),
        (
            lambda start: replace(
                start,
                fold=replace(
                    start.fold,
                    spec=replace(
                        start.fold.spec,
                        payload_hash=ContentHash(_sha("0")),
                    ),
                ),
            ),
            "persisted_fold_identity_drift",
        ),
        (
            lambda start: replace(
                start,
                fold=replace(
                    start.fold,
                    spec=replace(
                        start.fold.spec,
                        fold_role=FoldRole.EXPLORATION,
                    ),
                ),
            ),
            "persisted_stage_role_mismatch",
        ),
    ],
)
def test_worker_rejects_persisted_dispatch_identity_drift_before_numerics(
    start_transform: Callable[[PersistedAttemptStart], PersistedAttemptStart],
    reason: str,
) -> None:
    coordinator = _Coordinator(start_transform=start_transform)
    runner = _Runner()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=runner,
        report_publisher=_Publisher(),
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as captured:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert captured.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert captured.value.details["reason"] == reason
    assert runner.audits == []
    assert [name for name, _ in coordinator.calls] == ["renew", "start"]


def test_worker_rejects_already_running_duplicate_without_numerical_execution() -> None:
    coordinator = _Coordinator(started_now=False)
    runner = _Runner()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=runner,
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as captured:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert captured.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert captured.value.details["reason"] == "duplicate_attempt_delivery"
    assert runner.audits == []
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls] == ["renew", "start"]


@pytest.mark.parametrize(
    ("terminal_status", "failure_code", "expected_state"),
    [
        (ExperimentStatus.COMPLETED, None, ResearchWorkerState.COMPLETED),
        (
            ExperimentStatus.FAILED,
            ExperimentFailureCode.CANDIDATE_FAILED,
            ResearchWorkerState.CANDIDATE_FAILED,
        ),
        (
            ExperimentStatus.FAILED,
            ExperimentFailureCode.INPUT_HASH_MISMATCH,
            ResearchWorkerState.INPUT_FAILED,
        ),
        (
            ExperimentStatus.FAILED,
            ExperimentFailureCode.SYSTEM_ERROR,
            ResearchWorkerState.SYSTEM_FAILED,
        ),
    ],
)
def test_worker_returns_terminal_replay_without_numerics_or_second_write(
    terminal_status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
    expected_state: ResearchWorkerState,
) -> None:
    class _TerminalReplayCoordinator(_Coordinator):
        def start_attempt(self, dispatch, *, occurred_at):
            self.calls.append(("start", (dispatch, occurred_at)))
            attempt = replace(
                dispatch.attempt,
                projection=replace(
                    dispatch.attempt.projection,
                    status=terminal_status,
                    backtest_run_id=BacktestRunId("research-run-persisted"),
                    failure_code=failure_code,
                    revision=dispatch.attempt.projection.revision + 2,
                    updated_at=occurred_at,
                ),
            )
            fold = replace(
                dispatch.fold,
                projection=replace(
                    dispatch.fold.projection,
                    status=terminal_status,
                    claim_owner_token=None,
                    revision=dispatch.fold.projection.revision + 1,
                    updated_at=occurred_at,
                ),
            )
            return PersistedAttemptStart(
                attempt=attempt,
                fold=fold,
                started_now=False,
            )

    coordinator = _TerminalReplayCoordinator()
    resolver = _Resolver(_semantics())
    runner = _Runner()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=resolver,
        runner=runner,
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is expected_state
    assert result.failure_code is failure_code
    assert result.error_type is None
    assert resolver.calls == 0
    assert runner.audits == []
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls] == ["renew", "start"]


def test_concurrent_duplicate_delivery_runs_numerics_exactly_once() -> None:
    class _DuplicateCoordinator(_Coordinator):
        def __init__(self) -> None:
            super().__init__()
            self._start_count = 0
            self._start_lock = Lock()

        def start_attempt(self, dispatch, *, occurred_at):
            with self._start_lock:
                self.started_now = self._start_count == 0
                self._start_count += 1
                return super().start_attempt(dispatch, occurred_at=occurred_at)

    class _BlockingRunner(_Runner):
        def __init__(self) -> None:
            super().__init__()
            self.entered = Event()
            self.release = Event()

        def run(
            self,
            audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> ResearchFoldRunResult:
            _ = external_should_stop
            self.audits.append(audit)
            self.entered.set()
            assert self.release.wait(timeout=5)
            return ResearchFoldRunResult(
                ResearchFoldRunState.COMPLETED,
                _report_evidence(run_id=audit.backtest_run_id),
                SelectionEvidenceLog(),
            )

    coordinator = _DuplicateCoordinator()
    runner = _BlockingRunner()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=runner,
        report_publisher=_Publisher(),
        clock=lambda: _NOW,
    )
    dispatch = _dispatch()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker.execute, dispatch, occurred_at=_NOW)
        assert runner.entered.wait(timeout=5)
        duplicate = executor.submit(worker.execute, dispatch, occurred_at=_NOW)
        try:
            with pytest.raises(AppProcessError) as captured:
                duplicate.result(timeout=5)
        finally:
            runner.release.set()
        completed = first.result(timeout=5)

    assert captured.value.details["reason"] == "duplicate_attempt_delivery"
    assert completed.state is ResearchWorkerState.COMPLETED
    assert len(runner.audits) == 1


@pytest.mark.parametrize(
    ("error", "state", "failure_code"),
    [
        (
            ResearchCandidateExecutionError("candidate math failed"),
            ResearchWorkerState.CANDIDATE_FAILED,
            ExperimentFailureCode.CANDIDATE_FAILED,
        ),
        (
            AppProcessError(
                "frozen input drift",
                details={
                    "code": "REPRODUCIBILITY_FAILED",
                    "reason": "frame_content_hash_mismatch",
                },
            ),
            ResearchWorkerState.INPUT_FAILED,
            ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ),
        (
            AppProcessError(
                "invalid resolver request",
                details={"code": "SPEC_INVALID", "reason": "invalid_request"},
            ),
            ResearchWorkerState.SYSTEM_FAILED,
            ExperimentFailureCode.SYSTEM_ERROR,
        ),
        (
            research_execution_error("candidate_runtime_identity_drift"),
            ResearchWorkerState.INPUT_FAILED,
            ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ),
        (
            AppProcessError(
                "invalid reproducibility evidence",
                details={
                    "code": "REPRODUCIBILITY_FAILED",
                    "reason": "invalid_execution_evidence_shape",
                },
            ),
            ResearchWorkerState.SYSTEM_FAILED,
            ExperimentFailureCode.SYSTEM_ERROR,
        ),
        (
            RuntimeError("engine exploded"),
            ResearchWorkerState.SYSTEM_FAILED,
            ExperimentFailureCode.SYSTEM_ERROR,
        ),
    ],
)
def test_worker_persists_typed_failure_classification(
    error: Exception,
    state: ResearchWorkerState,
    failure_code: ExperimentFailureCode,
) -> None:
    coordinator = _Coordinator()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(error),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is state
    assert result.failure_code is failure_code
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls] == [
        "renew",
        "start",
        "renew",
        "renew",
        "renew",
        "fail",
    ]


def test_worker_marks_post_claim_semantic_drift_as_input_failure() -> None:
    coordinator = _Coordinator()
    resolver = _Resolver(replace(_semantics(), seed=18))
    runner = _Runner()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=resolver,
        runner=runner,
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.INPUT_FAILED
    assert result.failure_code is ExperimentFailureCode.INPUT_HASH_MISMATCH
    assert runner.audits == []
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls] == [
        "renew",
        "start",
        "renew",
        "renew",
        "renew",
        "fail",
    ]


def test_worker_renews_authority_before_resolving_persisted_semantics() -> None:
    coordinator = _Coordinator(
        renew_error_on_call=2,
        renew_error_code="LEASE_LOST",
    )
    resolver = _Resolver(_semantics())
    runner = _Runner()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=resolver,
        runner=runner,
        report_publisher=_Publisher(),
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as captured:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert captured.value.details["code"] == "LEASE_LOST"
    assert resolver.calls == 0
    assert runner.audits == []
    assert [name for name, _ in coordinator.calls] == ["renew", "start", "renew"]


@pytest.mark.parametrize("error_code", ["LEASE_LOST", "EXPERIMENT_INTEGRITY_FAILED"])
def test_worker_renews_lease_from_engine_control_and_stops_on_fence_error(
    error_code: str,
) -> None:
    coordinator = _Coordinator(
        renew_error_on_call=2,
        renew_error_code=error_code,
    )
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(poll_control=True),
        report_publisher=_Publisher(),
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as captured:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert captured.value.details["code"] == error_code
    assert [name for name, _ in coordinator.calls] == ["renew", "start", "renew"]


def test_worker_heartbeats_while_fold_runner_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_module, "_EXECUTION_HEARTBEAT_INTERVAL_SECONDS", 0.001)
    heartbeat_observed = Event()

    class _HeartbeatCoordinator(_Coordinator):
        def renew_lease(self, *, occurred_at: datetime) -> SchedulerLease:
            lease = super().renew_lease(occurred_at=occurred_at)
            if self.renew_calls >= 4:
                heartbeat_observed.set()
            return lease

    class _BlockingRunner(_Runner):
        def run(
            self,
            audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> ResearchFoldRunResult:
            assert heartbeat_observed.wait(timeout=1)
            return super().run(
                audit,
                external_should_stop=external_should_stop,
            )

    coordinator = _HeartbeatCoordinator()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_BlockingRunner(),
        report_publisher=_Publisher(),
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.COMPLETED
    assert heartbeat_observed.is_set()


def test_worker_fails_closed_when_background_heartbeat_loses_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_module, "_EXECUTION_HEARTBEAT_INTERVAL_SECONDS", 0.001)
    heartbeat_failed = Event()

    class _FailingHeartbeatCoordinator(_Coordinator):
        def renew_lease(self, *, occurred_at: datetime) -> SchedulerLease:
            try:
                return super().renew_lease(occurred_at=occurred_at)
            finally:
                if self.renew_calls >= 4:
                    heartbeat_failed.set()

    class _BlockingRunner(_Runner):
        def run(
            self,
            audit: ResearchExecutionAudit,
            *,
            external_should_stop: Callable[[], bool],
        ) -> ResearchFoldRunResult:
            assert heartbeat_failed.wait(timeout=1)
            return super().run(
                audit,
                external_should_stop=external_should_stop,
            )

    coordinator = _FailingHeartbeatCoordinator(renew_error_on_call=4)
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_BlockingRunner(),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    with pytest.raises(AppProcessError) as captured:
        worker.execute(_dispatch(), occurred_at=_NOW)

    assert captured.value.details["code"] == "LEASE_LOST"
    assert heartbeat_failed.is_set()
    assert publisher.calls == []
    assert "complete" not in [name for name, _ in coordinator.calls]
    assert "fail" not in [name for name, _ in coordinator.calls]


def test_worker_never_completes_a_cooperatively_stopped_engine() -> None:
    coordinator = _Coordinator()
    publisher = _Publisher()
    worker = _make_worker(
        coordinator=coordinator,
        semantics_resolver=_Resolver(_semantics()),
        runner=_Runner(state=ResearchFoldRunState.STOPPED),
        report_publisher=publisher,
        clock=lambda: _NOW,
    )

    result = worker.execute(_dispatch(), occurred_at=_NOW)

    assert result.state is ResearchWorkerState.SYSTEM_FAILED
    assert result.failure_code is ExperimentFailureCode.SYSTEM_ERROR
    assert publisher.calls == []
    assert [name for name, _ in coordinator.calls] == [
        "renew",
        "start",
        "renew",
        "renew",
        "renew",
        "fail",
    ]
