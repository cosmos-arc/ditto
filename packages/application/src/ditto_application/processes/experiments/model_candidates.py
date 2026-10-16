"""
Fail-closed fold-scoped training for registered model candidates (#268).

One candidate × one fold: validate the registered isolation against the real
label intervals, fit transforms and the model on the training range only,
predict the fold's test window, and freeze immutable training/prediction
records. Every refusal carries an explicit reason; nothing half-finished is
ever reported as success. Publishing the frozen bytes into durable storage is
the caller's job (``ModelArtifactSink``), so this module performs no I/O.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import TypeGuard, cast

import numpy as np
import orjson
import polars as pl
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
from ditto_analysis.experiments.persistence import DateWindow
from ditto_features.evaluation.research_labels import (
    LABEL_STATUS_MATURE,
    ResearchLabelFrame,
    label_spec_hash,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.research_validation_windows import ValidationFoldPlan

__all__ = [
    "ModelFoldIsolationReport",
    "ModelFoldTrainingRequest",
    "ModelTrainingFailure",
    "ModelTrainingSuccess",
    "canonical_model_state_bytes",
    "lightgbm_predictions_from_state",
    "model_state_sha256",
    "train_model_candidate",
    "transform_feature_matrix",
    "validate_fold_label_isolation",
]

_ENTITY_COLUMN = "instrument_id"
_SESSION_COLUMN = "session"
_MIN_TRAINING_SAMPLES_PER_FEATURE = 2


def _training_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "model candidate training failed closed",
        details={"code": "MODEL_TRAINING_FAILED", "reason": reason, **details},
    )


@dataclass(frozen=True, slots=True)
class ModelFoldIsolationReport:
    """Real-interval isolation outcome for one fold's training labels."""

    retained_sample_count: int
    excluded_immature_count: int
    excluded_gap_count: int
    worst_retained_exit_session: date | None
    required_gap_sessions: int

    def __post_init__(self) -> None:
        """Validate counting invariants."""
        for field_name in (
            "retained_sample_count",
            "excluded_immature_count",
            "excluded_gap_count",
            "required_gap_sessions",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise _training_error("isolation_report_field_invalid")


@dataclass(frozen=True, slots=True)
class ModelFoldTrainingRequest:
    """Complete typed inputs for one candidate-fold training execution."""

    experiment_id: str
    candidate_id: str
    fold_id: str
    lineage: ModelCandidateLineage
    fold: ValidationFoldPlan
    feature_frame: pl.DataFrame
    labels: ResearchLabelFrame
    trading_sessions: tuple[date, ...]
    snapshot_id: str
    knowledge_cutoff_epoch_us: int
    trained_at_epoch_us: int

    def __post_init__(self) -> None:
        """Validate typed identity before any training work."""
        _require_execution_lineage(
            self.experiment_id,
            self.candidate_id,
            self.fold_id,
        )
        if type(self.lineage) is not ModelCandidateLineage:
            raise _training_error("lineage_invalid")
        if type(self.fold) is not ValidationFoldPlan:
            raise _training_error("fold_invalid")
        if self.fold.train_window is None:
            raise _training_error("fold_train_window_missing")
        if type(self.labels) is not ResearchLabelFrame:
            raise _training_error("labels_invalid")
        _require_label_binding(self.labels, self.lineage)
        if type(self.feature_frame) is not pl.DataFrame:
            raise _training_error("feature_frame_invalid")
        _require_feature_frame(self.feature_frame, self.lineage.feature_names)
        _require_trading_sessions(self.trading_sessions)
        _require_window_sessions(self.fold, self.trading_sessions)
        if type(self.snapshot_id) is not str or not self.snapshot_id:
            raise _training_error("snapshot_id_invalid")
        for field_name in (
            "knowledge_cutoff_epoch_us",
            "trained_at_epoch_us",
        ):
            if (
                type(getattr(self, field_name)) is not int
                or getattr(self, field_name) < 0
            ):
                raise _training_error("cutoff_invalid", field=field_name)


def _require_execution_lineage(
    experiment_id: str,
    candidate_id: str,
    fold_id: str,
) -> None:
    """Reject blank, padded, or path-unsafe execution lineage identities."""
    for field_name, value in (
        ("experiment_id", experiment_id),
        ("candidate_id", candidate_id),
        ("fold_id", fold_id),
    ):
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or "/" in value
        ):
            raise _training_error("execution_lineage_invalid", field=field_name)


