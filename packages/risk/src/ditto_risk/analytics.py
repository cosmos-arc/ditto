"""R4 tail-risk diagnostics and versioned operational stress catalog."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

__all__ = [
    "R4_STRESS_CATALOG",
    "StressCatalog",
    "StressScenarioDefinition",
    "StressTestInput",
    "StressTestReport",
    "TailRiskReport",
    "compute_stress_tests",
    "compute_tail_risk",
]

_MINIMUM_OBSERVATIONS = 60
_DEFAULT_MONTE_CARLO_SAMPLES = 10_000
_MINIMUM_MONTE_CARLO_SAMPLES = 100


@dataclass(frozen=True)
class TailRiskReport:
    """Positive-loss historical headline and parametric/MC diagnostics."""

    confidence_level: float
    observation_count: int
    historical_var: float
    historical_es: float
    parametric_var: float
    monte_carlo_var: float
    monte_carlo_seed: int
    loss_sign_convention: str = "positive_loss"


@dataclass(frozen=True)
class StressScenarioDefinition:
    """One immutable historical period or hypothetical shock recipe."""

    scenario_id: str
    kind: str
    start_date: str | None = None
    end_date: str | None = None
    market_shock: float | None = None
    largest_industry_shock: float | None = None
    liquidity_cost_multiplier: float | None = None
    style_sigma_shock: float | None = None


@dataclass(frozen=True)
class StressCatalog:
    """Versioned deterministic set of required R4 stress scenarios."""

    version: str
    scenarios: tuple[StressScenarioDefinition, ...]


@dataclass(frozen=True)
class StressTestInput:
    """Portfolio-level inputs for every versioned R4 stress recipe."""

    historical_returns: Mapping[str, tuple[float, ...]]
    market_exposure: float
    industry_weights: Mapping[str, float]
    base_liquidity_cost: float
    style_one_sigma_losses: Mapping[str, float] | None


@dataclass(frozen=True)
class StressTestReport:
    """Positive losses and scenarios unavailable without genuine exposure data."""

    catalog_version: str
    losses: Mapping[str, float]
    unavailable_scenarios: tuple[str, ...] = ()


R4_STRESS_CATALOG = StressCatalog(
    version="r4-v1",
    scenarios=(
        StressScenarioDefinition(
            scenario_id="historical:2015-equity-crash",
            kind="historical",
            start_date="2015-06-12",
            end_date="2015-08-26",
        ),
        StressScenarioDefinition(
            scenario_id="historical:2020-covid",
            kind="historical",
            start_date="2020-02-03",
            end_date="2020-03-23",
        ),
        StressScenarioDefinition(
            scenario_id="historical:2024-small-cap-liquidity",
            kind="historical",
            start_date="2024-01-02",
            end_date="2024-02-05",
        ),
        StressScenarioDefinition(
            scenario_id="hypothetical:market-minus-10pct",
            kind="hypothetical",
            market_shock=-0.10,
        ),
        StressScenarioDefinition(
            scenario_id="hypothetical:largest-industry-minus-20pct",
            kind="hypothetical",
            largest_industry_shock=-0.20,
        ),
        StressScenarioDefinition(
            scenario_id="hypothetical:liquidity-cost-x2",
            kind="hypothetical",
            liquidity_cost_multiplier=2.0,
        ),
        StressScenarioDefinition(
            scenario_id="hypothetical:style-factor-plus-minus-3sigma",
            kind="hypothetical",
            style_sigma_shock=3.0,
        ),
    ),
)


def compute_stress_tests(
    input_: StressTestInput,
    *,
    catalog: StressCatalog = R4_STRESS_CATALOG,
) -> StressTestReport:
    """Evaluate the versioned R4 catalog without inventing missing factor data."""
    _validate_stress_input(input_, catalog)
    losses: dict[str, float] = {}
    unavailable: list[str] = []
    for scenario in catalog.scenarios:
        if scenario.kind == "historical":
            returns = input_.historical_returns[scenario.scenario_id]
            compounded_return = math.prod(1.0 + value for value in returns) - 1.0
            losses[scenario.scenario_id] = max(0.0, -compounded_return)
        elif scenario.market_shock is not None:
            losses[scenario.scenario_id] = max(
                0.0,
                -scenario.market_shock * input_.market_exposure,
            )
        elif scenario.largest_industry_shock is not None:
            largest_weight = max(input_.industry_weights.values(), default=0.0)
            losses[scenario.scenario_id] = max(
                0.0,
                -scenario.largest_industry_shock * largest_weight,
            )
        elif scenario.liquidity_cost_multiplier is not None:
            losses[scenario.scenario_id] = (
                scenario.liquidity_cost_multiplier * input_.base_liquidity_cost
            )
        elif scenario.style_sigma_shock is not None:
            if input_.style_one_sigma_losses is None:
                unavailable.append(scenario.scenario_id)
            else:
                losses[scenario.scenario_id] = scenario.style_sigma_shock * sum(
                    abs(value) for value in input_.style_one_sigma_losses.values()
                )
    return StressTestReport(
        catalog_version=catalog.version,
        losses=losses,
        unavailable_scenarios=tuple(unavailable),
    )


def _validate_stress_input(
    input_: StressTestInput,
    catalog: StressCatalog,
) -> None:
    historical_ids = tuple(
        scenario.scenario_id
        for scenario in catalog.scenarios
        if scenario.kind == "historical"
    )
    for scenario_id in historical_ids:
        returns = input_.historical_returns.get(scenario_id)
        if not returns:
            raise ValueError(f"stress returns missing for {scenario_id}")
        if not all(math.isfinite(value) and value > -1.0 for value in returns):
            raise ValueError(f"stress returns invalid for {scenario_id}")
    if not math.isfinite(input_.market_exposure) or input_.market_exposure < 0.0:
        raise ValueError("market_exposure must be finite and non-negative")
    if not math.isfinite(input_.base_liquidity_cost) or input_.base_liquidity_cost < 0:
        raise ValueError("base_liquidity_cost must be finite and non-negative")
    if not all(
        name.strip() and math.isfinite(weight) and weight >= 0.0
        for name, weight in input_.industry_weights.items()
    ):
        raise ValueError("industry weights must be named, finite, and non-negative")
    if input_.style_one_sigma_losses is not None and not all(
        name.strip() and math.isfinite(value)
        for name, value in input_.style_one_sigma_losses.items()
    ):
        raise ValueError("style stress inputs must be named and finite")


def compute_tail_risk(
    returns: tuple[float, ...],
    *,
    confidence_level: float = 0.99,
    monte_carlo_seed: int = 20260804,
    monte_carlo_samples: int = _DEFAULT_MONTE_CARLO_SAMPLES,
) -> TailRiskReport:
    """Compute one-day positive-loss tail metrics without hidden randomness."""
    if len(returns) < _MINIMUM_OBSERVATIONS:
        raise ValueError(
            f"tail risk requires at least {_MINIMUM_OBSERVATIONS} observations"
        )
    if not all(math.isfinite(value) for value in returns):
        raise ValueError("tail risk returns must be finite")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be in (0, 1)")
    if monte_carlo_samples < _MINIMUM_MONTE_CARLO_SAMPLES:
        raise ValueError("monte_carlo_samples must be at least 100")
    losses = sorted(-value for value in returns)
    var_index = math.ceil(confidence_level * (len(losses) - 1))
    historical_var = max(0.0, losses[var_index])
    tail = [loss for loss in losses if loss >= historical_var]
    historical_es = max(historical_var, statistics.fmean(tail))
    mean = statistics.fmean(returns)
    standard_deviation = statistics.stdev(returns)
    normal_quantile = statistics.NormalDist().inv_cdf(confidence_level)
    parametric_var = max(0.0, -mean + normal_quantile * standard_deviation)
    generator = np.random.default_rng(monte_carlo_seed)
    simulated_losses = np.sort(
        -generator.normal(mean, standard_deviation, monte_carlo_samples)
    )
    monte_carlo_index = math.ceil(confidence_level * (len(simulated_losses) - 1))
    return TailRiskReport(
        confidence_level=confidence_level,
        observation_count=len(returns),
        historical_var=historical_var,
        historical_es=historical_es,
        parametric_var=parametric_var,
        monte_carlo_var=max(0.0, float(simulated_losses[monte_carlo_index])),
        monte_carlo_seed=monte_carlo_seed,
    )
