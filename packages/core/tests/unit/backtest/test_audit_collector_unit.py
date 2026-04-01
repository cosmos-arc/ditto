"""ExecutionAuditCollector / PortfolioStatistics / TradeStatistics unit tests."""

from datetime import datetime
from types import MappingProxyType

import pytest
from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.cash import CashBook
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.order_book import (
    OrderBookReadOnly,
    OrderSide,
)
from ditto_engine.accounting.position import Position
from ditto_engine.backtest.risk.post_trade import RiskActionType, RiskSeverity
from ditto_engine.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    ExecutionAuditCollector,
    PortfolioStatistics,
    PreTradeDecisionRecord,
    RiskScanRecord,
    TradeStatistics,
    build_report,
    compute_aggregated_trade_statistics,
    compute_alpha_statistics,
    compute_portfolio_statistics,
    compute_trade_statistics,
)
from ditto_engine.execution.trade_builder import TradeRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _account_view(
    nav: float = 100_000.0,
    exposure: float = 60_000.0,
    cash: float = 40_000.0,
    positions: dict[int, Position] | None = None,
) -> AccountView:
    """Build an AccountView with sensible defaults."""
    cash_book = CashBook(available=cash, settled=cash, frozen=0.0)
    pos_map = MappingProxyType(positions or {})
    return AccountView(
        positions=pos_map,
        cash=cash_book,
        total_value=nav,
        nav=nav,
        exposure=exposure,
        pending_buy_value=0.0,
        order_book=OrderBookReadOnly({}),
    )


