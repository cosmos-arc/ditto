"""Contract tests for the exact, PIT-bound research evidence facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.contracts import StrategyVersionDetailInfo
from ditto_application.exceptions import AppQueryError
from ditto_application.providers_strategy import AppStrategyQueryProvider
from ditto_application.queries.backtest import BacktestQueryFacade, RunSummary
from ditto_application.queries.evaluation import FactorEvaluationFacade
from ditto_application.queries.evidence_contracts import (
    EvidenceTemporalContext,
    FactorEvidenceQuery,
    ResearchEvidenceKind,
)
from ditto_application.queries.experiments import (
    ExperimentArtifactReadModel,
    ExperimentCandidateReadModel,
    ExperimentDetailReadModel,
    ExperimentFoldReadModel,
    ExperimentGateReadModel,
    ExperimentQueryFacade,
)
from ditto_application.queries.research_evidence import ResearchEvidenceQueryFacade
from ditto_application.queries.strategy import StrategyQueryFacade

_NOW = datetime(2026, 8, 16, 8, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _context(*, snapshot_id: str = "snapshot-1") -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=_NOW,
        knowledge_cutoff=datetime(2026, 8, 16, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 16, 6, tzinfo=UTC),
        source_snapshot_id=snapshot_id,
    )


def _experiment_detail() -> ExperimentDetailReadModel:
    return ExperimentDetailReadModel(
        experiment_id="experiment-1",
        research_cycle_id="cycle-1",
        research_cycle_hash=_HASH_A,
        strategy_version="strategy-1:v3",
        strategy_spec_hash=_HASH_B,
        snapshot_id="snapshot-1",
        status="completed",
        desired_state="run",
        stage="selection",
        failure_code=None,
        queue_ordinal=1,
        revision=4,
        created_at=_NOW,
        updated_at=_NOW,
        seed=7,
        worker_count=1,
        failure_policy="continue",
        candidate_limit=2,
        fold_run_limit=2,
        fold_protocol_id="walk-forward",
        fold_protocol_version=1,
        fold_protocol_hash=_HASH_A,
        candidates=(
            ExperimentCandidateReadModel("candidate-1", 0, True, {"window": 20}),
        ),
        folds=(
            ExperimentFoldReadModel(
                candidate_id="candidate-1",
                fold_id="fold-1",
                ordinal=0,
                role="validation",
                status="completed",
                train_start=date(2024, 1, 1),
                train_end=date(2024, 6, 30),
                test_start=date(2024, 7, 1),
                test_end=date(2024, 9, 30),
                purge_sessions=5,
                embargo_sessions=5,
                claim_owner_token=None,
                revision=2,
                updated_at=_NOW,
            ),
        ),
    )


@dataclass(frozen=True)
class _FactorReportFixture:
    factor_id: str = "momentum"
    factor_version: int = 4
    evaluation_period: tuple[str, str] = ("2024-01-01", "2024-12-31")
    holding_period: int = 5
    n_quantiles: int = 5
    dataset_id: str = "etf-daily"
    catalog_snapshot_id: str = "snapshot-1"
    universe: str = "cn-etf"
    cost_bps: float = 5.0
    n_observations: int = 100
    n_dates: int = 20
    computed_at: str = "2026-08-16T07:00:00Z"


@dataclass(frozen=True)
class _ResearchHarness:
    facade: ResearchEvidenceQueryFacade
    experiments: MagicMock
    factor: MagicMock
    strategy: MagicMock
    backtest: MagicMock


def _research_harness() -> _ResearchHarness:
    experiments = MagicMock(spec=ExperimentQueryFacade)
    experiments.get.return_value = _experiment_detail()
    experiments.list_gate_evaluations.return_value = (
        ExperimentGateReadModel(
            evaluation_id="gate-1",
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_id="fold-1",
            attempt_id="attempt-1",
            rule_id="risk",
            policy_version="v1",
            layer="hard",
            outcome="pass",
            observed={"value": 1},
            policy={"minimum": 1},
            artifact_id="artifact-1",
            payload_hash=_HASH_A,
            evaluated_at=_NOW,
        ),
    )
    experiments.list_artifacts.return_value = (
        ExperimentArtifactReadModel(
            artifact_id="artifact-1",
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_id="fold-1",
            attempt_id="attempt-1",
            artifact_kind="selection",
            relative_path="private/path.json",
            content_hash=_HASH_A,
            schema_hash=_HASH_B,
            row_count=1,
            byte_size=100,
            reproduction_fingerprint=_HASH_B,
            manifest={"schema_version": 1},
            is_pinned=True,
            pinned_at=_NOW,
            created_at=_NOW,
            revision=1,
        ),
    )
    experiments.get_review_packet.return_value = None

    factor = MagicMock(spec=FactorEvaluationFacade)
    factor.evaluate.return_value = _FactorReportFixture()

    strategy = MagicMock(spec=StrategyQueryFacade)
    strategy.get_version_detail.return_value = StrategyVersionDetailInfo(
        strategy_id="strategy-1",
        version=3,
        canonical_spec={"strategy_id": "strategy-1", "version": 3},
        spec_hash=_HASH_B,
        parent_version=2,
        state="published",
        review_outcome="approved",
        created_at="2026-08-15T00:00:00Z",
    )

    backtest = MagicMock(spec=BacktestQueryFacade)
    backtest.get_run.return_value = RunSummary(
        run_id="run-1",
        strategy_id="strategy-1",
        strategy_version="3",
        status="completed",
        config_json=(
            '{"research_snapshot_id":"snapshot-1",'
            f'"research_snapshot_manifest_hash":"{_HASH_A}"}}'
        ),
    )
    backtest.get_report.return_value = {
        "run_id": "run-1",
        "metrics": {"sharpe": 1.2},
    }
    backtest.get_replay_proof.return_value = {
        "proof_version": 2,
        "replay_run_id": "run-1",
        "is_reproducible": True,
    }

    return _ResearchHarness(
        facade=ResearchEvidenceQueryFacade(
            experiment_query=cast(ExperimentQueryFacade, experiments),
            factor_evaluation=cast(FactorEvaluationFacade, factor),
            strategy_query=cast(StrategyQueryFacade, strategy),
            backtest_query=cast(BacktestQueryFacade, backtest),
        ),
        experiments=experiments,
        factor=factor,
        strategy=strategy,
        backtest=backtest,
    )


def test_research_facade_returns_typed_exact_evidence_for_all_capabilities() -> None:
    harness = _research_harness()
    context = _context()

    experiment = harness.facade.get_experiment_evidence(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        fold_id="fold-1",
        context=context,
    )
    factor_result = harness.facade.get_factor_evidence(
        query=FactorEvidenceQuery(
            factor_id="momentum",
            factor_version=4,
            dataset_id="etf-daily",
            catalog_snapshot_id="snapshot-1",
            universe="cn-etf",
        ),
        context=context,
    )
    strategy = harness.facade.get_strategy_evidence(
        strategy_id="strategy-1",
        version=3,
        context=context,
    )
    backtest_result = harness.facade.get_backtest_evidence(
        run_id="run-1",
        strategy_id="strategy-1",
        strategy_version="3",
        dataset_id="etf-daily",
        include_replay_proof=True,
        context=context,
    )

    assert experiment.kind is ResearchEvidenceKind.EXPERIMENT
    assert experiment.artifact_refs[0].artifact_id == "artifact-1"
    assert "private/path.json" not in str(experiment.payload.value)
    assert factor_result.kind is ResearchEvidenceKind.FACTOR
    assert factor_result.subject_version == "4"
    assert strategy.kind is ResearchEvidenceKind.STRATEGY
    assert strategy.artifact_refs[0].content_hash == _HASH_B
    assert backtest_result.kind is ResearchEvidenceKind.BACKTEST
    assert {ref.artifact_kind for ref in backtest_result.artifact_refs} == {
        "backtest_report",
        "replay_proof",
        "research_snapshot_manifest",
    }
    harness.factor.evaluate.assert_called_once()
    assert harness.factor.evaluate.call_args.args == ("momentum", 4)
    harness.backtest.get_run.assert_called_once_with("run-1")


def _invoke_drift_case(operation: str, harness: _ResearchHarness) -> None:
    if operation == "experiment_snapshot":
        harness.facade.get_experiment_evidence(
            experiment_id="experiment-1",
            context=_context(snapshot_id="wrong-snapshot"),
        )
        return
    if operation == "factor_version":
        harness.factor.evaluate.return_value = _FactorReportFixture(factor_version=5)
        harness.facade.get_factor_evidence(
            query=FactorEvidenceQuery(
                factor_id="momentum",
                factor_version=4,
                dataset_id="etf-daily",
                catalog_snapshot_id="snapshot-1",
                universe="cn-etf",
            ),
            context=_context(),
        )
        return
    if operation == "strategy_identity":
        harness.strategy.get_version_detail.return_value = StrategyVersionDetailInfo(
            strategy_id="other",
            version=3,
            canonical_spec={},
            spec_hash=_HASH_B,
            parent_version=None,
            state="published",
            review_outcome="approved",
            created_at="2026-08-15T00:00:00Z",
        )
        harness.facade.get_strategy_evidence(
            strategy_id="strategy-1",
            version=3,
            context=_context(),
        )
        return
    harness.backtest.get_run.return_value = RunSummary(
        run_id="run-1",
        strategy_id="strategy-1",
        strategy_version="3",
        status="completed",
        config_json="{}",
    )
    harness.facade.get_backtest_evidence(
        run_id="run-1",
        strategy_id="strategy-1",
        strategy_version="3",
        dataset_id="etf-daily",
        context=_context(),
    )


@pytest.mark.parametrize(
    ("operation", "expected_code"),
    [
        ("experiment_snapshot", "EVIDENCE_SNAPSHOT_MISMATCH"),
        ("factor_version", "EVIDENCE_IDENTITY_MISMATCH"),
        ("strategy_identity", "EVIDENCE_IDENTITY_MISMATCH"),
        ("backtest_manifest", "EVIDENCE_PROVENANCE_INCOMPLETE"),
    ],
)
def test_research_facade_fails_closed_on_identity_or_provenance_drift(
    operation: str,
    expected_code: str,
) -> None:
    harness = _research_harness()

    with pytest.raises(AppQueryError) as exc_info:
        _invoke_drift_case(operation, harness)

    assert exc_info.value.details["code"] == expected_code


def test_strategy_provider_wires_research_evidence_facade() -> None:
    harness = _research_harness()
    provider = AppStrategyQueryProvider()

    wired = provider.research_evidence_query_facade(
        experiment_query=cast(ExperimentQueryFacade, harness.experiments),
        factor_evaluation=cast(FactorEvaluationFacade, harness.factor),
        strategy_query=cast(StrategyQueryFacade, harness.strategy),
        backtest_query=cast(BacktestQueryFacade, harness.backtest),
    )

    assert isinstance(wired, ResearchEvidenceQueryFacade)


def _expect_evidence_error(
    code: str,
    reason: str,
    factory: Callable[[], object],
) -> None:
    with pytest.raises(AppQueryError) as exc_info:
        factory()
    assert exc_info.value.details["code"] == code
    assert exc_info.value.details["reason"] == reason


class TestResearchEvidenceFailureMatrix:
    pytestmark = pytest.mark.pit

    def test_rejects_noncanonical_identity_and_versions(self) -> None:
        harness = _research_harness()
        _expect_evidence_error(
            "EVIDENCE_IDENTITY_REQUIRED",
            "missing_or_noncanonical_identity",
            lambda: harness.facade.get_experiment_evidence(
                experiment_id=" experiment-1",
                context=_context(),
            ),
        )
        _expect_evidence_error(
            "EVIDENCE_IDENTITY_REQUIRED",
            "factor_version_invalid",
            lambda: harness.facade.get_factor_evidence(
                query=FactorEvidenceQuery(
                    factor_id="momentum",
                    factor_version=cast("int", True),
                    dataset_id="etf-daily",
                    catalog_snapshot_id="snapshot-1",
                    universe="cn-etf",
                ),
                context=_context(),
            ),
        )
        _expect_evidence_error(
            "EVIDENCE_SNAPSHOT_MISMATCH",
            "factor_snapshot_mismatch",
            lambda: harness.facade.get_factor_evidence(
                query=FactorEvidenceQuery(
                    factor_id="momentum",
                    factor_version=4,
                    dataset_id="etf-daily",
                    catalog_snapshot_id="snapshot-other",
                    universe="cn-etf",
                ),
                context=_context(),
            ),
        )
        _expect_evidence_error(
            "EVIDENCE_IDENTITY_REQUIRED",
            "strategy_version_invalid",
            lambda: harness.facade.get_strategy_evidence(
                strategy_id="strategy-1",
                version=cast("int", True),
                context=_context(),
            ),
        )

    def test_experiment_read_rejects_missing_identity_and_scope(self) -> None:
        harness = _research_harness()
        harness.experiments.get.return_value = None
        _expect_evidence_error(
            "EVIDENCE_NOT_FOUND",
            "experiment_not_found",
            lambda: harness.facade.get_experiment_evidence(
                experiment_id="experiment-1",
                context=_context(),
            ),
        )

        harness = _research_harness()
        harness.experiments.get.return_value = replace(
            _experiment_detail(),
            experiment_id="experiment-other",
        )
        _expect_evidence_error(
            "EVIDENCE_IDENTITY_MISMATCH",
            "experiment_identity_mismatch",
            lambda: harness.facade.get_experiment_evidence(
                experiment_id="experiment-1",
                context=_context(),
            ),
        )

        harness = _research_harness()
        _expect_evidence_error(
            "EVIDENCE_NOT_FOUND",
            "candidate_not_found",
            lambda: harness.facade.get_experiment_evidence(
                experiment_id="experiment-1",
                candidate_id="candidate-other",
                context=_context(),
            ),
        )
        _expect_evidence_error(
            "EVIDENCE_NOT_FOUND",
            "fold_not_found",
            lambda: harness.facade.get_experiment_evidence(
                experiment_id="experiment-1",
                candidate_id="candidate-1",
                fold_id="fold-other",
                context=_context(),
            ),
        )

    def test_experiment_scope_is_bounded_and_gate_lineage_is_complete(self) -> None:
        harness = _research_harness()
        gate = harness.experiments.list_gate_evaluations.return_value[0]
        harness.experiments.list_gate_evaluations.return_value = (gate,) * 1_001
        _expect_evidence_error(
            "EVIDENCE_RESULT_TOO_LARGE",
            "experiment_scope_exceeds_limit",
            lambda: harness.facade.get_experiment_evidence(
                experiment_id="experiment-1",
                context=_context(),
            ),
        )

        harness = _research_harness()
        harness.experiments.list_artifacts.return_value = ()
        _expect_evidence_error(
            "EVIDENCE_PROVENANCE_INCOMPLETE",
            "gate_artifact_reference_missing",
            lambda: harness.facade.get_experiment_evidence(
                experiment_id="experiment-1",
                context=_context(),
            ),
        )

    def test_experiment_unscoped_read_and_review_filter_are_explicit(self) -> None:
        harness = _research_harness()
        unscoped = harness.facade.get_experiment_evidence(
            experiment_id="experiment-1",
            context=_context(),
        )
        assert unscoped.lineage == ("experiment:experiment-1",)

        harness = _research_harness()
        harness.experiments.get_review_packet.return_value = MagicMock(
            candidate_id="candidate-other"
        )
        selected = harness.facade.get_experiment_evidence(
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            context=_context(),
        )
        assert selected.payload.value["review"] is None

    def test_strategy_read_requires_an_existing_exact_version(self) -> None:
        harness = _research_harness()
        harness.strategy.get_version_detail.return_value = None
        _expect_evidence_error(
            "EVIDENCE_NOT_FOUND",
            "strategy_version_not_found",
            lambda: harness.facade.get_strategy_evidence(
                strategy_id="strategy-1",
                version=3,
                context=_context(),
            ),
        )

    @pytest.mark.parametrize(
        ("mutation", "reason"),
        [
            ("missing_run", "backtest_run_not_found"),
            ("identity", "backtest_identity_mismatch"),
            ("running", "backtest_run_not_completed"),
            ("invalid_json", "backtest_config_invalid"),
            ("non_mapping_json", "backtest_config_invalid"),
            ("missing_report", "backtest_report_missing"),
            ("missing_proof", "replay_proof_missing"),
        ],
    )
    def test_backtest_read_fails_closed_on_each_durable_gap(
        self,
        mutation: str,
        reason: str,
    ) -> None:
        harness = _research_harness()
        include_replay_proof = mutation == "missing_proof"
        if mutation == "missing_run":
            harness.backtest.get_run.return_value = None
        elif mutation == "identity":
            harness.backtest.get_run.return_value = replace(
                harness.backtest.get_run.return_value,
                strategy_id="strategy-other",
            )
        elif mutation == "running":
            harness.backtest.get_run.return_value = replace(
                harness.backtest.get_run.return_value,
                status="running",
            )
        elif mutation == "invalid_json":
            harness.backtest.get_run.return_value = replace(
                harness.backtest.get_run.return_value,
                config_json="{",
            )
        elif mutation == "non_mapping_json":
            harness.backtest.get_run.return_value = replace(
                harness.backtest.get_run.return_value,
                config_json="[]",
            )
        elif mutation == "missing_report":
            harness.backtest.get_report.return_value = None
        else:
            harness.backtest.get_replay_proof.return_value = None

        _expect_evidence_error(
            (
                "EVIDENCE_NOT_FINAL"
                if mutation == "running"
                else "EVIDENCE_IDENTITY_MISMATCH"
                if mutation == "identity"
                else "EVIDENCE_NOT_FOUND"
                if mutation == "missing_run"
                else "EVIDENCE_PROVENANCE_INCOMPLETE"
            ),
            reason,
            lambda: harness.facade.get_backtest_evidence(
                run_id="run-1",
                strategy_id="strategy-1",
                strategy_version="3",
                dataset_id="etf-daily",
                include_replay_proof=include_replay_proof,
                context=_context(),
            ),
        )

    def test_backtest_without_replay_proof_is_explicit_success(self) -> None:
        result = _research_harness().facade.get_backtest_evidence(
            run_id="run-1",
            strategy_id="strategy-1",
            strategy_version="3",
            dataset_id="etf-daily",
            include_replay_proof=False,
            context=_context(),
        )

        assert {ref.artifact_kind for ref in result.artifact_refs} == {
            "backtest_report",
            "research_snapshot_manifest",
        }
