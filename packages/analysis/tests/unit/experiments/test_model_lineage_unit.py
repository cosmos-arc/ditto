"""Unit tests for model-candidate lineage and artifact contracts (#268)."""

from __future__ import annotations

from typing import Any

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.model_lineage import (
    MODEL_PREDICTION_ARTIFACT_SCHEMA,
    MODEL_TRAINING_ARTIFACT_SCHEMA,
    ModelCandidateLineage,
    ModelKind,
    ModelPredictionRecord,
    ModelPredictionRow,
    ModelTrainingRecord,
    TrainFittedTransformSpec,
)
from ditto_analysis.experiments.persistence import canonical_payload

_LABEL_HASH = "a" * 64
_CODE_ENV = {
    "implementation_key": "ditto_application.model_candidates.ridge.v1",
    "python": "3.13.14",
    "lockfile_sha256": "b" * 64,
}


def _lineage(
    kind: ModelKind = ModelKind.LINEAR,
    hyperparameters: dict[str, object] | None = None,
    feature_names: tuple[str, ...] = ("momentum_20d", "ep_ttm"),
) -> ModelCandidateLineage:
    if hyperparameters is None:
        if kind is ModelKind.LINEAR:
            hyperparameters = {"alpha": 1.0}
        elif kind is ModelKind.RULE:
            hyperparameters = {"ranking_feature": feature_names[0]}
        else:
            hyperparameters = {
                "num_leaves": 4,
                "learning_rate": 0.1,
                "num_iterations": 5,
            }
    return ModelCandidateLineage(
        model_kind=kind,
        feature_names=feature_names,
        label_id="research.label.forward_return.next_open_hold5.v1",
        label_spec_hash=_LABEL_HASH,
        transform_spec=TrainFittedTransformSpec(),
        hyperparameters=hyperparameters,
        seed=7,
        code_environment=dict(_CODE_ENV),
    )


def test_linear_lineage_freezes_and_hashes() -> None:
    lineage = _lineage()
    payload = lineage.canonical_payload()
    assert payload["model_kind"] == "linear"
    assert payload["hyperparameters"] == {"alpha": 1.0}
    assert lineage.registration_hash == _lineage().registration_hash
    assert len(lineage.registration_hash) == 64


def test_rule_lineage_requires_registered_ranking_feature() -> None:
    assert _lineage(ModelKind.RULE).registration_hash != _lineage().registration_hash
    with pytest.raises(ExperimentSpecError):
        _lineage(ModelKind.RULE, {"ranking_feature": "not_a_feature"})
    with pytest.raises(ExperimentSpecError):
        _lineage(ModelKind.RULE, {"alpha": 1.0})


def test_linear_alpha_must_be_positive_finite() -> None:
    with pytest.raises(ExperimentSpecError):
        _lineage(ModelKind.LINEAR, {"alpha": 0.0})
    with pytest.raises(ExperimentSpecError):
        _lineage(ModelKind.LINEAR, {"alpha": float("inf")})
    with pytest.raises(ExperimentSpecError):
        _lineage(ModelKind.LINEAR, {})


def test_lightgbm_lineage_freezes_registered_hyperparameters() -> None:
    lineage = _lineage(
        ModelKind.LIGHTGBM,
        {"num_leaves": 8, "learning_rate": 0.05, "num_iterations": 20},
    )
    payload = lineage.canonical_payload()
    assert payload["model_kind"] == "lightgbm"
    assert payload["hyperparameters"] == {
        "num_leaves": 8.0,
        "learning_rate": 0.05,
        "num_iterations": 20.0,
    }
    assert (
        lineage.registration_hash
        == _lineage(
            ModelKind.LIGHTGBM,
            {"num_leaves": 8, "learning_rate": 0.05, "num_iterations": 20},
        ).registration_hash
    )


def test_lightgbm_hyperparameters_are_range_checked() -> None:
    with pytest.raises(ExperimentSpecError):
        _lineage(
            ModelKind.LIGHTGBM,
            {"num_leaves": 1, "learning_rate": 0.1, "num_iterations": 5},
        )
    with pytest.raises(ExperimentSpecError):
        _lineage(
            ModelKind.LIGHTGBM,
            {"num_leaves": 8, "learning_rate": 0.0, "num_iterations": 5},
        )
    with pytest.raises(ExperimentSpecError):
        _lineage(
            ModelKind.LIGHTGBM,
            {"num_leaves": 8, "learning_rate": 0.1, "num_iterations": 0},
        )
    with pytest.raises(ExperimentSpecError):
        _lineage(ModelKind.LIGHTGBM, {"alpha": 1.0})


