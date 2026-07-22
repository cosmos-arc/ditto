"""Typed sampling evidence used by multiple-testing adjustments."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from statistics import fmean, stdev
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    R3_RESEARCH_METRIC_SCHEMA,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricScale,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import CandidateId, ContentHash
from ditto_analysis.experiments.pbo_plan import (
    PboEstimator,
    PboPartitionIdentity,
    PboPartitionPlan,
    ReturnFrequency,
    SamplingReturnUnit,
    partition_observation_date_grid_hash,
)
from ditto_analysis.experiments.persistence import (
    canonical_payload as _canonical_payload,
)

__all__ = [
    "MAX_PBO_COMBINATIONS",
    "DeflatedSharpeEvidence",
    "EvidenceStatus",
    "PboEstimator",
    "PboEvidence",
    "PboPartitionIdentity",
    "PboPartitionPlan",
    "PboPartitionReturns",
    "PboSamplingEvidence",
    "ReturnFrequency",
    "SamplingReturnUnit",
    "SharpeRatioScale",
    "SharpeSamplingEvidence",
    "partition_observation_date_grid_hash",
    "partition_returns_hash",
]

MAX_PBO_COMBINATIONS = 100_000
_MIN_RETURN_OBSERVATIONS = 2
_PERIODS_PER_YEAR = {
    "daily": 252,
    "weekly": 52,
    "monthly": 12,
}


def _statistics_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _finite_number(value: object, field_name: str) -> float:
    if (
        type(value) not in {int, float}
        or isinstance(value, bool)
        or not math.isfinite(cast("float", value))
    ):
        raise _statistics_error(
            f"{field_name} must be a finite number",
            "non_finite_statistical_value",
            field=field_name,
        )
    return float(cast("int | float", value))


def _return_values(value: object) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _statistics_error(
            "partition returns must be an ordered sequence",
            "invalid_partition_returns",
        )
    returns = tuple(
        _finite_number(item, f"returns[{index}]")
        for index, item in enumerate(cast("Sequence[object]", value))
    )
    if not returns or any(item <= -1.0 for item in returns):
        raise _statistics_error(
            "partition returns must be non-empty simple returns greater than -1",
            "invalid_partition_returns",
        )
    return returns


class EvidenceStatus(StrEnum):
    """Whether a statistical method's prerequisites were satisfied."""

    EVALUATED = "evaluated"
    NOT_EVALUATED = "not_evaluated"


class SharpeRatioScale(StrEnum):
    """Scale of the declared Sharpe ratio before DSR normalization."""

    PER_PERIOD = "per_period"
    ANNUALIZED = "annualized"


@dataclass(frozen=True, slots=True)
class SharpeSamplingEvidence:
    """Hashed return-moment evidence supporting one Sharpe observation."""

    sharpe_ratio: ResearchMetricValue
    scale: SharpeRatioScale
    return_unit: SamplingReturnUnit
    return_frequency: ReturnFrequency
    periods_per_year: int
    observation_count: int
    return_skewness: float
    pearson_kurtosis: float
    return_series_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate units, frequency, count, moments, and content identity."""
        if (
            type(self.sharpe_ratio) is not ResearchMetricValue
            or self.sharpe_ratio.metric_id is not ResearchMetricId.SHARPE_RATIO
        ):
            raise _statistics_error(
                "sharpe sampling value must use the Sharpe metric",
                "invalid_sharpe_sampling_metric",
            )
        if type(self.scale) is not SharpeRatioScale:
            raise _statistics_error(
                "sharpe scale must be SharpeRatioScale",
                "invalid_sharpe_scale",
            )
        if self.return_unit is not SamplingReturnUnit.PER_PERIOD_DECIMAL:
            raise _statistics_error(
                "Sharpe sampling returns must use per-period decimal units",
                "invalid_sampling_return_unit",
            )
        if type(self.return_frequency) is not ReturnFrequency:
            raise _statistics_error(
                "return frequency must be ReturnFrequency",
                "invalid_return_frequency",
            )
        expected_periods = _PERIODS_PER_YEAR[self.return_frequency.value]
        if (
            type(self.periods_per_year) is not int
            or self.periods_per_year != expected_periods
        ):
            raise _statistics_error(
                "periods_per_year must match the typed return frequency",
                "invalid_periods_per_year",
                expected=expected_periods,
                observed=self.periods_per_year,
            )
        if (
            type(self.observation_count) is not int
            or self.observation_count < _MIN_RETURN_OBSERVATIONS
        ):
            raise _statistics_error(
                "observation_count must be at least two",
                "invalid_trial_observation_count",
            )
        skewness = _finite_number(self.return_skewness, "return_skewness")
        kurtosis = _finite_number(self.pearson_kurtosis, "pearson_kurtosis")
        if kurtosis < 1.0:
            raise _statistics_error(
                "Pearson kurtosis must be at least one",
                "invalid_pearson_kurtosis",
            )
        if type(self.return_series_hash) is not ContentHash:
            raise _statistics_error(
                "return series hash must be ContentHash",
                "invalid_return_series_hash",
            )
        object.__setattr__(self, "return_skewness", skewness)
        object.__setattr__(self, "pearson_kurtosis", kurtosis)

    @property
    def per_period_sharpe(self) -> float:
        """Return the Sharpe ratio on the declared sampling interval."""
        if self.scale is SharpeRatioScale.PER_PERIOD:
            return self.sharpe_ratio.value
        return self.sharpe_ratio.value / math.sqrt(self.periods_per_year)

    @property
    def annualized_sharpe(self) -> ResearchMetricValue:
        """Normalize the observation to the governance schema's annualized scale."""
        definition = R3_RESEARCH_METRIC_SCHEMA.definition(ResearchMetricId.SHARPE_RATIO)
        if (
            definition.scale is not ResearchMetricScale.ANNUALIZED
            or definition.periods_per_year is None
            or self.periods_per_year != definition.periods_per_year
        ):
            raise _statistics_error(
                "Sharpe sampling scale must match the governance metric schema",
                "sharpe_sampling_schema_scale_mismatch",
            )
        value = self.sharpe_ratio.value
        if self.scale is SharpeRatioScale.PER_PERIOD:
            value *= math.sqrt(self.periods_per_year)
        return ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, value)


