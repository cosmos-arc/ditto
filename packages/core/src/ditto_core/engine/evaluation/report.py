"""Factor evaluation report dataclasses."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FactorEvaluationReport",
    "ICSummary",
    "LongShortResult",
]


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
class LongShortResult:
    """
    Long-short portfolio risk metrics.

    Attributes:
        annual_return: Annualized return.
        annual_volatility: Annualized volatility.
        sharpe: Sharpe ratio = return / vol (equals IR_2 when R_f = 0).
        portfolio_ir: Factor Portfolio IR = (return - R_f) / vol.
        sortino: Sortino ratio = return / downside_dev.
        max_drawdown: Maximum drawdown.

    """

    annual_return: float
    annual_volatility: float
    sharpe: float
    portfolio_ir: float
    sortino: float
    max_drawdown: float


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
        sub_period_ic: {period_label: ICSummary}.
        n_observations: Total number of cross-section observations.
        n_dates: Number of trading dates in the evaluation window.
        computed_at: ISO timestamp of when the report was generated.

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

    # Sub-period stability
    sub_period_ic: dict[str, ICSummary]

    # Metadata
    n_observations: int
    n_dates: int
    computed_at: str