def _fill_event(
    fill_id: str = "f-1",
    instrument_id: int = 1,
    direction: OrderSide = OrderSide.BUY,
) -> FillEvent:
    return FillEvent(
        fill_id=fill_id,
        order_id="o-1",
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=100,
        fill_price=10.0,
        fee=5.0,
        slippage=0.01,
        event_time=datetime(2026, 1, 1),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def _trade_record(
    trade_id: str = "trade-1",
    instrument_id: int = 1,
    exit_date: str | None = "2026-01-10",
) -> TradeRecord:
    return TradeRecord(
        trade_id=trade_id,
        instrument_id=instrument_id,
        direction=OrderSide.BUY,
        entry_date="2026-01-05",
        exit_date=exit_date,
        entry_price=10.0,
        exit_price=10.5 if exit_date else None,
        quantity=100,
        gross_pnl=50.0 if exit_date else None,
        fees=10.0,
        net_pnl=40.0 if exit_date else None,
        holding_days=5 if exit_date else None,
        return_pct=5.0 if exit_date else None,
        entry_order_ids=("o-1",),
        exit_order_ids=("o-2",) if exit_date else (),
    )


def _closed_trade(
    trade_id: str,
    gross_pnl: float,
    holding_days: int,
    return_pct: float,
    direction: OrderSide = OrderSide.BUY,
) -> TradeRecord:
    """Build a closed TradeRecord with explicit PnL values."""
    return TradeRecord(
        trade_id=trade_id,
        instrument_id=1,
        direction=direction,
        entry_date="2026-01-01",
        exit_date="2026-01-06",
        entry_price=10.0,
        exit_price=10.0,
        quantity=100,
        gross_pnl=gross_pnl,
        fees=5.0,
        net_pnl=gross_pnl - 5.0,
        holding_days=holding_days,
        return_pct=return_pct,
        entry_order_ids=("o-1",),
        exit_order_ids=("o-2",),
    )


# ---------------------------------------------------------------------------
# test_record_fill
# ---------------------------------------------------------------------------


class TestRecordFill:
    def test_record_fill_returns_both(self) -> None:
        collector = ExecutionAuditCollector()
        fill1 = _fill_event(fill_id="f-1")
        fill2 = _fill_event(fill_id="f-2", instrument_id=2)

        collector.record_fill(fill1)
        collector.record_fill(fill2)

        fills = collector.get_fills()
        assert len(fills) == 2
        assert fills[0].fill_id == "f-1"
        assert fills[1].fill_id == "f-2"


# ---------------------------------------------------------------------------
# test_record_account_view
# ---------------------------------------------------------------------------


class TestRecordAccountView:
    def test_record_account_view(self) -> None:
        collector = ExecutionAuditCollector()
        view1 = _account_view(nav=100_000.0)
        view2 = _account_view(nav=101_000.0)
        view3 = _account_view(nav=99_500.0)

        collector.record_account_view("2026-01-01", view1)
        collector.record_account_view("2026-01-02", view2)
        collector.record_account_view("2026-01-03", view3)

        snapshots = collector.get_daily_snapshots()
        assert len(snapshots) == 3
        assert snapshots[0][0] == "2026-01-01"
        assert snapshots[0][1].nav == 100_000.0
        assert snapshots[1][0] == "2026-01-02"
        assert snapshots[1][1].nav == 101_000.0
        assert snapshots[2][0] == "2026-01-03"
        assert snapshots[2][1].nav == 99_500.0


# ---------------------------------------------------------------------------
# test_record_closed_trade
# ---------------------------------------------------------------------------


class TestRecordClosedTrade:
    def test_record_closed_trade(self) -> None:
        collector = ExecutionAuditCollector()
        trade1 = _trade_record(trade_id="trade-1")
        trade2 = _trade_record(
            trade_id="trade-2",
            instrument_id=2,
        )

        collector.record_closed_trade(trade1)
        collector.record_closed_trade(trade2)

        trades = collector.get_closed_trades()
        assert len(trades) == 2
        assert trades[0].trade_id == "trade-1"
        assert trades[1].trade_id == "trade-2"


# ---------------------------------------------------------------------------
# test_compute_portfolio_statistics
# ---------------------------------------------------------------------------


class TestComputePortfolioStatistics:
    def test_three_day_series(self) -> None:
        """Day 1: 100k, Day 2: 101k, Day 3: 99.5k."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_account_view("2026-01-03", _account_view(nav=99_500.0))

        stats = compute_portfolio_statistics(collector)
        assert len(stats) == 3

        # Day 1
        assert stats[0].trade_date == "2026-01-01"
        assert stats[0].nav == 100_000.0
        assert stats[0].daily_return == pytest.approx(0.0, abs=1e-9)
        assert stats[0].cumulative_return == pytest.approx(0.0, abs=1e-9)
        assert stats[0].drawdown == pytest.approx(0.0, abs=1e-9)
        assert stats[0].max_drawdown == pytest.approx(0.0, abs=1e-9)

        # Day 2
        assert stats[1].daily_return == pytest.approx(1.0, abs=1e-6)
        assert stats[1].cumulative_return == pytest.approx(1.0, abs=1e-6)
        assert stats[1].drawdown == pytest.approx(0.0, abs=1e-9)
        assert stats[1].max_drawdown == pytest.approx(0.0, abs=1e-9)

        # Day 3
        # daily_return = (99500 - 101000) / 101000 * 100 = -1.4851...
        assert stats[2].daily_return == pytest.approx(-1.485148, abs=1e-3)
        # cumulative_return = (99500 - 100000) / 100000 * 100 = -0.5
        assert stats[2].cumulative_return == pytest.approx(-0.5, abs=1e-6)
        # drawdown = (99500 - 101000) / 101000 * 100
        assert stats[2].drawdown == pytest.approx(-1.485148, abs=1e-3)
        # max_drawdown = running max of abs(drawdown) = 1.485148...
        assert stats[2].max_drawdown == pytest.approx(-1.485148, abs=1e-3)


# ---------------------------------------------------------------------------
# test_compute_trade_statistics
# ---------------------------------------------------------------------------


class TestComputeTradeStatistics:
    def test_maps_trade_record(self) -> None:
        collector = ExecutionAuditCollector()
        collector.record_closed_trade(_trade_record(trade_id="trade-1"))
        collector.record_closed_trade(
            _trade_record(
                trade_id="trade-2",
                instrument_id=2,
                exit_date=None,
            ),
        )

        trade_stats = compute_trade_statistics(collector)
        assert len(trade_stats) == 2

        # Closed trade
        ts1 = trade_stats[0]
        assert ts1.trade_id == "trade-1"
        assert ts1.instrument_id == 1
        assert ts1.direction == "buy"
        assert ts1.entry_date == "2026-01-05"
        assert ts1.exit_date == "2026-01-10"
        assert ts1.holding_days == 5
        assert ts1.return_pct == pytest.approx(5.0)
        assert ts1.gross_pnl == pytest.approx(50.0)
        assert ts1.net_pnl == pytest.approx(40.0)
        assert ts1.fees == pytest.approx(10.0)

        # Open trade
        ts2 = trade_stats[1]
        assert ts2.trade_id == "trade-2"
        assert ts2.instrument_id == 2
        assert ts2.exit_date is None
        assert ts2.holding_days is None
        assert ts2.return_pct is None
        assert ts2.gross_pnl is None
        assert ts2.net_pnl is None


# ---------------------------------------------------------------------------
# test_empty_collector
# ---------------------------------------------------------------------------


class TestEmptyCollector:
    def test_all_getters_return_empty(self) -> None:
        collector = ExecutionAuditCollector()

        assert collector.get_fills() == ()
        assert collector.get_daily_snapshots() == ()
        assert collector.get_closed_trades() == ()
        assert compute_portfolio_statistics(collector) == ()
        assert compute_trade_statistics(collector) == ()


# ---------------------------------------------------------------------------
# test_portfolio_statistics_with_cash_ratio
# ---------------------------------------------------------------------------


class TestPortfolioStatisticsWithCashRatio:
    def test_cash_ratio_calculation(self) -> None:
        """AccountView with positions + cash — verify cash_ratio."""
        collector = ExecutionAuditCollector()
        # NAV = 100k, cash = 40k → cash_ratio = 40%
        view = _account_view(
            nav=100_000.0,
            exposure=60_000.0,
            cash=40_000.0,
            positions={
                1: Position(
                    instrument_id=1,
                    quantity=6000,
                    available_quantity=6000,
                    average_cost=10.0,
                    market_value=60_000.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=0.0,
                ),
            },
        )
        collector.record_account_view("2026-01-01", view)

        stats = compute_portfolio_statistics(collector)
        assert len(stats) == 1
        assert stats[0].cash_ratio == pytest.approx(40.0)
        assert stats[0].position_count == 1
        assert stats[0].exposure == pytest.approx(60_000.0)

    def test_frozen(self) -> None:
        """PortfolioStatistics is frozen."""
        with pytest.raises(AttributeError):
            PortfolioStatistics(
                trade_date="2026-01-01",
                nav=100_000.0,
                daily_return=0.0,
                cumulative_return=0.0,
                drawdown=0.0,
                max_drawdown=0.0,
                exposure=0.0,
                cash_ratio=100.0,
                position_count=0,
            ).nav = 200_000.0  # type: ignore[misc]

    def test_trade_statistics_frozen(self) -> None:
        """TradeStatistics is frozen."""
        with pytest.raises(AttributeError):
            TradeStatistics(
                trade_id="t-1",
                instrument_id=1,
                direction="buy",
                entry_date="2026-01-01",
                exit_date=None,
                holding_days=None,
                return_pct=None,
                gross_pnl=None,
                net_pnl=None,
                fees=0.0,
            ).fees = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestAggregatedTradeStatistics
# ---------------------------------------------------------------------------


class TestAggregatedTradeStatistics:
    """Tests for compute_aggregated_trade_statistics()."""

    def test_no_trades_returns_zeros(self) -> None:
        """Empty collector → all fields zero."""
        collector = ExecutionAuditCollector()
        stats = compute_aggregated_trade_statistics(collector)

        assert stats.total_trades == 0
        assert stats.win_trades == 0
        assert stats.loss_trades == 0
        assert stats.win_rate == 0.0
        assert stats.profit_factor == 0.0
        assert stats.max_consecutive_wins == 0
        assert stats.max_consecutive_losses == 0
        assert stats.best_trade == 0.0
        assert stats.worst_trade == 0.0

    def test_open_trades_excluded(self) -> None:
        """Only closed trades (exit_date not None) are counted."""
        collector = ExecutionAuditCollector()
        collector.record_closed_trade(
            _trade_record(trade_id="open-1", exit_date=None),
        )
        stats = compute_aggregated_trade_statistics(collector)
        assert stats.total_trades == 0

    def test_basic_aggregation(self) -> None:
        """
        5 trades: W(+100), W(+200), L(-80), W(+50), L(-30).
        Expected:
          total=5, win=3, loss=2, win_rate=60%
          profit_factor = 350/110 ≈ 3.1818
          avg_win = 350/3 ≈ 116.667
          avg_loss = 110/2 = 55.0
          avg_win_loss_ratio = 116.667/55.0 ≈ 2.1212
          max_consec_wins = 2 (first two)
          max_consec_losses = 1
        """
        collector = ExecutionAuditCollector()
        # Sequence: W, W, L, W, L
        collector.record_closed_trade(
            _closed_trade("t1", gross_pnl=100.0, holding_days=5, return_pct=2.0),
        )
        collector.record_closed_trade(
            _closed_trade("t2", gross_pnl=200.0, holding_days=10, return_pct=4.0),
        )
        collector.record_closed_trade(
            _closed_trade("t3", gross_pnl=-80.0, holding_days=3, return_pct=-1.6),
        )
        collector.record_closed_trade(
            _closed_trade("t4", gross_pnl=50.0, holding_days=7, return_pct=1.0),
        )
        collector.record_closed_trade(
            _closed_trade("t5", gross_pnl=-30.0, holding_days=2, return_pct=-0.6),
        )

        stats = compute_aggregated_trade_statistics(collector)

        assert stats.total_trades == 5
        assert stats.long_trades == 5
        assert stats.short_trades == 0
        assert stats.win_trades == 3
        assert stats.loss_trades == 2
        assert stats.win_rate == pytest.approx(60.0)
        assert stats.profit_factor == pytest.approx(350.0 / 110.0)
        assert stats.avg_win == pytest.approx(350.0 / 3)
        assert stats.avg_loss == pytest.approx(110.0 / 2)
        assert stats.avg_win_loss_ratio == pytest.approx((350.0 / 3) / (110.0 / 2))
        assert stats.max_consecutive_wins == 2
        assert stats.max_consecutive_losses == 1
        assert stats.avg_holding_days == pytest.approx((5 + 10 + 3 + 7 + 2) / 5)
        assert stats.median_holding_days == pytest.approx(5.0)
        assert stats.best_trade == pytest.approx(200.0)
        assert stats.worst_trade == pytest.approx(-80.0)
        assert stats.avg_trade_return_pct == pytest.approx(
            (2.0 + 4.0 - 1.6 + 1.0 - 0.6) / 5,
        )

    def test_all_wins(self) -> None:
        """Edge case: all trades are winners — profit_factor = inf."""
        collector = ExecutionAuditCollector()
        collector.record_closed_trade(
            _closed_trade("t1", gross_pnl=100.0, holding_days=3, return_pct=1.0),
        )
        collector.record_closed_trade(
            _closed_trade("t2", gross_pnl=200.0, holding_days=5, return_pct=2.0),
        )
        stats = compute_aggregated_trade_statistics(collector)

        assert stats.win_trades == 2
        assert stats.loss_trades == 0
        assert stats.profit_factor == float("inf")
        assert stats.avg_loss == 0.0
        assert stats.avg_win_loss_ratio == float("inf")
        assert stats.max_consecutive_wins == 2
        assert stats.max_consecutive_losses == 0

    def test_all_losses(self) -> None:
        """Edge case: all trades are losers."""
        collector = ExecutionAuditCollector()
        collector.record_closed_trade(
            _closed_trade("t1", gross_pnl=-50.0, holding_days=2, return_pct=-1.0),
        )
        collector.record_closed_trade(
            _closed_trade("t2", gross_pnl=-100.0, holding_days=4, return_pct=-2.0),
        )
        stats = compute_aggregated_trade_statistics(collector)

        assert stats.win_trades == 0
        assert stats.loss_trades == 2
        assert stats.win_rate == pytest.approx(0.0)
        assert stats.profit_factor == 0.0
        assert stats.avg_win == 0.0
        assert stats.max_consecutive_losses == 2

    def test_mixed_directions(self) -> None:
        """Long and short trades are counted separately."""
        collector = ExecutionAuditCollector()
        collector.record_closed_trade(
            _closed_trade("t1", gross_pnl=100.0, holding_days=3, return_pct=1.0),
        )
        collector.record_closed_trade(
            _closed_trade(
                "t2",
                gross_pnl=-50.0,
                holding_days=2,
                return_pct=-1.0,
                direction=OrderSide.SELL,
            ),
        )
        stats = compute_aggregated_trade_statistics(collector)

        assert stats.total_trades == 2
        assert stats.long_trades == 1
        assert stats.short_trades == 1

    def test_frozen(self) -> None:
        """AggregatedTradeStatistics is frozen."""
        stats = AggregatedTradeStatistics(
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
        with pytest.raises(AttributeError):
            stats.total_trades = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestAlphaStatistics
# ---------------------------------------------------------------------------


class TestAlphaStatistics:
    """Tests for compute_alpha_statistics()."""

    def test_empty_collector_returns_zeros(self) -> None:
        """No snapshots → all numeric fields zero, benchmark fields None."""
        collector = ExecutionAuditCollector()
        alpha = compute_alpha_statistics(
            collector,
        )

        assert alpha.annualized_return == 0.0
        assert alpha.annualized_volatility == 0.0
        assert alpha.sharpe_ratio == 0.0
        assert alpha.sortino_ratio == 0.0
        assert alpha.max_drawdown == 0.0
        assert alpha.max_drawdown_duration_days == 0
        assert alpha.calmar_ratio == 0.0
        assert alpha.information_ratio is None
        assert alpha.tracking_error is None
        assert alpha.beta is None
        assert alpha.alpha_annualized is None
        assert alpha.total_fees == 0.0
        assert alpha.cost_drag == 0.0

    def test_single_day_returns_zero_volatility(self) -> None:
        """One day snapshot → no daily returns → volatility = 0."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        alpha = compute_alpha_statistics(
            collector,
        )

        assert alpha.annualized_return == pytest.approx(0.0)
        assert alpha.annualized_volatility == 0.0
        assert alpha.sharpe_ratio == 0.0

    def test_basic_alpha_stats(self) -> None:
        """
        Simple 3-day NAV series: 100k → 101k → 100.5k.
        Verify annualized metrics are non-zero.
        """
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_account_view("2026-01-03", _account_view(nav=100_500.0))

        alpha = compute_alpha_statistics(
            collector,
        )

        # total_return = (100500 - 100000) / 100000 = 0.005
        # annualized = (1.005)^(252/2) - 1 ≈ ... (positive)
        assert alpha.annualized_return > 0.0
        # Volatility should be positive (2 daily returns with variance)
        assert alpha.annualized_volatility > 0.0
        # Sharpe should be positive since return > 0
        assert alpha.sharpe_ratio > 0.0
        # Max drawdown is negative (peak=101k, trough=100.5k)
        assert alpha.max_drawdown < 0.0

    def test_max_drawdown_duration(self) -> None:
        """
        NAV series: 100 → 110 → 105 → 100 → 95 → 90 → 92 → 100.
        Drawdown from day 1 (peak=110) to day 5 (trough=90) = 5 days.
        Day 6 (92) still in drawdown, day 7 (100) still below peak.
        Total consecutive drawdown days = 6 (days 2-7).
        """
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100.0))
        collector.record_account_view("2026-01-02", _account_view(nav=110.0))
        collector.record_account_view("2026-01-03", _account_view(nav=105.0))
        collector.record_account_view("2026-01-04", _account_view(nav=100.0))
        collector.record_account_view("2026-01-05", _account_view(nav=95.0))
        collector.record_account_view("2026-01-06", _account_view(nav=90.0))
        collector.record_account_view("2026-01-07", _account_view(nav=92.0))
        collector.record_account_view("2026-01-08", _account_view(nav=100.0))

        alpha = compute_alpha_statistics(
            collector,
        )
        assert alpha.max_drawdown_duration_days == 6

    def test_calmar_ratio(self) -> None:
        """Calmar = annualized_return / |max_drawdown|."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100.0))
        collector.record_account_view("2026-01-02", _account_view(nav=110.0))
        collector.record_account_view("2026-01-03", _account_view(nav=105.0))

        alpha = compute_alpha_statistics(
            collector,
        )
        if alpha.max_drawdown != 0:
            expected = alpha.annualized_return / abs(alpha.max_drawdown)
            assert alpha.calmar_ratio == pytest.approx(expected)
        else:
            assert alpha.calmar_ratio == 0.0

    def test_without_benchmark(self) -> None:
        """No benchmark → IR, tracking_error, beta, alpha = None."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_account_view("2026-01-03", _account_view(nav=100_500.0))

        alpha = compute_alpha_statistics(
            collector,
        )

        assert alpha.information_ratio is None
        assert alpha.tracking_error is None
        assert alpha.beta is None
        assert alpha.alpha_annualized is None

    def test_with_benchmark(self) -> None:
        """With benchmark NAVs → all benchmark-relative fields computed."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_account_view("2026-01-03", _account_view(nav=100_500.0))

        benchmark = (100_000.0, 100_500.0, 100_200.0)
        alpha = compute_alpha_statistics(collector, benchmark_navs=benchmark)

        assert alpha.information_ratio is not None
        assert alpha.tracking_error is not None
        assert alpha.beta is not None
        assert alpha.alpha_annualized is not None

    def test_turnover_from_fills(self) -> None:
        """Total turnover = sum(fill_price * filled_quantity) / avg_nav."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_fill(_fill_event(fill_id="f-1"))  # price=10, qty=100
        collector.record_fill(_fill_event(fill_id="f-2"))  # price=10, qty=100

        alpha = compute_alpha_statistics(
            collector,
        )
        # total_fill_value = 10 * 100 * 2 = 2000
        # avg_nav = (100000 + 101000) / 2 = 100500
        # total_turnover = 2000 / 100500
        assert alpha.total_turnover == pytest.approx(2000.0 / 100500.0)

    def test_cost_drag_and_fees(self) -> None:
        """Cost drag = total_fees / initial_nav * 100."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_fill(_fill_event(fill_id="f-1"))

        alpha = compute_alpha_statistics(
            collector,
        )
        assert alpha.total_fees == pytest.approx(5.0)
        assert alpha.cost_drag == pytest.approx(5.0 / 100_000.0 * 100)

    def test_frozen(self) -> None:
        """AlphaStatistics is frozen."""
        alpha = AlphaStatistics(
            annualized_return=0.0,
            annualized_volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration_days=0,
            calmar_ratio=0.0,
            information_ratio=None,
            tracking_error=None,
            beta=None,
            alpha_annualized=None,
            total_turnover=0.0,
            avg_turnover_per_rebalance=0.0,
            total_fees=0.0,
            net_return_after_cost=0.0,
            cost_drag=0.0,
        )
        with pytest.raises(AttributeError):
            alpha.sharpe_ratio = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestBacktestReport
# ---------------------------------------------------------------------------


class TestBacktestReport:
    """Tests for build_report()."""

    def test_empty_report(self) -> None:
        """Empty collector produces valid report with zero-length series."""
        collector = ExecutionAuditCollector()
        report = build_report(collector, run_id="test-empty")

        assert report.run_id == "test-empty"
        assert report.period == ("", "")
        assert report.initial_cash == 0.0
        assert report.final_nav == 0.0
        assert report.trade_stats == ()
        assert report.portfolio_stats == ()
        assert report.aggregated_trade_stats.total_trades == 0
        assert report.alpha_stats.annualized_return == 0.0
        assert report.nav_series == ()
        assert report.trade_log == ()
        assert report.fill_log == ()
        assert report.risk_log == ()
        assert report.pre_trade_log == ()

    def test_complete_report(self) -> None:
        """Report contains all dimensions when data is present."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_closed_trade(
            _closed_trade("t1", gross_pnl=100.0, holding_days=3, return_pct=1.0),
        )
        collector.record_fill(_fill_event(fill_id="f-1"))

        report = build_report(collector, run_id="run-001")

        assert report.run_id == "run-001"
        assert report.period == ("2026-01-01", "2026-01-02")
        assert report.initial_cash == 100_000.0
        assert report.final_nav == 101_000.0
        assert len(report.portfolio_stats) == 2
        assert len(report.trade_stats) == 1
        assert report.aggregated_trade_stats.total_trades == 1
        assert report.alpha_stats.annualized_return > 0.0
        assert len(report.nav_series) == 2
        assert report.nav_series[0] == ("2026-01-01", 100_000.0)
        assert report.nav_series[1] == ("2026-01-02", 101_000.0)
        assert len(report.trade_log) == 1
        assert report.trade_log[0].trade_id == "t1"
        assert len(report.fill_log) == 1
        assert report.fill_log[0].fill_id == "f-1"
        assert report.risk_log == ()
        assert report.pre_trade_log == ()

    def test_report_with_benchmark(self) -> None:
        """Report passes benchmark to alpha_stats computation."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-02", _account_view(nav=101_000.0))
        collector.record_account_view("2026-01-03", _account_view(nav=100_500.0))

        benchmark = (100_000.0, 100_500.0, 100_200.0)
        report = build_report(
            collector,
            run_id="bench-test",
            benchmark_navs=benchmark,
        )

        assert report.alpha_stats.beta is not None
        assert report.alpha_stats.tracking_error is not None

    def test_frozen(self) -> None:
        """BacktestReport is frozen."""
        report = BacktestReport(
            run_id="test",
            period=("2026-01-01", "2026-01-31"),
            initial_cash=100_000.0,
            final_nav=101_000.0,
            trade_stats=(),
            portfolio_stats=(),
            aggregated_trade_stats=AggregatedTradeStatistics(
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
            ),
            alpha_stats=AlphaStatistics(
                annualized_return=0.0,
                annualized_volatility=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_duration_days=0,
                calmar_ratio=0.0,
                information_ratio=None,
                tracking_error=None,
                beta=None,
                alpha_annualized=None,
                total_turnover=0.0,
                avg_turnover_per_rebalance=0.0,
                total_fees=0.0,
                net_return_after_cost=0.0,
                cost_drag=0.0,
            ),
            nav_series=(),
            trade_log=(),
            fill_log=(),
            risk_log=(),
            pre_trade_log=(),
        )
        with pytest.raises(AttributeError):
            report.run_id = "changed"  # type: ignore[misc]

    def test_report_includes_risk_log(self) -> None:
        """build_report fills risk_log from recorded risk scans."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        risk_record = RiskScanRecord(
            trade_date="2026-01-01",
            rule_id="max_drawdown",
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.EMERGENCY,
            action_taken=RiskActionType.LIQUIDATE,
            detail="drawdown exceeded",
            current_value=0.25,
            threshold=0.20,
        )
        collector.record_risk_scan("2026-01-01", (risk_record,))

        report = build_report(collector, run_id="risk-test")
        assert len(report.risk_log) == 1
        assert report.risk_log[0].rule_id == "max_drawdown"
        assert report.risk_log[0].severity == RiskSeverity.EMERGENCY

    def test_report_includes_pre_trade_log(self) -> None:
        """build_report fills pre_trade_log from recorded decisions."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-01", _account_view(nav=100_000.0))
        decision = PreTradeDecisionRecord(
            trade_date="2026-01-01",
            order_id="o-1",
            instrument_id=1,
            direction="buy",
            original_quantity=500,
            final_quantity=500,
            decision="accepted",
            reason=None,
        )
        collector.record_pre_trade_decisions("2026-01-01", (decision,))

        report = build_report(collector, run_id="pretrade-test")
        assert len(report.pre_trade_log) == 1
        assert report.pre_trade_log[0].order_id == "o-1"
        assert report.pre_trade_log[0].decision == "accepted"


# ---------------------------------------------------------------------------
# TestRiskScanRecord
# ---------------------------------------------------------------------------


class TestRiskScanRecord:
    def test_frozen(self) -> None:
        record = RiskScanRecord(
            trade_date="2026-01-15",
            rule_id="max_drawdown",
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.EMERGENCY,
            action_taken=RiskActionType.LIQUIDATE,
            detail="组合回撤 25.00% 超过紧急阈值 20.00%",
            current_value=0.25,
            threshold=0.20,
        )
        with pytest.raises(AttributeError):
            record.detail = "changed"  # type: ignore[misc]

    def test_default_fields(self) -> None:
        record = RiskScanRecord(
            trade_date="2026-01-15",
            rule_id="test",
            instrument_id=1,
            scope="instrument",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.ALERT,
            detail="test",
            current_value=0.1,
            threshold=0.05,
        )
        assert record.trade_date == "2026-01-15"
        assert record.rule_id == "test"

    def test_severity_is_risk_severity_enum(self) -> None:
        """severity 字段类型为 RiskSeverity 枚举。"""
        record = RiskScanRecord(
            trade_date="2026-01-15",
            rule_id="test",
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.CRITICAL,
            action_taken=RiskActionType.REDUCE_POSITION,
            detail="test",
            current_value=0.1,
            threshold=0.05,
        )
        assert isinstance(record.severity, RiskSeverity)
        assert record.severity == RiskSeverity.CRITICAL

    def test_action_taken_is_risk_action_type_enum(self) -> None:
        """action_taken 字段类型为 RiskActionType 枚举。"""
        record = RiskScanRecord(
            trade_date="2026-01-15",
            rule_id="test",
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.REDUCE_POSITION,
            detail="test",
            current_value=0.1,
            threshold=0.05,
        )
        assert isinstance(record.action_taken, RiskActionType)
        assert record.action_taken == RiskActionType.REDUCE_POSITION

    def test_enum_values_compatible_with_str(self) -> None:
        """StrEnum 枚举值与原始字符串兼容。"""
        record = RiskScanRecord(
            trade_date="2026-01-15",
            rule_id="test",
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.EMERGENCY,
            action_taken=RiskActionType.LIQUIDATE,
            detail="test",
            current_value=0.1,
            threshold=0.05,
        )
        assert record.severity == "emergency"
        assert record.action_taken == "liquidate"

    def test_portfolio_wide_record_has_none_instrument_id(self) -> None:
        """Portfolio-wide record: instrument_id=None, scope='portfolio'."""
        record = RiskScanRecord(
            trade_date="2026-01-15",
            rule_id="max_drawdown",
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.ALERT,
            detail="组合回撤",
            current_value=0.12,
            threshold=0.10,
        )
        assert record.instrument_id is None
        assert record.scope == "portfolio"

    def test_instrument_record_has_concrete_instrument_id(self) -> None:
        """Instrument-scoped record: concrete instrument_id, scope='instrument'."""
        record = RiskScanRecord(
            trade_date="2026-01-15",
            rule_id="single_loss_limit",
            instrument_id=1,
            scope="instrument",
            severity=RiskSeverity.CRITICAL,
            action_taken=RiskActionType.REDUCE_POSITION,
            detail="亏损超限",
            current_value=-0.20,
            threshold=-0.15,
        )
        assert record.instrument_id == 1
        assert record.scope == "instrument"


# ---------------------------------------------------------------------------
# TestPreTradeDecisionRecord
# ---------------------------------------------------------------------------


class TestPreTradeDecisionRecord:
    def test_frozen(self) -> None:
        record = PreTradeDecisionRecord(
            trade_date="2026-01-15",
            order_id="o-1",
            instrument_id=1,
            direction="buy",
            original_quantity=500,
            final_quantity=500,
            decision="accepted",
            reason=None,
            check_sequence=(),
        )
        with pytest.raises(AttributeError):
            record.decision = "rejected"  # type: ignore[misc]

    def test_default_check_sequence(self) -> None:
        record = PreTradeDecisionRecord(
            trade_date="2026-01-15",
            order_id="o-1",
            instrument_id=1,
            direction="buy",
            original_quantity=500,
            final_quantity=500,
            decision="accepted",
            reason=None,
        )
        assert record.check_sequence == ()

    def test_resize_with_check_sequence(self) -> None:
        record = PreTradeDecisionRecord(
            trade_date="2026-01-15",
            order_id="o-1",
            instrument_id=1,
            direction="buy",
            original_quantity=150,
            final_quantity=200,
            decision="resized",
            reason="lot_size: 150 not a multiple of 100, resize to 200",
            check_sequence=("lot_size",),
        )
        assert record.decision == "resized"
        assert record.check_sequence == ("lot_size",)
        assert record.reason is not None


# ---------------------------------------------------------------------------
# TestRiskLogRecording
# ---------------------------------------------------------------------------


class TestRiskLogRecording:
    def test_record_and_retrieve_risk_log(self) -> None:
        collector = ExecutionAuditCollector()
        records = (
            RiskScanRecord(
                trade_date="2026-01-15",
                rule_id="max_drawdown",
                instrument_id=None,
                scope="portfolio",
                severity=RiskSeverity.EMERGENCY,
                action_taken=RiskActionType.LIQUIDATE,
                detail="组合回撤 25.00%",
                current_value=0.25,
                threshold=0.20,
            ),
            RiskScanRecord(
                trade_date="2026-01-15",
                rule_id="single_loss_limit",
                instrument_id=1,
                scope="instrument",
                severity=RiskSeverity.CRITICAL,
                action_taken=RiskActionType.REDUCE_POSITION,
                detail="510300.SH 亏损 20.00%",
                current_value=-0.20,
                threshold=-0.15,
            ),
        )
        collector.record_risk_scan("2026-01-15", records)

        log = collector.get_risk_log()
        assert len(log) == 2
        assert log[0].rule_id == "max_drawdown"
        assert log[0].trade_date == "2026-01-15"
        assert log[0].severity == RiskSeverity.EMERGENCY
        assert log[1].rule_id == "single_loss_limit"
        assert log[1].action_taken == RiskActionType.REDUCE_POSITION

    def test_empty_risk_log(self) -> None:
        collector = ExecutionAuditCollector()
        assert collector.get_risk_log() == ()

    def test_multiple_days_risk_log(self) -> None:
        collector = ExecutionAuditCollector()
        collector.record_risk_scan(
            "2026-01-15",
            (
                RiskScanRecord(
                    trade_date="2026-01-15",
                    rule_id="test",
                    instrument_id=None,
                    scope="portfolio",
                    severity=RiskSeverity.WARNING,
                    action_taken=RiskActionType.ALERT,
                    detail="d",
                    current_value=0.1,
                    threshold=0.1,
                ),
            ),
        )
        collector.record_risk_scan(
            "2026-01-16",
            (
                RiskScanRecord(
                    trade_date="2026-01-16",
                    rule_id="test",
                    instrument_id=None,
                    scope="portfolio",
                    severity=RiskSeverity.WARNING,
                    action_taken=RiskActionType.ALERT,
                    detail="d",
                    current_value=0.1,
                    threshold=0.1,
                ),
            ),
        )
        log = collector.get_risk_log()
        assert len(log) == 2


# ---------------------------------------------------------------------------
# TestPreTradeLogRecording
# ---------------------------------------------------------------------------


class TestPreTradeLogRecording:
    def test_record_and_retrieve_pre_trade_log(self) -> None:
        collector = ExecutionAuditCollector()
        decisions = (
            PreTradeDecisionRecord(
                trade_date="2026-01-15",
                order_id="o-1",
                instrument_id=1,
                direction="buy",
                original_quantity=500,
                final_quantity=500,
                decision="accepted",
                reason=None,
            ),
            PreTradeDecisionRecord(
                trade_date="2026-01-15",
                order_id="o-2",
                instrument_id=2,
                direction="sell",
                original_quantity=200,
                final_quantity=0,
                decision="rejected",
                reason="no_short_sell: 159915.SZ available=0, requested=200",
                check_sequence=("no_short_sell",),
            ),
        )
        collector.record_pre_trade_decisions("2026-01-15", decisions)

        log = collector.get_pre_trade_log()
        assert len(log) == 2
        assert log[0].decision == "accepted"
        assert log[1].decision == "rejected"
        assert log[1].check_sequence == ("no_short_sell",)

    def test_empty_pre_trade_log(self) -> None:
        collector = ExecutionAuditCollector()
        assert collector.get_pre_trade_log() == ()

    def test_resize_decision_records_check_sequence(self) -> None:
        collector = ExecutionAuditCollector()
        decisions = (
            PreTradeDecisionRecord(
                trade_date="2026-01-15",
                order_id="o-1",
                instrument_id=1,
                direction="buy",
                original_quantity=150,
                final_quantity=200,
                decision="resized",
                reason="lot_size: 150 not a multiple of 100",
                check_sequence=("lot_size",),
            ),
        )
        collector.record_pre_trade_decisions("2026-01-15", decisions)
        log = collector.get_pre_trade_log()
        assert log[0].original_quantity == 150
        assert log[0].final_quantity == 200
        assert log[0].decision == "resized"


# ---------------------------------------------------------------------------
# Part 04b: NAV=0 边界 + benchmark 长度不匹配
# ---------------------------------------------------------------------------


class TestNavZeroBoundary:
    """空仓场景 (NAV=0) 下统计计算不除零."""

    def test_portfolio_stats_all_zero_nav(self) -> None:
        """所有快照 NAV=0 → daily_return=0, cumulative_return=0, drawdown=0."""
        collector = ExecutionAuditCollector()
        for i in range(3):
            collector.record_account_view(
                f"2026-01-{10 + i}",
                _account_view(nav=0.0, exposure=0.0, cash=0.0),
            )
        stats = compute_portfolio_statistics(collector)
        assert len(stats) == 3
        for s in stats:
            assert s.nav == 0.0
            assert s.daily_return == 0.0
            assert s.cumulative_return == 0.0
            assert s.drawdown == 0.0
            assert s.max_drawdown == 0.0
            assert s.cash_ratio == 0.0

    def test_portfolio_stats_zero_to_positive(self) -> None:
        """NAV 从 0 恢复到正值 → daily_return=0 (除零保护)."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-10", _account_view(nav=0.0))
        collector.record_account_view("2026-01-11", _account_view(nav=100_000.0))
        stats = compute_portfolio_statistics(collector)
        assert stats[0].daily_return == 0.0  # first day always 0
        assert stats[1].daily_return == 0.0  # prev_nav=0 → protected

    def test_portfolio_stats_positive_to_zero(self) -> None:
        """NAV 从正值跌到 0 → daily_return=-100%."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-10", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-11", _account_view(nav=0.0))
        stats = compute_portfolio_statistics(collector)
        assert stats[1].daily_return == pytest.approx(-100.0)

    def test_alpha_stats_single_snapshot(self) -> None:
        """单个快照 → 无日收益率 → vol=0, sharpe=0."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-10", _account_view(nav=100_000.0))
        alpha = compute_alpha_statistics(
            collector,
        )
        assert alpha.annualized_volatility == 0.0
        assert alpha.sharpe_ratio == 0.0
        assert alpha.sortino_ratio == 0.0