def partition_returns_hash(
    identity: PboPartitionIdentity,
    returns: Sequence[float],
) -> ContentHash:
    """Hash one partition identity together with its canonical simple returns."""
    if type(identity) is not PboPartitionIdentity:
        raise _statistics_error(
            "partition identity must be PboPartitionIdentity",
            "invalid_pbo_partition_identity",
        )
    frozen_returns = _return_values(returns)
    payload = {
        "schema_id": "r3-pbo-partition-returns",
        "schema_version": 1,
        "identity": identity.canonical_payload(),
        "returns": list(frozen_returns),
    }
    return _canonical_payload(payload, schema_version=1).content_hash


@dataclass(frozen=True, slots=True)
class PboPartitionReturns:
    """Raw, hashed returns for one declared CSCV partition."""

    identity: PboPartitionIdentity
    returns: Sequence[float]
    return_hash: ContentHash

    def __post_init__(self) -> None:
        """Freeze returns and verify count and canonical content hash."""
        if type(self.identity) is not PboPartitionIdentity:
            raise _statistics_error(
                "partition identity must be PboPartitionIdentity",
                "invalid_pbo_partition_identity",
            )
        returns = _return_values(self.returns)
        if len(returns) != self.identity.observation_count:
            raise _statistics_error(
                "partition return count must equal its declared observation count",
                "partition_observation_count_mismatch",
            )
        if type(self.return_hash) is not ContentHash:
            raise _statistics_error(
                "partition return hash must be ContentHash",
                "invalid_partition_return_hash",
            )
        expected_hash = partition_returns_hash(self.identity, returns)
        if self.return_hash != expected_hash:
            raise _statistics_error(
                "partition return hash does not match its canonical evidence",
                "partition_return_hash_mismatch",
            )
        object.__setattr__(self, "returns", returns)


_ESTIMATOR_METRICS = {
    PboEstimator.COMPOUND_RETURN: ResearchMetricId.NET_RETURN,
    PboEstimator.SHARPE_RATIO: ResearchMetricId.SHARPE_RATIO,
}


