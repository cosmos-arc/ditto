"""BacktestReportRenderer 单元测试 — HTML 渲染与格式化验证."""

from __future__ import annotations

from ditto_engine.backtest.report_renderer import BacktestReportRenderer
from ditto_engine.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)

_ALPHA_DEFAULTS: dict[str, float | None | int] = {
    "annualized_return": 15.30,
    "annualized_volatility": 12.50,
    "sharpe_ratio": 1.22,
    "sortino_ratio": 1.65,
    "max_drawdown": -8.45,
    "max_drawdown_duration_days": 15,
    "calmar_ratio": 1.81,
    "information_ratio": None,
    "tracking_error": None,
    "beta": None,
    "alpha_annualized": None,
    "total_turnover": 3.20,
    "avg_turnover_per_rebalance": 0.80,
    "total_fees": 120.50,
    "net_return_after_cost": 14.90,
    "cost_drag": 0.40,
}


def _make_alpha_stats(**overrides: float | None | int) -> AlphaStatistics:
    return AlphaStatistics(**{**_ALPHA_DEFAULTS, **overrides})


_TRADE_DEFAULTS: dict[str, float | int] = {
    "total_trades": 42,
    "long_trades": 28,
    "short_trades": 14,
    "win_trades": 26,
    "loss_trades": 16,
    "win_rate": 61.9,
    "profit_factor": 1.85,
    "avg_win": 3500.00,
    "avg_loss": 1800.00,
    "avg_win_loss_ratio": 1.94,
    "max_consecutive_wins": 6,
    "max_consecutive_losses": 3,
    "avg_holding_days": 5.2,
    "median_holding_days": 4.0,
    "best_trade": 8200.00,
    "worst_trade": -4500.00,
    "avg_trade_return_pct": 2.15,
}


def _make_trade_stats(**overrides: float | int) -> AggregatedTradeStatistics:
    return AggregatedTradeStatistics(**{**_TRADE_DEFAULTS, **overrides})


def _make_report(**overrides: object) -> BacktestReport:
    defaults: dict[str, object] = {
        "run_id": "run-20260422-abc",
        "period": ("2025-01-02", "2025-12-31"),
        "initial_cash": 1_000_000.0,
        "final_nav": 1_153_000.0,
        "trade_stats": (),
        "portfolio_stats": (),
        "aggregated_trade_stats": _make_trade_stats(),
        "alpha_stats": _make_alpha_stats(),
        "nav_series": (),
        "trade_log": (),
        "fill_log": (),
    }
    defaults.update(overrides)
    return BacktestReport(**defaults)


class TestFmt:
    """_fmt 静态方法 — 正负零及大值格式化."""

    def test_positive_value(self) -> None:
        assert BacktestReportRenderer._fmt(1.23) == "+1.23"

    def test_negative_value(self) -> None:
        assert BacktestReportRenderer._fmt(-1.23) == "-1.23"

    def test_zero_value(self) -> None:
        assert BacktestReportRenderer._fmt(0.0) == "+0.00"

    def test_large_value(self) -> None:
        assert BacktestReportRenderer._fmt(999_999.99) == "+999999.99"


class TestRender:
    """render() — HTML 结构与内容验证."""

    def test_render_returns_valid_html(self) -> None:
        report = _make_report()
        html = BacktestReportRenderer().render(report)
        assert "<!DOCTYPE html>" in html
        assert "container" in html
        assert "metric" in html

    def test_render_no_unsubstituted_variables(self) -> None:
        report = _make_report()
        html = BacktestReportRenderer().render(report)
        assert "$" not in html

    def test_render_contains_report_metadata(self) -> None:
        report = _make_report()
        html = BacktestReportRenderer().render(report)
        assert "run-20260422-abc" in html
        assert "2025-01-02" in html
        assert "2025-12-31" in html
        assert "1,000,000.00" in html
        assert "1,153,000.0000" in html
