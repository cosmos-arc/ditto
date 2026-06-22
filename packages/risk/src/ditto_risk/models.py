"""Risk models — 风险领域数据模型与轻量报告构建。"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

__all__ = [
    "BenchmarkActiveWeight",
    "ConcentrationMetrics",
    "DrawdownMetrics",
    "LaunchRiskReport",
    "RiskPosition",
    "StressScenario",
    "TailRiskMetrics",
    "build_launch_risk_report",
]

_UNCLASSIFIED_INDUSTRY = "unclassified"


def _empty_industry_shocks() -> dict[str, float]:
    return {}


@dataclass(frozen=True)
class RiskPosition:
    """Position weight input for launch risk reporting."""

    instrument_id: int
    weight: float
    industry: str | None = None


@dataclass(frozen=True)
class StressScenario:
    """Simple shock scenario for weighted portfolio stress returns."""

    name: str
    market_shock: float = 0.0
    industry_shocks: Mapping[str, float] = field(
        default_factory=_empty_industry_shocks,
    )


@dataclass(frozen=True)
class ConcentrationMetrics:
    """Concentration summary for target or actual portfolio weights."""

    max_weight: float
    top_5_weight: float
    herfindahl_index: float


@dataclass(frozen=True)
class BenchmarkActiveWeight:
    """Active weight versus a supplied benchmark composition."""

    total_abs_active_weight: float
    active_weights: Mapping[str, float]


@dataclass(frozen=True)
class DrawdownMetrics:
    """Drawdown summary from NAV observations."""

    current_drawdown: float
    max_drawdown: float


@dataclass(frozen=True)
class TailRiskMetrics:
    """Historical left-tail return metrics."""

    var_95: float
    cvar_95: float


@dataclass(frozen=True)
class LaunchRiskReport:
    """Minimum launch risk report contract."""

    concentration: ConcentrationMetrics
    industry_exposure: Mapping[str, float]
    benchmark_active_weight: BenchmarkActiveWeight
    drawdown: DrawdownMetrics
    tail_risk: TailRiskMetrics
    stress_scenario_returns: Mapping[str, float]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-stable report payload."""
        return {
            "concentration": dataclasses.asdict(self.concentration),
            "industry_exposure": dict(self.industry_exposure),
            "benchmark_active_weight": {
                "total_abs_active_weight": (
                    self.benchmark_active_weight.total_abs_active_weight
                ),
                "active_weights": dict(self.benchmark_active_weight.active_weights),
            },
            "drawdown": dataclasses.asdict(self.drawdown),
            "tail_risk": dataclasses.asdict(self.tail_risk),
            "stress_scenario_returns": dict(self.stress_scenario_returns),
        }


def build_launch_risk_report(
    *,
    positions: Sequence[RiskPosition],
    benchmark_weights: Mapping[int, float] | None = None,
    nav_series: Sequence[tuple[str, float]] = (),
    stress_scenarios: Sequence[StressScenario] = (),
) -> LaunchRiskReport:
    """Build the minimum launch risk report from supplied portfolio inputs."""
    return LaunchRiskReport(
        concentration=_concentration_metrics(positions),
        industry_exposure=_industry_exposure(positions),
        benchmark_active_weight=_benchmark_active_weight(
            positions,
            benchmark_weights or {},
        ),
        drawdown=_drawdown_metrics(nav_series),
        tail_risk=_tail_risk_metrics(nav_series),
        stress_scenario_returns=_stress_scenario_returns(
            positions,
            stress_scenarios,
        ),
    )


def _concentration_metrics(
    positions: Sequence[RiskPosition],
) -> ConcentrationMetrics:
    positive_weights = sorted(
        (max(position.weight, 0.0) for position in positions),
        reverse=True,
    )
    max_weight = positive_weights[0] if positive_weights else 0.0
    return ConcentrationMetrics(
        max_weight=max_weight,
        top_5_weight=sum(positive_weights[:5]),
        herfindahl_index=sum(weight * weight for weight in positive_weights),
    )


def _industry_exposure(
    positions: Sequence[RiskPosition],
) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for position in positions:
        industry = position.industry or _UNCLASSIFIED_INDUSTRY
        exposure[industry] = exposure.get(industry, 0.0) + position.weight
    return dict(sorted(exposure.items()))


def _benchmark_active_weight(
    positions: Sequence[RiskPosition],
    benchmark_weights: Mapping[int, float],
) -> BenchmarkActiveWeight:
    portfolio_weights: dict[str, float] = {}
    for position in positions:
        instrument_key = str(position.instrument_id)
        portfolio_weights[instrument_key] = (
            portfolio_weights.get(instrument_key, 0.0) + position.weight
        )
    benchmark = {str(iid): float(weight) for iid, weight in benchmark_weights.items()}
    active_weights: dict[str, float] = {}
    for instrument_key in sorted(set(portfolio_weights) | set(benchmark)):
        active_weight = portfolio_weights.get(instrument_key, 0.0) - benchmark.get(
            instrument_key,
            0.0,
        )
        if active_weight != 0.0:
            active_weights[instrument_key] = active_weight
    return BenchmarkActiveWeight(
        total_abs_active_weight=sum(abs(weight) for weight in active_weights.values()),
        active_weights=active_weights,
    )


def _drawdown_metrics(
    nav_series: Sequence[tuple[str, float]],
) -> DrawdownMetrics:
    peak: float | None = None
    current_drawdown = 0.0
    max_drawdown = 0.0
    for _trade_date, nav in nav_series:
        if peak is None or nav > peak:
            peak = nav
        current_drawdown = 0.0 if peak <= 0.0 else nav / peak - 1.0
        max_drawdown = min(max_drawdown, current_drawdown)
    return DrawdownMetrics(
        current_drawdown=current_drawdown,
        max_drawdown=max_drawdown,
    )


def _tail_risk_metrics(
    nav_series: Sequence[tuple[str, float]],
) -> TailRiskMetrics:
    returns = _return_series(nav_series)
    if not returns:
        return TailRiskMetrics(var_95=0.0, cvar_95=0.0)
    sorted_returns = sorted(returns)
    tail_count = max(1, math.ceil(0.05 * len(sorted_returns)))
    tail = sorted_returns[:tail_count]
    return TailRiskMetrics(
        var_95=tail[-1],
        cvar_95=sum(tail) / len(tail),
    )


def _return_series(
    nav_series: Sequence[tuple[str, float]],
) -> list[float]:
    returns: list[float] = []
    previous_nav: float | None = None
    for _trade_date, nav in nav_series:
        if previous_nav is not None and previous_nav > 0.0:
            returns.append(nav / previous_nav - 1.0)
        previous_nav = nav
    return returns


def _stress_scenario_returns(
    positions: Sequence[RiskPosition],
    stress_scenarios: Sequence[StressScenario],
) -> dict[str, float]:
    scenario_returns: dict[str, float] = {}
    for scenario in stress_scenarios:
        stressed_return = 0.0
        for position in positions:
            industry = position.industry or _UNCLASSIFIED_INDUSTRY
            industry_shock = scenario.industry_shocks.get(industry, 0.0)
            stressed_return += position.weight * (
                scenario.market_shock + industry_shock
            )
        scenario_returns[scenario.name] = stressed_return
    return scenario_returns