def _require_label_binding(
    labels: ResearchLabelFrame,
    lineage: ModelCandidateLineage,
) -> None:
    """Bind the registration to the label identity and builder actually in use."""
    if labels.label_id != lineage.label_id:
        raise _training_error(
            "label_identity_mismatch",
            registered=lineage.label_id,
            provided=labels.label_id,
        )
    if lineage.label_spec_hash != label_spec_hash():
        raise _training_error(
            "label_spec_hash_not_bound_to_builder",
            registered=lineage.label_spec_hash,
            builder=label_spec_hash(),
        )


def _require_feature_frame(
    frame: pl.DataFrame,
    feature_names: tuple[str, ...],
) -> None:
    """Validate feature schema and key uniqueness against the registration."""
    schema = frame.schema
    expected_columns = [_ENTITY_COLUMN, _SESSION_COLUMN, *feature_names]
    if set(schema) != set(expected_columns):
        raise _training_error(
            "feature_frame_schema_drift",
            expected=sorted(expected_columns),
            observed=sorted(schema),
        )
    if (
        schema.get(_ENTITY_COLUMN) != pl.String
        or schema.get(_SESSION_COLUMN) != pl.Date
    ):
        raise _training_error("feature_frame_identity_columns_invalid")
    for name in feature_names:
        if schema.get(name) != pl.Float64:
            raise _training_error(
                "feature_column_dtype_invalid",
                feature=name,
                expected="Float64",
                observed=str(schema.get(name)),
            )
    if frame.select([_ENTITY_COLUMN, _SESSION_COLUMN]).is_duplicated().any():
        raise _training_error("feature_frame_duplicate_keys")


def _require_trading_sessions(sessions: tuple[date, ...]) -> None:
    """Require a strictly increasing, typed trading calendar."""
    if (
        not sessions
        or any(type(item) is not date for item in sessions)
        or any(current >= following for current, following in pairwise(sessions))
    ):
        raise _training_error("trading_sessions_invalid")


def _require_window_sessions(
    fold: ValidationFoldPlan,
    sessions: tuple[date, ...],
) -> None:
    """Require every fold boundary to be a real trading session."""
    train_window = fold.train_window
    if train_window is None:
        raise _training_error("fold_train_window_missing")
    boundaries = (
        ("train_window_start", train_window.start),
        ("train_window_end", train_window.end),
        ("test_window_start", fold.test_window.start),
        ("test_window_end", fold.test_window.end),
    )
    for field_name, boundary in boundaries:
        if boundary not in sessions:
            raise _training_error(f"{field_name}_not_a_session")


@dataclass(frozen=True, slots=True)
class ModelTrainingSuccess:
    """Published-contract outputs of one successful training execution."""

    training: ModelTrainingRecord
    predictions: ModelPredictionRecord
    model_state_bytes: bytes
    transform_state_bytes: bytes
    isolation: ModelFoldIsolationReport


@dataclass(frozen=True, slots=True)
class ModelTrainingFailure:
    """Explicit refusal reason; no partial artifact is ever attached."""

    reason: str
    details: Mapping[str, object] | None = None


def _session_ordinals(sessions: tuple[date, ...]) -> dict[date, int]:
    return {session: ordinal for ordinal, session in enumerate(sessions)}


