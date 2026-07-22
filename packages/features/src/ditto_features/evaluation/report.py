"""Factor evaluation report dataclasses."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import cast

import orjson

from ditto_features.evaluation.r3_diagnostics_identity import (
    R3FactorDiagnosticsProvenance,
)

__all__ = [
    "R3_FACTOR_DIAGNOSTICS_SCHEMA_VERSION",
    "R3_FACTOR_DIAGNOSTIC_METRIC_IDS",
    "AttributionContribution",
    "FactorEvaluationReport",
    "FactorExposureResult",
    "FamaMacBethResult",
    "ICSummary",
    "LongShortResult",
    "PerformanceAttributionResult",
    "R3FactorDiagnosticsProjection",
    "R3FactorDiagnosticsProvenance",
    "RegimeICResult",
    "TailRiskMetrics",
    "project_r3_factor_diagnostics",
    "r3_factor_diagnostics_content_hash",
    "r3_factor_diagnostics_projection_hash",
]

R3_FACTOR_DIAGNOSTICS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class R3FactorDiagnosticsProjection:
    """Honest factor diagnostics bound to their immutable source artifact."""

    provenance: R3FactorDiagnosticsProvenance
    content_hash: str
    computed_metrics: tuple[str, ...]
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize, validate, and recursively freeze projected evidence."""
        if type(self.provenance) is not R3FactorDiagnosticsProvenance:
            raise ValueError("provenance must be exact factor-evaluation provenance")
        metric_ids = _copy_sequence(self.computed_metrics, "computed metric IDs")
        if metric_ids != tuple(self.values):
            raise ValueError("computed metric IDs must match diagnostic values")
        unknown = tuple(
            metric_id
            for metric_id in metric_ids
            if metric_id not in R3_FACTOR_DIAGNOSTIC_METRIC_IDS
        )
        if unknown:
            raise ValueError(f"unsupported R3 diagnostic metric: {unknown[0]}")
        expected_order = tuple(
            metric_id
            for metric_id in R3_FACTOR_DIAGNOSTIC_METRIC_IDS
            if metric_id in metric_ids
        )
        if metric_ids != expected_order:
            raise ValueError("computed metric IDs must use canonical schema order")
        normalized = {
            metric_id: _deep_freeze(
                _normalize_diagnostic(metric_id, self.values[metric_id])
            )
            for metric_id in metric_ids
        }
        expected_hash = _diagnostic_values_hash(
            normalized,
            self.provenance,
        )
        if self.content_hash != expected_hash:
            raise ValueError("diagnostics artifact content hash does not match values")
        object.__setattr__(self, "computed_metrics", metric_ids)
        object.__setattr__(self, "values", MappingProxyType(normalized))


_R3_DIAGNOSTIC_SOURCES = (
    ("coverage", "coverage"),
    ("missingness", "missingness"),
    ("rank_ic", "rank_ic"),
    ("icir", "icir"),
    ("decay", "ic_decay"),
    ("quantile_return", "quantile_annual_returns"),
    ("turnover", "avg_turnover"),
    ("cost_drag", "cost_drag"),
    ("fold_stability", "fold_stability"),
    ("factor_contribution", "factor_contribution"),
    ("exposure", "factor_exposure"),
    ("parameter_neighborhood_stability", "parameter_neighborhood_stability"),
    ("market_regime_performance", "market_regime_performance"),
    ("liquidity", "liquidity"),
    ("industry_exposure", "industry_exposure"),
    ("size_exposure", "size_exposure"),
    ("style_exposure", "style_exposure"),
)

R3_FACTOR_DIAGNOSTIC_METRIC_IDS: tuple[str, ...] = tuple(
    metric_id for metric_id, _ in _R3_DIAGNOSTIC_SOURCES
)


