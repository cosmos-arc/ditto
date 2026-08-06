"""Pre-registered, typed partition semantics for CSCV PBO evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    R3_RESEARCH_METRIC_SCHEMA,
    ResearchMetricDirection,
    ResearchMetricId,
)
from ditto_analysis.experiments.models import ContentHash

__all__ = [
    "PboEstimator",
    "PboPartitionIdentity",
    "PboPartitionPlan",
    "ReturnFrequency",
    "SamplingReturnUnit",
    "partition_observation_date_grid_hash",
]

_MIN_PBO_PARTITIONS = 4
_PERIODS_PER_YEAR = {
    "daily": 252,
    "weekly": 52,
    "monthly": 12,
}


def _plan_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


class ReturnFrequency(StrEnum):
    """Sampling interval for a declared return series."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SamplingReturnUnit(StrEnum):
    """Unit of raw sampling returns; metric percentages are never accepted."""

    PER_PERIOD_DECIMAL = "per_period_decimal"


class PboEstimator(StrEnum):
    """Estimator recomputed from raw partition returns for every CSCV split."""

    COMPOUND_RETURN = "compound_return"
    SHARPE_RATIO = "sharpe_ratio"


_ESTIMATOR_METRICS = {
    PboEstimator.COMPOUND_RETURN: ResearchMetricId.NET_RETURN,
    PboEstimator.SHARPE_RATIO: ResearchMetricId.SHARPE_RATIO,
}


