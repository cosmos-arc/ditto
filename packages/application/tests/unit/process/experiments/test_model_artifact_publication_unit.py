"""Unit tests for lease-fenced indexed model artifact publication (#268)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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
    LeaseFence,
    canonical_payload,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.model_artifact_publication import (
    IndexedModelArtifactSink,
    ModelArtifactPublicationContext,
)
from ditto_application.processes.experiments.model_candidates import (
    model_state_sha256,
)
from ditto_features.evaluation.research_labels import label_spec_hash

from .conftest import MemoryArtifactIndex

_EXPERIMENT = ExperimentId("experiment-1")
_CANDIDATE = CandidateId("candidate-1")
_FOLD = FoldId("fold-1")
_FINGERPRINT = ContentHash("1" * 64)
_FENCE = LeaseFence(experiment_id=_EXPERIMENT, owner_token="owner-1", revision=3)
_NOW_US = 1_000_000


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


def _training(alpha: float = 1.0) -> ModelTrainingRecord:
    registration_payload: dict[str, object] = {
        "model_kind": "linear",
        "feature_names": ["momentum_20d"],
        "label_id": "research.label.forward_return.next_open_hold5.v1",
        "label_spec_hash": label_spec_hash(),
        "transform_spec": {
            "imputation": "median",
            "winsorize_lower_quantile": 0.01,
            "winsorize_upper_quantile": 0.99,
            "scaling": "zscore",
        },
        "hyperparameters": {"alpha": alpha},
        "seed": 7,
        "code_environment": {
            "implementation_key": "ditto_application.model_candidates.ridge.v1",
            "python": "3.13.14",
            "lockfile_sha256": "b" * 64,
        },
    }
    model_state: dict[str, object] = {"coef": [0.1], "intercept": 0.01}
    transform_state: dict[str, object] = {"momentum_20d": {"median": 1.0}}
    _ = alpha  # registration-only difference; state bytes stay shared
    return ModelTrainingRecord(
        schema=MODEL_TRAINING_ARTIFACT_SCHEMA,
        registration_hash=canonical_payload(registration_payload).content_hash.value,
        registration_payload=registration_payload,
        snapshot_id="snap-1",
        train_window_start="2025-01-01",
        train_window_end="2025-06-30",
        label_maturity_cutoff_epoch_us=1_000,
        trained_at_epoch_us=2_000,
        sample_count=10,
        model_state_sha256=model_state_sha256(model_state),
        transform_state_sha256=model_state_sha256(transform_state),
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
    tmp_path: Path,
    memory_artifact_index: MemoryArtifactIndex,
    artifact_service: ResearchArtifactService,
) -> None:
    sink = IndexedModelArtifactSink(artifact_service)
    record, model, transform = sink.publish_training(
        _context(), _training(), *_state_bytes()
    )
    base = "experiments/experiment-1/candidates/candidate-1/folds/fold-1"
    assert record.relative_path == f"{base}/model-training.json"
    assert model.relative_path == f"{base}/model-state.json"
    assert transform.relative_path == f"{base}/transform-state.json"
    assert record.artifact_kind == "model_training_state"
    for published in (record, model, transform):
        assert (tmp_path / published.relative_path).is_file()
        assert memory_artifact_index.get_artifact(published.artifact_id) is published
    expected_hash = canonical_payload(
        dict(_training().canonical_payload())
    ).content_hash
    assert record.content_hash == expected_hash


def test_publish_predictions_binds_model_artifact(
    tmp_path: Path,
    memory_artifact_index: MemoryArtifactIndex,
    artifact_service: ResearchArtifactService,
) -> None:
    sink = IndexedModelArtifactSink(artifact_service)
    training = _training()
    published = sink.publish_predictions(
        _context(), _predictions(training), trained_at_epoch_us=2_000
    )
    assert published.artifact_kind == "model_predictions"
    assert published.relative_path.endswith("model-predictions.json")
    payload = orjson.loads((tmp_path / published.relative_path).read_bytes())
    assert payload["model_artifact_hash"] == training.artifact_hash
    assert payload["rows"][0]["entity_id"] == "000001.SZ"


def test_publication_replay_is_idempotent(
    memory_artifact_index: MemoryArtifactIndex,
    artifact_service: ResearchArtifactService,
) -> None:
    sink = IndexedModelArtifactSink(artifact_service)
    context = _context()
    training = _training()
    first = sink.publish_training(context, training, *_state_bytes())
    # A crash retry arrives with a different lease clock; the batch timestamp
    # derives from the record, so the replay must still complete.
    retried_context = replace(context, now_epoch_us=_NOW_US + 987_654_321)
    second = sink.publish_training(retried_context, training, *_state_bytes())
    assert [item.artifact_id for item in first] == [item.artifact_id for item in second]
    assert len(memory_artifact_index.records) == 3


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


def _state_bytes(*, alpha: float = 1.0) -> tuple[bytes, bytes]:
    _ = alpha  # sibling candidates share identical frozen state bytes
    return (
        orjson.dumps({"coef": [0.1], "intercept": 0.01}),
        orjson.dumps({"momentum_20d": {"median": 1.0}}),
    )


def test_publish_refuses_state_bytes_contradicting_record_checksums(
    artifact_service: ResearchArtifactService,
    memory_artifact_index: MemoryArtifactIndex,
) -> None:
    sink = IndexedModelArtifactSink(artifact_service)
    with pytest.raises(AppProcessError) as error:
        sink.publish_training(
            _context(),
            _training(),
            orjson.dumps({"coef": [0.42], "intercept": 0.0}),
            orjson.dumps({"momentum_20d": {"median": 1.0}}),
        )
    assert error.value.details["reason"] == "state_checksum_unbound"
    assert len(memory_artifact_index.records) == 0


def test_sibling_candidates_sharing_fold_and_states_can_all_publish(
    artifact_service: ResearchArtifactService,
    memory_artifact_index: MemoryArtifactIndex,
) -> None:
    """#269 场景：同 fold 同特征集的兄弟候选不因共享状态字节冲突。"""
    sink = IndexedModelArtifactSink(artifact_service)
    sibling = replace(_CANDIDATE, value="candidate-2")
    for candidate, training in ((_CANDIDATE, _training()), (sibling, _training(2.0))):
        context = replace(_context(), candidate_id=candidate)
        record, _model, _transform = sink.publish_training(
            context, training, *_state_bytes(alpha=2.0)
        )
        assert record.artifact_id.startswith("model-training-")
        assert str(candidate) in record.relative_path
    assert len(memory_artifact_index.records) == 6
