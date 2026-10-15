"""Unit tests for fold-scoped model candidate training (#268).

Covers the acceptance-critical PIT counterexamples: future labels, validation
period outliers, and future constituents must not change early training;
refusals must carry explicit reasons and never partial artifacts.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

import numpy as np
import orjson
import polars as pl
import pytest
from ditto_analysis.experiments.model_lineage import (
    ModelCandidateLineage,
    ModelKind,
    TrainFittedTransformSpec,
)
from ditto_analysis.experiments.persistence import DateWindow, FoldRole
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.model_candidates import (
    ModelFoldTrainingRequest,
    ModelTrainingFailure,
    ModelTrainingSuccess,
    train_model_candidate,
    validate_fold_label_isolation,
)
from ditto_application.research_validation_windows import ValidationFoldPlan
from ditto_features.evaluation.research_labels import (
    build_forward_return_labels,
    label_spec_hash,
)

_START = date(2026, 3, 2)
SESSIONS = tuple(_START + timedelta(days=index) for index in range(30))
ENTITIES = ("000001.SZ", "000002.SZ", "600000.SH")
_EPOCH_BASE = 5_000_000_000_000_000
_LABEL_HASH = label_spec_hash()
_CODE_ENV = {
    "implementation_key": "ditto_application.model_candidates.ridge.v1",
    "python": "3.13.14",
    "lockfile_sha256": "b" * 64,
}
_KNOWLEDGE_CUTOFF = _EPOCH_BASE + 60 * 86_400_000_000
_TRAINED_AT = _KNOWLEDGE_CUTOFF + 1


def _price_frame(
    *,
    price_multiplier: float = 1.0,
    extra_entities_sessions: tuple[date, ...] = (),
) -> pl.DataFrame:
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
    instruments: list[str] = list(ENTITIES)
    if extra_entities_sessions:
        instruments.append("300999.SZ")
    for instrument in instruments:
        offset = instruments.index(instrument)
        for index, session in enumerate(SESSIONS):
            if instrument == "300999.SZ" and session not in extra_entities_sessions:
                continue
            base = 10.0 + offset
            multiplier = price_multiplier if session >= SESSIONS[20] else 1.0
            rows["instrument_id"].append(instrument)
            rows["session"].append(session)
            rows["open"].append((base + index) * multiplier)
            rows["close"].append((base + 0.5 + index) * multiplier)
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


def _feature_frame(
    *,
    test_outlier: bool = False,
    future_constituent: bool = False,
) -> pl.DataFrame:
    rows: dict[str, list[object]] = {
        "instrument_id": [],
        "session": [],
        "momentum_20d": [],
        "ep_ttm": [],
    }
    instruments = list(ENTITIES) + (["300999.SZ"] if future_constituent else [])
    for instrument in instruments:
        offset = instruments.index(instrument)
        for index, session in enumerate(SESSIONS):
            if (
                future_constituent
                and instrument == "300999.SZ"
                and session < SESSIONS[25]
            ):
                continue
            momentum = float(offset * 0.1 + (index % 7) * 0.05)
            ep = float(offset * 0.2 + (index % 5) * 0.03)
            if test_outlier and session >= SESSIONS[25]:
                momentum *= 1_000.0
                ep *= 1_000.0
            rows["instrument_id"].append(instrument)
            rows["session"].append(session)
            rows["momentum_20d"].append(momentum)
            rows["ep_ttm"].append(ep)
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


def _request(
    *,
    kind: ModelKind = ModelKind.LINEAR,
    features: pl.DataFrame | None = None,
    prices: pl.DataFrame | None = None,
    fold: ValidationFoldPlan | None = None,
    knowledge_cutoff: int = _KNOWLEDGE_CUTOFF,
) -> ModelFoldTrainingRequest:
    labels = build_forward_return_labels(
        prices if prices is not None else _price_frame(), list(SESSIONS)
    )
    return ModelFoldTrainingRequest(
        lineage=_lineage(kind),
        fold=fold if fold is not None else _fold(),
        feature_frame=features if features is not None else _feature_frame(),
        labels=labels,
        trading_sessions=SESSIONS,
        snapshot_id="snap-test-1",
        knowledge_cutoff_epoch_us=knowledge_cutoff,
        trained_at_epoch_us=_TRAINED_AT,
    )


def test_linear_training_succeeds_with_expected_shape() -> None:
    result = train_model_candidate(_request())
    assert isinstance(result, ModelTrainingSuccess)
    # Retained decisions: exit ordinal + 5 <= test start 25 -> decisions <= 14.
    assert result.isolation.retained_sample_count == 45  # 15 decisions x 3
    assert result.isolation.excluded_gap_count == 15  # decisions 15..19 x 3
    assert result.isolation.excluded_immature_count == 0
    assert result.training.sample_count == 45
    assert result.training.registration_hash == _lineage().registration_hash
    # Test window d25..d29 x 3 instruments.
    assert len(result.predictions.rows) == 15
    sessions = {row.decision_session for row in result.predictions.rows}
    assert sessions == {SESSIONS[index].isoformat() for index in range(25, 30)}
    assert all(np.isfinite(row.prediction) for row in result.predictions.rows)


def _as_float(value: object) -> float:
    """Narrow a polars scalar aggregate to a plain float for hand checks."""
    assert value is not None
    return float(cast("float", value))


def test_ridge_prediction_matches_reference_implementation() -> None:
    result = train_model_candidate(_request())
    assert isinstance(result, ModelTrainingSuccess)
    features = _feature_frame()
    train = features.filter(
        (pl.col("session") >= SESSIONS[0]) & (pl.col("session") <= SESSIONS[14])
    )
    # Recompute the exact train-only recipe independently.
    stats: dict[str, dict[str, float]] = {}
    for name in ("momentum_20d", "ep_ttm"):
        column = train.get_column(name)
        lower = _as_float(column.quantile(0.01, interpolation="linear"))
        upper = _as_float(column.quantile(0.99, interpolation="linear"))
        clipped = column.clip(lower_bound=lower, upper_bound=upper)
        stats[name] = {
            "median": _as_float(column.median()),
            "winsor_lower": lower,
            "winsor_upper": upper,
            "mean": _as_float(clipped.mean()),
            "std": _as_float(clipped.std()),
        }
    labels = build_forward_return_labels(_price_frame(), list(SESSIONS)).frame
    joined = train.join(
        labels.filter(pl.col("status") == "mature").select(
            [
                pl.col("instrument_id"),
                pl.col("decision_session").alias("session"),
                pl.col("label_value"),
            ]
        ),
        on=["instrument_id", "session"],
        how="inner",
    ).filter(pl.col("session") <= SESSIONS[14])
    columns = []
    for name in ("momentum_20d", "ep_ttm"):
        column = (
            joined.get_column(name)
            .fill_null(value=stats[name]["median"])
            .clip(
                lower_bound=stats[name]["winsor_lower"],
                upper_bound=stats[name]["winsor_upper"],
            )
        )
        columns.append(((column - stats[name]["mean"]) / stats[name]["std"]).to_numpy())
    matrix = np.column_stack(columns)
    targets = joined.get_column("label_value").to_numpy()
    intercept = float(targets.mean())
    weights = np.linalg.solve(
        matrix.T @ matrix + np.eye(2), matrix.T @ (targets - intercept)
    )
    probe = features.filter(
        (pl.col("instrument_id") == "000001.SZ") & (pl.col("session") == SESSIONS[25])
    )
    probe_columns = []
    for name in ("momentum_20d", "ep_ttm"):
        column = (
            probe.get_column(name)
            .fill_null(value=stats[name]["median"])
            .clip(
                lower_bound=stats[name]["winsor_lower"],
                upper_bound=stats[name]["winsor_upper"],
            )
        )
        probe_columns.append(
            ((column - stats[name]["mean"]) / stats[name]["std"]).to_numpy()[0]
        )
    expected = float(np.asarray(probe_columns) @ weights + intercept)
    observed = next(
        row.prediction
        for row in result.predictions.rows
        if row.entity_id == "000001.SZ"
        and row.decision_session == SESSIONS[25].isoformat()
    )
    assert observed == pytest.approx(expected, rel=1e-9)


def test_rule_model_predicts_registered_factor_value() -> None:
    result = train_model_candidate(_request(kind=ModelKind.RULE))
    assert isinstance(result, ModelTrainingSuccess)
    expected = (
        _feature_frame()
        .filter(
            (pl.col("instrument_id") == "000002.SZ")
            & (pl.col("session") == SESSIONS[26])
        )
        .get_column("momentum_20d")
        .item()
    )
    observed = next(
        row.prediction
        for row in result.predictions.rows
        if row.entity_id == "000002.SZ"
        and row.decision_session == SESSIONS[26].isoformat()
    )
    assert observed == pytest.approx(expected)


@pytest.mark.pit
def test_future_labels_do_not_change_early_training() -> None:
    baseline = train_model_candidate(_request())
    assert isinstance(baseline, ModelTrainingSuccess)
    modified = train_model_candidate(
        _request(prices=_price_frame(price_multiplier=10.0))
    )
    assert isinstance(modified, ModelTrainingSuccess)
    assert modified.model_state_bytes == baseline.model_state_bytes
    assert modified.transform_state_bytes == baseline.transform_state_bytes
    assert modified.predictions.artifact_hash == baseline.predictions.artifact_hash


@pytest.mark.pit
def test_validation_period_outliers_do_not_change_training() -> None:
    baseline = train_model_candidate(_request())
    assert isinstance(baseline, ModelTrainingSuccess)
    outlier = train_model_candidate(
        _request(features=_feature_frame(test_outlier=True))
    )
    assert isinstance(outlier, ModelTrainingSuccess)
    assert outlier.model_state_bytes == baseline.model_state_bytes
    assert outlier.transform_state_bytes == baseline.transform_state_bytes
    assert outlier.predictions.artifact_hash != baseline.predictions.artifact_hash


@pytest.mark.pit
def test_future_constituents_do_not_change_early_training() -> None:
    baseline = train_model_candidate(_request())
    assert isinstance(baseline, ModelTrainingSuccess)
    extended = train_model_candidate(
        _request(features=_feature_frame(future_constituent=True))
    )
    assert isinstance(extended, ModelTrainingSuccess)
    assert extended.model_state_bytes == baseline.model_state_bytes
    assert extended.transform_state_bytes == baseline.transform_state_bytes
    assert len(extended.predictions.rows) == 20  # 15 baseline + 5 new-entity rows


def test_immature_labels_are_refused_with_reason() -> None:
    result = train_model_candidate(
        _request(knowledge_cutoff=0)  # nothing mature at this cutoff
    )
    assert isinstance(result, ModelTrainingFailure)
    assert result.reason == "no_mature_training_samples"


def test_embargo_below_label_window_is_refused() -> None:
    fold = ValidationFoldPlan(
        ordinal=1,
        role=_fold().role,
        train_window=DateWindow(start=SESSIONS[0], end=SESSIONS[19]),
        test_window=DateWindow(start=SESSIONS[25], end=SESSIONS[29]),
        purge_sessions=5,
        embargo_sessions=4,
    )
    result = train_model_candidate(_request(fold=fold))
    assert isinstance(result, ModelTrainingFailure)
    assert result.reason == "embargo_below_label_window"


def test_schema_drift_fails_closed_at_request_boundary() -> None:
    drifted = _feature_frame().rename({"ep_ttm": "ep_ttm_v2"})
    with pytest.raises(AppProcessError) as error:
        _request(features=drifted)
    assert error.value.details["reason"] == "feature_frame_schema_drift"


def test_fold_boundary_not_in_calendar_fails_closed() -> None:
    fold = ValidationFoldPlan(
        ordinal=1,
        role=_fold().role,
        train_window=DateWindow(
            start=SESSIONS[0], end=SESSIONS[19] + timedelta(days=40)
        ),
        test_window=DateWindow(start=SESSIONS[25], end=SESSIONS[29]),
        purge_sessions=5,
        embargo_sessions=5,
    )
    with pytest.raises(AppProcessError) as error:
        _request(fold=fold)
    assert error.value.details["reason"] == "train_window_end_not_a_session"


def test_deterministic_retraining_is_bit_identical() -> None:
    first = train_model_candidate(_request())
    second = train_model_candidate(_request())
    assert isinstance(first, ModelTrainingSuccess)
    assert isinstance(second, ModelTrainingSuccess)
    assert first.model_state_bytes == second.model_state_bytes
    assert first.training.artifact_hash == second.training.artifact_hash


def test_label_calendar_mismatch_returns_typed_failure() -> None:
    # Labels built on the full calendar; the request calendar drops sessions
    # 12..16, so the retained decision d11 has exit d16 off-calendar. The
    # training must refuse with an explicit reason, not a polars mapping error.
    request = ModelFoldTrainingRequest(
        lineage=_lineage(),
        fold=_fold(),
        feature_frame=_feature_frame(),
        labels=build_forward_return_labels(_price_frame(), list(SESSIONS)),
        trading_sessions=SESSIONS[:12] + SESSIONS[17:],
        snapshot_id="snap-test-1",
        knowledge_cutoff_epoch_us=_KNOWLEDGE_CUTOFF,
        trained_at_epoch_us=_TRAINED_AT,
    )
    result = train_model_candidate(request)
    assert isinstance(result, ModelTrainingFailure)
    assert result.reason == "label_exit_session_not_in_calendar"


def test_null_feature_rows_keep_rule_and_linear_row_counts_parity() -> None:
    features = _feature_frame().with_columns(
        pl.when(pl.col("session") == SESSIONS[27])
        .then(None)
        .otherwise(pl.col("momentum_20d"))
        .alias("momentum_20d")
    )
    rule = train_model_candidate(_request(kind=ModelKind.RULE, features=features))
    linear = train_model_candidate(_request(kind=ModelKind.LINEAR, features=features))
    assert isinstance(rule, ModelTrainingSuccess)
    assert isinstance(linear, ModelTrainingSuccess)
    rule_keys = {(row.entity_id, row.decision_session) for row in rule.predictions.rows}
    linear_keys = {
        (row.entity_id, row.decision_session) for row in linear.predictions.rows
    }
    assert rule_keys == linear_keys  # 同一缺失策略：null 行同被中位数填补


def test_isolation_report_counts_by_real_intervals() -> None:
    from ditto_features.evaluation.research_labels import (
        build_forward_return_labels,
    )

    labels = build_forward_return_labels(_price_frame(), list(SESSIONS))
    retained, report = validate_fold_label_isolation(
        _fold(),
        labels,
        SESSIONS,
        knowledge_cutoff_epoch_us=_KNOWLEDGE_CUTOFF,
    )
    assert report.retained_sample_count == 45
    assert report.excluded_gap_count == 15
    assert report.worst_retained_exit_session == SESSIONS[19]
    assert retained.height == 45


@pytest.mark.slow  # lightgbm 首次导入+训练 1.4s（#328 >0.5s 治理）
def test_lightgbm_training_succeeds_under_same_protocol() -> None:
    result = train_model_candidate(_request(kind=ModelKind.LIGHTGBM))
    assert isinstance(result, ModelTrainingSuccess)
    assert result.training.sample_count == 45
    assert len(result.predictions.rows) == 15
    assert all(np.isfinite(row.prediction) for row in result.predictions.rows)
    state = orjson.loads(result.model_state_bytes)
    assert state["feature_names"] == ["momentum_20d", "ep_ttm"]
    assert "booster_model" in state


def test_lightgbm_retraining_is_reproducible_within_tolerance() -> None:
    import lightgbm as lgb

    first = train_model_candidate(_request(kind=ModelKind.LIGHTGBM))
    second = train_model_candidate(_request(kind=ModelKind.LIGHTGBM))
    assert isinstance(first, ModelTrainingSuccess)
    assert isinstance(second, ModelTrainingSuccess)
    first_state = orjson.loads(first.model_state_bytes)
    second_state = orjson.loads(second.model_state_bytes)
    booster_one = lgb.Booster(model_str=first_state["booster_model"])
    booster_two = lgb.Booster(model_str=second_state["booster_model"])
    matrix = np.column_stack(
        [
            _feature_frame().get_column("momentum_20d").to_numpy(),
            _feature_frame().get_column("ep_ttm").to_numpy(),
        ]
    )[75:80]
    np.testing.assert_allclose(
        np.asarray(booster_one.predict(matrix)),
        np.asarray(booster_two.predict(matrix)),
        rtol=1e-12,
    )


@pytest.mark.pit
def test_lightgbm_future_labels_do_not_change_early_training() -> None:
    baseline = train_model_candidate(_request(kind=ModelKind.LIGHTGBM))
    modified = train_model_candidate(
        _request(kind=ModelKind.LIGHTGBM, prices=_price_frame(price_multiplier=10.0))
    )
    assert isinstance(baseline, ModelTrainingSuccess)
    assert isinstance(modified, ModelTrainingSuccess)
    assert modified.model_state_bytes == baseline.model_state_bytes
    assert modified.transform_state_bytes == baseline.transform_state_bytes
