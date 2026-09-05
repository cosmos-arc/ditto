"""Boundary and estimator tests for raw statistical sampling evidence."""

from datetime import date, timedelta
from types import SimpleNamespace
from typing import TypedDict, cast

import ditto_analysis.experiments.trial_statistics as statistics_module
import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricScale,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.pbo_plan import (
    PboEstimator,
    PboPartitionIdentity,
    ReturnFrequency,
    SamplingReturnUnit,
    partition_observation_date_grid_hash,
)
from ditto_analysis.experiments.trial_statistics import (
    PboPartitionReturns,
    PboSamplingEvidence,
    SharpeRatioScale,
    SharpeSamplingEvidence,
    partition_returns_hash,
)


class _SharpeOverrides(TypedDict, total=False):
    sharpe_ratio: object
    scale: object
    return_unit: object
    return_frequency: object
    periods_per_year: object
    observation_count: object
    return_skewness: object
    pearson_kurtosis: object
    return_series_hash: object


class _PboOverrides(TypedDict, total=False):
    score_metric_id: object
    direction: object
    estimator: object
    return_unit: object
    return_frequency: object
    periods_per_year: object
    partitions: object


def _sharpe(**overrides: object) -> SharpeSamplingEvidence:
    values: dict[str, object] = {
        "sharpe_ratio": ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, 1.5),
        "scale": SharpeRatioScale.ANNUALIZED,
        "return_unit": SamplingReturnUnit.PER_PERIOD_DECIMAL,
        "return_frequency": ReturnFrequency.DAILY,
        "periods_per_year": 252,
        "observation_count": 20,
        "return_skewness": 0.2,
        "pearson_kurtosis": 3.1,
        "return_series_hash": ContentHash("a" * 64),
    }
    values.update(overrides)
    return SharpeSamplingEvidence(
        sharpe_ratio=cast("ResearchMetricValue", values["sharpe_ratio"]),
        scale=cast("SharpeRatioScale", values["scale"]),
        return_unit=cast("SamplingReturnUnit", values["return_unit"]),
        return_frequency=cast("ReturnFrequency", values["return_frequency"]),
        periods_per_year=cast("int", values["periods_per_year"]),
        observation_count=cast("int", values["observation_count"]),
        return_skewness=cast("float", values["return_skewness"]),
        pearson_kurtosis=cast("float", values["pearson_kurtosis"]),
        return_series_hash=cast("ContentHash", values["return_series_hash"]),
    )


def _identity(
    ordinal: int,
    *,
    partition_id: str | None = None,
    observation_count: int = 2,
    start_offset: int | None = None,
) -> PboPartitionIdentity:
    offset = (ordinal - 1) * 2 if start_offset is None else start_offset
    start = date(2026, 1, 1) + timedelta(days=offset)
    dates = tuple(start + timedelta(days=index) for index in range(observation_count))
    return PboPartitionIdentity(
        partition_id=partition_id or f"partition-{ordinal}",
        ordinal=ordinal,
        window_start=dates[0],
        window_end=dates[-1],
        observation_count=observation_count,
        observation_date_grid_hash=partition_observation_date_grid_hash(dates),
    )


def _partition(
    ordinal: int,
    returns: tuple[float, ...] = (0.01, 0.02),
    *,
    identity: PboPartitionIdentity | None = None,
) -> PboPartitionReturns:
    resolved = identity or _identity(ordinal, observation_count=len(returns))
    return PboPartitionReturns(
        identity=resolved,
        returns=returns,
        return_hash=partition_returns_hash(resolved, returns),
    )


def _partitions(
    returns: tuple[float, ...] = (0.01, 0.02),
) -> tuple[PboPartitionReturns, ...]:
    return tuple(_partition(ordinal, returns) for ordinal in range(1, 5))


