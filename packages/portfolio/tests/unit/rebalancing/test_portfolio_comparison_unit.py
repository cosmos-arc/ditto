"""Tests for portfolio comparison module."""

from __future__ import annotations

import pytest
from ditto_backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)
from ditto_portfolio.rebalancing.comparison import (
    MetricsDelta,
    StrategyComparisonReport,
    compare_reports,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alpha_stats(
    *,
    annualized_return: float = 0.0,
    annualized_volatility: float = 0.0,
    sharpe_ratio: float = 0.0,
    sortino_ratio: float = 0.0,
    max_drawdown: float = 0.0,
    max_drawdown_duration_days: int = 0,
    calmar_ratio: float = 0.0,
    total_turnover: float = 0.0,
    avg_turnover_per_rebalance: float = 0.0,
    total_fees: float = 0.0,
    net_return_after_cost: float = 0.0,
    cost_drag: float = 0.0,
) -> AlphaStatistics:
    """Build an AlphaStatistics with only the fields relevant to comparison."""
    return AlphaStatistics(
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown=max_drawdown,
        max_drawdown_duration_days=max_drawdown_duration_days,
        calmar_ratio=calmar_ratio,
        information_ratio=None,
        tracking_error=None,
        beta=None,
        alpha_annualized=None,
        total_turnover=total_turnover,
        avg_turnover_per_rebalance=avg_turnover_per_rebalance,
        total_fees=total_fees,
        net_return_after_cost=net_return_after_cost,
        cost_drag=cost_drag,
    )


_EMPTY_AGG = AggregatedTradeStatistics(
    total_trades=0,
    long_trades=0,
    short_trades=0,
    win_trades=0,
    loss_trades=0,
    win_rate=0.0,
    profit_factor=0.0,
    avg_win=0.0,
    avg_loss=0.0,
    avg_win_loss_ratio=0.0,
    max_consecutive_wins=0,
    max_consecutive_losses=0,
    avg_holding_days=0.0,
    median_holding_days=0.0,
    best_trade=0.0,
    worst_trade=0.0,
    avg_trade_return_pct=0.0,
)


def _make_backtest_report(
    run_id: str = "run-1",
    *,
    final_nav: float = 1_000_000.0,
    total_trades: int = 0,
    alpha: AlphaStatistics | None = None,
) -> BacktestReport:
    """Build a BacktestReport with minimal required fields."""
    return BacktestReport(
        run_id=run_id,
        period=("2025-01-01", "2025-12-31"),
        initial_cash=1_000_000.0,
        final_nav=final_nav,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=_EMPTY_AGG,
        alpha_stats=alpha if alpha is not None else _make_alpha_stats(),
        nav_series=(),
        trade_log=(),
        fill_log=(),
        risk_log=(),
        pre_trade_log=(),
    )


# ---------------------------------------------------------------------------
# TestMetricsDelta
# ---------------------------------------------------------------------------


class TestMetricsDelta:
    def test_frozen_immutability(self) -> None:
        delta = MetricsDelta(
            annualized_return=1.0,
            sharpe_ratio=0.5,
            sortino_ratio=0.3,
            max_drawdown=-0.1,
            total_turnover=0.2,
            total_fees=10.0,
            cost_drag=0.05,
            final_nav=100.0,
            total_trades=5,
        )
        with pytest.raises(AttributeError):
            delta.annualized_return = 2.0  # type: ignore[misc]

    def test_default_construction(self) -> None:
        delta = MetricsDelta(
            annualized_return=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            total_turnover=0.0,
            total_fees=0.0,
            cost_drag=0.0,
            final_nav=0.0,
            total_trades=0,
        )
        assert delta.annualized_return == pytest.approx(0.0)
        assert delta.total_trades == 0


# ---------------------------------------------------------------------------
# TestStrategyComparisonReport
# ---------------------------------------------------------------------------


class TestStrategyComparisonReport:
    def test_frozen_immutability(self) -> None:
        delta = MetricsDelta(
            annualized_return=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            total_turnover=0.0,
            total_fees=0.0,
            cost_drag=0.0,
            final_nav=0.0,
            total_trades=0,
        )
        report = StrategyComparisonReport(
            baseline_run_id="run-1",
            compare_run_id="run-2",
            metrics_delta=delta,
            improved=(),
            degraded=(),
        )
        with pytest.raises(AttributeError):
            report.baseline_run_id = "run-x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestCompareReports
# ---------------------------------------------------------------------------


class TestCompareReports:
    def test_same_reports_zero_delta(self) -> None:
        """Same report for both args → all deltas 0, improved/degraded empty."""
        report = _make_backtest_report(
            run_id="run-1",
            final_nav=1_000_000.0,
            total_trades=10,
            alpha=_make_alpha_stats(
                annualized_return=10.0,
                sharpe_ratio=1.5,
                sortino_ratio=2.0,
                max_drawdown=-5.0,
                total_turnover=3.0,
                total_fees=100.0,
                cost_drag=0.5,
            ),
        )
        # Use the same report for both baseline and compare
        agg_same = AggregatedTradeStatistics(
            total_trades=10,
            long_trades=5,
            short_trades=5,
            win_trades=6,
            loss_trades=4,
            win_rate=60.0,
            profit_factor=1.5,
            avg_win=200.0,
            avg_loss=100.0,
            avg_win_loss_ratio=2.0,
            max_consecutive_wins=3,
            max_consecutive_losses=2,
            avg_holding_days=5.0,
            median_holding_days=4.0,
            best_trade=500.0,
            worst_trade=-200.0,
            avg_trade_return_pct=1.5,
        )
        report_with_trades = BacktestReport(
            run_id=report.run_id,
            period=report.period,
            initial_cash=report.initial_cash,
            final_nav=report.final_nav,
            trade_stats=(),
            portfolio_stats=(),
            aggregated_trade_stats=agg_same,
            alpha_stats=report.alpha_stats,
            nav_series=(),
            trade_log=(),
            fill_log=(),
            risk_log=(),
            pre_trade_log=(),
        )

        result = compare_reports(report_with_trades, report_with_trades)

        assert result.baseline_run_id == "run-1"
        assert result.compare_run_id == "run-1"
        assert result.metrics_delta.annualized_return == pytest.approx(0.0)
        assert result.metrics_delta.sharpe_ratio == pytest.approx(0.0)
        assert result.metrics_delta.sortino_ratio == pytest.approx(0.0)
        assert result.metrics_delta.max_drawdown == pytest.approx(0.0)
        assert result.metrics_delta.total_turnover == pytest.approx(0.0)
        assert result.metrics_delta.total_fees == pytest.approx(0.0)
        assert result.metrics_delta.cost_drag == pytest.approx(0.0)
        assert result.metrics_delta.final_nav == pytest.approx(0.0)
        assert result.metrics_delta.total_trades == 0
        assert result.improved == ()
        assert result.degraded == ()

    def test_higher_return_improved(self) -> None:
        """Compare has higher annualized return → 'annualized_return' in improved."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(annualized_return=10.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(annualized_return=15.0),
        )
        result = compare_reports(baseline, compare)

        assert "annualized_return" in result.improved
        assert "annualized_return" not in result.degraded
        assert result.metrics_delta.annualized_return == pytest.approx(5.0)

    def test_higher_fees_degraded(self) -> None:
        """Compare has higher total_fees → 'total_fees' in degraded."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(total_fees=100.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(total_fees=200.0),
        )
        result = compare_reports(baseline, compare)

        assert "total_fees" in result.degraded
        assert "total_fees" not in result.improved
        assert result.metrics_delta.total_fees == pytest.approx(100.0)

    def test_max_drawdown_improvement(self) -> None:
        """Compare has less negative max_drawdown → 'max_drawdown' in improved."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(max_drawdown=-20.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(max_drawdown=-10.0),
        )
        result = compare_reports(baseline, compare)

        # delta = -10.0 - (-20.0) = 10.0 (positive = improved)
        assert result.metrics_delta.max_drawdown == pytest.approx(10.0)
        assert "max_drawdown" in result.improved
        assert "max_drawdown" not in result.degraded

    def test_max_drawdown_worsened(self) -> None:
        """Compare has more negative max_drawdown → 'max_drawdown' in degraded."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(max_drawdown=-10.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(max_drawdown=-25.0),
        )
        result = compare_reports(baseline, compare)

        # delta = -25.0 - (-10.0) = -15.0 (negative = degraded)
        assert result.metrics_delta.max_drawdown == pytest.approx(-15.0)
        assert "max_drawdown" in result.degraded
        assert "max_drawdown" not in result.improved

    def test_mixed_improvements(self) -> None:
        """Mix of improved and degraded metrics across all dimensions."""
        baseline = _make_backtest_report(
            run_id="baseline",
            final_nav=1_000_000.0,
            alpha=_make_alpha_stats(
                annualized_return=10.0,
                sharpe_ratio=1.0,
                sortino_ratio=1.5,
                max_drawdown=-15.0,
                total_turnover=5.0,
                total_fees=500.0,
                cost_drag=1.0,
            ),
        )
        # Higher return, higher sharpe, higher sortino, less DD (improved)
        # Higher turnover, higher fees, higher cost_drag, lower nav (degraded)
        compare = _make_backtest_report(
            run_id="compare",
            final_nav=950_000.0,
            alpha=_make_alpha_stats(
                annualized_return=15.0,
                sharpe_ratio=1.5,
                sortino_ratio=2.0,
                max_drawdown=-8.0,
                total_turnover=8.0,
                total_fees=800.0,
                cost_drag=2.0,
            ),
        )
        result = compare_reports(baseline, compare)

        # Improved metrics (higher is better)
        assert "annualized_return" in result.improved
        assert "sharpe_ratio" in result.improved
        assert "sortino_ratio" in result.improved
        assert "max_drawdown" in result.improved

        # Degraded metrics (lower is better)
        assert "total_turnover" in result.degraded
        assert "total_fees" in result.degraded
        assert "cost_drag" in result.degraded

        # final_nav: higher is better → compare is lower → degraded
        assert "final_nav" in result.degraded

        # total_trades is neutral — never in improved or degraded
        assert "total_trades" not in result.improved
        assert "total_trades" not in result.degraded

        # Delta values
        assert result.metrics_delta.annualized_return == pytest.approx(5.0)
        assert result.metrics_delta.sharpe_ratio == pytest.approx(0.5)
        assert result.metrics_delta.sortino_ratio == pytest.approx(0.5)
        assert result.metrics_delta.max_drawdown == pytest.approx(7.0)
        assert result.metrics_delta.total_turnover == pytest.approx(3.0)
        assert result.metrics_delta.total_fees == pytest.approx(300.0)
        assert result.metrics_delta.cost_drag == pytest.approx(1.0)
        assert result.metrics_delta.final_nav == pytest.approx(-50_000.0)

    def test_run_ids_preserved(self) -> None:
        """Baseline and compare run IDs are correctly captured."""
        baseline = _make_backtest_report(run_id="run-baseline")
        compare = _make_backtest_report(run_id="run-compare")
        result = compare_reports(baseline, compare)

        assert result.baseline_run_id == "run-baseline"
        assert result.compare_run_id == "run-compare"

    def test_higher_sharpe_improved(self) -> None:
        """Compare has higher sharpe_ratio → 'sharpe_ratio' in improved."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(sharpe_ratio=1.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(sharpe_ratio=2.0),
        )
        result = compare_reports(baseline, compare)

        assert "sharpe_ratio" in result.improved
        assert result.metrics_delta.sharpe_ratio == pytest.approx(1.0)

    def test_higher_sortino_improved(self) -> None:
        """Compare has higher sortino_ratio → 'sortino_ratio' in improved."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(sortino_ratio=1.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(sortino_ratio=2.5),
        )
        result = compare_reports(baseline, compare)

        assert "sortino_ratio" in result.improved
        assert result.metrics_delta.sortino_ratio == pytest.approx(1.5)

    def test_lower_turnover_improved(self) -> None:
        """Compare has lower total_turnover → 'total_turnover' in improved."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(total_turnover=10.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(total_turnover=5.0),
        )
        result = compare_reports(baseline, compare)

        assert "total_turnover" in result.improved
        assert result.metrics_delta.total_turnover == pytest.approx(-5.0)

    def test_lower_cost_drag_improved(self) -> None:
        """Compare has lower cost_drag → 'cost_drag' in improved."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(cost_drag=2.0),
        )
        compare = _make_backtest_report(
            run_id="run-2",
            alpha=_make_alpha_stats(cost_drag=0.5),
        )
        result = compare_reports(baseline, compare)

        assert "cost_drag" in result.improved
        assert result.metrics_delta.cost_drag == pytest.approx(-1.5)

    def test_higher_final_nav_improved(self) -> None:
        """Compare has higher final_nav → 'final_nav' in improved."""
        baseline = _make_backtest_report(run_id="run-1", final_nav=1_000_000.0)
        compare = _make_backtest_report(run_id="run-2", final_nav=1_100_000.0)
        result = compare_reports(baseline, compare)

        assert "final_nav" in result.improved
        assert result.metrics_delta.final_nav == pytest.approx(100_000.0)

    def test_total_trades_delta_neutral(self) -> None:
        """total_trades delta is computed but not in improved/degraded."""
        baseline = _make_backtest_report(
            run_id="run-1",
            alpha=_make_alpha_stats(),
        )
        # Manually set different total_trades via aggregated_trade_stats
        agg_baseline = AggregatedTradeStatistics(
            total_trades=10,
            long_trades=5,
            short_trades=5,
            win_trades=6,
            loss_trades=4,
            win_rate=60.0,
            profit_factor=1.5,
            avg_win=200.0,
            avg_loss=100.0,
            avg_win_loss_ratio=2.0,
            max_consecutive_wins=3,
            max_consecutive_losses=2,
            avg_holding_days=5.0,
            median_holding_days=4.0,
            best_trade=500.0,
            worst_trade=-200.0,
            avg_trade_return_pct=1.5,
        )
        agg_compare = AggregatedTradeStatistics(
            total_trades=20,
            long_trades=10,
            short_trades=10,
            win_trades=12,
            loss_trades=8,
            win_rate=60.0,
            profit_factor=1.5,
            avg_win=200.0,
            avg_loss=100.0,
            avg_win_loss_ratio=2.0,
            max_consecutive_wins=3,
            max_consecutive_losses=2,
            avg_holding_days=5.0,
            median_holding_days=4.0,
            best_trade=500.0,
            worst_trade=-200.0,
            avg_trade_return_pct=1.5,
        )
        report_base = BacktestReport(
            run_id="run-1",
            period=("2025-01-01", "2025-12-31"),
            initial_cash=1_000_000.0,
            final_nav=1_000_000.0,
            trade_stats=(),
            portfolio_stats=(),
            aggregated_trade_stats=agg_baseline,
            alpha_stats=baseline.alpha_stats,
            nav_series=(),
            trade_log=(),
            fill_log=(),
            risk_log=(),
            pre_trade_log=(),
        )
        report_cmp = BacktestReport(
            run_id="run-2",
            period=("2025-01-01", "2025-12-31"),
            initial_cash=1_000_000.0,
            final_nav=1_000_000.0,
            trade_stats=(),
            portfolio_stats=(),
            aggregated_trade_stats=agg_compare,
            alpha_stats=baseline.alpha_stats,
            nav_series=(),
            trade_log=(),
            fill_log=(),
            risk_log=(),
            pre_trade_log=(),
        )
        result = compare_reports(report_base, report_cmp)

        assert result.metrics_delta.total_trades == 10
        assert "total_trades" not in result.improved
        assert "total_trades" not in result.degraded