def validate_fold_label_isolation(
    fold: ValidationFoldPlan,
    labels: ResearchLabelFrame,
    trading_sessions: tuple[date, ...],
    *,
    knowledge_cutoff_epoch_us: int,
) -> tuple[pl.DataFrame, ModelFoldIsolationReport]:
    """
    Retain only training labels isolated from the test window by real dates.

    Purge and embargo are applied on the actual label intervals using session
    ordinals, never on row counts. Labels whose exit session reaches the
    required gap are excluded (purge); immature labels are excluded; the
    registered embargo must still cover the label window carried by the
    supplied frame or the fold is refused outright.
    """
    if fold.train_window is None:
        raise _training_error("fold_train_window_missing")
    required_gap = max(fold.purge_sessions, fold.embargo_sessions)
    if fold.embargo_sessions < labels.holding_sessions:
        raise _training_error(
            "embargo_below_label_window",
            embargo_sessions=fold.embargo_sessions,
            holding_sessions=labels.holding_sessions,
        )
    ordinals = _session_ordinals(trading_sessions)
    test_start_ordinal = ordinals[fold.test_window.start]
    candidates = labels.frame.filter(
        (pl.col("decision_session") >= fold.train_window.start)
        & (pl.col("decision_session") <= fold.train_window.end)
    )
    mature = candidates.filter(
        (pl.col("status") == LABEL_STATUS_MATURE)
        & (pl.col("mature_at_epoch_us") <= knowledge_cutoff_epoch_us)
    )
    excluded_immature = candidates.height - mature.height
    unmapped_exits = (
        mature.get_column("exit_session").is_in(list(ordinals)).not_().sum()
    )
    if unmapped_exits:
        # Exit sessions outside the request calendar cannot be gap-measured on
        # real sessions; refuse instead of letting polars mapping errors escape.
        raise _training_error(
            "label_exit_session_not_in_calendar",
            unmapped_exit_sessions=int(unmapped_exits),
        )
    exit_ordinal = mature.get_column("exit_session").replace_strict(
        ordinals, return_dtype=pl.Int64
    )
    gaps = (
        pl.Series("gap", [test_start_ordinal] * mature.height, dtype=pl.Int64)
        - exit_ordinal
        - 1
    )
    retained_frame = mature.with_columns(gaps.alias("test_gap_sessions")).filter(
        pl.col("test_gap_sessions") >= required_gap
    )
    excluded_gap = mature.height - retained_frame.height
    worst_exit: date | None = None
    if retained_frame.height:
        worst_exit = cast(
            "date | None", retained_frame.get_column("exit_session").max()
        )
    report = ModelFoldIsolationReport(
        retained_sample_count=retained_frame.height,
        excluded_immature_count=excluded_immature,
        excluded_gap_count=excluded_gap,
        worst_retained_exit_session=worst_exit,
        required_gap_sessions=required_gap,
    )
    return retained_frame, report


def canonical_model_state_bytes(payload: Mapping[str, object]) -> bytes:
    """
    Encode one frozen model/transform state deterministically.

    Shared by training, publication, and recovery so checksums always refer to
    one serialization authority.
    """
    return orjson.dumps(dict(payload), option=orjson.OPT_SORT_KEYS)


def model_state_sha256(payload: Mapping[str, object]) -> str:
    """Return the canonical content checksum of one frozen state."""
    return hashlib.sha256(canonical_model_state_bytes(payload)).hexdigest()


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fit_transform_state(
    train_frame: pl.DataFrame,
    transform_spec: TrainFittedTransformSpec,
    feature_names: tuple[str, ...],
) -> tuple[dict[str, dict[str, float]], bytes]:
    """
    Fit median imputation, winsorize bounds, and z-score on train rows only.

    The winsorize bounds come from the registered spec, never from defaults,
    so changing the registration changes the fitted transform.
    """
    state: dict[str, dict[str, float]] = {}
    for name in feature_names:
        column = train_frame.get_column(name).drop_nulls()
        if column.len() == 0:
            raise _training_error("train_feature_all_null", feature=name)
        median = cast("float | None", column.median())
        lower: float | None = column.quantile(
            transform_spec.winsorize_lower_quantile, interpolation="linear"
        )
        upper: float | None = column.quantile(
            transform_spec.winsorize_upper_quantile, interpolation="linear"
        )
        if median is None or lower is None or upper is None:
            raise _training_error("train_feature_non_finite", feature=name)
        clipped = column.clip(lower_bound=lower, upper_bound=upper)
        mean = cast("float | None", clipped.mean())
        std = cast("float | None", clipped.std())
        if mean is None or std is None or not math.isfinite(std) or std <= 0.0:
            raise _training_error("train_feature_degenerate", feature=name)
        values = [median, lower, upper, mean, std]
        if any(not math.isfinite(value) for value in values):
            raise _training_error("train_feature_non_finite", feature=name)
        state[name] = {
            "median": median,
            "winsor_lower": lower,
            "winsor_upper": upper,
            "mean": mean,
            "std": std,
        }
    return state, canonical_model_state_bytes(state)


