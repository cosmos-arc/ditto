"""Unit tests for lease-fenced indexed model artifact publication (#268)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Lock

import orjson
import pytest
from ditto_analysis.experiments.model_lineage import (
    MODEL_PREDICTION_ARTIFACT_SCHEMA,
    MODEL_TRAINING_ARTIFACT_SCHEMA,
    ModelPredictionRecord,
    ModelPredictionRow,
    ModelTrainingRecord,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
    canonical_payload,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.model_artifact_publication import (
    IndexedModelArtifactSink,
    ModelArtifactPublicationContext,
)

_EXPERIMENT = ExperimentId("experiment-1")
_CANDIDATE = CandidateId("candidate-1")
_FOLD = FoldId("fold-1")
_FINGERPRINT = ContentHash("1" * 64)
_FENCE = LeaseFence(experiment_id=_EXPERIMENT, owner_token="owner-1", revision=3)
_NOW_US = 1_000_000


class _MemoryArtifactIndex:
    """Minimal reader/writer port pair for indexed publication tests."""

    def __init__(self, root: Path) -> None:
        self.artifact_root = root
        self.records: dict[str, ArtifactRecord] = {}
        self._lock = Lock()

    # -- reader ---------------------------------------------------------------
    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self, relative_path: str
    ) -> ArtifactRecord | None:
        for record in self.records.values():
            if record.relative_path == relative_path:
                return record
        return None

    # -- writer ---------------------------------------------------------------
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
def index(tmp_path: Path) -> _MemoryArtifactIndex:
    return _MemoryArtifactIndex(tmp_path)


@pytest.fixture
def service(tmp_path: Path, index: _MemoryArtifactIndex) -> ResearchArtifactService:
    return ResearchArtifactService(
        artifact_root=tmp_path,
        indexed_artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )


def _context() -> ModelArtifactPublicationContext:
    return ModelArtifactPublicationContext(
        experiment_id=_EXPERIMENT,
        candidate_id=_CANDIDATE,
        fold_id=_FOLD,
        attempt_id=None,
        reproduction_fingerprint=_FINGERPRINT,
        lease_fence=_FENCE,
        now_epoch_us=_NOW_US,
    )


def _training() -> ModelTrainingRecord:
    return ModelTrainingRecord(
        schema=MODEL_TRAINING_ARTIFACT_SCHEMA,
        registration_hash="2" * 64,
        snapshot_id="snap-1",
        train_window_start="2025-01-01",
        train_window_end="2025-06-30",
        label_maturity_cutoff_epoch_us=1_000,
        trained_at_epoch_us=2_000,
        sample_count=10,
        model_state_sha256="3" * 64,
        transform_state_sha256="4" * 64,
        feature_names=("momentum_20d",),
    )


def _predictions(training: ModelTrainingRecord) -> ModelPredictionRecord:
    return ModelPredictionRecord(
        schema=MODEL_PREDICTION_ARTIFACT_SCHEMA,
        registration_hash=training.registration_hash,
        model_artifact_hash=training.artifact_hash,
        prediction_window_start="2025-07-01",
        prediction_window_end="2025-07-31",
        rows=(ModelPredictionRow("000001.SZ", "2025-07-01", 0.5),),
    )


def test_publish_training_writes_three_indexed_artifacts(
    tmp_path: Path, index: _MemoryArtifactIndex, service: ResearchArtifactService
) -> None:
    sink = IndexedModelArtifactSink(service)
    model_bytes = orjson.dumps({"coef": [0.1], "intercept": 0.01})
    transform_bytes = orjson.dumps({"momentum_20d": {"median": 1.0}})
    record, model, transform = sink.publish_training(
        _context(), _training(), model_bytes, transform_bytes
    )
    base = "experiments/experiment-1/candidates/candidate-1/folds/fold-1"
    assert record.relative_path == f"{base}/model-training.json"
    assert model.relative_path == f"{base}/model-state.json"
    assert transform.relative_path == f"{base}/transform-state.json"
    assert record.artifact_kind == "model_training_state"
    for published in (record, model, transform):
        assert (tmp_path / published.relative_path).is_file()
        assert index.get_artifact(published.artifact_id) is published
    expected_hash = canonical_payload(
        dict(_training().canonical_payload())
    ).content_hash
    assert record.content_hash == expected_hash


def test_publish_predictions_binds_model_artifact(
    tmp_path: Path, index: _MemoryArtifactIndex, service: ResearchArtifactService
) -> None:
    sink = IndexedModelArtifactSink(service)
    training = _training()
    published = sink.publish_predictions(_context(), _predictions(training))
    assert published.artifact_kind == "model_predictions"
    assert published.relative_path.endswith("model-predictions.json")
    payload = orjson.loads((tmp_path / published.relative_path).read_bytes())
    assert payload["model_artifact_hash"] == training.artifact_hash
    assert payload["rows"][0]["entity_id"] == "000001.SZ"


def test_publication_replay_is_idempotent(
    index: _MemoryArtifactIndex, service: ResearchArtifactService
) -> None:
    sink = IndexedModelArtifactSink(service)
    context = _context()
    training = _training()
    model_bytes = orjson.dumps({"coef": [0.1]})
    transform_bytes = orjson.dumps({"momentum_20d": {"median": 1.0}})
    first = sink.publish_training(context, training, model_bytes, transform_bytes)
    second = sink.publish_training(context, training, model_bytes, transform_bytes)
    assert [item.artifact_id for item in first] == [item.artifact_id for item in second]
    assert len(index.records) == 3


def test_context_rejects_lineage_gap_and_untyped_fence() -> None:
    from ditto_analysis.experiments.models import AttemptId

    with pytest.raises(AppProcessError):  # attempt without fold is a lineage gap
        ModelArtifactPublicationContext(
            experiment_id=_EXPERIMENT,
            candidate_id=_CANDIDATE,
            fold_id=None,
            attempt_id=AttemptId("attempt-1"),
            reproduction_fingerprint=_FINGERPRINT,
            lease_fence=_FENCE,
            now_epoch_us=_NOW_US,
        )
    with pytest.raises(AppProcessError):
        ModelArtifactPublicationContext(
            experiment_id=_EXPERIMENT,
            candidate_id=_CANDIDATE,
            fold_id=_FOLD,
            attempt_id=None,
            reproduction_fingerprint=_FINGERPRINT,
            lease_fence="not-a-fence",  # type: ignore[arg-type]
            now_epoch_us=_NOW_US,
        )