def project_r3_factor_diagnostics(
    source: Mapping[str, object] | FactorEvaluationReport,
    *,
    provenance: R3FactorDiagnosticsProvenance,
) -> R3FactorDiagnosticsProjection:
    """Project evaluator output without inventing absent diagnostic results."""
    if type(provenance) is not R3FactorDiagnosticsProvenance:
        raise ValueError("provenance must be exact factor-evaluation provenance")
    if type(source) is FactorEvaluationReport:
        _validate_report_identity(source, provenance)
    values = _normalized_diagnostic_values(source)
    return R3FactorDiagnosticsProjection(
        provenance=provenance,
        content_hash=_diagnostic_values_hash(values, provenance),
        computed_metrics=tuple(values),
        values=values,
    )


def r3_factor_diagnostics_content_hash(
    source: Mapping[str, object] | FactorEvaluationReport,
    *,
    provenance: R3FactorDiagnosticsProvenance,
) -> str:
    """Compatibility alias for :func:`r3_factor_diagnostics_projection_hash`."""
    return r3_factor_diagnostics_projection_hash(source, provenance=provenance)


def r3_factor_diagnostics_projection_hash(
    source: Mapping[str, object] | FactorEvaluationReport,
    *,
    provenance: R3FactorDiagnosticsProvenance,
) -> str:
    """Hash the canonical projection values and every declared source field."""
    if type(provenance) is not R3FactorDiagnosticsProvenance:
        raise ValueError("provenance must be exact diagnostics provenance")
    return _diagnostic_values_hash(_normalized_diagnostic_values(source), provenance)


def _diagnostic_raw(
    source: Mapping[str, object] | FactorEvaluationReport,
) -> Mapping[str, object]:
    if isinstance(source, Mapping):
        return source
    if type(source) is not FactorEvaluationReport:
        raise ValueError("source must be factor diagnostics or evaluation report")
    if source.n_observations == 0:
        return {}
    return {
        "rank_ic": source.rank_ic_summary.mean,
        "icir": source.rank_ic_summary.icir,
        "ic_decay": source.ic_decay,
        "quantile_annual_returns": source.quantile_annual_returns,
        "avg_turnover": source.avg_turnover,
        "cost_drag": source.long_short.annual_return - source.net_return_after_cost,
        "factor_exposure": source.factor_exposure,
    }


def _normalized_diagnostic_values(
    source: Mapping[str, object] | FactorEvaluationReport,
) -> dict[str, object]:
    raw = _diagnostic_raw(source)
    values: dict[str, object] = {}
    for metric_id, source_key in _R3_DIAGNOSTIC_SOURCES:
        value = raw.get(source_key)
        if _diagnostic_was_computed(value):
            values[metric_id] = _normalize_diagnostic(metric_id, value)
    return values


def _canonical_hash_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return [
            [item.name, _canonical_hash_value(getattr(value, item.name))]
            for item in fields(value)
        ]
    if isinstance(value, Mapping):
        return [
            [
                f"{type(key).__name__}:{key}",
                _canonical_hash_value(item),
            ]
            for key, item in cast("Mapping[object, object]", value).items()
        ]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_hash_value(item) for item in cast("Sequence[object]", value)]
    return value


def _diagnostic_values_hash(
    values: Mapping[str, object],
    provenance: R3FactorDiagnosticsProvenance,
) -> str:
    payload = {
        "schema": "r3_factor_diagnostics_projection",
        "version": R3_FACTOR_DIAGNOSTICS_SCHEMA_VERSION,
        "factor_provenance": provenance.canonical_payload(),
        "values": [
            [metric_id, _canonical_hash_value(value)]
            for metric_id, value in values.items()
        ],
    }
    encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


def _validate_report_identity(
    report: FactorEvaluationReport,
    provenance: R3FactorDiagnosticsProvenance,
) -> None:
    expected = (
        report.factor_id,
        report.factor_version,
        report.evaluation_period,
        report.dataset_id,
        report.catalog_snapshot_id,
        report.universe,
        float(report.cost_bps),
    )
    actual = (
        provenance.factor_id,
        provenance.factor_version,
        provenance.evaluation_period,
        provenance.dataset_id,
        provenance.catalog_snapshot_id,
        provenance.universe,
        provenance.cost_bps,
    )
    if actual != expected:
        raise ValueError("diagnostics source identity does not match evaluation report")