def transform_feature_matrix(
    frame: pl.DataFrame,
    feature_names: tuple[str, ...],
    transform_state: Mapping[str, dict[str, float]],
) -> np.ndarray:
    """
    Apply the fitted impute/winsorize/scale recipe to raw feature columns.

    Shared by fold training and recovered-model inference so both paths apply
    exactly one frozen transform implementation. Row-level nulls follow the
    frozen training policy (train median); an entirely missing feature column
    is a different failure and is refused outright.
    """
    columns: list[np.ndarray] = []
    for name in feature_names:
        stats = transform_state[name]
        raw_column = frame.get_column(name)
        if raw_column.null_count() == raw_column.len():
            raise _training_error("feature_column_missing", feature=name)
        column = raw_column.fill_null(value=stats["median"]).clip(
            lower_bound=stats["winsor_lower"],
            upper_bound=stats["winsor_upper"],
        )
        scaled = (column - stats["mean"]) / stats["std"]
        columns.append(scaled.to_numpy())
    return np.column_stack(columns).astype(np.float64, copy=False)


def _fit_ridge(
    matrix: np.ndarray,
    targets: np.ndarray,
    alpha: float,
) -> tuple[np.ndarray, float]:
    """Closed-form ridge regression: w = (X'X + alpha*I)^-1 X'(y - y_mean)."""
    intercept = float(targets.mean())
    centered = targets - intercept
    gram = matrix.T @ matrix
    regularized = gram + alpha * np.eye(matrix.shape[1], dtype=np.float64)
    try:
        weights = np.linalg.solve(regularized, matrix.T @ centered)
    except np.linalg.LinAlgError as error:
        raise _training_error("ridge_solve_failed") from error
    if not np.all(np.isfinite(weights)):
        raise _training_error("ridge_weights_non_finite")
    return weights, intercept


def _joined_training_frame(
    request: ModelFoldTrainingRequest,
    retained_labels: pl.DataFrame,
    train_window: object,
) -> pl.DataFrame | None:
    """Join training-range features to retained labels, or None when empty."""
    window = cast("DateWindow", train_window)
    training_features = request.feature_frame.filter(
        (pl.col(_SESSION_COLUMN) >= window.start)
        & (pl.col(_SESSION_COLUMN) <= window.end)
    )
    joined = training_features.join(
        retained_labels.select(
            [
                pl.col(_ENTITY_COLUMN),
                pl.col("decision_session").alias(_SESSION_COLUMN),
                pl.col("label_value"),
            ]
        ),
        on=[_ENTITY_COLUMN, _SESSION_COLUMN],
        how="inner",
    )
    return joined if joined.height else None


def _fit_model_state(
    lineage: ModelCandidateLineage,
    joined: pl.DataFrame,
    transform_state: dict[str, dict[str, float]],
    *,
    seed: int,
) -> tuple[dict[str, object], bytes]:
    """Fit the registered model kind on the transformed training matrix."""
    if lineage.model_kind is ModelKind.RULE:
        model_state: dict[str, object] = {
            "ranking_feature": cast("str", lineage.hyperparameters["ranking_feature"])
        }
        return model_state, canonical_model_state_bytes(model_state)
    matrix = transform_feature_matrix(joined, lineage.feature_names, transform_state)
    targets = joined.get_column("label_value").to_numpy().astype(np.float64, copy=False)
    if lineage.model_kind is ModelKind.LIGHTGBM:
        return _fit_lightgbm_state(lineage, matrix, targets, seed=seed)
    alpha = float(cast("int | float", lineage.hyperparameters["alpha"]))
    weights, intercept = _fit_ridge(matrix, targets, alpha)
    state: dict[str, object] = {
        "coef": [float(value) for value in weights],
        "intercept": intercept,
    }
    return state, canonical_model_state_bytes(state)


def _fit_lightgbm_state(
    lineage: ModelCandidateLineage,
    matrix: np.ndarray,
    targets: np.ndarray,
    *,
    seed: int,
) -> tuple[dict[str, object], bytes]:
    """Train the registered LightGBM regressor with deterministic settings."""
    import lightgbm as lgb  # noqa: PLC0415 - lazy import keeps ML-only cost

    params = {
        "objective": "regression",
        "num_leaves": int(cast("int", lineage.hyperparameters["num_leaves"])),
        "learning_rate": float(
            cast("int | float", lineage.hyperparameters["learning_rate"])
        ),
        "seed": seed,
        "deterministic": True,
        "force_col_wise": True,
        "num_threads": 1,
        "verbosity": -1,
    }
    dataset = lgb.Dataset(matrix, label=targets)
    booster = lgb.train(  # pyright: ignore[reportUnknownMemberType] - stub gap
        params,
        dataset,
        num_boost_round=int(cast("int", lineage.hyperparameters["num_iterations"])),
    )
    state: dict[str, object] = {
        "booster_model": booster.model_to_string(),
        "feature_names": list(lineage.feature_names),
    }
    return state, canonical_model_state_bytes(state)


