"""Research statistics preserve the initial-capital contract and honest gaps."""

import pytest
from ditto_analysis.experiments.metric_schema import (
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.statistics import return_statistics


def test_initial_capital_loss_is_retained_in_return_and_drawdown() -> None:
    metrics = return_statistics((-0.1, 0.1), (90.0, 99.0), initial_capital=100.0)
    net = metrics[ResearchMetricId.NET_RETURN]
    drawdown = metrics[ResearchMetricId.MAX_DRAWDOWN]
    sharpe = metrics[ResearchMetricId.SHARPE_RATIO]
    assert isinstance(net, ResearchMetricValue)
    assert net.value == pytest.approx(-1.0)
    assert isinstance(drawdown, ResearchMetricValue)
    assert drawdown.value == pytest.approx(-10.0)
    assert isinstance(sharpe, ResearchMetricValue)
    assert sharpe.value == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("returns", "navs", "sharpe_reason"),
    [
        ((0.0, 0.0), (100.0, 100.0), "zero_return_volatility"),
        ((0.1,), (110.0,), "insufficient_daily_return_evidence"),
    ],
)
def test_unavailable_ratios_remain_reasons(returns, navs, sharpe_reason) -> None:
    metrics = return_statistics(returns, navs, initial_capital=100.0)
    assert metrics[ResearchMetricId.SHARPE_RATIO] == sharpe_reason
    assert metrics[ResearchMetricId.CALMAR_RATIO] == "zero_max_drawdown"


def test_research_daily_returns_and_cost_units() -> None:
    from ditto_analysis.experiments.statistics import (
        daily_returns,
        execution_statistics,
    )

    assert daily_returns(100.0, (90.0, 99.0)) == pytest.approx((-0.1, 0.1))
    result = execution_statistics(
        (100.0, 100.0), initial_capital=100.0, fill_notional=40.0, explicit_cost=3.5
    )
    assert result[ResearchMetricId.TURNOVER].value == 0.4
    assert result[ResearchMetricId.COST_DRAG].value == pytest.approx(3.5)


def test_sample_sharpe_and_geometric_calmar() -> None:
    result = return_statistics((-0.1, 0.0), (90.0, 90.0), initial_capital=100.0)
    sharpe, calmar = (
        result[ResearchMetricId.SHARPE_RATIO],
        result[ResearchMetricId.CALMAR_RATIO],
    )
    assert isinstance(sharpe, ResearchMetricValue)
    assert sharpe.value == pytest.approx(-11.2249721603)
    assert isinstance(calmar, ResearchMetricValue)
    assert calmar.value == pytest.approx(-9.9999828385)
