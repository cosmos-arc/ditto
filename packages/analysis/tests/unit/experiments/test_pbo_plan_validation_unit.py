"""Fail-closed validation tests for pre-registered PBO partition plans."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import TypedDict, cast

import ditto_analysis.experiments.pbo_plan as pbo_plan_module
import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    ResearchMetricDirection,
    ResearchMetricId,
)
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.pbo_plan import (
    PboEstimator,
    PboPartitionIdentity,
    PboPartitionPlan,
    ReturnFrequency,
    SamplingReturnUnit,
    partition_observation_date_grid_hash,
)


class _PlanOverrides(TypedDict, total=False):
    metric: object
    direction: object
    estimator: object
    return_unit: object
    frequency: object
    periods_per_year: object
    partitions: object


_DEFAULT_PARTITIONS = object()


def _identity(
    ordinal: object = 1,
    *,
    partition_id: object = "partition-1",
    start: object = date(2026, 1, 1),
    end: object = date(2026, 1, 1),
    count: object = 1,
    grid_hash: object | None = None,
) -> PboPartitionIdentity:
    resolved_hash = (
        partition_observation_date_grid_hash((cast("date", start),))
        if grid_hash is None and type(start) is date
        else grid_hash
    )
    return PboPartitionIdentity(
        partition_id=cast("str", partition_id),
        ordinal=cast("int", ordinal),
        window_start=cast("date", start),
        window_end=cast("date", end),
        observation_count=cast("int", count),
        observation_date_grid_hash=cast("ContentHash", resolved_hash),
    )


def _identities(count: int = 4) -> tuple[PboPartitionIdentity, ...]:
    origin = date(2026, 1, 1)
    return tuple(
        _identity(
            ordinal,
            partition_id=f"partition-{ordinal}",
            start=origin + timedelta(days=ordinal - 1),
            end=origin + timedelta(days=ordinal - 1),
        )
        for ordinal in range(1, count + 1)
    )


def _plan(
    *,
    metric: object = ResearchMetricId.NET_RETURN,
    direction: object = ResearchMetricDirection.MAXIMIZE,
    estimator: object = PboEstimator.COMPOUND_RETURN,
    return_unit: object = SamplingReturnUnit.PER_PERIOD_DECIMAL,
    frequency: object = ReturnFrequency.DAILY,
    periods_per_year: object = 252,
    partitions: object = _DEFAULT_PARTITIONS,
) -> PboPartitionPlan:
    return PboPartitionPlan(
        score_metric_id=cast("ResearchMetricId", metric),
        direction=cast("ResearchMetricDirection", direction),
        estimator=cast("PboEstimator", estimator),
        return_unit=cast("SamplingReturnUnit", return_unit),
        return_frequency=cast("ReturnFrequency", frequency),
        periods_per_year=cast("int", periods_per_year),
        partitions=cast(
            "tuple[PboPartitionIdentity, ...]",
            _identities() if partitions is _DEFAULT_PARTITIONS else partitions,
        ),
    )


@pytest.mark.parametrize("value", [None, "2026-01-01", b"date", bytearray(b"date"), 1])
def test_observation_grid_rejects_non_date_sequences(value: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        partition_observation_date_grid_hash(value)
    assert exc_info.value.details["reason_code"] == "invalid_pbo_observation_date_grid"


@pytest.mark.parametrize(
    "value",
    [
        (),
        (date(2026, 1, 1), datetime(2026, 1, 2)),
        (date(2026, 1, 1), date(2026, 1, 1)),
        (date(2026, 1, 2), date(2026, 1, 1)),
    ],
)
def test_observation_grid_rejects_empty_non_exact_or_non_increasing_dates(
    value: tuple[object, ...],
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        partition_observation_date_grid_hash(value)
    assert exc_info.value.details["reason_code"] == "invalid_pbo_observation_date_grid"


def test_observation_grid_hash_is_stable_and_order_sensitive() -> None:
    first = date(2026, 1, 1)
    second = date(2026, 1, 2)
    assert partition_observation_date_grid_hash((first, second)) == (
        partition_observation_date_grid_hash((first, second))
    )
    assert partition_observation_date_grid_hash((first,)) != (
        partition_observation_date_grid_hash((second,))
    )


@pytest.mark.parametrize("value", [None, "", " padded", "padded ", 7])
def test_partition_identity_rejects_invalid_ids(value: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _identity(partition_id=value)
    assert exc_info.value.details["reason_code"] == "invalid_pbo_partition_identity"


@pytest.mark.parametrize("value", [None, True, 0, -1, 1.0])
def test_partition_identity_requires_an_exact_positive_ordinal(value: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _identity(value)
    assert exc_info.value.details["reason_code"] == "invalid_pbo_partition_ordinal"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 1, 1), date(2026, 1, 1)),
        (date(2026, 1, 1), "2026-01-01"),
        (date(2026, 1, 2), date(2026, 1, 1)),
    ],
)
def test_partition_identity_rejects_invalid_windows(start: object, end: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _identity(start=start, end=end)
    assert exc_info.value.details["reason_code"] == "invalid_pbo_partition_window"


@pytest.mark.parametrize("value", [None, True, 0, -1, 1.0])
def test_partition_identity_requires_an_exact_positive_observation_count(
    value: object,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _identity(count=value)
    assert (
        exc_info.value.details["reason_code"]
        == "invalid_pbo_partition_observation_count"
    )


def test_partition_identity_requires_a_typed_grid_hash() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _identity(grid_hash="a" * 64)
    assert (
        exc_info.value.details["reason_code"]
        == "invalid_pbo_observation_date_grid_hash"
    )


def test_partition_identity_canonical_payload_is_exact() -> None:
    identity = _identity()
    assert identity.canonical_payload() == {
        "partition_id": "partition-1",
        "ordinal": 1,
        "window_start": "2026-01-01",
        "window_end": "2026-01-01",
        "observation_count": 1,
        "observation_date_grid_hash": str(identity.observation_date_grid_hash),
    }


@pytest.mark.parametrize("partitions", [None, "partitions", b"partitions", 4])
def test_plan_rejects_non_sequence_partition_inputs(partitions: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(partitions=partitions)
    assert exc_info.value.details["reason_code"] == "invalid_pbo_partition_plan"


def test_plan_rejects_non_identity_partition_members() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(partitions=(*_identities()[:3], object()))
    assert exc_info.value.details["reason_code"] == "invalid_pbo_partition_plan"


@pytest.mark.parametrize("count", [0, 2, 3, 5])
def test_plan_requires_an_even_partition_count_of_at_least_four(count: int) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(partitions=_identities(count))
    assert exc_info.value.details["reason_code"] == "invalid_pbo_partition_count"
    assert exc_info.value.details["partition_count"] == count


def test_plan_rejects_duplicate_partition_identity() -> None:
    identities = _identities()
    duplicate = _identity(
        4,
        partition_id="partition-1",
        start=date(2026, 1, 4),
        end=date(2026, 1, 4),
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(partitions=(*identities[:3], duplicate))
    assert exc_info.value.details["reason_code"] == "duplicate_pbo_partition_identity"


def test_plan_rejects_non_contiguous_ordinals() -> None:
    identities = (
        *_identities()[:3],
        _identity(
            5, partition_id="partition-5", start=date(2026, 1, 4), end=date(2026, 1, 4)
        ),
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(partitions=identities)
    assert (
        exc_info.value.details["reason_code"] == "pbo_partition_ordinals_not_contiguous"
    )


def test_plan_rejects_unequal_partition_observation_counts() -> None:
    identities = (
        *_identities()[:3],
        _identity(
            4,
            partition_id="partition-4",
            start=date(2026, 1, 4),
            end=date(2026, 1, 4),
            count=2,
        ),
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(partitions=identities)
    assert (
        exc_info.value.details["reason_code"]
        == "unequal_pbo_partition_observation_count"
    )


def test_plan_rejects_overlapping_partition_windows() -> None:
    identities = (
        *_identities()[:3],
        _identity(
            4, partition_id="partition-4", start=date(2026, 1, 3), end=date(2026, 1, 4)
        ),
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(partitions=identities)
    assert exc_info.value.details["reason_code"] == "overlapping_pbo_partition_windows"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"metric": "net_return"}, "invalid_pbo_metric"),
        ({"direction": "maximize"}, "invalid_pbo_direction"),
        ({"estimator": "compound_return"}, "invalid_pbo_estimator"),
        ({"return_unit": "percent"}, "invalid_sampling_return_unit"),
        ({"frequency": "daily"}, "invalid_return_frequency"),
        ({"periods_per_year": True}, "invalid_periods_per_year"),
        ({"periods_per_year": 365}, "invalid_periods_per_year"),
        (
            {"direction": ResearchMetricDirection.MINIMIZE},
            "pbo_metric_direction_mismatch",
        ),
        ({"estimator": PboEstimator.SHARPE_RATIO}, "pbo_estimator_metric_mismatch"),
        (
            {"frequency": ReturnFrequency.WEEKLY, "periods_per_year": 52},
            "pbo_sampling_schema_scale_mismatch",
        ),
    ],
)
def test_plan_rejects_invalid_schema_and_estimator_combinations(
    overrides: _PlanOverrides,
    reason: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(**overrides)
    assert exc_info.value.details["reason_code"] == reason


def test_sharpe_plan_fails_closed_if_metric_schema_annualization_drifts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DriftedSchema:
        @staticmethod
        def definition(_: ResearchMetricId) -> SimpleNamespace:
            return SimpleNamespace(
                direction=ResearchMetricDirection.MAXIMIZE,
                periods_per_year=365,
            )

    monkeypatch.setattr(pbo_plan_module, "R3_RESEARCH_METRIC_SCHEMA", DriftedSchema())

    with pytest.raises(ExperimentSpecError) as exc_info:
        _plan(
            metric=ResearchMetricId.SHARPE_RATIO,
            estimator=PboEstimator.SHARPE_RATIO,
        )
    assert exc_info.value.details["reason_code"] == "pbo_sampling_schema_scale_mismatch"


def test_plan_sorts_partitions_and_emits_a_versioned_canonical_payload() -> None:
    identities = _identities()
    plan = _plan(partitions=tuple(reversed(identities)))
    payload = plan.canonical_payload()
    assert tuple(item.ordinal for item in plan.partitions) == (1, 2, 3, 4)
    assert payload["schema_id"] == "r3-pbo-partition-plan"
    assert payload["schema_version"] == 1
    assert payload["score_metric_id"] == "net_return"
    assert payload["estimator"] == "compound_return"
    assert [
        item["partition_id"]
        for item in cast("list[dict[str, object]]", payload["partitions"])
    ] == [
        "partition-1",
        "partition-2",
        "partition-3",
        "partition-4",
    ]
