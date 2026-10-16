"""
Model-candidate fold execution and binding-routed dispatch (#565 W2).

The worker-facing routing seam: an audit whose strategy binding is the
claim-time :class:`ModelCandidateExecutionBinding` routes to
:class:`ModelCandidateFoldRunner`, everything else keeps the existing
verified backtest path unchanged. The model runner composes the W1 governed
fold execution (load, label, train, publish-first) with the W3 prediction
backtest leg: it trains and publishes under the scheduler lease, projects
the published prediction record into the frozen predictions frame, registers
that frame as a content-addressed research input, upgrades the semantics to
a :class:`PredictionExecutorBinding` over the exact published artifacts, and
delegates to the existing backtest runner. The upgraded audit is what the
factory attests; the plan binding never reaches a backtest build.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from ditto_analysis.experiments import (
    AttemptId,
    CandidateId,
    ExperimentId,
    FoldId,
    FoldRole,
    LeaseFence,
)
from ditto_analysis.experiments.model_lineage import (
    ModelCandidateLineage,
    model_candidate_lineage_from_payload,
)
from ditto_analysis.experiments.persistence import DateWindow

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._execution_bundle_inputs import (
    PREDICTION_EXECUTOR_IMPLEMENTATION_KEY,
    ModelCandidateExecutionBinding,
    PredictionExecutorBinding,
)
from ditto_application.processes.experiments._worker_contract import (
    ResearchFoldRunResult,
    ResearchFoldRunState,
)
from ditto_application.processes.experiments.execution_bundle import (
    ResearchExecutionAudit,
)
from ditto_application.processes.experiments.model_artifact_publication import (
    IndexedModelArtifactSink,
)
from ditto_application.processes.experiments.model_candidate_folds import (
    ModelCandidateFoldFailure,
    ModelCandidateFoldRequest,
    ModelCandidateFoldSuccess,
    ModelFoldDataPort,
    ModelFoldInputBinding,
    ModelFoldInputKind,
    ModelFoldInputSet,
    execute_model_candidate_fold,
)
from ditto_application.processes.experiments.model_predictions_frame import (
    prediction_frame_from_record,
    prediction_frame_parquet_bytes,
    prediction_input_evidence,
)
from ditto_application.research_validation_windows import ValidationFoldPlan

__all__ = [
    "BindingRoutedResearchFoldRunner",
    "ModelCandidateFoldRunner",
    "ModelFoldPublicationAuthority",
    "PredictionFrameInputSink",
    "upgrade_model_fold_semantics",
]


def _runner_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "model candidate fold execution failed closed",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


class ModelFoldPublicationAuthority(Protocol):
    """Acquire the scheduler lease under which model artifacts publish."""

    def publish_fold_artifacts(
        self,
        callback: Callable[[LeaseFence, int], object],
    ) -> object:
        """Run one lease-fenced publication callback and return its value."""
        ...


class PredictionFrameInputSink(Protocol):
    """Register one frozen prediction frame as a loadable research input."""

    def register_prediction_frame(self, input_id: str, frame_bytes: bytes) -> None:
        """Publish immutable frame bytes; byte-equal replay is idempotent."""
        ...


class ResearchFoldRunnerProtocol(Protocol):
    """Run one audit-bound fold through a verified execution path."""

    def run(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> ResearchFoldRunResult:
        """Execute one audit-bound fold."""
        ...


class BindingRoutedResearchFoldRunner:
    """Dispatch each audit to the runner its strategy binding declares."""

    def __init__(
        self,
        *,
        backtest_runner: ResearchFoldRunnerProtocol,
        model_runner: ResearchFoldRunnerProtocol,
    ) -> None:
        self._backtest_runner = backtest_runner
        self._model_runner = model_runner

    def run(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> ResearchFoldRunResult:
        """Route by binding variant; plan bindings are model-fold work only."""
        if type(audit.semantics.strategy) is ModelCandidateExecutionBinding:
            return self._model_runner.run(
                audit,
                external_should_stop=external_should_stop,
            )
        return self._backtest_runner.run(
            audit,
            external_should_stop=external_should_stop,
        )


def _fold_input_binding(
    binding: ModelCandidateExecutionBinding,
    kind: ModelFoldInputKind,
) -> ModelFoldInputBinding:
    evidence = tuple(item for item in binding.inputs if item.input_kind == kind.value)
    if len(evidence) != 1:
        raise _runner_error(
            "model_fold_input_evidence_missing",
            input_kind=kind.value,
        )
    item = evidence[0]
    return ModelFoldInputBinding(
        kind=kind,
        input_id=item.input_id,
        content_hash=item.content_hash,
        schema_hash=item.schema_hash,
        source_snapshot_ids=item.source_snapshot_ids,
    )


def _prediction_frame_source_snapshot(
    binding: ModelCandidateExecutionBinding,
) -> str:
    """Stamp predictions with the feature frame's primary source snapshot."""
    features = tuple(item for item in binding.inputs if item.input_kind == "features")
    if (  # pragma: no cover - binding validation guarantees the shapes
        len(features) != 1 or not features[0].source_snapshot_ids
    ):
        raise _runner_error("model_fold_input_evidence_missing", input_kind="features")
    return features[0].source_snapshot_ids[0]