def _pbo(**overrides: object) -> PboSamplingEvidence:
    values: dict[str, object] = {
        "score_metric_id": ResearchMetricId.NET_RETURN,
        "direction": ResearchMetricDirection.MAXIMIZE,
        "estimator": PboEstimator.COMPOUND_RETURN,
        "return_unit": SamplingReturnUnit.PER_PERIOD_DECIMAL,
        "return_frequency": ReturnFrequency.DAILY,
        "periods_per_year": 252,
        "partitions": _partitions(),
    }
    values.update(overrides)
    return PboSamplingEvidence(
        score_metric_id=cast("ResearchMetricId", values["score_metric_id"]),
        direction=cast("ResearchMetricDirection", values["direction"]),
        estimator=cast("PboEstimator", values["estimator"]),
        return_unit=cast("SamplingReturnUnit", values["return_unit"]),
        return_frequency=cast("ReturnFrequency", values["return_frequency"]),
        periods_per_year=cast("int", values["periods_per_year"]),
        partitions=cast("tuple[PboPartitionReturns, ...]", values["partitions"]),
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"sharpe_ratio": ResearchMetricValue(ResearchMetricId.NET_RETURN, 1.0)},
            "invalid_sharpe_sampling_metric",
        ),
        ({"sharpe_ratio": "sharpe_ratio"}, "invalid_sharpe_sampling_metric"),
        ({"scale": "annualized"}, "invalid_sharpe_scale"),
        ({"return_unit": "percent"}, "invalid_sampling_return_unit"),
        ({"return_frequency": "daily"}, "invalid_return_frequency"),
        ({"periods_per_year": True}, "invalid_periods_per_year"),
        ({"periods_per_year": 365}, "invalid_periods_per_year"),
        ({"observation_count": True}, "invalid_trial_observation_count"),
        ({"observation_count": 1}, "invalid_trial_observation_count"),
        ({"return_skewness": True}, "non_finite_statistical_value"),
        ({"return_skewness": float("nan")}, "non_finite_statistical_value"),
        ({"pearson_kurtosis": float("inf")}, "non_finite_statistical_value"),
        ({"pearson_kurtosis": 0.99}, "invalid_pearson_kurtosis"),
        ({"return_series_hash": "a" * 64}, "invalid_return_series_hash"),
    ],
)
def test_sharpe_sampling_rejects_invalid_evidence(
    overrides: _SharpeOverrides,
    reason: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _sharpe(**overrides)
    assert exc_info.value.details["reason_code"] == reason


def test_sharpe_sampling_normalizes_both_declared_scales() -> None:
    per_period = _sharpe(
        sharpe_ratio=ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, 0.1),
        scale=SharpeRatioScale.PER_PERIOD,
    )
    annualized = _sharpe()
    assert per_period.per_period_sharpe == 0.1
    assert per_period.annualized_sharpe.value == pytest.approx(0.1 * (252**0.5))
    assert annualized.per_period_sharpe == pytest.approx(1.5 / (252**0.5))
    assert annualized.annualized_sharpe.value == 1.5


