"""Application-owned read models for the durable experiment control plane."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import cast

from ditto_analysis.errors import AnalysisError, ExperimentIdentityError
from ditto_analysis.experiments import (
    CandidateId,
    ExperimentId,
    ExperimentProjection,
    ExperimentReaderProtocol,
    ExperimentStatus,
    FoldView,
    GateEvaluationRecord,
    ReviewPacket,
    review_blocked_by_hard_gates,
)

from ditto_application.exceptions import AppQueryError

__all__ = [
    "ExperimentCandidateReadModel",
    "ExperimentDetailReadModel",
    "ExperimentFoldReadModel",
    "ExperimentGateReadModel",
    "ExperimentQueryFacade",
    "ExperimentReviewPacketReadModel",
    "ReviewGateOutcome",
    "build_review_packet_read_model",
]

type ReadScalar = str | bool | int | float | None
type ReadValue = ReadScalar | tuple[ReadValue, ...] | Mapping[str, ReadValue]

_DETAIL_READ_ATTEMPTS = 2
_PARENTS_WITHOUT_RUNNING_FOLDS = frozenset(
    {
        ExperimentStatus.DRAFT,
        ExperimentStatus.BLOCKED,
        ExperimentStatus.QUEUED,
        ExperimentStatus.PAUSED,
    }
)
_TERMINAL_PARENT_STATUSES = frozenset(
    {
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.COMPLETED_WITH_FAILURES,
        ExperimentStatus.FAILED,
    }
)
_LIVE_FOLD_STATUSES = frozenset(
    {
        ExperimentStatus.QUEUED,
        ExperimentStatus.RUNNING,
    }
)


def _read_error(reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"experiment read model is inconsistent: {reason}",
        details={
            "code": "EXPERIMENT_READ_INTEGRITY",
            "reason": reason,
            **details,
        },
    )


def _freeze_read_value(value: object) -> ReadValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        raw_mapping = cast("Mapping[object, object]", value)
        frozen: dict[str, ReadValue] = {}
        for key, item in raw_mapping.items():
            if not isinstance(key, str):
                raise _read_error(
                    "non_string_persisted_mapping_key",
                    key_type=type(key).__name__,
                )
            frozen[key] = _freeze_read_value(item)
        return MappingProxyType(frozen)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return tuple(_freeze_read_value(item) for item in sequence)
    raise _read_error("unsupported_persisted_value", value_type=type(value).__name__)


def _analysis_read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except AnalysisError as exc:
        raise AppQueryError(
            "experiment persistence read failed",
            details={"code": "EXPERIMENT_READ_FAILED", **exc.details},
        ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentCandidateReadModel:
    """One immutable candidate projected into application-owned scalars."""

    candidate_id: str
    ordinal: int
    is_baseline: bool
    parameters: Mapping[str, ReadValue]


@dataclass(frozen=True, slots=True)
class ExperimentFoldReadModel:
    """One persisted fold specification and its current projection."""

    candidate_id: str
    fold_id: str
    ordinal: int
    role: str
    status: str
    train_start: date | None
    train_end: date | None
    test_start: date
    test_end: date
    purge_sessions: int
    embargo_sessions: int
    claim_owner_token: str | None
    revision: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ExperimentDetailReadModel:
    """Current durable server truth; draft fold assembly may still be partial."""

    experiment_id: str
    research_cycle_id: str
    research_cycle_hash: str
    strategy_version: str
    strategy_spec_hash: str
    snapshot_id: str
    status: str
    desired_state: str
    stage: str
    failure_code: str | None
    queue_ordinal: int | None
    revision: int
    created_at: datetime
    updated_at: datetime
    seed: int
    worker_count: int
    failure_policy: str
    candidate_limit: int
    fold_run_limit: int
    fold_protocol_id: str
    fold_protocol_version: int
    fold_protocol_hash: str
    candidates: tuple[ExperimentCandidateReadModel, ...]
    folds: tuple[ExperimentFoldReadModel, ...]

    @property
    def candidate_count(self) -> int:
        """Count the explicit baseline and every binder candidate."""
        return len(self.candidates)

    @property
    def fold_count(self) -> int:
        """Count all currently persisted folds."""
        return len(self.folds)


@dataclass(frozen=True, slots=True)
class ExperimentGateReadModel:
    """One append-only preflight or governance gate evaluation."""

    evaluation_id: str
    experiment_id: str
    candidate_id: str | None
    fold_id: str | None
    attempt_id: str | None
    rule_id: str
    policy_version: str
    layer: str
    outcome: str
    observed: ReadValue
    policy: ReadValue
    artifact_id: str | None
    payload_hash: str
    evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewGateOutcome:
    """One gate rule's identity and outcome in a review packet read model."""

    rule_id: str
    layer: str
    outcome: str