def upgrade_model_fold_semantics(
    audit: ResearchExecutionAudit,
    plan: ModelCandidateExecutionBinding,
    lineage: ModelCandidateLineage,
    success: ModelCandidateFoldSuccess,
    *,
    register_frame: Callable[[str, bytes], None],
) -> ResearchExecutionAudit:
    """
    Upgrade one plan-bound audit onto its published prediction artifacts.

    Verifies the trained registration and clock against the plan, projects
    the published prediction record into the frozen frame contract,
    registers those bytes as a content-addressed research input, and returns
    the audit the prediction backtest leg must be built from. The upgraded
    audit keeps the attempt identity; only the executor binding and snapshot
    inputs change.
    """
    semantics = audit.semantics
    training = success.training
    if training.registration_hash != plan.lineage_hash:
        # The trained model must be exactly the planned registration.
        raise _runner_error(
            "model_registration_drift",
            planned=plan.lineage_hash,
            trained=training.registration_hash,
        )
    if training.trained_at_epoch_us != plan.trained_at_epoch_us:
        raise _runner_error(
            "model_trained_at_drift",
            planned=plan.trained_at_epoch_us,
            trained=training.trained_at_epoch_us,
        )
    frame = prediction_frame_from_record(
        success.predictions,
        source_snapshot_id=_prediction_frame_source_snapshot(plan),
    )
    frame_bytes = prediction_frame_parquet_bytes(frame)
    input_id = ":".join(
        (
            semantics.experiment_id,
            "model-predictions",
            semantics.candidate_id,
            semantics.fold_id,
        )
    )
    evidence = prediction_input_evidence(frame_bytes, input_id=input_id)
    if any(item.input_id == input_id for item in semantics.snapshot.inputs):
        raise _runner_error("model_prediction_input_id_conflict")
    register_frame(input_id, frame_bytes)
    upgraded_binding = PredictionExecutorBinding(
        model_registration_hash=training.registration_hash,
        model_kind=lineage.model_kind.value,
        predictions_input_id=evidence.input_id,
        predictions_content_hash=evidence.content_hash,
        predictions_schema_hash=evidence.schema_hash,
        top_k=plan.top_k,
        implementation_key=PREDICTION_EXECUTOR_IMPLEMENTATION_KEY,
        executor_contract_version=1,
    )
    upgraded_semantics = replace(
        semantics,
        strategy=upgraded_binding,
        snapshot=replace(
            semantics.snapshot,
            inputs=(*semantics.snapshot.inputs, evidence),
        ),
    )
    return ResearchExecutionAudit.create(
        semantics=upgraded_semantics,
        attempt_id=audit.attempt_id,
        attempt_ordinal=audit.attempt_ordinal,
        backtest_run_id=audit.backtest_run_id,
        parent_attempt_id=audit.parent_attempt_id,
        resume_from_run_id=audit.resume_from_run_id,
        created_at=audit.created_at,
    )


