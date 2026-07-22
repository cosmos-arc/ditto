"""Versioned canonical metric language for R3 research evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, cast

from ditto_analysis.errors import ExperimentSpecError

__all__ = [
    "R3_COMPARISON_METRIC_IDS",
    "R3_DIAGNOSTIC_METRIC_IDS",
    "R3_RESEARCH_METRIC_SCHEMA",
    "ResearchMetricAggregation",
    "ResearchMetricDefinition",
    "ResearchMetricDirection",
    "ResearchMetricDomain",
    "ResearchMetricId",
    "ResearchMetricScale",
    "ResearchMetricSchema",
    "ResearchMetricUnit",
    "ResearchMetricValue",
]


def _metric_error(reason_code: str, **details: object) -> NoReturn:
    raise ExperimentSpecError(
        "research metric schema is invalid",
        details={"reason_code": reason_code, **details},
    )


class ResearchMetricId(StrEnum):
    """Stable metric identifiers shared by R3 evidence and governance."""

    NET_RETURN = "net_return"
    RELATIVE_NET_RETURN = "relative_net_return"
    SHARPE_RATIO = "sharpe_ratio"
    CALMAR_RATIO = "calmar_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    TURNOVER = "turnover"
    COST_DRAG = "cost_drag"
    CAPACITY = "capacity"
    COVERAGE = "coverage"
    MISSINGNESS = "missingness"
    RANK_IC = "rank_ic"
    ICIR = "icir"
    DECAY = "decay"
    QUANTILE_RETURN = "quantile_return"
    FOLD_STABILITY = "fold_stability"
    FACTOR_CONTRIBUTION = "factor_contribution"
    EXPOSURE = "exposure"
    PARAMETER_NEIGHBORHOOD_STABILITY = "parameter_neighborhood_stability"
    MARKET_REGIME_PERFORMANCE = "market_regime_performance"
    LIQUIDITY = "liquidity"
    INDUSTRY_EXPOSURE = "industry_exposure"
    SIZE_EXPOSURE = "size_exposure"
    STYLE_EXPOSURE = "style_exposure"


class ResearchMetricUnit(StrEnum):
    """Canonical representation unit; percent values use 5.0 for five percent."""

    PERCENT = "percent"
    PERCENTAGE_POINTS = "percentage_points"
    RATIO = "ratio"
    FRACTION = "fraction"
    CNY = "CNY"
    PROFILE = "profile"


class ResearchMetricDomain(StrEnum):
    """Research evidence domain owning a metric's interpretation."""

    PERFORMANCE = "performance"
    RISK = "risk"
    EXECUTION = "execution"
    CAPACITY = "capacity"
    DATA_QUALITY = "data_quality"
    FACTOR = "factor"
    ROBUSTNESS = "robustness"
    EXPOSURE = "exposure"
    MARKET_REGIME = "market_regime"