def test_feature_names_must_be_unique_nonempty_strings() -> None:
    with pytest.raises(ExperimentSpecError):
        _lineage(feature_names=("dup", "dup"))
    with pytest.raises(ExperimentSpecError):
        _lineage(feature_names=())


def test_code_environment_requires_exact_identity_keys() -> None:
    environment = dict(_CODE_ENV)
    del environment["lockfile_sha256"]
    with pytest.raises(ExperimentSpecError):
        ModelCandidateLineage(
            model_kind=ModelKind.LINEAR,
            feature_names=("momentum_20d",),
            label_id="research.label.forward_return.next_open_hold5.v1",
            label_spec_hash=_LABEL_HASH,
            transform_spec=TrainFittedTransformSpec(),
            hyperparameters={"alpha": 2.0},
            seed=1,
            code_environment=environment,
        )


def test_transform_spec_rejects_recipe_drift() -> None:
    with pytest.raises(ExperimentSpecError):
        TrainFittedTransformSpec(imputation="mean")
    with pytest.raises(ExperimentSpecError):
        TrainFittedTransformSpec(
            winsorize_lower_quantile=0.5, winsorize_upper_quantile=0.4
        )


def _registration_payload() -> dict[str, object]:
    """Return one valid lineage payload bound to the linear test lineage."""
    return _lineage().canonical_payload()


def _training_record(**overrides: object) -> ModelTrainingRecord:
    payload = _registration_payload()
    registration_hash = canonical_payload(payload).content_hash.value
    fields: dict[str, Any] = {
        "schema": MODEL_TRAINING_ARTIFACT_SCHEMA,
        "experiment_id": "experiment-1",
        "candidate_id": "candidate-1",
        "fold_id": "fold-1",
        "registration_hash": registration_hash,
        "registration_payload": payload,
        "snapshot_id": "snap-1",
        "train_window_start": "2025-01-01",
        "train_window_end": "2025-06-30",
        "label_maturity_cutoff_epoch_us": 1_000,
        "trained_at_epoch_us": 2_000,
        "sample_count": 10,
        "model_state_sha256": "d" * 64,
        "transform_state_sha256": "e" * 64,
        "feature_names": ("momentum_20d", "ep_ttm"),
    }
    fields.update(overrides)
    return ModelTrainingRecord(**fields)


def test_training_record_accepts_complete_contract() -> None:
    record = _training_record()
    assert record.artifact_hash == _training_record().artifact_hash
    assert record.registration_hash == _lineage().registration_hash


def test_training_record_rejects_registration_payload_drift() -> None:
    tampered = dict(_registration_payload())
    tampered["seed"] = 99
    with pytest.raises(ExperimentSpecError):
        _training_record(registration_payload=tampered)


def test_training_record_rejects_training_before_maturity() -> None:
    with pytest.raises(ExperimentSpecError):
        _training_record(trained_at_epoch_us=999)


def test_training_record_rejects_nonpositive_samples() -> None:
    with pytest.raises(ExperimentSpecError):
        _training_record(sample_count=0)


def test_training_record_rejects_bad_hash_and_dates() -> None:
    with pytest.raises(ExperimentSpecError):
        _training_record(model_state_sha256="nothex")
    with pytest.raises(ExperimentSpecError):
        _training_record(train_window_start="2025-07-01")
    with pytest.raises(ExperimentSpecError):
        _training_record(train_window_start="20250101")


def _prediction_record(**overrides: object) -> ModelPredictionRecord:
    fields: dict[str, Any] = {
        "schema": MODEL_PREDICTION_ARTIFACT_SCHEMA,
        "registration_hash": "c" * 64,
        "model_artifact_hash": "f" * 64,
        "prediction_window_start": "2025-07-01",
        "prediction_window_end": "2025-08-01",
        "rows": (
            ModelPredictionRow("000001.SZ", "2025-07-01", 0.25),
            ModelPredictionRow("000002.SZ", "2025-07-01", -0.1),
        ),
    }
    fields.update(overrides)
    return ModelPredictionRecord(**fields)


def test_prediction_record_accepts_contract_rows() -> None:
    record = _prediction_record()
    assert len(record.rows) == 2
    assert record.artifact_hash == _prediction_record().artifact_hash


def test_prediction_record_rejects_duplicates_and_empty() -> None:
    with pytest.raises(ExperimentSpecError):
        _prediction_record(
            rows=(
                ModelPredictionRow("000001.SZ", "2025-07-01", 0.25),
                ModelPredictionRow("000001.SZ", "2025-07-01", 0.30),
            )
        )
    with pytest.raises(ExperimentSpecError):
        _prediction_record(rows=())


def test_prediction_row_rejects_nonfinite() -> None:
    with pytest.raises(ExperimentSpecError):
        ModelPredictionRow("000001.SZ", "2025-07-01", float("nan"))