def _diagnostic_was_computed(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, Mapping):
        return len(cast(Mapping[object, object], value)) > 0
    if isinstance(value, (list, tuple)):
        return len(cast(Sequence[object], value)) > 0
    return True


_SCALAR_DIAGNOSTICS = frozenset(
    {"coverage", "missingness", "rank_ic", "icir", "turnover", "cost_drag"}
)
_STRING_NUMERIC_MAPPING_DIAGNOSTICS = frozenset(
    {
        "fold_stability",
        "factor_contribution",
        "parameter_neighborhood_stability",
        "market_regime_performance",
        "liquidity",
        "industry_exposure",
        "size_exposure",
        "style_exposure",
    }
)
_DIAGNOSTIC_PAIR_LENGTH = 2


def _require_ordered_sequence(value: object, field_name: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a non-text sequence")


def _copy_sequence[T](value: Sequence[T], field_name: str) -> tuple[T, ...]:
    _require_ordered_sequence(value, field_name)
    return tuple(value)


def _normalize_diagnostic(metric_id: str, value: object) -> object:
    if metric_id in _SCALAR_DIAGNOSTICS:
        scalar = _require_finite_number(value, metric_id)
        if metric_id in {"coverage", "missingness"} and not 0.0 <= scalar <= 1.0:
            raise ValueError(f"{metric_id} diagnostic must be between zero and one")
        if metric_id in {"turnover", "cost_drag"} and scalar < 0.0:
            raise ValueError(f"{metric_id} diagnostic must be non-negative")
        if metric_id == "rank_ic" and not -1.0 <= scalar <= 1.0:
            raise ValueError("rank_ic diagnostic must be between minus one and one")
        return scalar
    if metric_id == "decay":
        return _normalize_decay(value)
    if metric_id == "quantile_return":
        return _normalize_numeric_mapping(value, metric_id, int)
    if metric_id in _STRING_NUMERIC_MAPPING_DIAGNOSTICS:
        return _normalize_numeric_mapping(value, metric_id, str)
    if metric_id == "exposure":
        return _normalize_exposure(value)
    raise ValueError(f"unsupported R3 diagnostic metric: {metric_id}")


def _require_finite_number(value: object, metric_id: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{metric_id} diagnostic must be a finite number")
    return float(value)


def _normalize_decay(value: object) -> tuple[tuple[int, float], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("decay diagnostic must be a sequence of period/value pairs")
    normalized: list[tuple[int, float]] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
            raise ValueError(
                "decay diagnostic must be a sequence of period/value pairs"
            )
        pair = cast(Sequence[object], item)
        if len(pair) != _DIAGNOSTIC_PAIR_LENGTH:
            raise ValueError(
                "decay diagnostic must be a sequence of period/value pairs"
            )
        period, score = pair
        if not isinstance(period, int) or isinstance(period, bool) or period < 1:
            raise ValueError(
                "decay diagnostic must be a sequence of period/value pairs"
            )
        normalized.append((period, _require_finite_number(score, "decay")))
    normalized.sort(key=lambda item: item[0])
    if len({period for period, _ in normalized}) != len(normalized):
        raise ValueError("decay diagnostic periods must be unique")
    return tuple(normalized)


def _normalize_numeric_mapping(
    value: object,
    metric_id: str,
    key_type: type[int] | type[str],
) -> Mapping[object, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{metric_id} diagnostic must be a numeric mapping")
    normalized: dict[object, float] = {}
    source = cast(Mapping[object, object], value)
    invalid_type = any(
        not isinstance(key, key_type) or isinstance(key, bool) for key in source
    )
    if invalid_type:
        raise ValueError(f"{metric_id} diagnostic must be a numeric mapping")
    if key_type is str and any(
        not cast("str", key) or cast("str", key) != cast("str", key).strip()
        for key in source
    ):
        raise ValueError(f"{metric_id} diagnostic key must be a canonical string")
    keys: tuple[int | str, ...]
    if key_type is str:
        keys = tuple(sorted(cast("str", key) for key in source))
    else:
        keys = tuple(sorted(cast("int", key) for key in source))
    for key in keys:
        try:
            normalized[key] = _require_finite_number(source[key], metric_id)
        except ValueError as exc:
            raise ValueError(
                f"{metric_id} diagnostic must be a numeric mapping"
            ) from exc
    return MappingProxyType(normalized)


def _normalize_exposure(value: object) -> object:
    if isinstance(value, FactorExposureResult):
        return FactorExposureResult(
            target_exposure=cast(
                dict[str, float],
                _normalize_numeric_mapping(value.target_exposure, "exposure", str),
            ),
            correlation_matrix=cast(
                dict[str, dict[str, float]],
                _normalize_nested_numeric_mapping(
                    value.correlation_matrix,
                    "exposure",
                ),
            ),
            orthogonal_residual_stats=cast(
                dict[str, float],
                _normalize_numeric_mapping(
                    value.orthogonal_residual_stats,
                    "exposure",
                    str,
                ),
            ),
            n_factors=_require_non_negative_int(value.n_factors, "exposure"),
            n_dates=_require_non_negative_int(value.n_dates, "exposure"),
        )
    return _normalize_nested_numeric_mapping(value, "exposure")


def _normalize_nested_numeric_mapping(
    value: object,
    metric_id: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{metric_id} diagnostic must be a numeric mapping")
    normalized: dict[str, object] = {}
    source = cast(Mapping[object, object], value)
    if any(not isinstance(key, str) for key in source):
        raise ValueError(f"{metric_id} diagnostic must be a numeric mapping")
    for key in sorted(cast("Mapping[str, object]", source)):
        item = source[key]
        if not key or key != key.strip():
            raise ValueError(f"{metric_id} diagnostic key must be a canonical string")
        if isinstance(item, Mapping):
            normalized[key] = _normalize_nested_numeric_mapping(
                cast(Mapping[object, object], item), metric_id
            )
        else:
            try:
                normalized[key] = _require_finite_number(item, metric_id)
            except ValueError as exc:
                raise ValueError(
                    f"{metric_id} diagnostic must be a numeric mapping"
                ) from exc
    return MappingProxyType(normalized)


def _require_non_negative_int(value: object, metric_id: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{metric_id} diagnostic count must be a non-negative int")
    return value


def _deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        source = cast(Mapping[object, object], value)
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in source.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in cast(Sequence[object], value))
    return value


@dataclass(frozen=True)
class ICSummary:
    """
    IC time-series statistical summary (shared by Rank IC and Pearson IC).

    Attributes:
        mean: IC mean.
        std: IC standard deviation.
        icir: ICIR = mean / std (IR_1: factor predictive power stability).
        t_stat: t-statistic = mean / (std / sqrt(T)).
        p_value: Two-sided t-test p-value.
        win_rate: Proportion of days with IC > 0.

    """

    mean: float
    std: float
    icir: float
    t_stat: float
    p_value: float
    win_rate: float


@dataclass(frozen=True)
class FamaMacBethResult:
    """
    Fama-MacBeth regression result across time-period cross-sections.

    For each date, an OLS cross-sectional regression of returns on the target
    factor (and optionally risk factors) is run.  The time-series of the target
    factor's slope coefficient is then summarised with standard error,
    t-statistic, and p-value.

    Attributes:
        factor_exposure: Mean slope (β) for the target factor across periods.
        exposure_t_stat: t-statistic of the mean slope.
        exposure_p_value: Two-sided p-value of the mean slope.
        exposure_stderr: Standard error of the slope (std / sqrt(n)).
        r_squared_avg: Average R² across periods.
        n_periods: Number of valid periods (dates) used.
        slopes: ``[(factor_name, mean_slope), ...]`` for all regressors.

    """

    factor_exposure: float
    exposure_t_stat: float
    exposure_p_value: float
    exposure_stderr: float
    r_squared_avg: float
    n_periods: int
    slopes: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class FactorExposureResult:
    """
    Factor exposure analysis.

    Measure how much the target factor is explained by risk factors.

    For each risk factor, the target is orthogonalised against it and the
    residual's IC with returns is computed.  A pairwise correlation matrix is
    also produced.

    Attributes:
        target_exposure: ``{risk_factor_name: R² contribution}`` measuring
            how much of the target's variance each risk factor explains.
        correlation_matrix: ``{factor_name: {other: corr}}`` pairwise
            correlation matrix (target + all risk factors).
        orthogonal_residual_stats: ``{factor_name: residual_mean_ic}`` the
            mean IC of the orthogonalised residual vs returns.
        n_factors: Number of risk factors analysed.
        n_dates: Number of trading dates used.

    """

    target_exposure: dict[str, float]
    correlation_matrix: dict[str, dict[str, float]]
    orthogonal_residual_stats: dict[str, float]
    n_factors: int
    n_dates: int


@dataclass(frozen=True)
class TailRiskMetrics:
    """
    Tail risk statistics for a long-short returns series.

    Attributes:
        cvar_95: CVaR at 95% confidence level (Expected Shortfall).
        cvar_99: CVaR at 99% confidence level (Expected Shortfall).
        skewness: Skewness of returns.
        kurtosis: Excess kurtosis (Pearson kurtosis minus 3).
        max_single_day_loss: Worst single-day return.

    """

    cvar_95: float
    cvar_99: float
    skewness: float
    kurtosis: float
    max_single_day_loss: float


@dataclass(frozen=True)
class LongShortResult:
    """
    Long-short portfolio risk metrics.

    Attributes:
        annual_return: Annualized return (net of risk-free rate).
        annual_volatility: Annualized volatility.
        sharpe: Sharpe ratio = (annual_return - rf) / vol.
        portfolio_ir: Factor Portfolio IR = (return - R_f) / vol.
        sortino: Sortino ratio = return / downside_dev.
        max_drawdown: Maximum drawdown.
        calmar: Calmar ratio = annual_return / abs(max_drawdown).
        tail_risk: Tail risk metrics (CVaR, skewness, kurtosis, etc.).

    """

    annual_return: float
    annual_volatility: float
    sharpe: float
    portfolio_ir: float
    sortino: float
    max_drawdown: float
    calmar: float
    tail_risk: TailRiskMetrics


@dataclass(frozen=True)
class RegimeICResult:
    """
    Regime-adjusted IC analysis result.

    Attributes:
        regimes: Mapping of regime name to IC summary statistics.
        regime_labels: List of (date_str, regime_label) per observation.
        transition_matrix: Markov transition probabilities ``{from: {to: prob}}``.
        ic_trend: Linear regression slope of IC over time (trend momentum).
        ic_trend_p_value: p-value testing whether the trend slope is non-zero.

    """

    regimes: dict[str, ICSummary]
    regime_labels: list[tuple[str, str]]
    transition_matrix: dict[str, dict[str, float]]
    ic_trend: float
    ic_trend_p_value: float


@dataclass(frozen=True)
class AttributionContribution:
    """
    Conservative contribution item for performance attribution.

    Attributes:
        label: Human-readable bucket label, for example ``quantile_5``.
        contribution_return: Annualized return contribution of this bucket.
        contribution_share: Contribution divided by total_return when defined.
        mean_return: Average per-period return for the bucket.
        observation_count: Number of return observations in the bucket.

    """

    label: str
    contribution_return: float
    contribution_share: float
    mean_return: float
    observation_count: int


@dataclass(frozen=True)
class PerformanceAttributionResult:
    """
    Performance attribution decomposition.

    Attributes:
        total_return: Annualized equal-weighted return across all quantiles.
        selection_return: Annualized long-short spread (top - bottom).
        timing_return: total_return - selection_return (simplified model).
        interaction_return: Residual component (0.0 in simplified model).
        annual_alpha: Annualized alpha (= selection_return in simplified model).
        tracking_error: Annualized daily std of LS return.
        information_ratio: alpha / tracking_error (0.0 if tracking_error is 0).
        win_rate_by_quantile: Fraction of days with positive return per quantile.
        contributions: Annualized return contribution items by attribution bucket.

    """

    total_return: float
    selection_return: float
    timing_return: float
    interaction_return: float
    annual_alpha: float
    tracking_error: float
    information_ratio: float
    win_rate_by_quantile: dict[int, float]
    contributions: tuple[AttributionContribution, ...] = ()


@dataclass(frozen=True)
class FactorEvaluationReport:
    """
    Complete factor evaluation result for a single run.

    Attributes:
        factor_id: Evaluated factor identifier.
        factor_version: Evaluated factor version.
        evaluation_period: (start_date, end_date) of the evaluation window.
        holding_period: Forward return holding period in days.
        n_quantiles: Number of quantile groups.
        rank_ic_summary: Rank IC full statistics (IR layer 1).
        pearson_ic_summary: Pearson IC full statistics (reference).
        ic_decay: [(lag, mean_ic), ...] decay profile.
        ic_half_life: IC half-life in days (None if not computable).
        ic_autocorrelation: [(lag, acf), ...] IC autocorrelation.
        quantile_annual_returns: {quantile: annualized_return}.
        long_short: Long-short portfolio complete risk metrics.
        avg_turnover: Average two-way turnover.
        net_return_after_cost: Net return after turnover cost.
        turnover_adjusted_ir: Turnover-adjusted IR (IR layer 3).
        grinold_kahn_ir: Grinold-Kahn fundamental law IR with autocorrelation
            correction.
        sub_period_ic: {period_label: ICSummary}.
        fama_macbeth: Fama-MacBeth regression result (None if not computed).
        factor_exposure: Factor exposure analysis result (None if not computed).
        n_observations: Total number of cross-section observations.
        n_dates: Number of trading dates in the evaluation window.
        computed_at: ISO timestamp of when the report was generated.
        dataset_id: Source dataset identifier used for the evaluation.
        catalog_snapshot_id: Catalog snapshot or evidence identifier.
        universe: Universe identifier used for the evaluation.
        cost_bps: Turnover cost in basis points used for net-return metrics.

    """

    factor_id: str
    factor_version: int
    evaluation_period: tuple[str, str]
    holding_period: int
    n_quantiles: int

    # IC analysis (IR layer 1)
    rank_ic_summary: ICSummary
    pearson_ic_summary: ICSummary

    # IC stability and decay
    ic_decay: list[tuple[int, float]]
    ic_half_life: float | None
    ic_autocorrelation: list[tuple[int, float]]

    # Quantile returns (IR layer 2)
    quantile_annual_returns: dict[int, float]
    long_short: LongShortResult

    # Turnover and cost
    avg_turnover: float
    net_return_after_cost: float

    # IR layer 3
    turnover_adjusted_ir: float
    grinold_kahn_ir: float

    # Sub-period stability
    sub_period_ic: dict[str, ICSummary]

    # Metadata
    n_observations: int
    n_dates: int
    computed_at: str
    dataset_id: str = ""
    catalog_snapshot_id: str = ""
    universe: str = ""
    cost_bps: float = 0.0

    # Fama-MacBeth and factor exposure (optional)
    fama_macbeth: FamaMacBethResult | None = None
    factor_exposure: FactorExposureResult | None = None

    # Regime-adjusted IC and performance attribution (optional)
    regime_ic: RegimeICResult | None = None
    performance_attribution: PerformanceAttributionResult | None = None