def lightgbm_predictions_from_state(
    model_state: Mapping[str, object],
    matrix: np.ndarray,
) -> np.ndarray:
    """
    Score with a frozen LightGBM booster, failing closed on bad state.

    Shared by fold training and recovered-model inference so booster
    reconstruction has exactly one authority.
    """
    import lightgbm as lgb  # noqa: PLC0415 - lazy import keeps ML-only cost

    booster_model = model_state.get("booster_model")
    if type(booster_model) is not str or not booster_model:
        raise _training_error("model_state_invalid")
    try:
        booster = lgb.Booster(model_file=None, model_str=booster_model)
    except (lgb.basic.LightGBMError, ValueError, TypeError) as error:
        raise _training_error("booster_state_corrupt") from error
    scores = booster.predict(  # pyright: ignore[reportUnknownMemberType] - stub gap
        matrix
    )
    if not isinstance(scores, np.ndarray) or scores.shape != (matrix.shape[0],):
        raise _training_error("booster_output_invalid")
    return scores.astype(np.float64, copy=False)


def _linear_prediction_inputs(
    model_state: Mapping[str, object],
) -> tuple[np.ndarray, float]:
    """Extract validated coef/intercept from a frozen linear model state."""
    coef = model_state.get("coef")
    intercept = model_state.get("intercept")
    if not isinstance(coef, list):
        raise _training_error("model_state_invalid")
    values: list[float] = []
    for item in cast("list[object]", coef):
        if not _is_real_number(item):
            raise _training_error("model_state_invalid")
        values.append(float(item))
    if isinstance(intercept, bool) or not _is_real_number(intercept):
        raise _training_error("model_state_invalid")
    return np.asarray(values, dtype=np.float64), float(intercept)


def _is_real_number(value: object) -> TypeGuard[int | float]:
    """Narrow to JSON-safe numeric values (bool is never a number here)."""
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _prediction_frame_for_test_window(
    request: ModelFoldTrainingRequest,
    lineage: ModelCandidateLineage,
    transform_state: dict[str, dict[str, float]],
    model_state: dict[str, object],
) -> pl.DataFrame:
    """Score the fold's test window with the frozen train-fitted state."""
    test_features = request.feature_frame.filter(
        (pl.col(_SESSION_COLUMN) >= request.fold.test_window.start)
        & (pl.col(_SESSION_COLUMN) <= request.fold.test_window.end)
        & pl.col(_SESSION_COLUMN).is_in(list(request.trading_sessions))
    )
    if lineage.model_kind is ModelKind.RULE:
        # The rule baseline ranks the registered factor directly; row-level
        # nulls follow the same frozen median policy as the other kinds so all
        # baselines score the same cross-section.
        ranking_feature = cast("str", lineage.hyperparameters["ranking_feature"])
        stats = transform_state[ranking_feature]
        prediction_values = test_features.get_column(ranking_feature).fill_null(
            value=stats["median"]
        )
    else:
        test_matrix = transform_feature_matrix(
            test_features, lineage.feature_names, transform_state
        )
        if lineage.model_kind is ModelKind.LIGHTGBM:
            prediction_values = pl.Series(
                lightgbm_predictions_from_state(model_state, test_matrix)
            )
        else:
            weights_array, intercept_value = _linear_prediction_inputs(model_state)
            prediction_values = pl.Series(test_matrix @ weights_array + intercept_value)
    return (
        test_features.select(
            [
                pl.col(_ENTITY_COLUMN),
                pl.col(_SESSION_COLUMN).alias("decision_session"),
            ]
        )
        .with_columns(prediction_values.alias("prediction"))
        .filter(pl.col("prediction").is_not_null() & pl.col("prediction").is_finite())
    )


