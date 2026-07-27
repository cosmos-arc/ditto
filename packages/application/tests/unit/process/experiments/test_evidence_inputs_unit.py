"""Unit tests for R3 evidence-input assembly helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from inspect import signature

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
    SnapshotId,
    canonical_payload,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.research.artifact_measurement import measure_json_bytes
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_inputs import (
    FoldEvidenceInput,
    SnapshotManifestProjection,
    assemble_candidate_fold_evidence,
    project_snapshot_manifest,
)
from ditto_application.processes.experiments._report_evidence import (
    BACKTEST_REPORT_ARTIFACT_KIND,
    BacktestReportArtifactIdentity,
    BacktestReportEvidence,
    LoadedBacktestReportArtifact,
    backtest_report_content_hash,
)
from ditto_application.processes.experiments.comparison import CandidateFoldEvidence
from ditto_backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import FillEvent

EXPERIMENT_ID = ExperimentId("experiment-r3")
CANDIDATE_ID = CandidateId("candidate-1")
FOLD_ID = FoldId("wf-1")
ATTEMPT_ID = AttemptId("attempt-1")
BACKTEST_RUN_ID = BacktestRunId("run-1")
SNAPSHOT_ID = SnapshotId("snapshot-r3")
SNAPSHOT_HASH = ContentHash("a" * 64)
PARAMETER_HASH = ContentHash("b" * 64)
RESOLVED_SPEC_HASH = ContentHash("c" * 64)
REPRO_FINGERPRINT = ContentHash("e" * 64)
REGISTRY_HASH = ContentHash("f" * 64)
FOLD_TEST_WINDOW = DateWindow(date(2024, 1, 1), date(2024, 1, 3))
OCCURRED_AT = datetime(2024, 1, 1, tzinfo=UTC)


def _fold_view() -> FoldView:
    key = FoldKey(EXPERIMENT_ID, CANDIDATE_ID, FOLD_ID)
    spec = FoldPersistenceSpec.create(
        key,
        1,
        FoldRole.WALK_FORWARD,
        None,
        FOLD_TEST_WINDOW,
        0,
        0,
    )
    return FoldView(
        spec,
        FoldProjection(
            key=key,
            status=ExperimentStatus.COMPLETED,
            claim_owner_token=None,
            created_at=OCCURRED_AT,
            updated_at=OCCURRED_AT,
            revision=1,
        ),
    )


def _attempt_view() -> AttemptView:
    key = FoldKey(EXPERIMENT_ID, CANDIDATE_ID, FOLD_ID)
    return AttemptView(
        AttemptPersistenceSpec(
            attempt_id=ATTEMPT_ID,
            fold_key=key,
            ordinal=1,
            parent_attempt_id=None,
            resume_from_run_id=None,
            reproduction_fingerprint=REPRO_FINGERPRINT,
            created_at=OCCURRED_AT,
        ),
        AttemptProjection(
            attempt_id=ATTEMPT_ID,
            status=ExperimentStatus.COMPLETED,
            backtest_run_id=BACKTEST_RUN_ID,
            checkpoint_ref=None,
            failure_code=None,
            created_at=OCCURRED_AT,
            updated_at=OCCURRED_AT,
            revision=1,
        ),
    )


def _report_artifact(report: BacktestReport) -> LoadedBacktestReportArtifact:
    evidence = BacktestReportEvidence.from_report(report)
    identity = BacktestReportArtifactIdentity(
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        fold_id=FOLD_ID,
        attempt_id=ATTEMPT_ID,
        attempt_created_at=OCCURRED_AT,
        run_id=BACKTEST_RUN_ID,
        test_window=FOLD_TEST_WINDOW,
        reproduction_fingerprint=REPRO_FINGERPRINT,
    )
    measurement = measure_json_bytes(
        canonical_payload(evidence.canonical_payload()).json_bytes
    )
    record = ArtifactManifest.create(
        spec=ArtifactPublicationSpec(
            artifact_id=identity.artifact_id,
            experiment_id=identity.experiment_id,
            candidate_id=identity.candidate_id,
            fold_id=identity.fold_id,
            attempt_id=identity.attempt_id,
            artifact_kind=BACKTEST_REPORT_ARTIFACT_KIND,
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
    return LoadedBacktestReportArtifact(
        record=record,
        evidence=evidence,
    )


def _empty_trades() -> AggregatedTradeStatistics:
    return AggregatedTradeStatistics(
        0,
        0,
        0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )


def _alpha() -> AlphaStatistics:
    return AlphaStatistics(
        annualized_return=999.0,
        annualized_volatility=999.0,
        sharpe_ratio=999.0,
        sortino_ratio=999.0,
        max_drawdown=-99.0,
        max_drawdown_duration_days=999,
        calmar_ratio=999.0,
        information_ratio=None,
        tracking_error=None,
        beta=None,
        alpha_annualized=None,
        total_turnover=999.0,
        avg_turnover_per_rebalance=999.0,
        total_fees=999.0,
        net_return_after_cost=999.0,
        cost_drag=999.0,
    )


def _fill() -> FillEvent:
    return FillEvent(
        fill_id="fill-1",
        order_id="order-1",
        instrument_id=InstrumentId(1),
        direction=OrderSide.BUY,
        filled_quantity=2,
        fill_price=10.0,
        fee=1.0,
        slippage=0.0,
        event_time=OCCURRED_AT,
        cumulative_quantity=2,
        leaves_quantity=0,
    )


def _report() -> BacktestReport:
    return BacktestReport(
        run_id=str(BACKTEST_RUN_ID),
        period=(FOLD_TEST_WINDOW.start.isoformat(), FOLD_TEST_WINDOW.end.isoformat()),
        initial_cash=100.0,
        final_nav=110.0,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=_empty_trades(),
        alpha_stats=_alpha(),
        nav_series=(
            (FOLD_TEST_WINDOW.start.isoformat(), 100.0),
            (FOLD_TEST_WINDOW.end.isoformat(), 110.0),
        ),
        trade_log=(),
        fill_log=(_fill(),),
    )


def _fold_input(*, report: BacktestReport | None) -> FoldEvidenceInput:
    return FoldEvidenceInput(
        fold_view=_fold_view(),
        attempt_view=_attempt_view(),
        candidate_ordinal=1,
        snapshot_id=SNAPSHOT_ID,
        snapshot_hash=SNAPSHOT_HASH,
        parameter_hash=PARAMETER_HASH,
        resolved_spec_hash=RESOLVED_SPEC_HASH,
        report_artifact=None if report is None else _report_artifact(report),
        failure_reason=None,
    )


def test_assemble_candidate_fold_evidence_from_views() -> None:
    report = _report()

    evidence = assemble_candidate_fold_evidence(_fold_input(report=report))

    assert isinstance(evidence, CandidateFoldEvidence)
    assert evidence.candidate_ordinal == 1
    assert evidence.snapshot_id == SNAPSHOT_ID
    assert evidence.snapshot_hash == SNAPSHOT_HASH
    assert evidence.parameter_hash == PARAMETER_HASH
    assert evidence.resolved_spec_hash == RESOLVED_SPEC_HASH
    assert evidence.backtest_report == BacktestReportEvidence.from_report(report)
    assert evidence.result_hash == backtest_report_content_hash(report)
    assert evidence.artifact_hash == backtest_report_content_hash(report)
    assert evidence.artifact_ref is not None
    assert evidence.artifact_ref.endswith("backtest-report-evidence.json")
    assert evidence.execution_binding.fold_id == FOLD_ID
    assert evidence.execution_binding.attempt_id == ATTEMPT_ID
    assert evidence.execution_binding.run_id == BACKTEST_RUN_ID
    assert evidence.failure_reason is None


def test_assemble_candidate_fold_evidence_without_report() -> None:
    evidence = assemble_candidate_fold_evidence(_fold_input(report=None))

    assert isinstance(evidence, CandidateFoldEvidence)
    assert evidence.backtest_report is None
    assert evidence.artifact_hash is None
    assert evidence.artifact_ref is None
    assert evidence.failure_reason is None


def test_fold_input_accepts_only_the_verified_report_artifact() -> None:
    parameters = signature(FoldEvidenceInput).parameters

    assert "report_artifact" in parameters
    assert "artifact" not in parameters
    assert "backtest_report" not in parameters


def test_snapshot_manifest_projection_from_preflight_event() -> None:
    detail = {
        "preflight": {
            "executor": {
                "node_registry_manifest_hash": str(REGISTRY_HASH),
            },
            "authority": {
                "snapshot_identity": {
                    "snapshot_id": str(SNAPSHOT_ID),
                    "manifest_hash": str(SNAPSHOT_HASH),
                },
            },
            "identities": {
                "certification": {
                    "snapshot_evidence": {
                        "known_at_policy": "sample_time",
                    },
                },
            },
        },
    }

    projection = project_snapshot_manifest(detail)

    assert isinstance(projection, SnapshotManifestProjection)
    assert projection.snapshot_hash == SNAPSHOT_HASH
    assert projection.registry_hash == REGISTRY_HASH
    assert projection.pit_policy == "sample_time"


def test_project_snapshot_manifest_rejects_missing_preflight_key() -> None:
    with pytest.raises(AppProcessError):
        project_snapshot_manifest({"plan_preimage": {}})