class ModelCandidateFoldRunner:
    """Train, publish, then run the verified prediction backtest for one fold."""

    def __init__(
        self,
        *,
        data_port: ModelFoldDataPort,
        model_sink: IndexedModelArtifactSink,
        frame_sink: PredictionFrameInputSink,
        publication_authority: ModelFoldPublicationAuthority,
        backtest_runner: ResearchFoldRunnerProtocol,
    ) -> None:
        self._data_port = data_port
        self._model_sink = model_sink
        self._frame_sink = frame_sink
        self._publication_authority = publication_authority
        self._backtest_runner = backtest_runner

    def run(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> ResearchFoldRunResult:
        """Execute one model-candidate fold end to end under the plan binding."""
        if external_should_stop():
            return ResearchFoldRunResult(ResearchFoldRunState.STOPPED, None)
        semantics = audit.semantics
        binding = semantics.strategy
        if type(binding) is not ModelCandidateExecutionBinding:
            raise _runner_error("model_runner_requires_model_candidate_binding")
        plan = binding
        lineage = model_candidate_lineage_from_payload(plan.lineage_payload)
        if lineage.registration_hash != plan.lineage_hash:
            raise _runner_error("model_lineage_payload_drift")
        request = self._fold_request(audit, plan, lineage)
        result = self._publication_authority.publish_fold_artifacts(
            lambda lease_fence, now_epoch_us: execute_model_candidate_fold(
                request,
                data_port=self._data_port,
                sink=self._model_sink,
                lease_fence=lease_fence,
                now_epoch_us=now_epoch_us,
            )
        )
        if isinstance(result, ModelCandidateFoldFailure):
            raise _runner_error(
                "model_candidate_fold_stage_failed",
                stage=result.stage.value,
                stage_reason=result.reason,
            )
        if type(result) is not ModelCandidateFoldSuccess:
            raise _runner_error("invalid_model_candidate_fold_result")
        success = result
        if external_should_stop():
            return ResearchFoldRunResult(ResearchFoldRunState.STOPPED, None)
        upgraded_audit = upgrade_model_fold_semantics(
            audit,
            plan,
            lineage,
            success,
            register_frame=self._frame_sink.register_prediction_frame,
        )
        return self._backtest_runner.run(
            upgraded_audit,
            external_should_stop=external_should_stop,
        )

    def _fold_request(
        self,
        audit: ResearchExecutionAudit,
        plan: ModelCandidateExecutionBinding,
        lineage: ModelCandidateLineage,
    ) -> ModelCandidateFoldRequest:
        semantics = audit.semantics
        if semantics.train_start is None or semantics.train_end is None:
            raise _runner_error("model_fold_train_window_missing")
        # Fold ordinal/role carry no training semantics here (only windows and
        # purge/embargo do); the attempt ordinal is a stable stand-in for the
        # plan-graph contract while staying inside the audit's own identity.
        fold = ValidationFoldPlan(
            ordinal=audit.attempt_ordinal,
            role=FoldRole(semantics.fold_role),
            train_window=DateWindow(semantics.train_start, semantics.train_end),
            test_window=DateWindow(semantics.test_start, semantics.test_end),
            purge_sessions=semantics.purge_sessions,
            embargo_sessions=semantics.embargo_sessions,
        )
        return ModelCandidateFoldRequest(
            experiment_id=ExperimentId(semantics.experiment_id),
            candidate_id=CandidateId(semantics.candidate_id),
            fold_id=FoldId(semantics.fold_id),
            attempt_id=AttemptId(audit.attempt_id),
            lineage=lineage,
            fold=fold,
            inputs=ModelFoldInputSet(
                label_prices=_fold_input_binding(
                    plan,
                    ModelFoldInputKind.LABEL_PRICES,
                ),
                feature_frame=_fold_input_binding(plan, ModelFoldInputKind.FEATURES),
                calendar=_fold_input_binding(plan, ModelFoldInputKind.CALENDAR),
            ),
            snapshot_id=semantics.snapshot.exact_snapshot.snapshot_id,
            knowledge_cutoff_epoch_us=plan.knowledge_cutoff_epoch_us,
            trained_at_epoch_us=plan.trained_at_epoch_us,
            reproduction_fingerprint=semantics.reproduction_fingerprint,
        )