def _assemble_success(
    request: ModelFoldTrainingRequest,
    joined: pl.DataFrame,
    prediction_frame: pl.DataFrame,
    model_state: dict[str, object],
    model_bytes: bytes,
    transform_bytes: bytes,
    isolation: ModelFoldIsolationReport,
) -> ModelTrainingSuccess | ModelTrainingFailure:
    """Freeze the immutable training/prediction records for this fold."""
    lineage = request.lineage
    train_window = request.fold.train_window
    if train_window is None:  # pragma: no cover - guarded in request validation
        return ModelTrainingFailure("fold_train_window_missing")
    try:
        rows = tuple(
            ModelPredictionRow(
                entity_id=item[_ENTITY_COLUMN],
                decision_session=item["decision_session"].isoformat(),
                prediction=float(item["prediction"]),
            )
            for item in prediction_frame.to_dicts()
        )
        training_record = ModelTrainingRecord(
            schema=MODEL_TRAINING_ARTIFACT_SCHEMA,
            experiment_id=request.experiment_id,
            candidate_id=request.candidate_id,
            fold_id=request.fold_id,
            registration_hash=lineage.registration_hash,
            registration_payload=lineage.canonical_payload(),
            snapshot_id=request.snapshot_id,
            train_window_start=train_window.start.isoformat(),
            train_window_end=train_window.end.isoformat(),
            label_maturity_cutoff_epoch_us=request.knowledge_cutoff_epoch_us,
            trained_at_epoch_us=request.trained_at_epoch_us,
            sample_count=joined.height,
            model_state_sha256=_sha256_hex(model_bytes),
            transform_state_sha256=_sha256_hex(transform_bytes),
            feature_names=lineage.feature_names,
        )
        prediction_record = ModelPredictionRecord(
            schema=MODEL_PREDICTION_ARTIFACT_SCHEMA,
            registration_hash=lineage.registration_hash,
            model_artifact_hash=training_record.artifact_hash,
            prediction_window_start=request.fold.test_window.start.isoformat(),
            prediction_window_end=request.fold.test_window.end.isoformat(),
            rows=rows,
        )
    except ExperimentSpecError as error:
        return ModelTrainingFailure(
            "artifact_contract_invalid",
            details=dict(error.details),
        )
    except (KeyError, TypeError, AttributeError):
        return ModelTrainingFailure("artifact_contract_invalid")
    return ModelTrainingSuccess(
        training=training_record,
        predictions=prediction_record,
        model_state_bytes=model_bytes,
        transform_state_bytes=transform_bytes,
        isolation=isolation,
    )


def train_model_candidate(  # noqa: PLR0911 - fail-closed training stages
    request: ModelFoldTrainingRequest,
) -> ModelTrainingSuccess | ModelTrainingFailure:
    """Train one candidate fold, or refuse with an explicit reason."""
    lineage = request.lineage
    fold = request.fold
    train_window = fold.train_window
    if train_window is None:  # pragma: no cover - guarded in request validation
        return ModelTrainingFailure("fold_train_window_missing")
    try:
        retained_labels, isolation = validate_fold_label_isolation(
            fold,
            request.labels,
            request.trading_sessions,
            knowledge_cutoff_epoch_us=request.knowledge_cutoff_epoch_us,
        )
    except AppProcessError as error:
        return ModelTrainingFailure(
            str(error.details.get("reason", "isolation_failed")),
            details=dict(error.details),
        )
    if isolation.retained_sample_count == 0:
        return ModelTrainingFailure("no_mature_training_samples")
    joined = _joined_training_frame(request, retained_labels, train_window)
    if joined is None:
        return ModelTrainingFailure("train_features_labels_unmatched")
    minimum_samples = len(lineage.feature_names) * _MIN_TRAINING_SAMPLES_PER_FEATURE
    if joined.height < minimum_samples:
        return ModelTrainingFailure(
            "training_samples_insufficient",
            details={"observed": joined.height, "required": minimum_samples},
        )
    targets = joined.get_column("label_value").to_numpy().astype(np.float64, copy=False)
    if not np.all(np.isfinite(targets)):
        return ModelTrainingFailure("label_values_non_finite")
    try:
        transform_state, transform_bytes = _fit_transform_state(
            joined, lineage.transform_spec, lineage.feature_names
        )
        model_state, model_bytes = _fit_model_state(
            lineage, joined, transform_state, seed=lineage.seed
        )
    except AppProcessError as error:
        return ModelTrainingFailure(
            str(error.details.get("reason", "transform_fit_failed")),
            details=dict(error.details),
        )
    prediction_frame = _prediction_frame_for_test_window(
        request, lineage, transform_state, model_state
    )
    if prediction_frame.height == 0:
        return ModelTrainingFailure("test_features_missing")
    return _assemble_success(
        request,
        joined,
        prediction_frame,
        model_state,
        model_bytes,
        transform_bytes,
        isolation,
    )
