"""Pure research return statistics; production first-NAV statistics stay separate."""

import math
from collections.abc import Sequence
from statistics import stdev

from ditto_analysis.experiments.metric_schema import (
    ResearchMetricId,
    ResearchMetricValue,
)

_TRADING_DAYS_PER_YEAR = 252
_MIN_RETURN_OBSERVATIONS = 2


def return_statistics(
    returns: Sequence[float],
    navs: Sequence[float],
    *,
    initial_capital: float,
) -> dict[ResearchMetricId, ResearchMetricValue | str]:
    """
    Compute already-validated, nonempty research evidence without I/O.

    Returns include the first NAV relative to initial capital, not first NAV
    inception. Return/drawdown are percentages; Sharpe/Calmar are dimensionless.
    NAV is net of execution costs. Sharpe uses sample deviation, zero risk-free
    rate and 252 sessions; Calmar uses geometric annualization. A string is the
    existing not_evaluated reason, never a numeric zero placeholder.
    """
    growth = math.prod(1.0 + item for item in returns)
    peak, worst = initial_capital, 0.0
    for nav in navs:
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1.0)
    max_drawdown = worst * 100.0
    result: dict[ResearchMetricId, ResearchMetricValue | str] = {
        ResearchMetricId.NET_RETURN: ResearchMetricValue(
            ResearchMetricId.NET_RETURN, (growth - 1.0) * 100.0
        ),
        ResearchMetricId.MAX_DRAWDOWN: ResearchMetricValue(
            ResearchMetricId.MAX_DRAWDOWN, max_drawdown
        ),
    }
    volatility = stdev(returns) if len(returns) >= _MIN_RETURN_OBSERVATIONS else 0.0
    result[ResearchMetricId.SHARPE_RATIO] = (
        "insufficient_daily_return_evidence"
        if len(returns) < _MIN_RETURN_OBSERVATIONS
        else "zero_return_volatility"
        if volatility == 0.0
        else ResearchMetricValue(
            ResearchMetricId.SHARPE_RATIO,
            sum(returns)
            / len(returns)
            / volatility
            * math.sqrt(_TRADING_DAYS_PER_YEAR),
        )
    )
    result[ResearchMetricId.CALMAR_RATIO] = (
        "zero_max_drawdown"
        if max_drawdown == 0.0
        else ResearchMetricValue(
            ResearchMetricId.CALMAR_RATIO,
            ((growth ** (_TRADING_DAYS_PER_YEAR / len(returns))) - 1.0)
            * 100.0
            / abs(max_drawdown),
        )
    )
    return result


def daily_returns(initial_capital: float, navs: Sequence[float]) -> tuple[float, ...]:
    """Include initial capital to first NAV for validated research inputs."""
    result: list[float] = []
    prior = initial_capital
    for nav in navs:
        result.append(nav / prior - 1.0)
        prior = nav
    return tuple(result)


def execution_statistics(
    navs: Sequence[float],
    *,
    initial_capital: float,
    fill_notional: float,
    explicit_cost: float,
) -> dict[ResearchMetricId, ResearchMetricValue]:
    """Project validated gross fill notional and fees/absolute slippage totals."""
    average_nav = sum(navs) / len(navs)
    return {
        ResearchMetricId.TURNOVER: ResearchMetricValue(
            ResearchMetricId.TURNOVER, fill_notional / average_nav
        ),
        ResearchMetricId.COST_DRAG: ResearchMetricValue(
            ResearchMetricId.COST_DRAG, explicit_cost / initial_capital * 100.0
        ),
    }
