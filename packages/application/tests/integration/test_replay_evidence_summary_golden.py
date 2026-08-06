"""Synthetic restored-run replay evidence golden test.

This test uses real JSON artifact files with lightweight in-memory read models.
It proves the backend query surface can compose restored-run report provenance
with replay proof evidence without external market data, broker adapters or UI.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import orjson
import polars as pl
from ditto_analysis.experiments import (
    AttemptId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ContentHash,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldProtocolSpec,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SnapshotId,
    StrategyVersion,
)
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    AttemptPersistenceSpec,
    AttemptProjection,
    DateWindow,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    ResearchCycleIdentity,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.processes.execution.replay_process import (
    IndexedResearchReplayArtifactReader,
    build_research_replay_metadata,
)
from ditto_application.queries.backtest import BacktestQueryFacade
from ditto_backtest.manifest import RunManifest, RunMode, serialize_manifest
from ditto_backtest.manifest_types import ReplayArtifactRef, ResearchReplayEvidence
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord
from ditto_strategy.storage.sqlite.services.backtest_artifact_reader import (
    BacktestArtifactReader,
)


class _RunModel:
    """Minimal run read model for synthetic artifact composition."""

    def __init__(self, runs: dict[str, StrategyRunRecord]) -> None:
        self._runs = runs

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        return self._runs.get(run_id)

    def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StrategyRunRecord]:
        _ = (strategy_id, status, start_date, end_date, limit, offset)
        return list(self._runs.values())


class _ArtifactService:
    """Minimal artifact service exposing the query-side list contract."""

    def __init__(self, artifacts: list[StrategyArtifactRecord]) -> None:
        self._artifacts = artifacts

    def list_artifacts(self) -> list[StrategyArtifactRecord]:
        return self._artifacts


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def test_restored_run_replay_evidence_summary_reads_real_artifacts(
    tmp_path: Path,
) -> None:
    """Synthetic golden: report provenance and proof provenance stay aligned."""
    restored_dir = tmp_path / "run-restored"
    replay_dir = tmp_path / "run-replay"
    resume_provenance: dict[str, object] = {
        "from_run_id": "run-root",
        "checkpoint_trade_date": "2026-01-31",
        "checkpoint_completed_days": 21,
        "checkpoint_total_days": 60,
        "checkpoint_nav": 1_020_000.0,
        "checkpoint_order_count": 4,
        "checkpoint_fill_count": 4,
        "account_state_hash": "sha256:account",
        "settlement_state_hash": "sha256:settlement",
        "runtime_state_hash": "sha256:runtime",
    }

    _write_json(
        restored_dir / "backtest_report.json",
        {
            "run_id": "run-restored",
            "period": {"start": "2026-02-02", "end": "2026-03-31"},
            "initial_cash": 1_000_000.0,
            "final_nav": 1_080_000.0,
            "resume_provenance": resume_provenance,
        },
    )
    _write_json(
        replay_dir / "replay_proof.json",
        {
            "proof_version": 1,
            "original_run_id": "run-restored",
            "replay_run_id": "run-replay",
            "is_reproducible": True,
            "nav_correlation": 1.0,
            "max_nav_diff_bps": 0.0,
            "input_data_match": True,
            "manifest_diff": {"has_diff": False},
            "fill_match": True,
            "account_state_match": True,
            "original_resume_provenance": resume_provenance,
        },
    )

    runs = {
        run_id: StrategyRunRecord(
            run_id=run_id,
            strategy_id="momentum-etf",
            status="completed",
        )
        for run_id in ("run-restored", "run-replay")
    }
    artifact_service = _ArtifactService(
        [
            StrategyArtifactRecord(
                artifact_id="artifact-run-restored",
                strategy_id="momentum-etf",
                run_id="run-restored",
                artifact_type=ArtifactKind.BACKTEST_REPORT,
                file_path=str(restored_dir),
            ),
            StrategyArtifactRecord(
                artifact_id="replay-proof-run-replay",
                strategy_id="momentum-etf",
                run_id="run-replay",
                artifact_type=ArtifactKind.REPLAY_PROOF,
                file_path=str(replay_dir),
            ),
        ]
    )
    facade = BacktestQueryFacade(
        trade_facade=MagicMock(),
        run_model=_RunModel(runs),
        audit_service=MagicMock(),
        artifact_service=artifact_service,
        artifact_reader=BacktestArtifactReader(),
    )

    summary = facade.get_replay_evidence_summary("run-replay")

    assert summary is not None
    assert summary.original_run_id == "run-restored"
    assert summary.replay_run_id == "run-replay"
    assert summary.is_reproducible is True
    assert summary.input_data_match is True
    assert summary.fill_match is True
    assert summary.account_state_match is True
    assert summary.report_resume_provenance == resume_provenance
    assert summary.proof_resume_provenance == resume_provenance
    assert summary.resume_provenance_match is True
    assert summary.missing_sections == ()


_INDEXED_NOW = datetime(2026, 7, 23, 4, 0, tzinfo=UTC)
_INDEXED_NOW_US = 1_769_000_000_000_000
_EMPTY_PARAMETER_HASH = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


def _indexed_candidate(ordinal: int, *, baseline: bool) -> CandidateSpec:
    return CandidateSpec(
        candidate_id=CandidateId(f"candidate-{ordinal}"),
        ordinal=ordinal,
        is_baseline=baseline,
        parameters={"lookback": ordinal * 20},
    )


def _indexed_launch_spec() -> ExperimentLaunchSpec:
    candidates = (
        _indexed_candidate(1, baseline=True),
        _indexed_candidate(2, baseline=False),
    )
    objective = PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=CandidateId("candidate-1"),
        economic_rationale="Golden replay evidence boundary.",
        trial_family=TrialFamilyDeclaration(
            "replay-golden-v1",
            tuple(
                LogicalTrialIdentity(
                    ExperimentId("experiment-1"),
                    candidate.candidate_id,
                    candidate.ordinal,
                    candidate.parameter_hash,
                    TrialKind.CURRENT,
                )
                for candidate in candidates
            ),
        ),
    )
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId("experiment-1"),
        strategy_version=StrategyVersion("golden@1"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-certified-1"),
        candidates=candidates,
        execution_bindings=tuple(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash(f"{candidate.ordinal + 16:064x}"),
            )
            for candidate in candidates
        ),
        promotion_objective=objective,
        fold_protocol=FoldProtocolSpec(
            protocol_id="replay-golden",
            protocol_version=1,
            protocol_hash=ContentHash("b" * 64),
        ),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(candidate_limit=8, fold_run_limit=16),
        desired_state=ExperimentDesiredState.RUN,
        created_at=_INDEXED_NOW,
    )


def _prepare_indexed_attempt(
    writer: SQLiteExperimentWriter,
) -> object:
    experiment_id = ExperimentId("experiment-1")
    fold_key = FoldKey(
        experiment_id,
        CandidateId("candidate-1"),
        FoldId("fold-1"),
    )
    writer.create_experiment(
        ResearchCycleIdentity("cycle-replay-golden", ContentHash("c" * 64)),
        _indexed_launch_spec(),
        ExperimentRecord(
            experiment_id=experiment_id,
            status=ExperimentStatus.DRAFT,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=_INDEXED_NOW,
        ),
    )
    fold_spec = FoldPersistenceSpec.create(
        key=fold_key,
        ordinal=1,
        fold_role=FoldRole.WALK_FORWARD,
        train_window=DateWindow(date(2024, 1, 2), date(2025, 12, 31)),
        test_window=DateWindow(date(2026, 1, 5), date(2026, 3, 31)),
        purge_sessions=2,
        embargo_sessions=1,
    )
    writer.add_fold(
        fold_spec,
        FoldProjection(
            key=fold_key,
            status=ExperimentStatus.QUEUED,
            claim_owner_token=None,
            created_at=_INDEXED_NOW,
            updated_at=_INDEXED_NOW,
            revision=0,
        ),
    )
    writer.enqueue_experiment(
        experiment_id,
        expected_revision=0,
        occurred_at=_INDEXED_NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=ExperimentEnqueueFence.create(gates=(), folds=(fold_spec,)),
    )
    lease = writer.try_claim_lease(
        experiment_id,
        "owner-replay-golden",
        expected_revision=0,
        now_epoch_us=_INDEXED_NOW_US,
        lease_until_epoch_us=_INDEXED_NOW_US + 100,
    )
    assert lease is not None
    writer.transition_scheduled_experiment(
        experiment_id,
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=1,
        lease_fence=lease.fence,
        now_epoch_us=_INDEXED_NOW_US + 1,
        occurred_at=_INDEXED_NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="experiment_started",
        detail={},
    )
    writer.claim_fold_and_add_attempt(
        fold_key,
        AttemptPersistenceSpec(
            attempt_id=AttemptId("attempt-1"),
            fold_key=fold_key,
            ordinal=1,
            parent_attempt_id=None,
            resume_from_run_id=None,
            reproduction_fingerprint=ContentHash("d" * 64),
            created_at=_INDEXED_NOW,
        ),
        AttemptProjection(
            attempt_id=AttemptId("attempt-1"),
            status=ExperimentStatus.QUEUED,
            backtest_run_id=None,
            checkpoint_ref=None,
            failure_code=None,
            created_at=_INDEXED_NOW,
            updated_at=_INDEXED_NOW,
            revision=0,
        ),
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=_INDEXED_NOW_US + 2,
        occurred_at=_INDEXED_NOW,
    )
    return lease


def _publication_spec(
    artifact_id: str, kind: str, suffix: str
) -> ArtifactPublicationSpec:
    return ArtifactPublicationSpec(
        artifact_id=artifact_id,
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId("attempt-1"),
        artifact_kind=kind,
        relative_path=(
            "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
            f"attempts/attempt-1/{artifact_id}.{suffix}"
        ),
        reproduction_fingerprint=ContentHash("d" * 64),
        audit={
            "run_id": "run-indexed",
            "attempt_id": "attempt-1",
            "created_at": _INDEXED_NOW.isoformat(),
        },
        created_at=_INDEXED_NOW,
    )


def _replay_ref(record: ArtifactRecord) -> ReplayArtifactRef:
    manifest = record.manifest
    assert isinstance(manifest, Mapping)
    return ReplayArtifactRef(
        artifact_id=record.artifact_id,
        artifact_kind=record.artifact_kind,
        artifact_format=str(manifest["format"]),
        content_hash=str(record.content_hash),
        schema_hash=str(record.schema_hash),
        row_count=record.row_count,
        byte_size=record.byte_size,
    )


def test_indexed_replay_reader_golden_uses_temp_schema_v1_and_verified_files(
    tmp_path: Path,
) -> None:
    """Golden: production adapter reads a same-attempt bundle from temp Schema v1."""
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    lease = _prepare_indexed_attempt(writer)
    service = ResearchArtifactService(
        artifact_root=tmp_path / "legacy",
        indexed_artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    try:
        nav_record = service.publish_indexed_parquet(
            _publication_spec("artifact-nav", "nav", "parquet"),
            pl.DataFrame({"trade_date": ["2026-01-05"], "nav": [1.01]}),
            lease_fence=lease.fence,
            now_epoch_us=_INDEXED_NOW_US + 3,
        )
        summary_record = service.publish_indexed_json(
            _publication_spec("artifact-summary", "summary", "json"),
            {"run_id": "run-indexed", "nav_series": [1.0, 1.01]},
            lease_fence=lease.fence,
            now_epoch_us=_INDEXED_NOW_US + 4,
        )
        evidence = ResearchReplayEvidence(
            reproduction_fingerprint="d" * 64,
            key_result_summary_artifact_id="artifact-summary",
            required_artifacts=(
                _replay_ref(nav_record),
                _replay_ref(summary_record),
            ),
        )
        manifest = RunManifest(
            run_id="run-indexed",
            strategy_id="golden",
            strategy_version="1",
            mode=RunMode.BACKTEST,
            created_at=_INDEXED_NOW.isoformat(),
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash=_EMPTY_PARAMETER_HASH,
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
            replay_evidence=evidence,
        )
        manifest_payload = orjson.loads(serialize_manifest(manifest))
        manifest_record = service.publish_indexed_json(
            _publication_spec("artifact-manifest", "run_manifest", "json"),
            manifest_payload,
            lease_fence=lease.fence,
            now_epoch_us=_INDEXED_NOW_US + 5,
        )
        marker = build_research_replay_metadata(
            manifest_artifact=_replay_ref(manifest_record),
            replay_evidence=evidence,
        )
        strategy_service = _ArtifactService(
            [
                StrategyArtifactRecord(
                    artifact_id="strategy-run-indexed",
                    strategy_id="golden",
                    run_id="run-indexed",
                    artifact_type=ArtifactKind.BACKTEST_REPORT,
                    file_path=str(tmp_path / "unused-legacy-path"),
                    metadata=marker,
                )
            ]
        )
        adapter = IndexedResearchReplayArtifactReader(
            strategy_artifact_service=strategy_service,
            artifact_index_reader=reader,
            artifact_content_reader=service,
        )

        bundle = adapter.read_bundle("run-indexed")

        assert bundle.manifest_payload["run_id"] == "run-indexed"
        assert bundle.report_payload["nav_series"] == [1.0, 1.01]
        assert bundle.reproduction_fingerprint == "d" * 64
        assert tuple(item.artifact_id for item in bundle.verified_artifacts) == (
            "artifact-nav",
            "artifact-summary",
        )
    finally:
        database.close_all()
