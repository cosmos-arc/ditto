"""Unit tests for R3 evidence-input assembly helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from ditto_analysis.experiments import (
    ArtifactRecord,
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
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_inputs import (
    FoldEvidenceInput,
    SnapshotManifestProjection,
    assemble_candidate_fold_evidence,
    project_snapshot_manifest,
)
from ditto_application.processes.experiments._report_evidence import (
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
ARTIFACT_HASH = ContentHash("d" * 64)
REPRO_FINGERPRINT = ContentHash("e" * 64)
SCHEMA_HASH = ContentHash("0" * 64)
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


def _artifact() -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id="artifact-1",
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        fold_id=FOLD_ID,
        attempt_id=ATTEMPT_ID,
        artifact_kind="backtest_result",
        relative_path="artifacts/backtest/run-1.report.json",
        content_hash=ARTIFACT_HASH,
        schema_hash=SCHEMA_HASH,
        row_count=0,
        byte_size=0,
        reproduction_fingerprint=REPRO_FINGERPRINT,
        manifest={},
        is_pinned=False,
        pinned_at=None,
        created_at=OCCURRED_AT,
        revision=1,
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
        artifact=_artifact(),
        candidate_ordinal=1,
        snapshot_id=SNAPSHOT_ID,
        snapshot_hash=SNAPSHOT_HASH,
        parameter_hash=PARAMETER_HASH,
        resolved_spec_hash=RESOLVED_SPEC_HASH,
        backtest_report=report,
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
    assert evidence.backtest_report is report
    assert evidence.result_hash == backtest_report_content_hash(report)
    assert evidence.artifact_hash == ARTIFACT_HASH
    assert evidence.artifact_ref == "artifacts/backtest/run-1.report.json"
    assert evidence.execution_binding.fold_id == FOLD_ID
    assert evidence.execution_binding.attempt_id == ATTEMPT_ID
    assert evidence.execution_binding.run_id == BACKTEST_RUN_ID
    assert evidence.failure_reason is None


def test_assemble_candidate_fold_evidence_without_report() -> None:
    evidence = assemble_candidate_fold_evidence(_fold_input(report=None))

    assert isinstance(evidence, CandidateFoldEvidence)
    assert evidence.backtest_report is None
    assert evidence.artifact_hash == ARTIFACT_HASH
    assert evidence.failure_reason is None


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
