"""
Fold-level orchestration for registered model candidates (#565 W1).

Composes the #268 capability layer into one governed fold execution: load the
fold's frozen inputs through a content-addressed data port, build the v1
forward-return labels, train the registered candidate on the training range
only, then publish the training and prediction artifacts under the caller's
scheduler lease. Publication precedes the success return, so no fold can be
reported complete without verified immutable evidence (publish-first). Every
expected refusal names its stage and reason; nothing half-published is ever
reported as success.

Contracts owned by the caller (W2 scheduler wiring): ``trained_at_epoch_us``
is pinned from durable state, never re-read from the clock, so an identical
crash-retry replays byte-stable artifact identities; unexpected exceptions
propagate and map to system failures in the worker taxonomy; test-window
predictions come from the train-frozen state here, while recovery inference
(``model_inference``) is the consumer-side path over published artifacts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Protocol, cast

import polars as pl
from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments.model_lineage import (
    ModelCandidateLineage,
    ModelPredictionRecord,
    ModelTrainingRecord,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
)
from ditto_features.errors import EvaluationError
from ditto_features.evaluation.research_labels import (
    LABEL_STATUS_MATURE,
    LABEL_STATUS_PATH_INCOMPLETE,
    LABEL_STATUS_UNFILLABLE_ENTRY,
    LABEL_STATUS_UNFILLABLE_EXIT,
    ResearchLabelFrame,
    build_forward_return_labels,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.model_artifact_publication import (
    IndexedModelArtifactSink,
    ModelArtifactPublicationContext,
)
from ditto_application.processes.experiments.model_candidates import (
    ModelFoldIsolationReport,
    ModelFoldTrainingRequest,
    ModelTrainingSuccess,
    train_model_candidate,
)
from ditto_application.research_validation_windows import ValidationFoldPlan

__all__ = [
    "MODEL_FOLD_INPUT_KINDS",
    "ModelCandidateFoldFailure",
    "ModelCandidateFoldRequest",
    "ModelCandidateFoldSuccess",
    "ModelFoldData",
    "ModelFoldDataPort",
    "ModelFoldExecutionStage",
    "ModelFoldInputBinding",
    "ModelFoldInputEvidence",
    "ModelFoldInputKind",
    "ModelFoldInputSet",
    "ModelFoldLabelStatistics",
    "execute_model_candidate_fold",
]


class ModelFoldExecutionStage(StrEnum):
    """Stage names every fold refusal is attributed to."""

    DATA = "data"
    LABEL = "label"
    TRAIN = "train"
    PUBLISH = "publish"


_HASH_LENGTH = 64


class ModelFoldInputKind(StrEnum):
    """Stable artifact kinds for the three frames one fold execution reads."""

    LABEL_PRICES = "label_prices"
    FEATURES = "features"
    CALENDAR = "calendar"


def _fold_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "model candidate fold orchestration failed closed",
        details={"code": "MODEL_CANDIDATE_FOLD_FAILED", "reason": reason, **details},
    )


def _require_hash64(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or len(value) != _HASH_LENGTH
        or value != value.strip()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise _fold_error("input_binding_hash_invalid", field=field_name)
    return value


@dataclass(frozen=True, slots=True)
class ModelFoldInputBinding:
    """Content-addressed identity of one frozen input frame."""

    kind: ModelFoldInputKind
    input_id: str
    content_hash: str
    schema_hash: str
    source_snapshot_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject nominal or partial input identities."""
        if type(cast("object", self.kind)) is not ModelFoldInputKind:
            raise _fold_error("input_binding_kind_invalid")
        if type(self.input_id) is not str or not self.input_id.strip():
            raise _fold_error("input_binding_id_invalid", kind=self.kind)
        _require_hash64(self.content_hash, "content_hash")
        _require_hash64(self.schema_hash, "schema_hash")
        raw_sources: object = self.source_snapshot_ids
        if (
            type(raw_sources) is not tuple
            or not raw_sources
            or any(
                type(item) is not str or not item or item != item.strip()
                for item in cast("tuple[object, ...]", raw_sources)
            )
        ):
            raise _fold_error(
                "input_binding_source_snapshots_invalid",
                kind=self.kind,
            )
        sources = tuple(sorted(raw_sources))
        if len(set(sources)) != len(sources):
            raise _fold_error(
                "input_binding_source_snapshots_duplicated",
                kind=self.kind,
            )
        object.__setattr__(self, "source_snapshot_ids", sources)


