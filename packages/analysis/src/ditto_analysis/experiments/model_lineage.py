"""
Registered model-candidate lineage and immutable training/prediction records.

#268/#269 contract layer: the identity of a registered model candidate (rule
or linear; LightGBM joins the same contract later), the fail-closed content
contract for one immutable training artifact, and the prediction artifact that
a trained model emits for a fold's test window. Execution (fit/predict) lives
in the application layer; this module only owns identity, freezing, and
validation, so it stays numpy-free and I/O-free.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.persistence import (
    canonical_payload,
)

__all__ = [
    "MODEL_PREDICTION_ARTIFACT_SCHEMA",
    "MODEL_TRAINING_ARTIFACT_SCHEMA",
    "ModelCandidateLineage",
    "ModelKind",
    "ModelPredictionRecord",
    "ModelPredictionRow",
    "ModelTrainingRecord",
    "TrainFittedTransformSpec",
]

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MODEL_TRAINING_ARTIFACT_SCHEMA = "ditto.model.training-artifact.v1"
MODEL_PREDICTION_ARTIFACT_SCHEMA = "ditto.model.prediction-artifact.v1"

_HYPERPARAMETER_KEYS_BY_KIND: dict[str, frozenset[str]] = {
    "rule": frozenset({"ranking_feature"}),
    "linear": frozenset({"alpha"}),
}
_REQUIRED_CODE_ENVIRONMENT_KEYS = frozenset(
    {"implementation_key", "python", "lockfile_sha256"}
)


def _lineage_error(reason: str, **details: object) -> ExperimentSpecError:
    return ExperimentSpecError(
        "model candidate lineage is invalid",
        details={"reason_code": "MODEL_LINEAGE_INVALID", "reason": reason, **details},
    )


def _require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str or not _SHA256_PATTERN.match(value):
        raise _lineage_error(
            "sha256_field_invalid",
            field=field_name,
        )
    return value


def _require_iso_date(value: object, field_name: str) -> str:
    if type(value) is not str or not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise _lineage_error("date_field_invalid", field=field_name)
    return value


class ModelKind(StrEnum):
    """Registered model kinds sharing one training/prediction protocol."""

    RULE = "rule"
    LINEAR = "linear"


@dataclass(frozen=True, slots=True)
class TrainFittedTransformSpec:
    """Fixed v1 preprocessing fitted only inside each fold's training range."""

    imputation: str = "median"
    winsorize_lower_quantile: float = 0.01
    winsorize_upper_quantile: float = 0.99
    scaling: str = "zscore"

    def __post_init__(self) -> None:
        """Reject any preprocessing drift from the registered v1 recipe."""
        if self.imputation != "median" or self.scaling != "zscore":
            raise _lineage_error("transform_recipe_unsupported_v1")
        lower, upper = (
            self.winsorize_lower_quantile,
            self.winsorize_upper_quantile,
        )
        for value in (lower, upper):
            if type(value) is not float or not 0.0 <= value < 1.0:
                raise _lineage_error("transform_quantile_invalid")
        if not lower < upper:
            raise _lineage_error("transform_quantile_invalid")

    def canonical_payload(self) -> dict[str, object]:
        """Return the frozen recipe payload."""
        return {
            "imputation": self.imputation,
            "winsorize_lower_quantile": self.winsorize_lower_quantile,
            "winsorize_upper_quantile": self.winsorize_upper_quantile,
            "scaling": self.scaling,
        }


def _validated_hyperparameters(
    model_kind: ModelKind,
    hyperparameters: Mapping[str, object],
    *,
    feature_names: tuple[str, ...],
) -> dict[str, object]:
    """Validate the kind-specific registered hyperparameters."""
    values = dict(hyperparameters)
    expected_keys = _HYPERPARAMETER_KEYS_BY_KIND[model_kind.value]
    if set(values) != set(expected_keys):
        raise _lineage_error(
            "hyperparameter_keys_invalid",
            model_kind=model_kind.value,
            expected=sorted(expected_keys),
        )
    if model_kind is ModelKind.RULE:
        ranking_feature = values["ranking_feature"]
        if type(ranking_feature) is not str or ranking_feature not in feature_names:
            raise _lineage_error("ranking_feature_not_registered")
    else:
        if isinstance(values["alpha"], bool) or not isinstance(
            values["alpha"], (int, float)
        ):
            raise _lineage_error("alpha_invalid")
        alpha = float(values["alpha"])
        if not math.isfinite(alpha) or alpha <= 0.0:
            raise _lineage_error("alpha_invalid")
    return values


