"""ComparisonReport + PortfolioActualQueryFacade 单元测试 — 回测 vs 实际对比."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_app.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
)
from ditto_engine.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)

# ===========================================================================
# Test Fixtures
# ===========================================================================


def _make_alpha_stats(
    *,
    annualized_return: float = 10.0,
    sharpe_ratio: float = 1.5,
    total_fees: float = 500.0,
    net_return_after_cost: float = 9.5,
) -> AlphaStatistics:
    """构造测试用 AlphaStatistics."""
    return AlphaStatistics(
        annualized_return=annualized_return,
        annualized_volatility=12.0,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=2.0,
        max_drawdown=-5.0,
        max_drawdown_duration_days=10,
        calmar_ratio=2.0,
        information_ratio=None,
        tracking_error=None,
        beta=None,
        alpha_annualized=None,
        total_turnover=3.0,
        avg_turnover_per_rebalance=0.5,
        total_fees=total_fees,
        net_return_after_cost=net_return_after_cost,
        cost_drag=0.5,
    )


def _make_backtest_report(
    *,
    alpha_stats: AlphaStatistics | None = None,
    nav_series: tuple[tuple[str, float], ...] | None = None,
    initial_cash: float = 1_000_000.0,
    final_nav: float = 1_100_000.0,
) -> BacktestReport:
    """构造测试用 BacktestReport."""
    if alpha_stats is None:
        alpha_stats = _make_alpha_stats()
    if nav_series is None:
        nav_series = (
            ("2024-01-02", 1_000_000.0),
            ("2024-01-03", 1_010_000.0),
            ("2024-01-04", 1_020_000.0),
            ("2024-01-05", 1_030_000.0),
            ("2024-01-08", 1_040_000.0),
            ("2024-01-09", 1_050_000.0),
            ("2024-01-10", 1_060_000.0),
            ("2024-01-11", 1_070_000.0),
            ("2024-01-12", 1_080_000.0),
            ("2024-01-15", 1_090_000.0),
            ("2024-01-16", 1_100_000.0),
        )
    return BacktestReport(
        run_id="run-001",
        period=("2024-01-02", "2024-01-16"),
        initial_cash=initial_cash,
        final_nav=final_nav,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=AggregatedTradeStatistics(
            total_trades=5,
            long_trades=3,
            short_trades=2,
            win_trades=3,
            loss_trades=2,
            win_rate=60.0,
            profit_factor=1.5,
            avg_win=1000.0,
            avg_loss=500.0,
            avg_win_loss_ratio=2.0,
            max_consecutive_wins=2,
            max_consecutive_losses=1,
            avg_holding_days=3.0,
            median_holding_days=3.0,
            best_trade=2000.0,
            worst_trade=-800.0,
            avg_trade_return_pct=2.0,
        ),
        alpha_stats=alpha_stats,
        nav_series=nav_series,
        trade_log=(),
        fill_log=(),
    )


def _make_fill(
    *,
    fill_id: str = "fill-1",
    strategy_id: str = "strat-001",
    trade_date: str = "2024-01-10",
    instrument_id: int = 1,
    direction: str = "buy",
    quantity: int = 1000,
    fill_price: float = 1.5,
    fee: float = 10.0,
) -> ManualExecutionFill:
    """构造测试用 ManualExecutionFill."""
    return ManualExecutionFill(
        fill_id=fill_id,
        intent_id=f"intent-{fill_id}",
        strategy_id=strategy_id,
        trade_date=trade_date,
        instrument_id=instrument_id,
        direction=direction,
        quantity=quantity,
        fill_price=fill_price,
        fee=fee,
    )


def _make_snapshot(
    *,
    snapshot_id: str = "snap-1",
    strategy_id: str = "strat-001",
    snapshot_date: str = "2024-01-16",
    instrument_id: int = 1,
    quantity: int = 1000,
    available_quantity: int = 500,
    average_cost: float = 1.5,
    market_value: float = 1600.0,
    unrealized_pnl: float = 100.0,
    realized_pnl: float = 200.0,
    total_fees: float = 15.0,
) -> ActualPositionSnapshot:
    """构造测试用 ActualPositionSnapshot."""
    return ActualPositionSnapshot(
        snapshot_id=snapshot_id,
        strategy_id=strategy_id,
        snapshot_date=snapshot_date,
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=average_cost,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        total_fees=total_fees,
    )


def _make_mock_trade_service() -> MagicMock:
    """构造 mock TradeService."""
    service = MagicMock()
    service.list_positions.return_value = []
    service.list_fills.return_value = []
    service.get_latest_position.return_value = None
    return service


# ===========================================================================
# ComparisonMetrics — 数据类测试
# ===========================================================================


class TestComparisonMetrics:
    """ComparisonMetrics — 回测 vs 实际对比指标数据类."""

    def test_construction(self) -> None:
        """基本构造."""
        from ditto_app.query.comparison_math import ComparisonMetrics

        metrics = ComparisonMetrics(
            backtest_return=10.0,
            actual_return=8.0,
            return_diff=-2.0,
            return_diff_bps=-200.0,
            backtest_sharpe=1.5,
            actual_sharpe=1.2,
            backtest_total_cost=500.0,
            actual_total_cost=600.0,
            cost_drag_bps=10.0,
            nav_correlation=0.95,
            max_nav_diff_bps=50.0,
            avg_daily_tracking_error_bps=15.0,
        )
        assert metrics.backtest_return == 10.0
        assert metrics.actual_return == 8.0
        assert metrics.return_diff == -2.0
        assert metrics.return_diff_bps == -200.0

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        from ditto_app.query.comparison_math import ComparisonMetrics

        metrics = ComparisonMetrics(
            backtest_return=10.0,
            actual_return=8.0,
            return_diff=-2.0,
            return_diff_bps=-200.0,
            backtest_sharpe=1.5,
            actual_sharpe=1.2,
            backtest_total_cost=500.0,
            actual_total_cost=600.0,
            cost_drag_bps=10.0,
            nav_correlation=0.95,
            max_nav_diff_bps=50.0,
            avg_daily_tracking_error_bps=15.0,
        )
        with pytest.raises(AttributeError):
            metrics.backtest_return = 20.0  # type: ignore[misc]


# ===========================================================================
# compute_comparison — 核心计算函数测试
# ===========================================================================


class TestComputeComparison:
    """compute_comparison — 回测 vs 实际对比计算."""

    def test_basic_computation(self) -> None:
        """基本对比指标正确计算."""
        from ditto_app.process.execution.comparison import compute_comparison

        report = _make_backtest_report()
        fills = [
            _make_fill(fee=10.0),
            _make_fill(fill_id="fill-2", fee=15.0),
        ]
        actual_navs: list[tuple[str, float]] = [
            ("2024-01-02", 1_000_000.0),
            ("2024-01-03", 1_008_000.0),
            ("2024-01-04", 1_016_000.0),
            ("2024-01-05", 1_024_000.0),
            ("2024-01-08", 1_032_000.0),
            ("2024-01-09", 1_040_000.0),
            ("2024-01-10", 1_048_000.0),
            ("2024-01-11", 1_056_000.0),
            ("2024-01-12", 1_064_000.0),
            ("2024-01-15", 1_072_000.0),
            ("2024-01-16", 1_080_000.0),
        ]

        result = compute_comparison(
            backtest_report=report,
            actual_fills=fills,
            actual_navs=actual_navs,
            initial_cash=1_000_000.0,
        )

        # 回测收益率来自 alpha_stats.annualized_return
        assert result.backtest_return == 10.0
        # 实际收益率从 navs 计算: (1_080_000 - 1_000_000) / 1_000_000 * 100 = 8.0%
        assert result.actual_return == pytest.approx(8.0, abs=0.01)
        # 偏差 = actual - backtest
        assert result.return_diff == pytest.approx(-2.0, abs=0.01)
        # 基点偏差
        assert result.return_diff_bps == pytest.approx(-200.0, abs=1.0)
        # 回测 Sharpe
        assert result.backtest_sharpe == 1.5
        # 实际 Sharpe 需从 navs 计算
        assert result.actual_sharpe > 0.0
        # 成本: 回测 500, 实际 10+15=25
        assert result.backtest_total_cost == 500.0
        assert result.actual_total_cost == 25.0
        # 成本拖累 (基点): actual_cost - backtest_cost
        # cost_drag_bps = (actual_cost - backtest_cost) / initial_cash * 10_000
        assert result.cost_drag_bps == pytest.approx(
            (25.0 - 500.0) / 1_000_000.0 * 10_000,
            abs=0.1,
        )

    def test_empty_actual_data(self) -> None:
        """空 actual 数据 → None / 安全默认值."""
        from ditto_app.process.execution.comparison import compute_comparison

        report = _make_backtest_report()
        result = compute_comparison(
            backtest_report=report,
            actual_fills=[],
            actual_navs=[],
            initial_cash=1_000_000.0,
        )

        assert result.backtest_return == 10.0
        assert result.actual_return is None
        assert result.return_diff is None
        assert result.return_diff_bps is None
        assert result.actual_sharpe == 0.0
        assert result.actual_total_cost == 0.0
        assert result.nav_correlation == 0.0
        assert result.max_nav_diff_bps == 0.0
        assert result.avg_daily_tracking_error_bps == 0.0

    def test_nav_correlation_perfect(self) -> None:
        """NAV 完全相关 → correlation ≈ 1.0."""
        from ditto_app.process.execution.comparison import compute_comparison

        nav_series = tuple(
            (f"2024-01-{d:02d}", 1_000_000.0 + d * 10_000.0) for d in range(2, 13)
        )
        report = _make_backtest_report(nav_series=nav_series)
        actual_navs = list(nav_series)

        result = compute_comparison(
            backtest_report=report,
            actual_fills=[],
            actual_navs=actual_navs,
        )

        assert result.nav_correlation == pytest.approx(1.0, abs=0.01)

    def test_return_diff_bps_calculation(self) -> None:
        """基点偏差计算正确."""
        from ditto_app.process.execution.comparison import compute_comparison

        # 回测收益 10%, 实际收益 9.5%
        alpha_stats = _make_alpha_stats(annualized_return=10.0)
        report = _make_backtest_report(alpha_stats=alpha_stats)
        actual_navs = [
            ("2024-01-02", 1_000_000.0),
            ("2024-01-03", 1_095_000.0),
        ]

        result = compute_comparison(
            backtest_report=report,
            actual_fills=[],
            actual_navs=actual_navs,
            initial_cash=1_000_000.0,
        )

        assert result.actual_return == pytest.approx(9.5, abs=0.01)
        assert result.return_diff == pytest.approx(-0.5, abs=0.01)
        assert result.return_diff_bps == pytest.approx(-50.0, abs=1.0)

    def test_tracking_error_with_divergent_navs(self) -> None:
        """NAV 序列发散 → 跟踪误差 > 0."""
        from ditto_app.process.execution.comparison import compute_comparison

        backtest_navs = tuple(
            (f"2024-01-{d:02d}", 1_000_000.0 * (1 + d * 0.01)) for d in range(2, 12)
        )
        report = _make_backtest_report(nav_series=backtest_navs)

        # 实际 NAV 偏离更大
        actual_navs = [
            (f"2024-01-{d:02d}", 1_000_000.0 * (1 + d * 0.015)) for d in range(2, 12)
        ]

        result = compute_comparison(
            backtest_report=report,
            actual_fills=[],
            actual_navs=actual_navs,
        )

        assert result.avg_daily_tracking_error_bps > 0.0


# ===========================================================================
# PnlSummary — 数据类测试
# ===========================================================================


class TestPnlSummary:
    """PnlSummary — P&L 汇总数据类."""

    def test_construction(self) -> None:
        """基本构造."""
        from ditto_app.query.portfolio_actual import PnlSummary

        summary = PnlSummary(
            total_realized_pnl=1000.0,
            total_unrealized_pnl=500.0,
            total_fees=50.0,
            net_pnl=1450.0,
        )
        assert summary.total_realized_pnl == 1000.0
        assert summary.total_unrealized_pnl == 500.0
        assert summary.total_fees == 50.0
        assert summary.net_pnl == 1450.0

    def test_net_pnl_formula(self) -> None:
        """net_pnl = realized + unrealized - fees."""
        from ditto_app.query.portfolio_actual import PnlSummary

        summary = PnlSummary(
            total_realized_pnl=2000.0,
            total_unrealized_pnl=800.0,
            total_fees=120.0,
            net_pnl=2000.0 + 800.0 - 120.0,
        )
        assert summary.net_pnl == pytest.approx(2680.0)

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        from ditto_app.query.portfolio_actual import PnlSummary

        summary = PnlSummary(
            total_realized_pnl=0.0,
            total_unrealized_pnl=0.0,
            total_fees=0.0,
            net_pnl=0.0,
        )
        with pytest.raises(AttributeError):
            summary.total_realized_pnl = 100.0  # type: ignore[misc]


# ===========================================================================
# PortfolioActualQueryFacade — 查询门面测试
# ===========================================================================


class TestPortfolioActualQueryFacadeGetLatestPositions:
    """PortfolioActualQueryFacade.get_latest_positions — 正确映射."""

    def test_returns_mapped_snapshots(self) -> None:
        """从 TradeService 获取 positions 并映射为 DTO."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
        from ditto_data.models.trade import ActualPositionSnapshotRecord

        mock_service = _make_mock_trade_service()
        records = [
            ActualPositionSnapshotRecord(
                snapshot_id="snap-1",
                strategy_id="strat-001",
                snapshot_date="2024-01-16",
                instrument_id=1,
                quantity=1000,
                available_quantity=500,
                average_cost=1.5,
                market_value=1600.0,
                unrealized_pnl=100.0,
                realized_pnl=200.0,
                total_fees=15.0,
            ),
            ActualPositionSnapshotRecord(
                snapshot_id="snap-2",
                strategy_id="strat-001",
                snapshot_date="2024-01-16",
                instrument_id=2,
                quantity=2000,
                available_quantity=1000,
                average_cost=2.0,
                market_value=4000.0,
                unrealized_pnl=200.0,
                realized_pnl=300.0,
                total_fees=25.0,
            ),
        ]
        mock_service.list_positions.return_value = records

        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.get_latest_positions(strategy_id="strat-001")

        assert len(result) == 2
        assert result[0].snapshot_id == "snap-1"
        assert result[0].instrument_id == 1
        assert result[1].snapshot_id == "snap-2"
        assert result[1].instrument_id == 2

    def test_empty_positions(self) -> None:
        """无持仓时返回空列表."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade

        mock_service = _make_mock_trade_service()
        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.get_latest_positions(strategy_id="strat-001")

        assert result == []


class TestPortfolioActualQueryFacadeGetFills:
    """PortfolioActualQueryFacade.get_fills — 日期过滤."""

    def test_get_all_fills(self) -> None:
        """获取全部成交记录."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
        from ditto_data.models.trade import ManualExecutionFillRecord

        mock_service = _make_mock_trade_service()
        records = [
            ManualExecutionFillRecord(
                fill_id="fill-1",
                intent_id="intent-1",
                strategy_id="strat-001",
                trade_date="2024-01-10",
                instrument_id=1,
                direction="buy",
                quantity=1000,
                fill_price=1.5,
                fee=10.0,
            ),
        ]
        mock_service.list_fills.return_value = records

        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.get_fills(strategy_id="strat-001")

        assert len(result) == 1
        assert result[0].fill_id == "fill-1"
        mock_service.list_fills.assert_called_once_with(
            "strat-001",
            trade_date=None,
            end_date=None,
        )

    def test_get_fills_with_date_filter(self) -> None:
        """按日期过滤成交记录."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade

        mock_service = _make_mock_trade_service()
        mock_service.list_fills.return_value = []

        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        facade.get_fills(strategy_id="strat-001", start_date="2024-01-10")

        mock_service.list_fills.assert_called_once_with(
            "strat-001",
            trade_date="2024-01-10",
            end_date=None,
        )

    def test_empty_fills(self) -> None:
        """无成交记录时返回空列表."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade

        mock_service = _make_mock_trade_service()
        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.get_fills(strategy_id="strat-001")

        assert result == []


