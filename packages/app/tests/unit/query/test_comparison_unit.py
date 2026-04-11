"""Tests for ComparisonQueryFacade — 回测 vs 实际对比查询门面."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.query.comparison import ComparisonMetrics, ComparisonQueryFacade
from ditto_app.types import ActualPositionSnapshot, ManualExecutionFill


def _make_backtest_facade(
    report: dict[str, object] | None = None,
    nav_rows: list[dict[str, object]] | None = None,
) -> MagicMock:
    """构造 mock BacktestQueryFacade."""
    facade = MagicMock()
    facade.get_report.return_value = report
    if nav_rows is not None:
        facade.get_nav_series.return_value = nav_rows
    else:
        facade.get_nav_series.return_value = []
    return facade


def _make_actual_facade(
    fills: list[ManualExecutionFill] | None = None,
    positions: list[ActualPositionSnapshot] | None = None,
) -> MagicMock:
    """构造 mock PortfolioActualQueryFacade."""
    facade = MagicMock()
    facade.get_fills.return_value = fills or []
    facade.get_latest_positions.return_value = positions or []
    return facade


def _sample_report_dict() -> dict[str, object]:
    """构造样例回测报告 JSON dict."""
    return {
        "run_id": "run-001",
        "initial_cash": 1_000_000.0,
        "alpha_stats": {
            "annualized_return": 15.0,
            "sharpe_ratio": 1.5,
            "total_fees": 500.0,
        },
    }


def _sample_nav_rows() -> list[dict[str, object]]:
    """构造样例回测 NAV 序列."""
    return [
        {"trade_date": "2024-01-02", "nav": 1_000_000.0},
        {"trade_date": "2024-01-03", "nav": 1_005_000.0},
        {"trade_date": "2024-01-04", "nav": 1_010_000.0},
        {"trade_date": "2024-01-05", "nav": 1_008_000.0},
    ]


def _make_fill(
    fill_id: str = "fill-001",
    fee: float = 100.0,
) -> ManualExecutionFill:
    """构造测试用 ManualExecutionFill."""
    return ManualExecutionFill(
        fill_id=fill_id,
        intent_id="intent-001",
        strategy_id="strat-001",
        trade_date="2024-01-03",
        instrument_id=510300,
        direction="buy",
        quantity=1000,
        fill_price=4.0,
        fee=fee,
    )


# ========== get_comparison — 正常路径 ==========


class TestGetComparison:
    """ComparisonQueryFacade.get_comparison — 回测 vs 实际对比查询."""

    def test_returns_comparison_metrics_when_data_available(self) -> None:
        """正常路径: 回测报告 + NAV + 成交都可用时返回 ComparisonMetrics."""
        backtest_facade = _make_backtest_facade(
            report=_sample_report_dict(),
            nav_rows=_sample_nav_rows(),
        )
        actual_facade = _make_actual_facade(fills=[_make_fill()])
        facade = ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
        )

        result = facade.get_comparison(
            strategy_id="strat-001",
            run_id="run-001",
        )

        assert result is not None
        assert isinstance(result, ComparisonMetrics)
        # 回测指标来自报告 dict
        assert result.backtest_return == 15.0
        assert result.backtest_sharpe == 1.5
        assert result.backtest_total_cost == 500.0
        # 实际成本从 fills 累加
        assert result.actual_total_cost == 100.0

    def test_returns_none_when_report_missing(self) -> None:
        """回测报告不存在时返回 None."""
        backtest_facade = _make_backtest_facade(report=None)
        actual_facade = _make_actual_facade()
        facade = ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
        )

        result = facade.get_comparison(
            strategy_id="strat-001",
            run_id="run-001",
        )

        assert result is None

    def test_delegates_to_backtest_facade(self) -> None:
        """验证正确委托给 BacktestQueryFacade."""
        backtest_facade = _make_backtest_facade(
            report=_sample_report_dict(),
            nav_rows=_sample_nav_rows(),
        )
        actual_facade = _make_actual_facade()
        facade = ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
        )

        facade.get_comparison(strategy_id="strat-001", run_id="run-001")

        backtest_facade.get_report.assert_called_once_with("run-001")
        backtest_facade.get_nav_series.assert_called_once_with("run-001")

    def test_delegates_to_actual_facade(self) -> None:
        """验证正确委托给 PortfolioActualQueryFacade."""
        backtest_facade = _make_backtest_facade(
            report=_sample_report_dict(),
            nav_rows=_sample_nav_rows(),
        )
        actual_facade = _make_actual_facade(fills=[_make_fill()])
        facade = ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
        )

        facade.get_comparison(strategy_id="strat-001", run_id="run-001")

        actual_facade.get_fills.assert_called_once_with("strat-001")


# ========== get_comparison — 边界情况 ==========


class TestGetComparisonEdgeCases:
    """ComparisonQueryFacade.get_comparison — 边界情况."""

    def test_returns_zero_metrics_when_no_fills(self) -> None:
        """无成交记录时 actual_total_cost 为 0."""
        backtest_facade = _make_backtest_facade(
            report=_sample_report_dict(),
            nav_rows=_sample_nav_rows(),
        )
        actual_facade = _make_actual_facade(fills=[])
        facade = ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
        )

        result = facade.get_comparison(
            strategy_id="strat-001",
            run_id="run-001",
        )

        assert result is not None
        assert result.actual_total_cost == 0.0

    def test_returns_zero_metrics_when_no_nav(self) -> None:
        """无 NAV 序列时返回零值指标（不返回 None）."""
        backtest_facade = _make_backtest_facade(
            report=_sample_report_dict(),
            nav_rows=[],
        )
        actual_facade = _make_actual_facade()
        facade = ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
        )

        result = facade.get_comparison(
            strategy_id="strat-001",
            run_id="run-001",
        )

        assert result is not None
        assert result.actual_return == 0.0
        assert result.actual_sharpe == 0.0
        assert result.nav_correlation == 0.0
