"""Unit tests for model recovery and decision-context inference (#270)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from threading import Lock

import orjson
import polars as pl
import pytest
from ditto_analysis.experiments.model_lineage import (
    ModelCandidateLineage,
    ModelKind,
    TrainFittedTransformSpec,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    DateWindow,
    FoldRole,
    LeaseFence,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.model_artifact_publication import (
    IndexedModelArtifactSink,
    ModelArtifactPublicationContext,
)
from ditto_application.processes.experiments.model_candidates import (
    ModelFoldTrainingRequest,
    ModelTrainingSuccess,
    train_model_candidate,
)
from ditto_application.processes.experiments.model_inference import (
    ModelInferenceFailure,
    ModelInferenceRequest,
    ModelInferenceSuccess,
    infer_model_predictions,
    load_model_training_artifact,
)
from ditto_application.research_validation_windows import ValidationFoldPlan
from ditto_features.evaluation.research_labels import build_forward_return_labels

_START = date(2026, 3, 2)
SESSIONS = tuple(_START + timedelta(days=index) for index in range(30))
ENTITIES = ("000001.SZ", "000002.SZ", "600000.SH")
_EPOCH_BASE = 5_000_000_000_000_000
_LABEL_HASH = "a" * 64
_CODE_ENV = {
    "implementation_key": "ditto_application.model_candidates.ridge.v1",
    "python": "3.13.14",
    "lockfile_sha256": "b" * 64,
}
_KNOWLEDGE_CUTOFF = _EPOCH_BASE + 60 * 86_400_000_000
_TRAINED_AT = _KNOWLEDGE_CUTOFF + 1
_DECISION_TIME = _TRAINED_AT + 5_000_000


def _price_frame() -> pl.DataFrame:
    rows: dict[str, list[object]] = {
        "instrument_id": [],
        "session": [],
        "open": [],
        "close": [],
        "adj_factor": [],
        "buy_fillable_open": [],
        "sell_fillable_close": [],
        "session_close_known_at_epoch_us": [],
    }
    for offset, instrument in enumerate(ENTITIES):
        for index, session in enumerate(SESSIONS):
            base = 10.0 + offset
            rows["instrument_id"].append(instrument)
            rows["session"].append(session)
            rows["open"].append(base + index)
            rows["close"].append(base + 0.5 + index)
            rows["adj_factor"].append(1.0)
            rows["buy_fillable_open"].append(True)
            rows["sell_fillable_close"].append(True)
            rows["session_close_known_at_epoch_us"].append(
                _EPOCH_BASE + index * 86_400_000_000
            )
    schema = {
        "instrument_id": pl.String,
        "session": pl.Date,
        "open": pl.Float64,
        "close": pl.Float64,
        "adj_factor": pl.Float64,
        "buy_fillable_open": pl.Boolean,
        "sell_fillable_close": pl.Boolean,
        "session_close_known_at_epoch_us": pl.Int64,
    }
    return pl.DataFrame(rows, schema=schema)


def _feature_frame() -> pl.DataFrame:
    rows: dict[str, list[object]] = {
        "instrument_id": [],
        "session": [],
        "momentum_20d": [],
        "ep_ttm": [],
    }
    for offset, instrument in enumerate(ENTITIES):
        for index, session in enumerate(SESSIONS):
            rows["instrument_id"].append(instrument)
            rows["session"].append(session)
            rows["momentum_20d"].append(float(offset * 0.1 + (index % 7) * 0.05))
            rows["ep_ttm"].append(float(offset * 0.2 + (index % 5) * 0.03))
    return pl.DataFrame(
        rows,
        schema={
            "instrument_id": pl.String,
            "session": pl.Date,
            "momentum_20d": pl.Float64,
            "ep_ttm": pl.Float64,
        },
    )


def _lineage(kind: ModelKind = ModelKind.LINEAR) -> ModelCandidateLineage:
    if kind is ModelKind.LINEAR:
        hyperparameters: dict[str, object] = {"alpha": 1.0}
    elif kind is ModelKind.RULE:
        hyperparameters = {"ranking_feature": "momentum_20d"}
    else:
        hyperparameters = {
            "num_leaves": 4,
            "learning_rate": 0.1,
            "num_iterations": 5,
        }
    return ModelCandidateLineage(
        model_kind=kind,
        feature_names=("momentum_20d", "ep_ttm"),
        label_id="research.label.forward_return.next_open_hold5.v1",
        label_spec_hash=_LABEL_HASH,
        transform_spec=TrainFittedTransformSpec(),
        hyperparameters=hyperparameters,
        seed=7,
        code_environment=dict(_CODE_ENV),
    )


def _fold() -> ValidationFoldPlan:
    return ValidationFoldPlan(
        ordinal=1,
        role=FoldRole.WALK_FORWARD,
        train_window=DateWindow(start=SESSIONS[0], end=SESSIONS[19]),
        test_window=DateWindow(start=SESSIONS[25], end=SESSIONS[29]),
        purge_sessions=5,
        embargo_sessions=5,
    )


def _training_request(kind: ModelKind = ModelKind.LINEAR) -> ModelFoldTrainingRequest:
    return ModelFoldTrainingRequest(
        lineage=_lineage(kind),
        fold=_fold(),
        feature_frame=_feature_frame(),
        labels=build_forward_return_labels(_price_frame(), list(SESSIONS)),
        trading_sessions=SESSIONS,
        snapshot_id="snap-inference-1",
        knowledge_cutoff_epoch_us=_KNOWLEDGE_CUTOFF,
        trained_at_epoch_us=_TRAINED_AT,
    )


class _MemoryArtifactIndex:
    """Minimal reader/writer port pair backed by an in-memory record map."""

    def __init__(self, root: Path) -> None:
        self.artifact_root = root
        self.records: dict[str, ArtifactRecord] = {}
        self._lock = Lock()

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self, relative_path: str
    ) -> ArtifactRecord | None:
        for record in self.records.values():
            if record.relative_path == relative_path:
                return record
        return None

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        _ = lease_fence, now_epoch_us
        with self._lock:
            existing = self.records.get(record.artifact_id)
            if existing is not None:
                if existing.content_hash != record.content_hash:
                    raise AppProcessError("artifact replay drift")
                commit_guard()
                return
            self.records[record.artifact_id] = record
            commit_guard()

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: object,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        raise NotImplementedError


@pytest.fixture
def service(tmp_path: Path) -> ResearchArtifactService:
    index = _MemoryArtifactIndex(tmp_path)
    return ResearchArtifactService(
        artifact_root=tmp_path,
        indexed_artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )


def _publish(service: ResearchArtifactService, kind: ModelKind) -> ModelTrainingSuccess:
    result = train_model_candidate(_training_request(kind))
    assert isinstance(result, ModelTrainingSuccess)
    sink = IndexedModelArtifactSink(service)
    context = ModelArtifactPublicationContext(
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=None,
        reproduction_fingerprint=ContentHash("1" * 64),
        lease_fence=LeaseFence(
            experiment_id=ExperimentId("experiment-1"),
            owner_token="owner-1",
            revision=1,
        ),
        now_epoch_us=_TRAINED_AT,
    )
    sink.publish_training(
        context,
        result.training,
        result.model_state_bytes,
        result.transform_state_bytes,
    )
    sink.publish_predictions(context, result.predictions)
    return result


def _decision_frame() -> pl.DataFrame:
    return _feature_frame().filter(pl.col("session") == SESSIONS[27])


@pytest.mark.parametrize("kind", [ModelKind.LINEAR, ModelKind.RULE, ModelKind.LIGHTGBM])
@pytest.mark.slow  # lightgbm 首次导入约 1s（#328 >0.5s 治理）
def test_recovery_inference_round_trips_published_artifacts(
    service: ResearchArtifactService, kind: ModelKind
) -> None:
    published = _publish(service, kind)
    artifact = load_model_training_artifact(
        service, f"model-training-{published.training.artifact_hash}"
    )
    assert artifact.training.artifact_hash == published.training.artifact_hash
    result = infer_model_predictions(
        ModelInferenceRequest(
            lineage=_lineage(kind),
            artifact=artifact,
            feature_frame=_decision_frame(),
            decision_sessions=(SESSIONS[27],),
            decision_time_epoch_us=_DECISION_TIME,
        )
    )
    assert isinstance(result, ModelInferenceSuccess)
    assert len(result.rows) == len(ENTITIES)
    recovered = {
        (row.entity_id, row.decision_session): row.prediction for row in result.rows
    }
    published_rows = {
        (row.entity_id, row.decision_session): row.prediction
        for row in published.predictions.rows
        if row.decision_session == SESSIONS[27].isoformat()
    }
    assert recovered.keys() == published_rows.keys()
    for key, expected in published_rows.items():
        assert recovered[key] == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_recovery_inference_refuses_model_incomplete_at_decision(
    service: ResearchArtifactService,
) -> None:
    published = _publish(service, ModelKind.LINEAR)
    artifact = load_model_training_artifact(
        service, f"model-training-{published.training.artifact_hash}"
    )
    result = infer_model_predictions(
        ModelInferenceRequest(
            lineage=_lineage(),
            artifact=artifact,
            feature_frame=_decision_frame(),
            decision_sessions=(SESSIONS[27],),
            decision_time_epoch_us=_TRAINED_AT - 1,
        )
    )
    assert isinstance(result, ModelInferenceFailure)
    assert result.reason == "model_not_complete_at_decision_time"


def test_recovery_refuses_registration_identity_mismatch(
    service: ResearchArtifactService,
) -> None:
    published = _publish(service, ModelKind.LINEAR)
    artifact = load_model_training_artifact(
        service, f"model-training-{published.training.artifact_hash}"
    )
    other = ModelCandidateLineage(
        model_kind=ModelKind.LINEAR,
        feature_names=("momentum_20d", "ep_ttm"),
        label_id="research.label.forward_return.next_open_hold5.v1",
        label_spec_hash=_LABEL_HASH,
        transform_spec=TrainFittedTransformSpec(),
        hyperparameters={"alpha": 99.0},
        seed=7,
        code_environment=dict(_CODE_ENV),
    )
    result = infer_model_predictions(
        ModelInferenceRequest(
            lineage=other,
            artifact=artifact,
            feature_frame=_decision_frame(),
            decision_sessions=(SESSIONS[27],),
            decision_time_epoch_us=_DECISION_TIME,
        )
    )
    assert isinstance(result, ModelInferenceFailure)
    assert result.reason == "model_registration_identity_mismatch"


class _TamperedReader:
    """Reader wrapper that overrides selected artifact payloads."""

    def __init__(
        self,
        inner: ResearchArtifactService,
        overrides: dict[str, dict[str, object]],
    ) -> None:
        self._inner = inner
        self._overrides = overrides

    def read_indexed_json(self, artifact_id: str) -> dict[str, object]:
        if artifact_id in self._overrides:
            return dict(self._overrides[artifact_id])
        return self._inner.read_indexed_json(artifact_id)


def test_inference_refuses_schema_drift_frame(
    service: ResearchArtifactService,
) -> None:
    published = _publish(service, ModelKind.LINEAR)
    artifact = load_model_training_artifact(
        service, f"model-training-{published.training.artifact_hash}"
    )
    drifted = _decision_frame().drop("ep_ttm")
    with pytest.raises(AppProcessError) as error:
        ModelInferenceRequest(
            lineage=_lineage(),
            artifact=artifact,
            feature_frame=drifted,
            decision_sessions=(SESSIONS[27],),
            decision_time_epoch_us=_DECISION_TIME,
        )
    assert error.value.details["reason"] == "feature_frame_schema_drift"


def test_inference_refuses_sessions_outside_decision_context(
    service: ResearchArtifactService,
) -> None:
    published = _publish(service, ModelKind.LINEAR)
    artifact = load_model_training_artifact(
        service, f"model-training-{published.training.artifact_hash}"
    )
    with pytest.raises(AppProcessError) as error:
        ModelInferenceRequest(
            lineage=_lineage(),
            artifact=artifact,
            feature_frame=_feature_frame().filter(pl.col("session") <= SESSIONS[27]),
            decision_sessions=(SESSIONS[27],),
            decision_time_epoch_us=_DECISION_TIME,
        )
    assert (
        error.value.details["reason"]
        == "feature_frame_sessions_outside_decision_context"
    )


def test_checksum_verification_binds_published_state_bytes(
    service: ResearchArtifactService,
) -> None:
    published = _publish(service, ModelKind.LINEAR)
    training_id = f"model-training-{published.training.artifact_hash}"
    record = service.read_indexed_json(training_id)
    state = service.read_indexed_json(
        f"model-model-state-{record['model_state_sha256']}"
    )
    tampered = dict(state)
    tampered["intercept"] = float(tampered["intercept"]) + 1.0  # type: ignore[operator]
    tampered_reader = _TamperedReader(
        service, {f"model-model-state-{record['model_state_sha256']}": tampered}
    )
    with pytest.raises(AppProcessError) as error:
        load_model_training_artifact(tampered_reader, training_id)
    assert error.value.details["reason"] == "model_state_checksum_drift"
    _ = orjson  # keep orjson import meaningful for payload assertions