@dataclass(frozen=True, slots=True)
class ModelCandidateLineage:
    """
    Complete registered identity of one model candidate.

    Everything that can change training semantics is frozen here: feature
    order, label identity, transform recipe, kind hyperparameters, seed, and
    the code environment, so two candidates with the same lineage hash train
    bit-identically from the same inputs.
    """

    model_kind: ModelKind
    feature_names: tuple[str, ...]
    label_id: str
    label_spec_hash: str
    transform_spec: TrainFittedTransformSpec
    hyperparameters: Mapping[str, object]
    seed: int
    code_environment: Mapping[str, str]

    def __post_init__(self) -> None:
        """Validate and deep-freeze every registered semantic."""
        if type(self.model_kind) is not ModelKind:
            raise _lineage_error("model_kind_invalid")
        features = self.feature_names
        if (
            type(features) is not tuple
            or not features
            or any(
                type(name) is not str or not name.strip() or name != name.strip()
                for name in features
            )
            or len(set(features)) != len(features)
        ):
            raise _lineage_error("feature_names_invalid")
        if type(self.label_id) is not str or not self.label_id:
            raise _lineage_error("label_id_invalid")
        _require_sha256(self.label_spec_hash, "label_spec_hash")
        if type(self.transform_spec) is not TrainFittedTransformSpec:
            raise _lineage_error("transform_spec_invalid")
        hyperparameters = _validated_hyperparameters(
            self.model_kind,
            self.hyperparameters,
            feature_names=features,
        )
        if type(self.seed) is not int or self.seed < 0:
            raise _lineage_error("seed_invalid")
        environment = dict(self.code_environment)
        if (
            not environment
            or any(
                type(key) is not str or type(value) is not str or not value
                for key, value in environment.items()
            )
            or not set(environment) >= _REQUIRED_CODE_ENVIRONMENT_KEYS
        ):
            raise _lineage_error(
                "code_environment_invalid",
                required=sorted(_REQUIRED_CODE_ENVIRONMENT_KEYS),
            )
        object.__setattr__(
            self,
            "hyperparameters",
            MappingProxyType(dict(sorted(hyperparameters.items()))),
        )
        object.__setattr__(
            self,
            "code_environment",
            MappingProxyType(dict(sorted(environment.items()))),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return every training-semantics field of this registration."""
        return {
            "model_kind": self.model_kind.value,
            "feature_names": list(self.feature_names),
            "label_id": self.label_id,
            "label_spec_hash": self.label_spec_hash,
            "transform_spec": self.transform_spec.canonical_payload(),
            "hyperparameters": {
                key: _hyperparameter_json_value(value)
                for key, value in self.hyperparameters.items()
            },
            "seed": self.seed,
            "code_environment": dict(self.code_environment),
        }

    @property
    def registration_hash(self) -> str:
        """Return the canonical content identity of this registration."""
        return canonical_payload(self.canonical_payload()).content_hash.value


def _hyperparameter_json_value(value: object) -> str | float:
    """Render one validated hyperparameter as canonical JSON scalar."""
    if type(value) is str:
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _lineage_error("hyperparameter_value_invalid")
    return float(value)


@dataclass(frozen=True, slots=True)
class ModelTrainingRecord:
    """Content contract of one published immutable training artifact."""

    schema: str
    registration_hash: str
    snapshot_id: str
    train_window_start: str
    train_window_end: str
    label_maturity_cutoff_epoch_us: int
    trained_at_epoch_us: int
    sample_count: int
    model_state_sha256: str
    transform_state_sha256: str
    feature_names: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject partial or untyped training evidence."""
        if self.schema != MODEL_TRAINING_ARTIFACT_SCHEMA:
            raise _lineage_error("training_artifact_schema_invalid")
        _require_sha256(self.registration_hash, "registration_hash")
        if type(self.snapshot_id) is not str or not self.snapshot_id:
            raise _lineage_error("snapshot_id_invalid")
        _require_iso_date(self.train_window_start, "train_window_start")
        _require_iso_date(self.train_window_end, "train_window_end")
        if self.train_window_start > self.train_window_end:
            raise _lineage_error("train_window_inverted")
        for field_name in (
            "label_maturity_cutoff_epoch_us",
            "trained_at_epoch_us",
        ):
            if (
                type(getattr(self, field_name)) is not int
                or getattr(self, field_name) < 0
            ):
                raise _lineage_error("epoch_field_invalid", field=field_name)
        if self.trained_at_epoch_us < self.label_maturity_cutoff_epoch_us:
            # Training cannot complete before the newest label it consumed.
            raise _lineage_error("trained_before_label_maturity")
        if type(self.sample_count) is not int or self.sample_count <= 0:
            raise _lineage_error("sample_count_invalid")
        _require_sha256(self.model_state_sha256, "model_state_sha256")
        _require_sha256(self.transform_state_sha256, "transform_state_sha256")
        if (
            type(self.feature_names) is not tuple
            or not self.feature_names
            or any(type(name) is not str for name in self.feature_names)
        ):
            raise _lineage_error("feature_names_invalid")

    def canonical_payload(self) -> dict[str, object]:
        """Return every field a training-artifact reader must verify."""
        return {
            "schema": self.schema,
            "registration_hash": self.registration_hash,
            "snapshot_id": self.snapshot_id,
            "train_window_start": self.train_window_start,
            "train_window_end": self.train_window_end,
            "label_maturity_cutoff_epoch_us": self.label_maturity_cutoff_epoch_us,
            "trained_at_epoch_us": self.trained_at_epoch_us,
            "sample_count": self.sample_count,
            "model_state_sha256": self.model_state_sha256,
            "transform_state_sha256": self.transform_state_sha256,
            "feature_names": list(self.feature_names),
        }

    @property
    def artifact_hash(self) -> str:
        """Return the canonical content identity of this training record."""
        return canonical_payload(self.canonical_payload()).content_hash.value


@dataclass(frozen=True, slots=True)
class ModelPredictionRow:
    """One deterministic score for one instrument at one decision session."""

    entity_id: str
    decision_session: str
    prediction: float

    def __post_init__(self) -> None:
        """Reject ambiguous identity or non-finite scores."""
        if (
            type(self.entity_id) is not str
            or not self.entity_id
            or self.entity_id != self.entity_id.strip()
        ):
            raise _lineage_error("prediction_entity_invalid")
        _require_iso_date(self.decision_session, "prediction_decision_session")
        if type(self.prediction) is not float or not math.isfinite(self.prediction):
            raise _lineage_error("prediction_value_invalid")


@dataclass(frozen=True, slots=True)
class ModelPredictionRecord:
    """Content contract of one published immutable prediction artifact."""

    schema: str
    registration_hash: str
    model_artifact_hash: str
    prediction_window_start: str
    prediction_window_end: str
    rows: tuple[ModelPredictionRow, ...]

    def __post_init__(self) -> None:
        """Reject empty, duplicated, or untyped prediction evidence."""
        if self.schema != MODEL_PREDICTION_ARTIFACT_SCHEMA:
            raise _lineage_error("prediction_artifact_schema_invalid")
        _require_sha256(self.registration_hash, "registration_hash")
        _require_sha256(self.model_artifact_hash, "model_artifact_hash")
        _require_iso_date(self.prediction_window_start, "prediction_window_start")
        _require_iso_date(self.prediction_window_end, "prediction_window_end")
        if self.prediction_window_start > self.prediction_window_end:
            raise _lineage_error("prediction_window_inverted")
        rows = self.rows
        if (
            type(rows) is not tuple
            or not rows
            or any(type(row) is not ModelPredictionRow for row in rows)
        ):
            raise _lineage_error("prediction_rows_invalid")
        keys = [(row.entity_id, row.decision_session) for row in rows]
        if len(set(keys)) != len(keys):
            raise _lineage_error("prediction_rows_duplicated")

    def canonical_payload(self) -> dict[str, object]:
        """Return every field a prediction-artifact reader must verify."""
        return {
            "schema": self.schema,
            "registration_hash": self.registration_hash,
            "model_artifact_hash": self.model_artifact_hash,
            "prediction_window_start": self.prediction_window_start,
            "prediction_window_end": self.prediction_window_end,
            "rows": [
                {
                    "entity_id": row.entity_id,
                    "decision_session": row.decision_session,
                    "prediction": row.prediction,
                }
                for row in self.rows
            ],
        }

    @property
    def artifact_hash(self) -> str:
        """Return the canonical content identity of this prediction record."""
        return canonical_payload(self.canonical_payload()).content_hash.value


def freeze_prediction_rows(rows: object) -> tuple[ModelPredictionRow, ...]:
    """Freeze runtime prediction rows into validated contract rows."""
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise _lineage_error("prediction_rows_invalid")
    return tuple(
        row if type(row) is ModelPredictionRow else _coerce_prediction_row(row)
        for row in cast("Sequence[object]", rows)
    )


def _coerce_prediction_row(raw: object) -> ModelPredictionRow:
    """Build one contract row from a plain mapping, failing closed."""
    if not isinstance(raw, Mapping):
        raise _lineage_error("prediction_row_invalid")
    mapping = cast("Mapping[str, object]", raw)
    if set(mapping) != {"entity_id", "decision_session", "prediction"}:
        raise _lineage_error("prediction_row_invalid")
    entity_id = mapping["entity_id"]
    decision_session = mapping["decision_session"]
    prediction = mapping["prediction"]
    if type(entity_id) is not str or type(decision_session) is not str:
        raise _lineage_error("prediction_row_invalid")
    if isinstance(prediction, bool) or not isinstance(prediction, (int, float)):
        raise _lineage_error("prediction_value_invalid")
    return ModelPredictionRow(
        entity_id=entity_id,
        decision_session=decision_session,
        prediction=float(prediction),
    )