@dataclass(frozen=True, slots=True)
class ModelFoldInputSet:
    """The exact three frozen frames one fold execution consumes."""

    label_prices: ModelFoldInputBinding
    feature_frame: ModelFoldInputBinding
    calendar: ModelFoldInputBinding

    def __post_init__(self) -> None:
        """Require each binding to sit in its own kind-named field."""
        bindings = (self.label_prices, self.feature_frame, self.calendar)
        for binding in bindings:
            if type(cast("object", binding)) is not ModelFoldInputBinding:
                raise _fold_error("input_set_binding_invalid")
        if (
            self.label_prices.kind is not ModelFoldInputKind.LABEL_PRICES
            or self.feature_frame.kind is not ModelFoldInputKind.FEATURES
            or self.calendar.kind is not ModelFoldInputKind.CALENDAR
        ):
            raise _fold_error(
                "input_set_kind_field_mismatch",
                kinds=sorted(binding.kind.value for binding in bindings),
            )


# The evidence contract below publishes frozen input identities into plan
# payloads consumed across packages; it moved here from the private
# ``_execution_bundle_inputs`` so cross-package consumers import it from a
# public host (#572). Its failure payloads are contract — messages, reasons,
# and the REPRODUCIBILITY_FAILED code mirror the execution-bundle family
# verbatim and must not drift toward the fold-orchestration family above.
MODEL_FOLD_INPUT_KINDS = frozenset(
    {"label_prices", "features", "calendar"},
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _evidence_error(message: str, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        message,
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def _evidence_identity(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip() or "\x00" in value:
        raise _evidence_error(
            f"{field_name} must be a canonical non-empty string",
            "invalid_execution_identity",
            field=field_name,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _evidence_error(
            f"{field_name} must have a canonical UTF-8 identity",
            "invalid_execution_identity",
            field=field_name,
        ) from None
    return value


def _evidence_hash(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise _evidence_error(
            f"{field_name} must be a canonical SHA-256 digest",
            "invalid_content_hash",
            field=field_name,
        )
    return value


@dataclass(frozen=True, slots=True)
class ModelFoldInputEvidence:
    """Content-addressed identity of one frozen model-training input frame."""

    input_kind: str
    input_id: str
    content_hash: str
    schema_hash: str
    source_snapshot_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject nominal or partial training-input identities."""
        if self.input_kind not in MODEL_FOLD_INPUT_KINDS:
            raise _evidence_error(
                "model fold input kind must be exact and registered",
                "invalid_model_fold_input_evidence",
                input_kind=self.input_kind,
            )
        _evidence_identity(self.input_id, "model_fold_input_id")
        _evidence_hash(self.content_hash, "model_fold_input_content_hash")
        _evidence_hash(self.schema_hash, "model_fold_input_schema_hash")
        raw_sources: object = self.source_snapshot_ids
        if (
            type(raw_sources) is not tuple
            or not raw_sources
            or any(
                type(item) is not str or not item or item != item.strip()
                for item in cast("tuple[object, ...]", raw_sources)
            )
        ):
            raise _evidence_error(
                "model fold input must bind source snapshot identities",
                "invalid_model_fold_input_evidence",
                input_kind=self.input_kind,
            )
        sources = tuple(sorted(raw_sources))
        if len(set(sources)) != len(sources):
            raise _evidence_error(
                "model fold input source identities must be unique",
                "invalid_model_fold_input_evidence",
                input_kind=self.input_kind,
            )
        object.__setattr__(self, "source_snapshot_ids", sources)

    def as_payload(self) -> Mapping[str, object]:
        """Return the deterministic training-input identity payload."""
        return {
            "input_kind": self.input_kind,
            "input_id": self.input_id,
            "content_hash": self.content_hash,
            "schema_hash": self.schema_hash,
            "source_snapshot_ids": list(self.source_snapshot_ids),
        }


@dataclass(frozen=True, slots=True)
class ModelFoldData:
    """Verified fold frames handed over by the data port."""

    feature_frame: pl.DataFrame
    label_prices: pl.DataFrame
    trading_sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        """Check shapes only; deep schemas stay with the downstream owners."""
        if (
            type(self.feature_frame) is not pl.DataFrame
            or type(self.label_prices) is not pl.DataFrame
        ):
            raise _fold_error("fold_data_frame_invalid")
        if self.feature_frame.is_empty() or self.label_prices.is_empty():
            raise _fold_error("fold_data_frame_empty")
        raw_sessions: object = self.trading_sessions
        if (
            type(raw_sessions) is not tuple
            or not raw_sessions
            or any(
                type(item) is not date
                for item in cast("tuple[object, ...]", raw_sessions)
            )
        ):
            raise _fold_error("fold_data_sessions_invalid")


class ModelFoldDataPort(Protocol):
    """Load one fold's frozen frames from content-addressed inputs."""

    def load(self, inputs: ModelFoldInputSet) -> ModelFoldData:
        """Return verified frames or refuse with an explicit typed error."""
        ...


@dataclass(frozen=True, slots=True)
class ModelCandidateFoldRequest:
    """Complete typed identity and inputs for one governed fold execution."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId
    attempt_id: AttemptId | None
    lineage: ModelCandidateLineage
    fold: ValidationFoldPlan
    inputs: ModelFoldInputSet
    snapshot_id: str
    knowledge_cutoff_epoch_us: int
    trained_at_epoch_us: int
    reproduction_fingerprint: ContentHash

    def __post_init__(self) -> None:
        """Validate typed identity before any fold work."""
        self._require_fold_identity()
        for field_name in ("knowledge_cutoff_epoch_us", "trained_at_epoch_us"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise _fold_error("fold_clock_invalid", field=field_name)
        if self.knowledge_cutoff_epoch_us > self.trained_at_epoch_us:
            raise _fold_error(
                "knowledge_cutoff_after_training_time",
                knowledge_cutoff_epoch_us=self.knowledge_cutoff_epoch_us,
                trained_at_epoch_us=self.trained_at_epoch_us,
            )
        if type(cast("object", self.reproduction_fingerprint)) is not ContentHash:
            raise _fold_error("reproduction_fingerprint_invalid")

    def _require_fold_identity(self) -> None:
        if (
            type(cast("object", self.experiment_id)) is not ExperimentId
            or type(cast("object", self.candidate_id)) is not CandidateId
            or type(cast("object", self.fold_id)) is not FoldId
        ):
            raise _fold_error("fold_identity_invalid")
        if (
            self.attempt_id is not None
            and type(cast("object", self.attempt_id)) is not AttemptId
        ):
            raise _fold_error("fold_identity_invalid", field="attempt_id")
        if type(cast("object", self.lineage)) is not ModelCandidateLineage:
            raise _fold_error("lineage_invalid")
        if type(cast("object", self.fold)) is not ValidationFoldPlan:
            raise _fold_error("fold_plan_invalid")
        if self.fold.train_window is None:
            raise _fold_error("fold_train_window_missing")
        if type(cast("object", self.inputs)) is not ModelFoldInputSet:
            raise _fold_error("fold_inputs_invalid")
        if type(self.snapshot_id) is not str or not self.snapshot_id.strip():
            raise _fold_error("snapshot_id_invalid")


@dataclass(frozen=True, slots=True)
class ModelFoldLabelStatistics:
    """
    Fold-span label outcome counts surfaced as evaluation evidence.

    ``mature`` counts labels already mature at the fold's knowledge cutoff;
    labels whose maturity lands after the cutoff are kept in the separate
    ``mature_after_cutoff`` bucket so usable-sample denominators never
    conflate data maturity with as-of maturity.
    """

    decision_sample_count: int
    mature: int
    mature_after_cutoff: int
    unfillable_entry: int
    unfillable_exit: int
    path_incomplete: int

    def __post_init__(self) -> None:
        """Require non-negative counts that exactly partition the samples."""
        counts = (
            self.mature,
            self.mature_after_cutoff,
            self.unfillable_entry,
            self.unfillable_exit,
            self.path_incomplete,
        )
        if any(type(item) is not int or item < 0 for item in counts):
            raise _fold_error("label_statistics_invalid")
        if self.decision_sample_count != sum(counts):
            raise _fold_error(
                "label_statistics_do_not_partition",
                decision_sample_count=self.decision_sample_count,
                status_sum=sum(counts),
            )


@dataclass(frozen=True, slots=True)
class ModelCandidateFoldSuccess:
    """Published-contract outputs of one successful fold execution."""

    training: ModelTrainingRecord
    predictions: ModelPredictionRecord
    artifacts: tuple[ArtifactRecord, ...]
    labels: ModelFoldLabelStatistics
    isolation: ModelFoldIsolationReport


@dataclass(frozen=True, slots=True)
class ModelCandidateFoldFailure:
    """One stage-scoped refusal; the fold must not be reported complete."""

    stage: ModelFoldExecutionStage
    reason: str
    details: dict[str, object] = field(default_factory=dict)


def _failure_from_error(
    stage: ModelFoldExecutionStage,
    error: AppProcessError | AnalysisError,
) -> ModelCandidateFoldFailure:
    reason = error.details.get("reason")
    return ModelCandidateFoldFailure(
        stage=stage,
        # Analysis-domain refusals often carry no reason code; the exception
        # class name keeps every publish refusal stage-attributable.
        reason=(str(reason) if type(reason) is str else type(error).__name__),
        details=dict(error.details),
    )


def _label_statistics(
    labels: ResearchLabelFrame,
    fold: ValidationFoldPlan,
    *,
    knowledge_cutoff_epoch_us: int,
) -> ModelFoldLabelStatistics:
    """Count fold-span label outcomes by status, mature split at the cutoff."""
    train_window = fold.train_window
    if train_window is None:  # pragma: no cover - guarded in request validation
        raise _fold_error("fold_train_window_missing")
    status = pl.col("status")
    span = labels.frame.filter(
        (pl.col("decision_session") >= train_window.start)
        & (pl.col("decision_session") <= fold.test_window.end)
    )
    if span.height == 0:
        raise _fold_error("label_frame_fold_span_empty")
    mature_mask = status == LABEL_STATUS_MATURE
    mature_at_cutoff = span.filter(
        mature_mask & (pl.col("mature_at_epoch_us") <= knowledge_cutoff_epoch_us)
    ).height
    return ModelFoldLabelStatistics(
        decision_sample_count=span.height,
        mature=int(mature_at_cutoff),
        mature_after_cutoff=int(span.filter(mature_mask).height - mature_at_cutoff),
        unfillable_entry=int(
            span.filter(status == LABEL_STATUS_UNFILLABLE_ENTRY).height
        ),
        unfillable_exit=int(span.filter(status == LABEL_STATUS_UNFILLABLE_EXIT).height),
        path_incomplete=int(span.filter(status == LABEL_STATUS_PATH_INCOMPLETE).height),
    )


def _load_fold_data(
    request: ModelCandidateFoldRequest,
    data_port: ModelFoldDataPort,
) -> ModelFoldData:
    try:
        data = data_port.load(request.inputs)
    except AppProcessError as error:
        raise _FoldStageError(
            _failure_from_error(ModelFoldExecutionStage.DATA, error)
        ) from error
    if type(cast("object", data)) is not ModelFoldData:
        raise _FoldStageError(
            ModelCandidateFoldFailure(
                stage=ModelFoldExecutionStage.DATA,
                reason="fold_data_invalid",
            )
        )
    return data


def _build_labels(
    request: ModelCandidateFoldRequest,
    data: ModelFoldData,
) -> tuple[ResearchLabelFrame, ModelFoldLabelStatistics]:
    try:
        labels = build_forward_return_labels(
            data.label_prices,
            data.trading_sessions,
        )
        statistics = _label_statistics(
            labels,
            request.fold,
            knowledge_cutoff_epoch_us=request.knowledge_cutoff_epoch_us,
        )
    except EvaluationError as error:
        raise _FoldStageError(
            ModelCandidateFoldFailure(
                stage=ModelFoldExecutionStage.LABEL,
                reason=str(error.details.get("reason", "label_build_failed")),
                details=dict(error.details),
            )
        ) from error
    except AppProcessError as error:
        raise _FoldStageError(
            _failure_from_error(ModelFoldExecutionStage.LABEL, error)
        ) from error
    return labels, statistics


def _train_fold(
    request: ModelCandidateFoldRequest,
    data: ModelFoldData,
    labels: ResearchLabelFrame,
) -> ModelTrainingSuccess:
    try:
        training_request = ModelFoldTrainingRequest(
            experiment_id=str(request.experiment_id),
            candidate_id=str(request.candidate_id),
            fold_id=str(request.fold_id),
            lineage=request.lineage,
            fold=request.fold,
            feature_frame=data.feature_frame,
            labels=labels,
            trading_sessions=data.trading_sessions,
            snapshot_id=request.snapshot_id,
            knowledge_cutoff_epoch_us=request.knowledge_cutoff_epoch_us,
            trained_at_epoch_us=request.trained_at_epoch_us,
        )
    except AppProcessError as error:
        raise _FoldStageError(
            _failure_from_error(ModelFoldExecutionStage.TRAIN, error)
        ) from error
    result = train_model_candidate(training_request)
    if isinstance(result, ModelTrainingSuccess):
        if not result.predictions.rows:
            raise _FoldStageError(
                ModelCandidateFoldFailure(
                    stage=ModelFoldExecutionStage.TRAIN,
                    reason="test_window_predictions_empty",
                )
            )
        return result
    raise _FoldStageError(
        ModelCandidateFoldFailure(
            stage=ModelFoldExecutionStage.TRAIN,
            reason=result.reason,
            details=({} if result.details is None else dict(result.details)),
        )
    )


def _publish_fold_artifacts(
    request: ModelCandidateFoldRequest,
    result: ModelTrainingSuccess,
    sink: IndexedModelArtifactSink,
    lease_fence: LeaseFence,
    now_epoch_us: int,
) -> tuple[ArtifactRecord, ...]:
    try:
        context = ModelArtifactPublicationContext(
            experiment_id=request.experiment_id,
            candidate_id=request.candidate_id,
            fold_id=request.fold_id,
            attempt_id=request.attempt_id,
            reproduction_fingerprint=request.reproduction_fingerprint,
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )
        published_training = sink.publish_training(
            context,
            result.training,
            result.model_state_bytes,
            result.transform_state_bytes,
        )
        published_predictions = sink.publish_predictions(
            context,
            result.predictions,
            trained_at_epoch_us=request.trained_at_epoch_us,
        )
    except (AppProcessError, AnalysisError) as error:
        raise _FoldStageError(
            _failure_from_error(ModelFoldExecutionStage.PUBLISH, error)
        ) from error
    return (*published_training, published_predictions)


class _FoldStageError(Exception):
    """Internal carrier so stage failures never masquerade as system errors."""

    def __init__(self, failure: ModelCandidateFoldFailure) -> None:
        super().__init__(failure.reason)
        self.failure = failure


def execute_model_candidate_fold(
    request: ModelCandidateFoldRequest,
    *,
    data_port: ModelFoldDataPort,
    sink: IndexedModelArtifactSink,
    lease_fence: LeaseFence,
    now_epoch_us: int,
) -> ModelCandidateFoldSuccess | ModelCandidateFoldFailure:
    """Run one governed fold: load, label, train, then publish-first."""
    if type(cast("object", request)) is not ModelCandidateFoldRequest:
        raise _fold_error("fold_request_invalid")
    if type(cast("object", lease_fence)) is not LeaseFence:
        raise _fold_error("fold_lease_invalid")
    if type(now_epoch_us) is not int or now_epoch_us < 0:
        raise _fold_error("fold_clock_invalid", field="now_epoch_us")
    try:
        data = _load_fold_data(request, data_port)
        labels, statistics = _build_labels(request, data)
        result = _train_fold(request, data, labels)
        artifacts = _publish_fold_artifacts(
            request,
            result,
            sink,
            lease_fence,
            now_epoch_us,
        )
    except _FoldStageError as stage_failure:
        return stage_failure.failure
    return ModelCandidateFoldSuccess(
        training=result.training,
        predictions=result.predictions,
        artifacts=artifacts,
        labels=statistics,
        isolation=result.isolation,
    )
