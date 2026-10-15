"""
Fail-closed model recovery and decision-context inference (#270).

Reload one published training artifact (record + model state + transform
state), verify its identity and checksums, and score one explicit decision
context. Any schema drift, corrupted state, identity mismatch, or a model that
was not yet complete at the decision time returns an explicit refusal with no
signal — a recovery path may never emit an unfounded score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol, cast

import numpy as np
import polars as pl
from ditto_analysis.experiments.model_lineage import (
    MODEL_TRAINING_ARTIFACT_SCHEMA,
    ModelCandidateLineage,
    ModelKind,
    ModelPredictionRow,
    ModelTrainingRecord,
    model_state_artifact_id,
    transform_state_artifact_id,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.model_candidates import (
    lightgbm_predictions_from_state,
    model_state_sha256,
    transform_feature_matrix,
)

__all__ = [
    "IndexedJsonReaderPort",
    "LoadedModelArtifact",
    "ModelInferenceFailure",
    "ModelInferenceRequest",
    "ModelInferenceSuccess",
    "infer_model_predictions",
    "load_model_training_artifact",
    "verify_loaded_model_integrity",
]

_ENTITY_COLUMN = "instrument_id"
_SESSION_COLUMN = "session"


def _inference_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "model recovery inference failed closed",
        details={"code": "MODEL_INFERENCE_FAILED", "reason": reason, **details},
    )


class IndexedJsonReaderPort(Protocol):
    """Verified indexed read port implemented by ResearchArtifactService."""

    def read_indexed_json(self, artifact_id: str) -> dict[str, object]:
        """Read one indexed JSON artifact after full content verification."""
        ...


@dataclass(frozen=True, slots=True)
class LoadedModelArtifact:
    """One verified training record plus its decoded frozen states."""

    training: ModelTrainingRecord
    model_state: dict[str, object]
    transform_state: dict[str, dict[str, float]]


def _decode_transform_state(
    raw: object,
    feature_names: tuple[str, ...],
) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        raise _inference_error("transform_state_not_object")
    decoded = cast("dict[str, object]", raw)
    if tuple(sorted(decoded)) != tuple(sorted(feature_names)):
        raise _inference_error("transform_state_feature_drift")
    state: dict[str, dict[str, float]] = {}
    for name in feature_names:
        stats = decoded.get(name)
        if not isinstance(stats, dict):
            raise _inference_error("transform_state_stats_invalid")
        fields = cast("dict[str, object]", stats)
        if set(fields) != {
            "median",
            "winsor_lower",
            "winsor_upper",
            "mean",
            "std",
        }:
            raise _inference_error("transform_state_stats_invalid")
        values: dict[str, float] = {}
        for key, value in fields.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise _inference_error("transform_state_stats_invalid")
            if not math.isfinite(float(value)):
                raise _inference_error("transform_state_stats_invalid")
            values[key] = float(value)
        if values["std"] <= 0.0 or not values["winsor_lower"] < values["winsor_upper"]:
            raise _inference_error("transform_state_stats_invalid")
        state[name] = values
    return state


def _required_field(
    document: Mapping[str, object],
    key: str,
) -> object:
    """Read one required training-record field with a typed refusal."""
    value = document.get(key)
    if value is None:
        raise _inference_error("training_artifact_payload_invalid", missing=key)
    return value


def load_model_training_artifact(
    reader: IndexedJsonReaderPort,
    training_artifact_id: str,
) -> LoadedModelArtifact:
    """Load one training record and its bound states, verifying checksums."""
    if not training_artifact_id.startswith("model-training-"):
        raise _inference_error(
            "training_artifact_id_invalid",
            artifact_id=training_artifact_id,
        )
    record_document = reader.read_indexed_json(training_artifact_id)
    if record_document.get("schema") != MODEL_TRAINING_ARTIFACT_SCHEMA:
        raise _inference_error("training_artifact_schema_invalid")
    registration_payload = record_document.get("registration_payload")
    if not isinstance(registration_payload, dict):
        raise _inference_error("training_artifact_payload_invalid")
    training = ModelTrainingRecord(
        schema=cast("str", _required_field(record_document, "schema")),
        registration_hash=cast(
            "str", _required_field(record_document, "registration_hash")
        ),
        registration_payload=cast("dict[str, object]", registration_payload),
        snapshot_id=cast("str", _required_field(record_document, "snapshot_id")),
        train_window_start=cast(
            "str", _required_field(record_document, "train_window_start")
        ),
        train_window_end=cast(
            "str", _required_field(record_document, "train_window_end")
        ),
        label_maturity_cutoff_epoch_us=cast(
            "int", _required_field(record_document, "label_maturity_cutoff_epoch_us")
        ),
        trained_at_epoch_us=cast(
            "int", _required_field(record_document, "trained_at_epoch_us")
        ),
        sample_count=cast("int", _required_field(record_document, "sample_count")),
        model_state_sha256=cast(
            "str", _required_field(record_document, "model_state_sha256")
        ),
        transform_state_sha256=cast(
            "str", _required_field(record_document, "transform_state_sha256")
        ),
        feature_names=tuple(
            cast("list[str]", _required_field(record_document, "feature_names")),
        ),
    )
    model_state = reader.read_indexed_json(
        model_state_artifact_id(training.registration_hash, training.model_state_sha256)
    )
    transform_raw = reader.read_indexed_json(
        transform_state_artifact_id(
            training.registration_hash, training.transform_state_sha256
        )
    )
    if model_state_sha256(model_state) != training.model_state_sha256:
        raise _inference_error("model_state_checksum_drift")
    if model_state_sha256(transform_raw) != training.transform_state_sha256:
        raise _inference_error("transform_state_checksum_drift")
    transform_state = _decode_transform_state(transform_raw, training.feature_names)
    return LoadedModelArtifact(
        training=training,
        model_state=model_state,
        transform_state=transform_state,
    )


def verify_loaded_model_integrity(
    artifact: LoadedModelArtifact,
    lineage: ModelCandidateLineage,
) -> None:
    """Verify registration identity and kind state before inference."""
    if (
        artifact.training.registration_hash != lineage.registration_hash
        or artifact.training.feature_names != lineage.feature_names
    ):
        raise _inference_error(
            "model_registration_identity_mismatch",
            expected=lineage.registration_hash,
            observed=artifact.training.registration_hash,
        )
    if lineage.model_kind is ModelKind.RULE:
        if (
            artifact.model_state.get("ranking_feature")
            != lineage.hyperparameters["ranking_feature"]
        ):
            raise _inference_error("rule_model_state_invalid")
    elif lineage.model_kind is ModelKind.LIGHTGBM:
        state = artifact.model_state
        if (
            not isinstance(state.get("booster_model"), str)
            or tuple(state.get("feature_names") or ())  # type: ignore[arg-type]
            != lineage.feature_names
        ):
            raise _inference_error("lightgbm_model_state_invalid")
    elif not isinstance(artifact.model_state.get("coef"), list):
        raise _inference_error("linear_model_state_invalid")


@dataclass(frozen=True, slots=True)
class ModelInferenceRequest:
    """One decision context to score with one recovered model."""

    lineage: ModelCandidateLineage
    artifact: LoadedModelArtifact
    feature_frame: pl.DataFrame
    decision_sessions: tuple[date, ...]
    decision_time_epoch_us: int
    feature_snapshot_id: str
    knowledge_cutoff_epoch_us: int

    def __post_init__(self) -> None:
        """Validate frame schema, sessions, and the as-of decision binding."""
        if type(self.feature_frame) is not pl.DataFrame:
            raise _inference_error("feature_frame_invalid")
        schema = self.feature_frame.schema
        expected = {_ENTITY_COLUMN, _SESSION_COLUMN, *self.lineage.feature_names}
        if set(schema) != expected:
            raise _inference_error(
                "feature_frame_schema_drift",
                expected=sorted(expected),
                observed=sorted(schema),
            )
        if (
            self.feature_frame.select([_ENTITY_COLUMN, _SESSION_COLUMN])
            .is_duplicated()
            .any()
        ):
            raise _inference_error("feature_frame_duplicate_keys")
        if not self.decision_sessions or any(
            type(item) is not date for item in self.decision_sessions
        ):
            raise _inference_error("decision_sessions_invalid")
        allowed = set(self.decision_sessions)
        observed_sessions = set(
            self.feature_frame.get_column(_SESSION_COLUMN).to_list()
        )
        if not observed_sessions or not observed_sessions <= allowed:
            raise _inference_error("feature_frame_sessions_outside_decision_context")
        for field_name in (
            "decision_time_epoch_us",
            "knowledge_cutoff_epoch_us",
        ):
            if type(getattr(self, field_name)) is not int or (
                getattr(self, field_name) < 0
            ):
                raise _inference_error(f"{field_name}_invalid")
        if type(self.feature_snapshot_id) is not str or not self.feature_snapshot_id:
            raise _inference_error("feature_snapshot_invalid")


@dataclass(frozen=True, slots=True)
class ModelInferenceSuccess:
    """Verified deterministic scores for the requested decision context."""

    rows: tuple[ModelPredictionRow, ...]
    model_artifact_hash: str


@dataclass(frozen=True, slots=True)
class ModelInferenceFailure:
    """Explicit refusal reason; no signal is ever attached."""

    reason: str


def _linear_weights_from_state(
    model_state: dict[str, object],
    feature_count: int,
) -> tuple[list[float], float] | None:
    """Extract validated weights/intercept from a frozen linear state."""
    coef = model_state.get("coef")
    intercept = model_state.get("intercept")
    if not isinstance(coef, list):
        return None
    weights: list[float] = []
    for item in cast("list[object]", coef):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        weights.append(float(item))
    if (
        len(weights) != feature_count
        or isinstance(intercept, bool)
        or not isinstance(intercept, (int, float))
    ):
        return None
    return weights, float(intercept)


def infer_model_predictions(  # noqa: PLR0911, C901 - fail-closed recovery stages
    request: ModelInferenceRequest,
) -> ModelInferenceSuccess | ModelInferenceFailure:
    """Score one decision context with a recovered model, or refuse."""
    try:
        verify_loaded_model_integrity(request.artifact, request.lineage)
    except AppProcessError as error:
        return ModelInferenceFailure(
            str(error.details.get("reason", "integrity_failed"))
        )
    training = request.artifact.training
    if training.trained_at_epoch_us > request.decision_time_epoch_us:
        return ModelInferenceFailure("model_not_complete_at_decision_time")
    if request.feature_snapshot_id != training.snapshot_id:
        return ModelInferenceFailure("feature_snapshot_mismatch")
    if request.knowledge_cutoff_epoch_us > request.decision_time_epoch_us:
        # Feature knowledge must not reach past the decision itself.
        return ModelInferenceFailure("knowledge_cutoff_after_decision_time")
    lineage = request.lineage
    frame = request.feature_frame
    if lineage.model_kind is ModelKind.RULE:
        # Same frozen median policy as the other kinds: all baselines score
        # the same cross-section, row-level nulls included.
        ranking_feature = cast("str", lineage.hyperparameters["ranking_feature"])
        stats = request.artifact.transform_state[ranking_feature]
        prediction_values = frame.get_column(ranking_feature).fill_null(
            value=stats["median"]
        )
        scored = _scored_frame(frame, prediction_values)
        if scored.height == 0:
            return ModelInferenceFailure("predictions_non_finite")
        return _success(training, scored)
    try:
        matrix = transform_feature_matrix(
            frame, lineage.feature_names, request.artifact.transform_state
        )
        if lineage.model_kind is ModelKind.LIGHTGBM:
            prediction_values = pl.Series(
                lightgbm_predictions_from_state(request.artifact.model_state, matrix)
            )
        else:
            linear = _linear_weights_from_state(
                request.artifact.model_state, len(lineage.feature_names)
            )
            if linear is None:
                return ModelInferenceFailure("linear_model_state_invalid")
            weights, intercept_value = linear
            prediction_values = pl.Series(
                matrix @ np.asarray(weights, dtype=np.float64) + intercept_value
            )
    except AppProcessError as error:
        return ModelInferenceFailure(
            str(error.details.get("reason", "inference_execution_failed"))
        )
    scored = _scored_frame(frame, prediction_values)
    if scored.height == 0:
        return ModelInferenceFailure("predictions_non_finite")
    return _success(training, scored)


def _scored_frame(frame: pl.DataFrame, prediction_values: pl.Series) -> pl.DataFrame:
    """Attach finite-filtered prediction values to the decision frame."""
    return (
        frame.select(
            [
                pl.col(_ENTITY_COLUMN),
                pl.col(_SESSION_COLUMN).alias("decision_session"),
            ]
        )
        .with_columns(prediction_values.alias("prediction"))
        .filter(pl.col("prediction").is_not_null() & pl.col("prediction").is_finite())
    )


def _success(
    training: ModelTrainingRecord,
    scored: pl.DataFrame,
) -> ModelInferenceSuccess:
    """Freeze verified rows bound to the recovered training artifact."""
    rows = tuple(
        ModelPredictionRow(
            entity_id=item[_ENTITY_COLUMN],
            decision_session=item["decision_session"].isoformat(),
            prediction=float(item["prediction"]),
        )
        for item in scored.to_dicts()
    )
    return ModelInferenceSuccess(
        rows=rows,
        model_artifact_hash=training.artifact_hash,
    )