def test_sharpe_sampling_fails_closed_on_metric_schema_scale_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DriftedSchema:
        @staticmethod
        def definition(_: ResearchMetricId) -> SimpleNamespace:
            return SimpleNamespace(
                scale=ResearchMetricScale.POINT_ESTIMATE,
                periods_per_year=None,
            )

    monkeypatch.setattr(
        statistics_module,
        "R3_RESEARCH_METRIC_SCHEMA",
        DriftedSchema(),
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        _ = _sharpe().annualized_sharpe
    assert (
        exc_info.value.details["reason_code"] == "sharpe_sampling_schema_scale_mismatch"
    )


@pytest.mark.parametrize(
    "returns",
    [
        cast("object", "0.1"),
        cast("object", b"0.1"),
        cast("object", 0.1),
        (),
        (True,),
        (float("nan"),),
        (-1.0,),
    ],
)
def test_partition_return_hash_rejects_invalid_return_sequences(
    returns: object,
) -> None:
    with pytest.raises(ExperimentSpecError):
        partition_returns_hash(_identity(1), cast("tuple[float, ...]", returns))


def test_partition_return_hash_requires_typed_identity_and_is_stable() -> None:
    identity = _identity(1)
    returns = (0.01, 0.02)
    assert partition_returns_hash(identity, returns) == partition_returns_hash(
        identity, returns
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        partition_returns_hash(cast("PboPartitionIdentity", "partition-1"), returns)
    assert exc_info.value.details["reason_code"] == "invalid_pbo_partition_identity"


def test_partition_returns_freeze_valid_evidence() -> None:
    identity = _identity(1)
    evidence = PboPartitionReturns(
        identity,
        [0.01, 0.02],
        partition_returns_hash(identity, (0.01, 0.02)),
    )
    assert evidence.returns == (0.01, 0.02)


@pytest.mark.parametrize(
    ("identity", "returns", "return_hash", "reason"),
    [
        (
            "partition-1",
            (0.01, 0.02),
            ContentHash("a" * 64),
            "invalid_pbo_partition_identity",
        ),
        (
            _identity(1),
            (0.01,),
            ContentHash("a" * 64),
            "partition_observation_count_mismatch",
        ),
        (_identity(1), (0.01, 0.02), "hash", "invalid_partition_return_hash"),
        (
            _identity(1),
            (0.01, 0.02),
            ContentHash("a" * 64),
            "partition_return_hash_mismatch",
        ),
    ],
)
def test_partition_returns_reject_invalid_identity_count_and_hash(
    identity: object,
    returns: tuple[float, ...],
    return_hash: object,
    reason: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        PboPartitionReturns(
            cast("PboPartitionIdentity", identity),
            returns,
            cast("ContentHash", return_hash),
        )
    assert exc_info.value.details["reason_code"] == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"score_metric_id": "net_return"}, "invalid_pbo_metric"),
        ({"direction": "maximize"}, "invalid_pbo_direction"),
        ({"estimator": "compound_return"}, "invalid_pbo_estimator"),
        ({"return_unit": "percent"}, "invalid_sampling_return_unit"),
        ({"return_frequency": "daily"}, "invalid_return_frequency"),
        ({"periods_per_year": True}, "invalid_periods_per_year"),
        ({"periods_per_year": 365}, "invalid_periods_per_year"),
        (
            {"direction": ResearchMetricDirection.MINIMIZE},
            "pbo_metric_direction_mismatch",
        ),
        ({"estimator": PboEstimator.SHARPE_RATIO}, "pbo_estimator_metric_mismatch"),
        (
            {"return_frequency": ReturnFrequency.WEEKLY, "periods_per_year": 52},
            "pbo_sampling_schema_scale_mismatch",
        ),
        ({"partitions": "partitions"}, "invalid_pbo_partitions"),
        ({"partitions": ()}, "invalid_pbo_partitions"),
        ({"partitions": (*_partitions()[:3], object())}, "invalid_pbo_partitions"),
    ],
)
def test_pbo_sampling_rejects_invalid_type_schema_and_container_inputs(
    overrides: _PboOverrides,
    reason: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _pbo(**overrides)
    assert exc_info.value.details["reason_code"] == reason


def test_pbo_sampling_fails_closed_on_sharpe_schema_annualization_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DriftedSchema:
        @staticmethod
        def definition(_: ResearchMetricId) -> SimpleNamespace:
            return SimpleNamespace(
                direction=ResearchMetricDirection.MAXIMIZE,
                periods_per_year=365,
            )

    monkeypatch.setattr(
        statistics_module,
        "R3_RESEARCH_METRIC_SCHEMA",
        DriftedSchema(),
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        _pbo(
            score_metric_id=ResearchMetricId.SHARPE_RATIO,
            estimator=PboEstimator.SHARPE_RATIO,
        )
    assert exc_info.value.details["reason_code"] == "pbo_sampling_schema_scale_mismatch"


def test_pbo_sampling_rejects_invalid_partition_layouts() -> None:
    normal = _partitions()
    invalid_cases = [
        ((*normal[:3], normal[0]), "duplicate_pbo_partition_identity"),
        ((*normal[:3], _partition(5)), "pbo_partition_ordinals_not_contiguous"),
        (
            (*normal[:3], _partition(4, (0.01, 0.02, 0.03))),
            "unequal_pbo_partition_observation_count",
        ),
        (
            (*normal[:3], _partition(4, identity=_identity(4, start_offset=5))),
            "overlapping_pbo_partition_windows",
        ),
    ]
    for partitions, reason in invalid_cases:
        with pytest.raises(ExperimentSpecError) as exc_info:
            _pbo(partitions=partitions)
        assert exc_info.value.details["reason_code"] == reason


def test_pbo_sampling_recomputes_compound_and_sharpe_estimators() -> None:
    compound = _pbo()
    expected_percent = ((1.01 * 1.02) ** 4 - 1) * 100
    assert compound.aggregate_metric_value.value == pytest.approx(expected_percent)

    sharpe = _pbo(
        score_metric_id=ResearchMetricId.SHARPE_RATIO,
        estimator=PboEstimator.SHARPE_RATIO,
    )
    assert sharpe.aggregate_metric_value.value > 0


def test_pbo_sampling_handles_zero_volatility_without_fabricating_sharpe() -> None:
    zero = _pbo(
        score_metric_id=ResearchMetricId.SHARPE_RATIO,
        estimator=PboEstimator.SHARPE_RATIO,
        partitions=_partitions((0.0, 0.0)),
    )
    assert zero.aggregate_metric_value.value == 0.0

    nonzero = _pbo(
        score_metric_id=ResearchMetricId.SHARPE_RATIO,
        estimator=PboEstimator.SHARPE_RATIO,
        partitions=_partitions((0.01, 0.01)),
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        _ = nonzero.aggregate_metric_value
    assert exc_info.value.details["reason_code"] == "pbo_sampling_aggregate_undefined"