def partition_observation_date_grid_hash(
    observation_dates: object,
) -> ContentHash:
    """Hash the exact ordered trading-date grid of one planned partition."""
    if not isinstance(observation_dates, Sequence) or isinstance(
        observation_dates,
        (str, bytes, bytearray),
    ):
        raise _plan_error(
            "partition observation dates must be an ordered sequence",
            "invalid_pbo_observation_date_grid",
        )
    raw_dates = tuple(cast("Sequence[object]", observation_dates))
    if not raw_dates or any(type(item) is not date for item in raw_dates):
        raise _plan_error(
            "partition observation dates must be unique and increasing",
            "invalid_pbo_observation_date_grid",
        )
    dates = cast("tuple[date, ...]", raw_dates)
    if any(previous >= current for previous, current in pairwise(dates)):
        raise _plan_error(
            "partition observation dates must be unique and increasing",
            "invalid_pbo_observation_date_grid",
        )
    payload = json.dumps(
        {
            "schema_id": "r3-pbo-observation-date-grid",
            "schema_version": 1,
            "observation_dates": [item.isoformat() for item in dates],
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ContentHash(hashlib.sha256(payload).hexdigest())


@dataclass(frozen=True, slots=True)
class PboPartitionIdentity:
    """Stable pre-registered time partition used by CSCV."""

    partition_id: str
    ordinal: int
    window_start: date
    window_end: date
    observation_count: int
    observation_date_grid_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate the exact time window and observation cardinality."""
        if (
            type(self.partition_id) is not str
            or not self.partition_id.strip()
            or self.partition_id != self.partition_id.strip()
        ):
            raise _plan_error(
                "partition id must be a non-empty unpadded string",
                "invalid_pbo_partition_identity",
            )
        if type(self.ordinal) is not int or self.ordinal <= 0:
            raise _plan_error(
                "partition ordinal must be a positive integer",
                "invalid_pbo_partition_ordinal",
            )
        if type(self.window_start) is not date or type(self.window_end) is not date:
            raise _plan_error(
                "partition windows must use exact dates",
                "invalid_pbo_partition_window",
            )
        if self.window_start > self.window_end:
            raise _plan_error(
                "partition window start cannot follow its end",
                "invalid_pbo_partition_window",
            )
        if type(self.observation_count) is not int or self.observation_count <= 0:
            raise _plan_error(
                "partition observation count must be positive",
                "invalid_pbo_partition_observation_count",
            )
        if type(self.observation_date_grid_hash) is not ContentHash:
            raise _plan_error(
                "partition observation date grid hash must be ContentHash",
                "invalid_pbo_observation_date_grid_hash",
            )

    def canonical_payload(self) -> dict[str, object]:
        """Return the exact JSON-shaped partition identity."""
        return {
            "partition_id": self.partition_id,
            "ordinal": self.ordinal,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "observation_count": self.observation_count,
            "observation_date_grid_hash": str(self.observation_date_grid_hash),
        }


def _freeze_partition_identities(value: object) -> tuple[PboPartitionIdentity, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _plan_error(
            "PBO plan partitions must be an ordered sequence",
            "invalid_pbo_partition_plan",
        )
    raw = tuple(cast("Sequence[object]", value))
    if any(type(item) is not PboPartitionIdentity for item in raw):
        raise _plan_error(
            "PBO plan must contain exact partition identities",
            "invalid_pbo_partition_plan",
        )
    return tuple(
        sorted(
            cast("tuple[PboPartitionIdentity, ...]", raw),
            key=lambda item: item.ordinal,
        )
    )


def _validate_partition_layout(
    partitions: tuple[PboPartitionIdentity, ...],
) -> None:
    partition_count = len(partitions)
    if partition_count < _MIN_PBO_PARTITIONS or partition_count % 2:
        raise _plan_error(
            "PBO plan requires an even count of at least four partitions",
            "invalid_pbo_partition_count",
            partition_count=partition_count,
        )
    if len({item.partition_id for item in partitions}) != partition_count:
        raise _plan_error(
            "PBO partition ids must be unique",
            "duplicate_pbo_partition_identity",
        )
    ordinals = tuple(item.ordinal for item in partitions)
    if ordinals != tuple(range(1, partition_count + 1)):
        raise _plan_error(
            "PBO partition ordinals must be contiguous from one",
            "pbo_partition_ordinals_not_contiguous",
        )
    if len({item.observation_count for item in partitions}) != 1:
        raise _plan_error(
            "PBO plan partitions must have equal observation counts",
            "unequal_pbo_partition_observation_count",
        )
    if any(
        previous.window_end >= current.window_start
        for previous, current in pairwise(partitions)
    ):
        raise _plan_error(
            "PBO plan partition windows must be non-overlapping",
            "overlapping_pbo_partition_windows",
        )


@dataclass(frozen=True, slots=True)
class PboPartitionPlan:
    """Exact PBO estimator and time layout frozen before returns are observed."""

    score_metric_id: ResearchMetricId
    direction: ResearchMetricDirection
    estimator: PboEstimator
    return_unit: SamplingReturnUnit
    return_frequency: ReturnFrequency
    periods_per_year: int
    partitions: Sequence[PboPartitionIdentity]

    def __post_init__(self) -> None:  # noqa: C901 - aggregate invariant gate
        """Freeze a viable schema-aligned CSCV declaration."""
        if type(self.score_metric_id) is not ResearchMetricId:
            raise _plan_error("invalid PBO score metric", "invalid_pbo_metric")
        if type(self.direction) is not ResearchMetricDirection:
            raise _plan_error("invalid PBO direction", "invalid_pbo_direction")
        if type(self.estimator) is not PboEstimator:
            raise _plan_error("invalid PBO estimator", "invalid_pbo_estimator")
        if self.return_unit is not SamplingReturnUnit.PER_PERIOD_DECIMAL:
            raise _plan_error(
                "PBO returns must use per-period decimal units",
                "invalid_sampling_return_unit",
            )
        if type(self.return_frequency) is not ReturnFrequency:
            raise _plan_error(
                "invalid PBO return frequency",
                "invalid_return_frequency",
            )
        expected_periods = _PERIODS_PER_YEAR[self.return_frequency.value]
        if (
            type(self.periods_per_year) is not int
            or self.periods_per_year != expected_periods
        ):
            raise _plan_error(
                "PBO periods_per_year must match its return frequency",
                "invalid_periods_per_year",
                expected=expected_periods,
                observed=self.periods_per_year,
            )
        definition = R3_RESEARCH_METRIC_SCHEMA.definition(self.score_metric_id)
        if self.direction is not definition.direction:
            raise _plan_error(
                "PBO direction must match its metric schema",
                "pbo_metric_direction_mismatch",
            )
        if _ESTIMATOR_METRICS[self.estimator] is not self.score_metric_id:
            raise _plan_error(
                "PBO estimator is incompatible with its score metric",
                "pbo_estimator_metric_mismatch",
            )
        if self.return_frequency is not ReturnFrequency.DAILY:
            raise _plan_error(
                "R3 PBO governance metrics require daily raw returns",
                "pbo_sampling_schema_scale_mismatch",
            )
        if (
            self.estimator is PboEstimator.SHARPE_RATIO
            and definition.periods_per_year != self.periods_per_year
        ):
            raise _plan_error(
                "PBO Sharpe annualization must match the metric schema",
                "pbo_sampling_schema_scale_mismatch",
            )
        partitions = _freeze_partition_identities(self.partitions)
        _validate_partition_layout(partitions)
        object.__setattr__(self, "partitions", partitions)

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete versioned pre-registration payload."""
        return {
            "schema_id": "r3-pbo-partition-plan",
            "schema_version": 1,
            "score_metric_id": self.score_metric_id.value,
            "direction": self.direction.value,
            "estimator": self.estimator.value,
            "return_unit": self.return_unit.value,
            "return_frequency": self.return_frequency.value,
            "periods_per_year": self.periods_per_year,
            "partitions": [item.canonical_payload() for item in self.partitions],
        }