@dataclass(frozen=True, slots=True)
class ExperimentReviewPacketReadModel:
    """Application view of one immutable promotion review packet."""

    experiment_id: str
    candidate_id: str | None
    bundle_hash: str
    hard_review_blocked: bool
    gate_outcomes: tuple[ReviewGateOutcome, ...]


def build_review_packet_read_model(
    packet: ReviewPacket,
) -> ExperimentReviewPacketReadModel:
    """Derive an application read model from an immutable review packet."""
    return ExperimentReviewPacketReadModel(
        experiment_id=packet.lineage.experiment_id,
        candidate_id=packet.lineage.candidate_id,
        bundle_hash=str(packet.bundle_hash),
        hard_review_blocked=review_blocked_by_hard_gates(packet.gate_evaluations),
        gate_outcomes=tuple(
            ReviewGateOutcome(
                rule_id=evaluation.rule_id,
                layer=evaluation.layer.value,
                outcome=evaluation.outcome.value,
            )
            for evaluation in packet.gate_evaluations
        ),
    )


class ExperimentQueryFacade:
    """Map analysis-owned persistence contracts into application read models."""

    def __init__(self, *, reader: ExperimentReaderProtocol) -> None:
        self._reader = reader

    def get(self, experiment_id: str) -> ExperimentDetailReadModel | None:
        """
        Return one aggregate, failing closed on partial roots or candidates.

        Fold rows are reported exactly as persisted. A draft experiment may expose
        an incomplete enqueue-last saga until the same launch command resumes it.
        """
        typed_id = self._experiment_id(experiment_id)
        root_seen = False
        initial_revision: int | None = None
        observed_revision: int | None = None
        for _attempt in range(_DETAIL_READ_ATTEMPTS):
            projection = _analysis_read(
                lambda: self._reader.get_experiment_projection(typed_id)
            )
            if projection is None:
                if not root_seen:
                    return None
                break
            root_seen = True
            initial_revision = projection.revision
            detail = self._assemble_detail(experiment_id, typed_id, projection)
            observed = _analysis_read(
                lambda: self._reader.get_experiment_projection(typed_id)
            )
            observed_revision = None if observed is None else observed.revision
            if observed == projection:
                self._validate_fold_parent_coherence(
                    experiment_id,
                    projection.record.status,
                    detail.folds,
                )
                return detail

        raise _read_error(
            "concurrent_experiment_update",
            experiment_id=experiment_id,
            attempts=_DETAIL_READ_ATTEMPTS,
            initial_revision=initial_revision,
            observed_revision=observed_revision,
        )

    def _assemble_detail(
        self,
        experiment_id: str,
        typed_id: ExperimentId,
        projection: ExperimentProjection,
    ) -> ExperimentDetailReadModel:
        """Assemble one candidate/fold view bracketed by the caller's root reads."""
        cycle = _analysis_read(
            lambda: self._reader.get_research_cycle_identity(typed_id)
        )
        spec = _analysis_read(lambda: self._reader.get_launch_spec(typed_id))
        if cycle is None or spec is None:
            raise _read_error(
                "partial_experiment_aggregate",
                experiment_id=experiment_id,
            )
        if (
            spec.experiment_id != typed_id
            or projection.record.experiment_id != typed_id
        ):
            raise _read_error(
                "experiment_identity_mismatch",
                experiment_id=experiment_id,
            )

        candidates = tuple(
            sorted(
                _analysis_read(lambda: self._reader.list_candidates(typed_id)),
                key=lambda candidate: candidate.ordinal,
            )
        )
        if candidates != tuple(spec.candidates):
            raise _read_error(
                "candidate_aggregate_mismatch",
                experiment_id=experiment_id,
            )
        candidate_ordinals = {
            candidate.candidate_id: candidate.ordinal for candidate in candidates
        }
        fold_views = tuple(
            sorted(
                _analysis_read(lambda: self._reader.list_folds(typed_id)),
                key=lambda view: (
                    candidate_ordinals.get(view.spec.key.candidate_id, 2**31),
                    view.spec.ordinal,
                    str(view.spec.key.fold_id),
                ),
            )
        )
        folds = tuple(
            self._fold_model(typed_id, candidate_ordinals, view) for view in fold_views
        )
        candidate_models = tuple(
            ExperimentCandidateReadModel(
                candidate_id=str(candidate.candidate_id),
                ordinal=candidate.ordinal,
                is_baseline=candidate.is_baseline,
                parameters=cast(
                    "Mapping[str, ReadValue]",
                    _freeze_read_value(candidate.parameters),
                ),
            )
            for candidate in candidates
        )
        record = projection.record
        return ExperimentDetailReadModel(
            experiment_id=experiment_id,
            research_cycle_id=cycle.cycle_id,
            research_cycle_hash=str(cycle.cycle_hash),
            strategy_version=str(spec.strategy_version),
            strategy_spec_hash=str(spec.strategy_spec_hash),
            snapshot_id=str(spec.snapshot_id),
            status=record.status.value,
            desired_state=record.desired_state.value,
            stage=record.stage.value,
            failure_code=(
                None if record.failure_code is None else record.failure_code.value
            ),
            queue_ordinal=projection.queue_ordinal,
            revision=projection.revision,
            created_at=record.created_at,
            updated_at=projection.updated_at,
            seed=spec.seed,
            worker_count=spec.worker_count,
            failure_policy=spec.failure_policy.value,
            candidate_limit=spec.budget.candidate_limit,
            fold_run_limit=spec.budget.fold_run_limit,
            fold_protocol_id=spec.fold_protocol.protocol_id,
            fold_protocol_version=spec.fold_protocol.protocol_version,
            fold_protocol_hash=str(spec.fold_protocol.protocol_hash),
            candidates=candidate_models,
            folds=folds,
        )

    @staticmethod
    def _validate_fold_parent_coherence(
        experiment_id: str,
        parent_status: ExperimentStatus,
        folds: tuple[ExperimentFoldReadModel, ...],
    ) -> None:
        """Reject stable parent/child states forbidden by persistence transitions."""
        for fold in folds:
            fold_status = ExperimentStatus(fold.status)
            running_under_inactive_parent = (
                fold_status is ExperimentStatus.RUNNING
                and parent_status in _PARENTS_WITHOUT_RUNNING_FOLDS
            )
            live_under_terminal_parent = (
                parent_status in _TERMINAL_PARENT_STATUSES
                and fold_status in _LIVE_FOLD_STATUSES
            )
            if not (running_under_inactive_parent or live_under_terminal_parent):
                continue
            raise _read_error(
                "fold_parent_status_mismatch",
                experiment_id=experiment_id,
                parent_status=parent_status.value,
                candidate_id=fold.candidate_id,
                fold_id=fold.fold_id,
                fold_status=fold_status.value,
            )

    def get_gate(
        self,
        experiment_id: str,
        evaluation_id: str,
    ) -> ExperimentGateReadModel | None:
        """Return one deterministic gate without allowing cross-experiment reads."""
        typed_id = self._experiment_id(experiment_id)
        record = _analysis_read(lambda: self._reader.get_gate_evaluation(evaluation_id))
        if record is None:
            return None
        if record.experiment_id != typed_id:
            raise _read_error(
                "gate_experiment_mismatch",
                experiment_id=experiment_id,
                evaluation_id=evaluation_id,
            )
        return self._gate_model(record)

    @staticmethod
    def _experiment_id(value: str) -> ExperimentId:
        try:
            return ExperimentId(value)
        except ExperimentIdentityError as exc:
            raise AppQueryError(
                "experiment_id is invalid",
                details={"code": "SPEC_INVALID", **exc.details},
            ) from exc

    @staticmethod
    def _fold_model(
        experiment_id: ExperimentId,
        candidate_ordinals: Mapping[CandidateId, int],
        view: FoldView,
    ) -> ExperimentFoldReadModel:
        spec = view.spec
        projection = view.projection
        if (
            spec.key.experiment_id != experiment_id
            or projection.key != spec.key
            or spec.key.candidate_id not in candidate_ordinals
        ):
            raise _read_error(
                "fold_lineage_mismatch",
                fold_id=str(spec.key.fold_id),
            )
        train_window = spec.train_window
        return ExperimentFoldReadModel(
            candidate_id=str(spec.key.candidate_id),
            fold_id=str(spec.key.fold_id),
            ordinal=spec.ordinal,
            role=spec.fold_role.value,
            status=projection.status.value,
            train_start=None if train_window is None else train_window.start,
            train_end=None if train_window is None else train_window.end,
            test_start=spec.test_window.start,
            test_end=spec.test_window.end,
            purge_sessions=spec.purge_sessions,
            embargo_sessions=spec.embargo_sessions,
            claim_owner_token=projection.claim_owner_token,
            revision=projection.revision,
            updated_at=projection.updated_at,
        )

    @staticmethod
    def _gate_model(record: GateEvaluationRecord) -> ExperimentGateReadModel:
        return ExperimentGateReadModel(
            evaluation_id=record.evaluation_id,
            experiment_id=str(record.experiment_id),
            candidate_id=(
                None if record.candidate_id is None else str(record.candidate_id)
            ),
            fold_id=None if record.fold_id is None else str(record.fold_id),
            attempt_id=(None if record.attempt_id is None else str(record.attempt_id)),
            rule_id=record.rule_id,
            policy_version=record.policy_version,
            layer=record.layer,
            outcome=record.outcome,
            observed=_freeze_read_value(record.observed),
            policy=_freeze_read_value(record.policy),
            artifact_id=record.artifact_id,
            payload_hash=str(record.payload_hash),
            evaluated_at=record.evaluated_at,
        )