class ResearchMetricDirection(StrEnum):
    """Pre-registration direction; context-only metrics are never ranked."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    CONTEXT_ONLY = "context_only"


class ResearchMetricAggregation(StrEnum):
    """Canonical cross-fold treatment for each metric."""

    COMPOUND_DAILY_RETURNS = "compound_daily_returns"
    CANDIDATE_MINUS_BASELINE = "candidate_minus_baseline"
    RECOMPUTE_DAILY_RETURNS = "recompute_daily_returns"
    RECOMPUTE_CROSS_FOLD_EQUITY_CURVE = "recompute_cross_fold_equity_curve"
    RECOMPUTE_FILLS_AND_CAPITAL = "recompute_fills_and_capital"
    CONSERVATIVE_MINIMUM = "conservative_minimum"
    RETAIN_BY_FOLD = "retain_by_fold"


class ResearchMetricScale(StrEnum):
    """Canonical temporal scale of one metric value."""

    CUMULATIVE = "cumulative"
    ANNUALIZED = "annualized"
    POINT_ESTIMATE = "point_estimate"
    PROFILE = "profile"


@dataclass(frozen=True, slots=True)
class ResearchMetricDefinition:
    """One immutable metric definition in the versioned schema."""

    metric_id: ResearchMetricId
    unit: ResearchMetricUnit
    domain: ResearchMetricDomain
    direction: ResearchMetricDirection
    aggregation: ResearchMetricAggregation
    scale: ResearchMetricScale
    periods_per_year: int | None = None
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        """Reject untyped definitions and invalid scalar domains."""
        for value, expected, field_name in (
            (self.metric_id, ResearchMetricId, "metric_id"),
            (self.unit, ResearchMetricUnit, "unit"),
            (self.domain, ResearchMetricDomain, "domain"),
            (self.direction, ResearchMetricDirection, "direction"),
            (self.aggregation, ResearchMetricAggregation, "aggregation"),
            (self.scale, ResearchMetricScale, "scale"),
        ):
            if type(value) is not expected:
                _metric_error("invalid_metric_definition", field=field_name)
        for field_name in ("minimum", "maximum"):
            value = getattr(self, field_name)
            if value is not None and (
                type(value) not in {int, float} or not math.isfinite(value)
            ):
                _metric_error("invalid_metric_domain", field=field_name)
            if value is not None:
                object.__setattr__(self, field_name, float(value))
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            _metric_error("invalid_metric_domain", field="bounds")
        if self.scale is ResearchMetricScale.ANNUALIZED:
            if type(self.periods_per_year) is not int or self.periods_per_year <= 0:
                _metric_error("invalid_metric_annualization")
        elif self.periods_per_year is not None:
            _metric_error("invalid_metric_annualization")

    @property
    def is_scalar(self) -> bool:
        """Return whether the definition accepts canonical scalar values."""
        return self.unit is not ResearchMetricUnit.PROFILE


@dataclass(frozen=True, slots=True)
class ResearchMetricSchema:
    """Frozen ordered schema with exact typed lookup semantics."""

    schema_id: str
    version: int
    definitions: tuple[ResearchMetricDefinition, ...]

    def __post_init__(self) -> None:
        """Validate identity, version, order, and unique definitions."""
        if (
            type(self.schema_id) is not str
            or not self.schema_id
            or self.schema_id != self.schema_id.strip()
        ):
            _metric_error("invalid_metric_schema_identity")
        if type(self.version) is not int or self.version <= 0:
            _metric_error("invalid_metric_schema_version")
        definitions = tuple(self.definitions)
        if any(type(item) is not ResearchMetricDefinition for item in definitions):
            _metric_error("invalid_metric_definition")
        ids = tuple(item.metric_id for item in definitions)
        if len(set(ids)) != len(ids):
            _metric_error("duplicate_research_metric_id")
        object.__setattr__(self, "definitions", definitions)

    def definition(self, metric_id: ResearchMetricId) -> ResearchMetricDefinition:
        """Resolve one exact typed ID without accepting string lookalikes."""
        if type(metric_id) is not ResearchMetricId:
            _metric_error("invalid_research_metric_id")
        for definition in self.definitions:
            if definition.metric_id is metric_id:
                return definition
        _metric_error("unknown_research_metric_id", metric_id=metric_id.value)

    def canonical_payload(self) -> dict[str, object]:
        """Return a stable JSON-shaped representation of the whole schema."""
        return {
            "schema_id": self.schema_id,
            "version": self.version,
            "definitions": [
                {
                    "metric_id": item.metric_id.value,
                    "unit": item.unit.value,
                    "domain": item.domain.value,
                    "direction": item.direction.value,
                    "aggregation": item.aggregation.value,
                    "scale": item.scale.value,
                    "periods_per_year": item.periods_per_year,
                    "minimum": item.minimum,
                    "maximum": item.maximum,
                }
                for item in self.definitions
            ],
        }


@dataclass(frozen=True, slots=True)
class _MetricOptions:
    scale: ResearchMetricScale = ResearchMetricScale.POINT_ESTIMATE
    periods_per_year: int | None = None
    minimum: float | None = None
    maximum: float | None = None


_DEFAULT_OPTIONS = _MetricOptions()


def _definition(
    metric_id: ResearchMetricId,
    unit: ResearchMetricUnit,
    domain: ResearchMetricDomain,
    direction: ResearchMetricDirection,
    aggregation: ResearchMetricAggregation,
    options: _MetricOptions = _DEFAULT_OPTIONS,
) -> ResearchMetricDefinition:
    return ResearchMetricDefinition(
        metric_id,
        unit,
        domain,
        direction,
        aggregation,
        options.scale,
        options.periods_per_year,
        options.minimum,
        options.maximum,
    )


_P = ResearchMetricUnit.PERCENT
_PP = ResearchMetricUnit.PERCENTAGE_POINTS
_R = ResearchMetricUnit.RATIO
_F = ResearchMetricUnit.FRACTION
_CNY = ResearchMetricUnit.CNY
_PROFILE = ResearchMetricUnit.PROFILE
_MAX = ResearchMetricDirection.MAXIMIZE
_MIN = ResearchMetricDirection.MINIMIZE
_CONTEXT = ResearchMetricDirection.CONTEXT_ONLY
_DAILY = ResearchMetricAggregation.RECOMPUTE_DAILY_RETURNS
_RETAIN = ResearchMetricAggregation.RETAIN_BY_FOLD
_CUMULATIVE = ResearchMetricScale.CUMULATIVE
_ANNUALIZED = ResearchMetricScale.ANNUALIZED
_PROFILE_SCALE = ResearchMetricScale.PROFILE
_CUMULATIVE_RETURN = _MetricOptions(scale=_CUMULATIVE, minimum=-100.0)
_CUMULATIVE_VALUE = _MetricOptions(scale=_CUMULATIVE)
_ANNUALIZED_DAILY = _MetricOptions(scale=_ANNUALIZED, periods_per_year=252)
_DRAWDOWN_DOMAIN = _MetricOptions(minimum=-100.0, maximum=0.0)
_NONNEGATIVE_CUMULATIVE = _MetricOptions(scale=_CUMULATIVE, minimum=0.0)
_NONNEGATIVE = _MetricOptions(minimum=0.0)
_FRACTION_DOMAIN = _MetricOptions(minimum=0.0, maximum=1.0)
_CORRELATION_DOMAIN = _MetricOptions(minimum=-1.0, maximum=1.0)
_PROFILE_OPTIONS = _MetricOptions(scale=_PROFILE_SCALE)

R3_RESEARCH_METRIC_SCHEMA = ResearchMetricSchema(
    schema_id="r3-research-metrics",
    version=1,
    definitions=(
        _definition(
            ResearchMetricId.NET_RETURN,
            _P,
            ResearchMetricDomain.PERFORMANCE,
            _MAX,
            ResearchMetricAggregation.COMPOUND_DAILY_RETURNS,
            _CUMULATIVE_RETURN,
        ),
        _definition(
            ResearchMetricId.RELATIVE_NET_RETURN,
            _PP,
            ResearchMetricDomain.PERFORMANCE,
            _MAX,
            ResearchMetricAggregation.CANDIDATE_MINUS_BASELINE,
            _CUMULATIVE_VALUE,
        ),
        _definition(
            ResearchMetricId.SHARPE_RATIO,
            _R,
            ResearchMetricDomain.PERFORMANCE,
            _MAX,
            _DAILY,
            _ANNUALIZED_DAILY,
        ),
        _definition(
            ResearchMetricId.CALMAR_RATIO,
            _R,
            ResearchMetricDomain.PERFORMANCE,
            _MAX,
            _DAILY,
            _ANNUALIZED_DAILY,
        ),
        _definition(
            ResearchMetricId.MAX_DRAWDOWN,
            _P,
            ResearchMetricDomain.RISK,
            _MAX,
            ResearchMetricAggregation.RECOMPUTE_CROSS_FOLD_EQUITY_CURVE,
            _DRAWDOWN_DOMAIN,
        ),
        _definition(
            ResearchMetricId.TURNOVER,
            _R,
            ResearchMetricDomain.EXECUTION,
            _MIN,
            ResearchMetricAggregation.RECOMPUTE_FILLS_AND_CAPITAL,
            _NONNEGATIVE_CUMULATIVE,
        ),
        _definition(
            ResearchMetricId.COST_DRAG,
            _PP,
            ResearchMetricDomain.EXECUTION,
            _MIN,
            ResearchMetricAggregation.RECOMPUTE_FILLS_AND_CAPITAL,
            _NONNEGATIVE_CUMULATIVE,
        ),
        _definition(
            ResearchMetricId.CAPACITY,
            _CNY,
            ResearchMetricDomain.CAPACITY,
            _MAX,
            ResearchMetricAggregation.CONSERVATIVE_MINIMUM,
            _NONNEGATIVE,
        ),
        _definition(
            ResearchMetricId.COVERAGE,
            _F,
            ResearchMetricDomain.DATA_QUALITY,
            _MAX,
            _RETAIN,
            _FRACTION_DOMAIN,
        ),
        _definition(
            ResearchMetricId.MISSINGNESS,
            _F,
            ResearchMetricDomain.DATA_QUALITY,
            _MIN,
            _RETAIN,
            _FRACTION_DOMAIN,
        ),
        _definition(
            ResearchMetricId.RANK_IC,
            _R,
            ResearchMetricDomain.FACTOR,
            _MAX,
            _RETAIN,
            _CORRELATION_DOMAIN,
        ),
        _definition(
            ResearchMetricId.ICIR,
            _R,
            ResearchMetricDomain.FACTOR,
            _MAX,
            _RETAIN,
        ),
        *(
            _definition(
                metric_id,
                _PROFILE,
                domain,
                direction,
                _RETAIN,
                _PROFILE_OPTIONS,
            )
            for metric_id, domain, direction in (
                (
                    ResearchMetricId.DECAY,
                    ResearchMetricDomain.FACTOR,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.QUANTILE_RETURN,
                    ResearchMetricDomain.FACTOR,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.FOLD_STABILITY,
                    ResearchMetricDomain.ROBUSTNESS,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.FACTOR_CONTRIBUTION,
                    ResearchMetricDomain.FACTOR,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.EXPOSURE,
                    ResearchMetricDomain.EXPOSURE,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.PARAMETER_NEIGHBORHOOD_STABILITY,
                    ResearchMetricDomain.ROBUSTNESS,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.MARKET_REGIME_PERFORMANCE,
                    ResearchMetricDomain.MARKET_REGIME,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.LIQUIDITY,
                    ResearchMetricDomain.CAPACITY,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.INDUSTRY_EXPOSURE,
                    ResearchMetricDomain.EXPOSURE,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.SIZE_EXPOSURE,
                    ResearchMetricDomain.EXPOSURE,
                    _CONTEXT,
                ),
                (
                    ResearchMetricId.STYLE_EXPOSURE,
                    ResearchMetricDomain.EXPOSURE,
                    _CONTEXT,
                ),
            )
        ),
    ),
)

R3_COMPARISON_METRIC_IDS: tuple[ResearchMetricId, ...] = tuple(
    ResearchMetricId(item)
    for item in (
        "net_return",
        "relative_net_return",
        "sharpe_ratio",
        "calmar_ratio",
        "max_drawdown",
        "turnover",
        "cost_drag",
        "capacity",
    )
)

R3_DIAGNOSTIC_METRIC_IDS: tuple[ResearchMetricId, ...] = tuple(
    ResearchMetricId(item)
    for item in (
        "coverage",
        "missingness",
        "rank_ic",
        "icir",
        "decay",
        "quantile_return",
        "turnover",
        "cost_drag",
        "fold_stability",
        "factor_contribution",
        "exposure",
        "parameter_neighborhood_stability",
        "market_regime_performance",
        "liquidity",
        "industry_exposure",
        "size_exposure",
        "style_exposure",
    )
)


@dataclass(frozen=True, slots=True)
class ResearchMetricValue:
    """Canonical finite scalar bound to its typed definition and unit."""

    metric_id: ResearchMetricId
    value: float

    def __post_init__(self) -> None:
        """Normalize numbers while enforcing the schema's canonical domain."""
        if type(self.metric_id) is not ResearchMetricId:
            _metric_error("invalid_research_metric_id")
        raw = cast("object", self.value)
        if (
            type(raw) not in {int, float}
            or isinstance(raw, bool)
            or not math.isfinite(cast("float", raw))
        ):
            _metric_error("non_finite_metric_value", metric_id=self.metric_id.value)
        definition = R3_RESEARCH_METRIC_SCHEMA.definition(self.metric_id)
        if not definition.is_scalar:
            _metric_error(
                "non_scalar_research_metric",
                metric_id=self.metric_id.value,
            )
        value = float(cast("int | float", raw))
        if (definition.minimum is not None and value < definition.minimum) or (
            definition.maximum is not None and value > definition.maximum
        ):
            _metric_error(
                "metric_value_out_of_domain",
                metric_id=self.metric_id.value,
                value=value,
            )
        object.__setattr__(self, "value", value)

    @property
    def unit(self) -> ResearchMetricUnit:
        """Return the schema-owned canonical unit."""
        return R3_RESEARCH_METRIC_SCHEMA.definition(self.metric_id).unit

    def canonical_payload(self) -> dict[str, object]:
        """Return a deterministic JSON-shaped scalar representation."""
        return {
            "metric_id": self.metric_id.value,
            "unit": self.unit.value,
            "value": self.value,
        }