@dataclass(frozen=True, slots=True)
class PboSamplingEvidence:
    """Aligned raw-return schema and estimator for one logical trial."""

    score_metric_id: ResearchMetricId
    direction: ResearchMetricDirection
    estimator: PboEstimator
    return_unit: SamplingReturnUnit
    return_frequency: ReturnFrequency
    periods_per_year: int
    partitions: Sequence[PboPartitionReturns]

    def _validate_sampling_types(self) -> None:
        if type(self.score_metric_id) is not ResearchMetricId:
            raise _statistics_error(
                "PBO score metric must be ResearchMetricId",
                "invalid_pbo_metric",
            )
        if type(self.direction) is not ResearchMetricDirection:
            raise _statistics_error(
                "PBO direction must be ResearchMetricDirection",
                "invalid_pbo_direction",
            )
        if type(self.estimator) is not PboEstimator:
            raise _statistics_error(
                "PBO estimator must be PboEstimator",
                "invalid_pbo_estimator",
            )
        if self.return_unit is not SamplingReturnUnit.PER_PERIOD_DECIMAL:
            raise _statistics_error(
                "PBO returns must use per-period decimal units",
                "invalid_sampling_return_unit",
            )
        if type(self.return_frequency) is not ReturnFrequency:
            raise _statistics_error(
                "PBO return frequency must be ReturnFrequency",
                "invalid_return_frequency",
            )

    def _validate_sampling_schema(self) -> None:
        expected_periods = _PERIODS_PER_YEAR[self.return_frequency.value]
        if (
            type(self.periods_per_year) is not int
            or self.periods_per_year != expected_periods
        ):
            raise _statistics_error(
                "PBO periods_per_year must match its return frequency",
                "invalid_periods_per_year",
                expected=expected_periods,
                observed=self.periods_per_year,
            )
        definition = R3_RESEARCH_METRIC_SCHEMA.definition(self.score_metric_id)
        if self.direction is not definition.direction:
            raise _statistics_error(
                "PBO direction must match its metric schema",
                "pbo_metric_direction_mismatch",
            )
        if _ESTIMATOR_METRICS[self.estimator] is not self.score_metric_id:
            raise _statistics_error(
                "PBO estimator is incompatible with its score metric",
                "pbo_estimator_metric_mismatch",
            )
        if self.return_frequency is not ReturnFrequency.DAILY:
            raise _statistics_error(
                "R3 PBO governance metrics require daily raw returns",
                "pbo_sampling_schema_scale_mismatch",
            )
        if (
            self.estimator is PboEstimator.SHARPE_RATIO
            and definition.periods_per_year != self.periods_per_year
        ):
            raise _statistics_error(
                "PBO Sharpe annualization must match the governance schema",
                "pbo_sampling_schema_scale_mismatch",
            )

    def _freeze_partitions(self) -> tuple[PboPartitionReturns, ...]:
        raw_value = cast("object", self.partitions)
        if not isinstance(raw_value, Sequence) or isinstance(
            raw_value, (str, bytes, bytearray)
        ):
            raise _statistics_error(
                "PBO partitions must be an ordered sequence",
                "invalid_pbo_partitions",
            )
        raw = tuple(cast("Sequence[object]", raw_value))
        if not raw or any(type(item) is not PboPartitionReturns for item in raw):
            raise _statistics_error(
                "PBO partitions must contain PboPartitionReturns",
                "invalid_pbo_partitions",
            )
        return tuple(
            sorted(
                cast("tuple[PboPartitionReturns, ...]", raw),
                key=lambda item: item.identity.ordinal,
            )
        )

    @staticmethod
    def _validate_partition_layout(
        partitions: tuple[PboPartitionReturns, ...],
    ) -> None:
        identities = tuple(item.identity for item in partitions)
        if len(set(identities)) != len(identities):
            raise _statistics_error(
                "PBO partition identities must be unique",
                "duplicate_pbo_partition_identity",
            )
        ordinals = tuple(item.ordinal for item in identities)
        if ordinals != tuple(range(1, len(identities) + 1)):
            raise _statistics_error(
                "PBO partition ordinals must be contiguous from one",
                "pbo_partition_ordinals_not_contiguous",
            )
        if len({item.observation_count for item in identities}) != 1:
            raise _statistics_error(
                "PBO partitions must declare equal observation counts",
                "unequal_pbo_partition_observation_count",
            )
        if any(
            previous.window_end >= current.window_start
            for previous, current in pairwise(identities)
        ):
            raise _statistics_error(
                "PBO partition windows must be non-overlapping",
                "overlapping_pbo_partition_windows",
            )

    def __post_init__(self) -> None:
        """Freeze canonical partitions and reject estimator substitutions."""
        self._validate_sampling_types()
        self._validate_sampling_schema()
        partitions = self._freeze_partitions()
        self._validate_partition_layout(partitions)
        object.__setattr__(self, "partitions", partitions)

    @property
    def aggregate_metric_value(self) -> ResearchMetricValue:
        """Recompute the governance metric from every raw decimal return."""
        returns = tuple(
            value for partition in self.partitions for value in partition.returns
        )
        if self.estimator is PboEstimator.COMPOUND_RETURN:
            percent_return = (math.prod(1.0 + value for value in returns) - 1.0) * 100
            return ResearchMetricValue(self.score_metric_id, percent_return)
        mean_return = fmean(returns)
        volatility = stdev(returns)
        if volatility == 0.0:
            if mean_return == 0.0:
                return ResearchMetricValue(self.score_metric_id, 0.0)
            raise _statistics_error(
                "aggregate Sharpe is undefined for zero-volatility returns",
                "pbo_sampling_aggregate_undefined",
            )
        annualized_sharpe = mean_return / volatility * math.sqrt(self.periods_per_year)
        return ResearchMetricValue(self.score_metric_id, annualized_sharpe)


@dataclass(frozen=True, slots=True)
class DeflatedSharpeEvidence:
    """Transparent Deflated Sharpe result or fail-closed evidence."""

    status: EvidenceStatus
    method: str
    method_prerequisites: tuple[str, ...]
    reason: str
    candidate_id: CandidateId | None
    probability: float | None
    observed_sharpe: float | None
    expected_max_sharpe: float | None
    declared_trial_count: int
    observed_trial_count: int
    completed_sharpe_trial_count: int
    return_frequency: ReturnFrequency | None
    periods_per_year: int | None


@dataclass(frozen=True, slots=True)
class PboEvidence:
    """Transparent CSCV PBO result or fail-closed evidence."""

    status: EvidenceStatus
    method: str
    method_prerequisites: tuple[str, ...]
    reason: str
    probability: float | None
    declared_trial_count: int
    observed_trial_count: int
    partition_count: int | None
    combination_budget: int
    combination_count: int
    evaluated_combination_count: int
    score_metric_id: ResearchMetricId | None
    direction: ResearchMetricDirection | None
    estimator: PboEstimator | None
    tie_method: str
    overfit_lambda_threshold: float
