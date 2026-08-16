"""Fail-closed PIT materialization for one generated-candidate fold."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from threading import Lock
from types import MappingProxyType
from typing import Protocol, cast

import orjson
from ditto_analysis.experiments.campaign import (
    EvaluationResult,
    ExperimentPlan,
    ResearchCandidateSpec,
)
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxResourceLimits,
)
from ditto_analysis.experiments.models import CandidateId, ContentHash, SnapshotId
from ditto_analysis.experiments.persistence import (
    DateWindow,
    FoldRole,
    canonical_payload,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_sandbox_port import (
    CandidateSandboxPort,
    FrozenSandboxWindow,
    SandboxArtifactFormat,
    SandboxScoreKey,
    freeze_sandbox_artifact,
)
from ditto_application.processes.experiments.generated_candidate_evaluator import (
    GeneratedCandidateEvaluationRequest,
    GeneratedCandidateEvaluator,
    TrustedCandidateEvaluationPort,
)
from ditto_application.research_validation_windows import ValidationFoldPlan

__all__ = [
    "GeneratedCandidatePitData",
    "GeneratedCandidatePitDataFeed",
    "GeneratedCandidatePitEvaluationRequest",
    "GeneratedCandidatePitEvaluator",
    "GeneratedCandidatePitQuery",
    "GeneratedCandidatePitRow",
    "GeneratedCandidatePitRowReader",
    "GeneratedCandidateSandboxContext",
    "GeneratedCandidateSandboxFactory",
]

type GeneratedCandidateFeatureValue = str | bool | int | float | None


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "generated candidate PIT feed failed closed",
        details={
            "code": "GENERATED_CANDIDATE_PIT_INVALID",
            "reason": reason,
            **details,
        },
    )


def _non_negative_epoch(value: object, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise _error("pit_timestamp_invalid", field=field)
    return value


def _freeze_features(
    value: object,
) -> Mapping[str, GeneratedCandidateFeatureValue]:
    if not isinstance(value, Mapping):
        raise _error("pit_features_invalid")
    frozen: dict[str, GeneratedCandidateFeatureValue] = {}
    for raw_key, raw_value in cast("Mapping[object, object]", value).items():
        if (
            type(raw_key) is not str
            or not raw_key
            or raw_key != raw_key.strip()
            or raw_key in frozen
        ):
            raise _error("pit_feature_name_invalid")
        if type(raw_value) not in (str, bool, int, float, type(None)):
            raise _error("pit_feature_value_invalid", feature=raw_key)
        if type(raw_value) is float and not math.isfinite(raw_value):
            raise _error("pit_feature_value_invalid", feature=raw_key)
        frozen[raw_key] = cast("GeneratedCandidateFeatureValue", raw_value)
    if not frozen:
        raise _error("pit_features_invalid")
    return MappingProxyType(dict(sorted(frozen.items())))


@dataclass(frozen=True, slots=True)
class GeneratedCandidatePitRow:
    """One source revision with host-owned visibility and execution times."""

    entity_id: str
    session_date: date
    event_time_epoch_us: int
    known_at_epoch_us: int
    publication_time_epoch_us: int
    execution_eligible_at_epoch_us: int
    source_snapshot_id: SnapshotId
    revision_id: str
    features: Mapping[str, GeneratedCandidateFeatureValue]

    def __post_init__(self) -> None:
        """Deep-freeze one revision without applying a caller cutoff."""
        for field_name in ("entity_id", "revision_id"):
            value = getattr(self, field_name)
            if type(value) is not str or not value or value != value.strip():
                raise _error("pit_row_identity_invalid", field=field_name)
        if type(self.session_date) is not date:
            raise _error("pit_session_date_invalid")
        for field_name in (
            "event_time_epoch_us",
            "known_at_epoch_us",
            "publication_time_epoch_us",
            "execution_eligible_at_epoch_us",
        ):
            _non_negative_epoch(getattr(self, field_name), field=field_name)
        if type(self.source_snapshot_id) is not SnapshotId:
            raise _error("pit_source_snapshot_invalid")
        if self.publication_time_epoch_us > self.known_at_epoch_us:
            raise _error("pit_publication_after_knowledge")
        if self.execution_eligible_at_epoch_us <= self.event_time_epoch_us:
            raise _error("same_close_execution_forbidden")
        object.__setattr__(self, "features", _freeze_features(self.features))


def _trading_sessions(value: object) -> tuple[date, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error("pit_trading_sessions_invalid")
    sessions = tuple(cast("Sequence[object]", value))
    if not sessions or any(type(item) is not date for item in sessions):
        raise _error("pit_trading_sessions_invalid")
    typed_sessions = cast("tuple[date, ...]", sessions)
    if any(current >= following for current, following in pairwise(typed_sessions)):
        raise _error("pit_trading_sessions_invalid")
    return typed_sessions


def _window_sessions(
    sessions: tuple[date, ...],
    *,
    start: date,
    end: date,
) -> tuple[date, ...]:
    selected = tuple(item for item in sessions if start <= item <= end)
    if not selected or selected[0] != start or selected[-1] != end:
        raise _error("pit_fold_calendar_boundary_missing")
    return selected


def _required_train_window(fold: ValidationFoldPlan) -> DateWindow:
    train = fold.train_window
    if type(train) is not DateWindow:
        raise _error("pit_fold_not_walk_forward")
    return train


def _validated_fold_and_sessions(
    raw_fold: object,
    raw_sessions: object,
) -> tuple[ValidationFoldPlan, tuple[date, ...]]:
    if type(raw_fold) is not ValidationFoldPlan:
        raise _error("pit_fold_invalid")
    fold = raw_fold
    train_window = _required_train_window(fold)
    if fold.role is not FoldRole.WALK_FORWARD:
        raise _error("pit_fold_not_walk_forward")
    if type(fold.ordinal) is not int or fold.ordinal <= 0:
        raise _error("pit_fold_invalid")
    if type(fold.test_window) is not DateWindow:
        raise _error("pit_fold_invalid")
    for field_name in ("purge_sessions", "embargo_sessions"):
        value = getattr(fold, field_name)
        if type(value) is not int or value < 0:
            raise _error("pit_fold_isolation_invalid", field=field_name)
    sessions = _trading_sessions(raw_sessions)
    train = _window_sessions(
        sessions,
        start=train_window.start,
        end=train_window.end,
    )
    test = _window_sessions(
        sessions,
        start=fold.test_window.start,
        end=fold.test_window.end,
    )
    if train_window.end >= fold.test_window.start:
        raise _error("pit_fold_windows_overlap")
    if fold.purge_sessions >= len(train):
        raise _error("pit_purge_exhausts_training_window")
    if fold.embargo_sessions >= len(test):
        raise _error("pit_embargo_exhausts_test_window")
    return fold, sessions


@dataclass(frozen=True, slots=True)
class GeneratedCandidatePitQuery:
    """Exact snapshot, fold, calendar, and visibility identity for one read."""

    fold: ValidationFoldPlan
    snapshot_id: SnapshotId
    input_schema_hash: ContentHash
    decision_time_epoch_us: int
    knowledge_cutoff_epoch_us: int
    publication_cutoff_epoch_us: int
    trading_sessions: Sequence[date]

    def __post_init__(self) -> None:
        """Require an executable walk-forward fold and complete PIT identity."""
        if type(self.snapshot_id) is not SnapshotId:
            raise _error("pit_source_snapshot_invalid")
        if type(self.input_schema_hash) is not ContentHash:
            raise _error("pit_input_schema_invalid")
        for field_name in (
            "decision_time_epoch_us",
            "knowledge_cutoff_epoch_us",
            "publication_cutoff_epoch_us",
        ):
            _non_negative_epoch(getattr(self, field_name), field=field_name)
        if not (
            self.publication_cutoff_epoch_us
            <= self.knowledge_cutoff_epoch_us
            <= self.decision_time_epoch_us
        ):
            raise _error("pit_temporal_order_invalid")
        _fold, sessions = _validated_fold_and_sessions(
            cast("object", self.fold),
            cast("object", self.trading_sessions),
        )
        object.__setattr__(self, "trading_sessions", sessions)

    @property
    def eligible_training_sessions(self) -> tuple[date, ...]:
        """Remove the compiled purge width from the training boundary."""
        fold = self.fold
        train_window = _required_train_window(fold)
        sessions = _window_sessions(
            tuple(self.trading_sessions),
            start=train_window.start,
            end=train_window.end,
        )
        return (
            sessions if fold.purge_sessions == 0 else sessions[: -fold.purge_sessions]
        )

    @property
    def eligible_test_sessions(self) -> tuple[date, ...]:
        """Apply the compiled embargo as an authoritative post-split gap."""
        sessions = _window_sessions(
            tuple(self.trading_sessions),
            start=self.fold.test_window.start,
            end=self.fold.test_window.end,
        )
        return sessions[self.fold.embargo_sessions :]

    @property
    def cache_key(self) -> ContentHash:
        """Bind snapshot and every temporal/fold field that changes visibility."""
        fold = self.fold
        train_window = _required_train_window(fold)
        return canonical_payload(
            {
                "schema_id": "r5-generated-candidate-pit-query",
                "schema_version": 1,
                "snapshot_id": str(self.snapshot_id),
                "input_schema_hash": str(self.input_schema_hash),
                "decision_time_epoch_us": self.decision_time_epoch_us,
                "knowledge_cutoff_epoch_us": self.knowledge_cutoff_epoch_us,
                "publication_cutoff_epoch_us": self.publication_cutoff_epoch_us,
                "fold": {
                    "ordinal": fold.ordinal,
                    "role": fold.role.value,
                    "train_start": train_window.start.isoformat(),
                    "train_end": train_window.end.isoformat(),
                    "test_start": fold.test_window.start.isoformat(),
                    "test_end": fold.test_window.end.isoformat(),
                    "purge_sessions": fold.purge_sessions,
                    "embargo_sessions": fold.embargo_sessions,
                },
                "trading_sessions": [
                    item.isoformat() for item in self.trading_sessions
                ],
            }
        ).content_hash


class GeneratedCandidatePitRowReader(Protocol):
    """Provider port requiring an exact snapshot query with no latest fallback."""

    def read_rows(
        self, query: GeneratedCandidatePitQuery
    ) -> Sequence[GeneratedCandidatePitRow]:
        """Return candidate rows for the exact query identity."""
        ...


@dataclass(frozen=True, slots=True)
class GeneratedCandidatePitData:
    """Exact purged training and embargoed visible windows for one fold."""

    training_stream: FrozenSandboxWindow
    visible_window: FrozenSandboxWindow

    def __post_init__(self) -> None:
        """Require complete matching frozen window contracts."""
        if (
            type(self.training_stream) is not FrozenSandboxWindow
            or type(self.visible_window) is not FrozenSandboxWindow
        ):
            raise _error("pit_fold_data_invalid")


def _latest_visible_rows(
    rows: Sequence[GeneratedCandidatePitRow],
) -> tuple[GeneratedCandidatePitRow, ...]:
    grouped: dict[tuple[str, int], list[GeneratedCandidatePitRow]] = {}
    for row in rows:
        grouped.setdefault((row.entity_id, row.event_time_epoch_us), []).append(row)
    selected: list[GeneratedCandidatePitRow] = []
    for revisions in grouped.values():
        by_visibility = {
            (item.known_at_epoch_us, item.publication_time_epoch_us)
            for item in revisions
        }
        if len(by_visibility) != len(revisions):
            raise _error("pit_revision_visibility_ambiguous")
        selected.append(
            max(
                revisions,
                key=lambda item: (
                    item.known_at_epoch_us,
                    item.publication_time_epoch_us,
                    item.revision_id,
                ),
            )
        )
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                item.session_date,
                item.entity_id,
                item.event_time_epoch_us,
            ),
        )
    )


def _window(
    query: GeneratedCandidatePitQuery,
    rows: Sequence[GeneratedCandidatePitRow],
    *,
    phase: str,
) -> FrozenSandboxWindow:
    selected = _latest_visible_rows(rows)
    if not selected:
        raise _error("pit_fold_window_empty", phase=phase)
    payload = orjson.dumps(
        {
            "schema_id": "r5-generated-candidate-pit-window",
            "schema_version": 1,
            "rows": [
                {
                    "entity_id": item.entity_id,
                    "event_time_epoch_us": item.event_time_epoch_us,
                    "features": dict(item.features),
                }
                for item in selected
            ],
        },
        option=orjson.OPT_SORT_KEYS,
    )
    artifact = freeze_sandbox_artifact(
        payload,
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=query.input_schema_hash,
        row_count=len(selected),
    )
    return FrozenSandboxWindow(
        artifact=artifact,
        snapshot_id=query.snapshot_id,
        decision_time_epoch_us=query.decision_time_epoch_us,
        knowledge_cutoff_epoch_us=query.knowledge_cutoff_epoch_us,
        publication_cutoff_epoch_us=query.publication_cutoff_epoch_us,
        score_keys=tuple(
            SandboxScoreKey(
                entity_id=item.entity_id,
                event_time_epoch_us=item.event_time_epoch_us,
                known_at_epoch_us=item.known_at_epoch_us,
                publication_time_epoch_us=item.publication_time_epoch_us,
                execution_eligible_at_epoch_us=item.execution_eligible_at_epoch_us,
            )
            for item in selected
        ),
    )


class GeneratedCandidatePitDataFeed:
    """Materialize exact fold windows and cache only by complete PIT identity."""

    def __init__(self, reader: GeneratedCandidatePitRowReader) -> None:
        self._reader = reader
        self._cache: dict[ContentHash, GeneratedCandidatePitData] = {}

    def load(self, query: GeneratedCandidatePitQuery) -> GeneratedCandidatePitData:
        """Filter future revisions, enforce snapshot, and apply fold isolation."""
        if type(query) is not GeneratedCandidatePitQuery:
            raise _error("pit_query_invalid")
        cached = self._cache.get(query.cache_key)
        if cached is not None:
            return cached
        raw_rows = cast("object", self._reader.read_rows(query))
        if not isinstance(raw_rows, Sequence) or isinstance(
            raw_rows, (str, bytes, bytearray)
        ):
            raise _error("pit_reader_result_invalid")
        rows = tuple(cast("Sequence[object]", raw_rows))
        if any(type(item) is not GeneratedCandidatePitRow for item in rows):
            raise _error("pit_reader_result_invalid")
        typed = cast("tuple[GeneratedCandidatePitRow, ...]", rows)
        if any(item.source_snapshot_id != query.snapshot_id for item in typed):
            raise _error("pit_source_snapshot_mismatch")
        visible = tuple(
            item
            for item in typed
            if item.event_time_epoch_us <= query.decision_time_epoch_us
            and item.known_at_epoch_us <= query.knowledge_cutoff_epoch_us
            and item.publication_time_epoch_us <= query.publication_cutoff_epoch_us
        )
        training_dates = frozenset(query.eligible_training_sessions)
        test_dates = frozenset(query.eligible_test_sessions)
        result = GeneratedCandidatePitData(
            training_stream=_window(
                query,
                tuple(item for item in visible if item.session_date in training_dates),
                phase="fit",
            ),
            visible_window=_window(
                query,
                tuple(item for item in visible if item.session_date in test_dates),
                phase="score",
            ),
        )
        self._cache[query.cache_key] = result
        return result


@dataclass(frozen=True, slots=True)
class GeneratedCandidatePitEvaluationRequest:
    """One preregistered candidate/fold with exact calendar and PIT cutoffs."""

    candidate: ResearchCandidateSpec
    experiment_plan: ExperimentPlan
    code_artifact: ResearchCodeArtifact
    fold: ValidationFoldPlan
    trading_sessions: Sequence[date]
    decision_time_epoch_us: int
    knowledge_cutoff_epoch_us: int
    publication_cutoff_epoch_us: int
    resource_limits: SandboxResourceLimits
    seed: int

    def __post_init__(self) -> None:
        """Bind the compiled fold and PIT query to the preregistered plan."""
        typed = (
            (self.candidate, ResearchCandidateSpec),
            (self.experiment_plan, ExperimentPlan),
            (self.code_artifact, ResearchCodeArtifact),
            (self.fold, ValidationFoldPlan),
            (self.resource_limits, SandboxResourceLimits),
        )
        if any(type(value) is not expected for value, expected in typed):
            raise _error("pit_evaluation_request_invalid")
        if type(self.seed) is not int or self.seed < 0:
            raise _error("pit_evaluation_seed_invalid")
        if self.seed != self.experiment_plan.seed:
            raise _error("pit_evaluation_seed_plan_mismatch")
        if (
            self.fold.purge_sessions != self.experiment_plan.purge_sessions
            or self.fold.embargo_sessions != self.experiment_plan.embargo_sessions
        ):
            raise _error("pit_fold_isolation_plan_mismatch")
        query = self._build_query()
        object.__setattr__(self, "trading_sessions", query.trading_sessions)

    def _build_query(self) -> GeneratedCandidatePitQuery:
        return GeneratedCandidatePitQuery(
            fold=self.fold,
            snapshot_id=self.experiment_plan.snapshot_id,
            input_schema_hash=self.code_artifact.input_schema_hash,
            decision_time_epoch_us=self.decision_time_epoch_us,
            knowledge_cutoff_epoch_us=self.knowledge_cutoff_epoch_us,
            publication_cutoff_epoch_us=self.publication_cutoff_epoch_us,
            trading_sessions=self.trading_sessions,
        )

    @property
    def pit_query(self) -> GeneratedCandidatePitQuery:
        """Rebuild the immutable provider request without wall-clock defaults."""
        return self._build_query()


@dataclass(frozen=True, slots=True)
class GeneratedCandidateSandboxContext:
    """Exact candidate/fold identity required to allocate a fresh sandbox."""

    candidate_id: CandidateId
    candidate_hash: ContentHash
    fold_ordinal: int
    snapshot_id: SnapshotId
    pit_query_hash: ContentHash
    code_artifact_hash: ContentHash

    def __post_init__(self) -> None:
        """Reject untyped context before asking a physical factory to allocate."""
        typed = (
            (self.candidate_id, CandidateId),
            (self.candidate_hash, ContentHash),
            (self.snapshot_id, SnapshotId),
            (self.pit_query_hash, ContentHash),
            (self.code_artifact_hash, ContentHash),
        )
        if any(type(value) is not expected for value, expected in typed):
            raise _error("pit_sandbox_context_invalid")
        if type(self.fold_ordinal) is not int or self.fold_ordinal <= 0:
            raise _error("pit_sandbox_context_invalid")


class GeneratedCandidateSandboxFactory(Protocol):
    """Consumer-owned factory allocating one fresh sandbox per evaluation."""

    def create(self, context: GeneratedCandidateSandboxContext) -> CandidateSandboxPort:
        """Return a never-before-used sandbox for this candidate/fold."""
        ...


class GeneratedCandidatePitEvaluator:
    """Load an exact PIT fold, allocate a fresh sandbox, and evaluate on host."""

    def __init__(
        self,
        *,
        data_feed: GeneratedCandidatePitDataFeed,
        sandbox_factory: GeneratedCandidateSandboxFactory,
        trusted: TrustedCandidateEvaluationPort,
    ) -> None:
        self._data_feed = data_feed
        self._sandbox_factory = sandbox_factory
        self._trusted = trusted
        self._sandbox_lock = Lock()
        self._used_sandboxes: list[CandidateSandboxPort] = []

    def evaluate(
        self, request: GeneratedCandidatePitEvaluationRequest
    ) -> EvaluationResult:
        """Run one fold without latest data or sandbox reuse."""
        if type(request) is not GeneratedCandidatePitEvaluationRequest:
            raise _error("pit_evaluation_request_invalid")
        query = request.pit_query
        data = self._data_feed.load(query)
        candidate = request.candidate
        context = GeneratedCandidateSandboxContext(
            candidate_id=candidate.candidate.candidate_id,
            candidate_hash=candidate.candidate_hash,
            fold_ordinal=request.fold.ordinal,
            snapshot_id=request.experiment_plan.snapshot_id,
            pit_query_hash=query.cache_key,
            code_artifact_hash=request.code_artifact.artifact_hash,
        )
        sandbox = self._sandbox_factory.create(context)
        if not hasattr(sandbox, "fit") or not hasattr(sandbox, "score"):
            raise _error("pit_sandbox_invalid")
        with self._sandbox_lock:
            if any(sandbox is existing for existing in self._used_sandboxes):
                raise _error("pit_sandbox_reused")
            self._used_sandboxes.append(sandbox)
        evaluator = GeneratedCandidateEvaluator(sandbox=sandbox, trusted=self._trusted)
        return evaluator.evaluate(
            GeneratedCandidateEvaluationRequest(
                candidate=request.candidate,
                experiment_plan=request.experiment_plan,
                code_artifact=request.code_artifact,
                training_stream=data.training_stream,
                visible_window=data.visible_window,
                resource_limits=request.resource_limits,
                seed=request.seed,
            )
        )