class TestBenchmarkLengthMismatch:
    """benchmark 长度与快照数不一致时 graceful 降级."""

    def test_benchmark_too_short(self) -> None:
        """benchmark 少于快照数 → 基准字段为 None."""
        collector = ExecutionAuditCollector()
        for i in range(3):
            collector.record_account_view(
                f"2026-01-{10 + i}",
                _account_view(nav=100_000.0 * (1 + 0.001 * i)),
            )
        # 3 snapshots but only 2 benchmark values
        alpha = compute_alpha_statistics(collector, benchmark_navs=(100.0, 101.0))
        assert alpha.beta is None
        assert alpha.tracking_error is None
        assert alpha.information_ratio is None
        assert alpha.alpha_annualized is None
        # 非基准字段正常（3 个快照有微小日收益）
        assert alpha.annualized_return > 0.0

    def test_benchmark_too_long(self) -> None:
        """benchmark 多于快照数 → 基准字段为 None."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-10", _account_view(nav=100_000.0))
        alpha = compute_alpha_statistics(
            collector,
            benchmark_navs=(100.0, 101.0, 102.0),
        )
        assert alpha.beta is None
        assert alpha.tracking_error is None

    def test_benchmark_none_returns_none_fields(self) -> None:
        """不传 benchmark → 基准字段全为 None."""
        collector = ExecutionAuditCollector()
        collector.record_account_view("2026-01-10", _account_view(nav=100_000.0))
        collector.record_account_view("2026-01-11", _account_view(nav=101_000.0))
        alpha = compute_alpha_statistics(
            collector,
        )
        assert alpha.beta is None
        assert alpha.tracking_error is None
        assert alpha.information_ratio is None
        assert alpha.alpha_annualized is None

    def test_benchmark_matching_length_computes(self) -> None:
        """benchmark 与快照等长 → 正常计算基准字段."""
        collector = ExecutionAuditCollector()
        for i in range(3):
            collector.record_account_view(
                f"2026-01-{10 + i}",
                _account_view(nav=100_000.0 * (1 + 0.001 * i)),
            )
        alpha = compute_alpha_statistics(
            collector,
            benchmark_navs=(100.0, 100.1, 100.201),
        )
        assert alpha.beta is not None
        assert alpha.tracking_error is not None
        assert alpha.alpha_annualized is not None