class TestPortfolioActualQueryFacadeGetPositionHistory:
    """PortfolioActualQueryFacade.get_position_history — 持仓历史查询."""

    def test_get_history(self) -> None:
        """获取持仓历史快照."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
        from ditto_data.models.trade import ActualPositionSnapshotRecord

        mock_service = _make_mock_trade_service()
        records = [
            ActualPositionSnapshotRecord(
                snapshot_id="snap-1",
                strategy_id="strat-001",
                snapshot_date="2024-01-10",
                instrument_id=1,
                quantity=1000,
                available_quantity=500,
                average_cost=1.5,
                market_value=1500.0,
                unrealized_pnl=0.0,
                realized_pnl=100.0,
                total_fees=10.0,
            ),
            ActualPositionSnapshotRecord(
                snapshot_id="snap-2",
                strategy_id="strat-001",
                snapshot_date="2024-01-15",
                instrument_id=1,
                quantity=1000,
                available_quantity=1000,
                average_cost=1.5,
                market_value=1600.0,
                unrealized_pnl=100.0,
                realized_pnl=100.0,
                total_fees=10.0,
            ),
        ]
        mock_service.list_positions.return_value = records

        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.get_position_history(
            strategy_id="strat-001",
            snapshot_date="2024-01-15",
        )

        assert len(result) == 2
        mock_service.list_positions.assert_called_once_with(
            "strat-001",
            snapshot_date="2024-01-15",
        )


class TestPortfolioActualQueryFacadeComputePnl:
    """PortfolioActualQueryFacade.compute_pnl — P&L 汇总计算."""

    def test_compute_pnl_aggregation(self) -> None:
        """多持仓 P&L 正确汇总."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
        from ditto_data.models.trade import ActualPositionSnapshotRecord

        mock_service = _make_mock_trade_service()
        records = [
            ActualPositionSnapshotRecord(
                snapshot_id="snap-1",
                strategy_id="strat-001",
                snapshot_date="2024-01-16",
                instrument_id=1,
                quantity=1000,
                available_quantity=500,
                average_cost=1.5,
                market_value=1600.0,
                unrealized_pnl=100.0,
                realized_pnl=200.0,
                total_fees=15.0,
            ),
            ActualPositionSnapshotRecord(
                snapshot_id="snap-2",
                strategy_id="strat-001",
                snapshot_date="2024-01-16",
                instrument_id=2,
                quantity=2000,
                available_quantity=1000,
                average_cost=2.0,
                market_value=4200.0,
                unrealized_pnl=200.0,
                realized_pnl=300.0,
                total_fees=25.0,
            ),
        ]
        mock_service.list_positions.return_value = records

        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.compute_pnl(
            strategy_id="strat-001",
            snapshot_date="2024-01-16",
        )

        assert result.total_realized_pnl == pytest.approx(500.0)
        assert result.total_unrealized_pnl == pytest.approx(300.0)
        assert result.total_fees == pytest.approx(40.0)
        # net_pnl = realized + unrealized - fees
        assert result.net_pnl == pytest.approx(500.0 + 300.0 - 40.0)

    def test_compute_pnl_empty(self) -> None:
        """无持仓时返回零值 P&L."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade

        mock_service = _make_mock_trade_service()
        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.compute_pnl(
            strategy_id="strat-001",
            snapshot_date="2024-01-16",
        )

        assert result.total_realized_pnl == 0.0
        assert result.total_unrealized_pnl == 0.0
        assert result.total_fees == 0.0
        assert result.net_pnl == 0.0

    def test_compute_pnl_single_position(self) -> None:
        """单持仓 P&L 汇总."""
        from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
        from ditto_data.models.trade import ActualPositionSnapshotRecord

        mock_service = _make_mock_trade_service()
        record = ActualPositionSnapshotRecord(
            snapshot_id="snap-1",
            strategy_id="strat-001",
            snapshot_date="2024-01-16",
            instrument_id=1,
            quantity=1000,
            available_quantity=500,
            average_cost=1.5,
            market_value=1600.0,
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            total_fees=10.0,
        )
        mock_service.list_positions.return_value = [record]

        facade = PortfolioActualQueryFacade(trade_service=mock_service)
        result = facade.compute_pnl(
            strategy_id="strat-001",
            snapshot_date="2024-01-16",
        )

        assert result.total_realized_pnl == 0.0
        assert result.total_unrealized_pnl == 100.0
        assert result.total_fees == 10.0
        assert result.net_pnl == pytest.approx(90.0)
