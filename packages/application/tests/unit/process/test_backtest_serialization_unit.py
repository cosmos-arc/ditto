"""Tests for BacktestReportSerializer (pure computation)."""

from __future__ import annotations

from datetime import datetime

import orjson
from ditto_application.processes.execution.backtest_serialization import (
    serialize_report,
)
from ditto_backtest.audit.records import PreTradeDecisionRecord, RiskScanRecord
from ditto_backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    PortfolioStatistics,
    TradeStatistics,
)
from ditto_execution.trade_builder import TradeRecord
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.fills import FillEvent
from ditto_risk.post_trade import RiskActionType, RiskSeverity

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_portfolio_stats() -> list[PortfolioStatistics]:
    return [
        PortfolioStatistics(
            trade_date="2026-03-20",
            nav=1_010_000.0,
            daily_return=1.0,
            cumulative_return=1.0,
            drawdown=0.0,
            max_drawdown=0.0,
            exposure=500_000.0,
            cash_ratio=50.49,
            position_count=3,
        ),
        PortfolioStatistics(
            trade_date="2026-03-21",
            nav=1_005_000.0,
            daily_return=-0.495,
            cumulative_return=0.5,
            drawdown=-0.495,
            max_drawdown=-0.495,
            exposure=500_000.0,
            cash_ratio=50.25,
            position_count=3,
        ),
    ]


def _make_trade_stats() -> list[TradeStatistics]:
    return [
        TradeStatistics(
            trade_id="T-001",
            instrument_id=1,
            direction="buy",
            entry_date="2026-03-20",
            exit_date="2026-03-21",
            holding_days=1,
            return_pct=-1.0,
            gross_pnl=-5000.0,
            net_pnl=-5010.0,
            fees=10.0,
        ),
    ]


def _make_aggregated_stats() -> AggregatedTradeStatistics:
    return AggregatedTradeStatistics(
        total_trades=1,
        long_trades=1,
        short_trades=0,
        win_trades=0,
        loss_trades=1,
        win_rate=0.0,
        profit_factor=0.0,
        avg_win=0.0,
        avg_loss=5000.0,
        avg_win_loss_ratio=0.0,
        max_consecutive_wins=0,
        max_consecutive_losses=1,
        avg_holding_days=1.0,
        median_holding_days=1.0,
        best_trade=0.0,
        worst_trade=-5000.0,
        avg_trade_return_pct=-1.0,
    )


def _make_alpha_stats() -> AlphaStatistics:
    return AlphaStatistics(
        annualized_return=5.0,
        annualized_volatility=10.0,
        sharpe_ratio=0.5,
        sortino_ratio=0.6,
        max_drawdown=-0.495,
        max_drawdown_duration_days=1,
        calmar_ratio=10.1,
        information_ratio=None,
        tracking_error=None,
        beta=None,
        alpha_annualized=None,
        total_turnover=0.2,
        avg_turnover_per_rebalance=0.2,
        total_fees=10.0,
        net_return_after_cost=4.99,
        cost_drag=0.01,
    )


def _make_nav_series() -> list[tuple[str, float]]:
    return [("2026-03-20", 1_010_000.0), ("2026-03-21", 1_005_000.0)]


def _make_trade_log() -> list[TradeRecord]:
    return [
        TradeRecord(
            trade_id="T-001",
            instrument_id=1,
            direction=OrderSide.BUY,
            entry_date="2026-03-20",
            exit_date="2026-03-21",
            entry_price=4.0,
            exit_price=3.95,
            quantity=1000,
            gross_pnl=-5000.0,
            fees=10.0,
            net_pnl=-5010.0,
            holding_days=1,
            return_pct=-1.0,
            entry_order_ids=("ORD-001",),
            exit_order_ids=("ORD-002",),
        ),
    ]


def _make_fill_log() -> list[FillEvent]:
    return [
        FillEvent(
            fill_id="F-001",
            order_id="ORD-001",
            instrument_id=1,
            direction=OrderSide.BUY,
            filled_quantity=1000,
            fill_price=4.0,
            fee=5.0,
            slippage=0.01,
            event_time=datetime(2026, 3, 20, 10, 30, 0),
            cumulative_quantity=1000,
            leaves_quantity=0,
        ),
    ]


def _make_risk_log() -> list[RiskScanRecord]:
    return [
        RiskScanRecord(
            trade_date="2026-03-20",
            rule_id="max_drawdown",
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.ALERT,
            detail="drawdown test",
            current_value=0.5,
            threshold=0.1,
        ),
    ]


def _make_pre_trade_log() -> list[PreTradeDecisionRecord]:
    return [
        PreTradeDecisionRecord(
            trade_date="2026-03-20",
            order_id="ORD-001",
            instrument_id=1,
            direction="buy",
            original_quantity=1000,
            final_quantity=1000,
            decision="accepted",
            reason=None,
            check_sequence=("lot_size",),
        ),
    ]


def _make_report(
    *,
    with_trades: bool = True,
    with_fills: bool = True,
    with_risk: bool = False,
    with_pre_trade: bool = False,
    instrument_id: int = 1,
) -> BacktestReport:
    return BacktestReport(
        run_id="test-run-001",
        period=("2026-03-20", "2026-03-21"),
        initial_cash=1_000_000.0,
        final_nav=1_005_000.0,
        trade_stats=tuple(_make_trade_stats()) if with_trades else (),
        portfolio_stats=tuple(_make_portfolio_stats()),
        aggregated_trade_stats=_make_aggregated_stats(),
        alpha_stats=_make_alpha_stats(),
        nav_series=tuple(_make_nav_series()),
        trade_log=tuple(_make_trade_log()) if with_trades else (),
        fill_log=tuple(_make_fill_log()) if with_fills else (),
        risk_log=tuple(_make_risk_log()) if with_risk else (),
        pre_trade_log=tuple(_make_pre_trade_log()) if with_pre_trade else (),
    )


# ---------------------------------------------------------------------------
# Tests: serialize_report with minimal report (no trades/fills)
# ---------------------------------------------------------------------------


class TestSerializeReportMinimal:
    """serialize_report with empty trade_log and fill_log."""

    def test_returns_json_bytes_with_expected_keys(self) -> None:
        report = _make_report(with_trades=False, with_fills=False)
        json_bytes, _ = serialize_report(report)

        data = orjson.loads(json_bytes)
        assert data["run_id"] == "test-run-001"
        assert data["initial_cash"] == 1_000_000.0
        assert data["final_nav"] == 1_005_000.0
        assert data["period"] == {"start": "2026-03-20", "end": "2026-03-21"}

    def test_json_contains_aggregated_and_alpha_stats(self) -> None:
        report = _make_report(with_trades=False, with_fills=False)
        json_bytes, _ = serialize_report(report)
        data = orjson.loads(json_bytes)

        agg = data["aggregated_trade_stats"]
        assert agg["total_trades"] == 1
        assert agg["win_rate"] == 0.0
        assert data["alpha_stats"]["sharpe_ratio"] == 0.5

    def test_returns_nav_and_portfolio_stats_parquet(self) -> None:
        report = _make_report(with_trades=False, with_fills=False)
        _, parquet_tables = serialize_report(report)

        assert "nav" in parquet_tables
        assert "portfolio_stats" in parquet_tables
        assert "trade_log" not in parquet_tables
        assert "fill_log" not in parquet_tables

    def test_nav_dataframe_content(self) -> None:
        report = _make_report(with_trades=False, with_fills=False)
        _, parquet_tables = serialize_report(report)

        df = parquet_tables["nav"]
        assert len(df) == 2
        assert "trade_date" in df.columns
        assert "nav" in df.columns
        assert df[0, "trade_date"] == "2026-03-20"
        assert df[0, "nav"] == 1_010_000.0
        assert df[1, "trade_date"] == "2026-03-21"
        assert df[1, "nav"] == 1_005_000.0

    def test_portfolio_stats_dataframe_content(self) -> None:
        report = _make_report(with_trades=False, with_fills=False)
        _, parquet_tables = serialize_report(report)

        df = parquet_tables["portfolio_stats"]
        assert len(df) == 2


# ---------------------------------------------------------------------------
# Tests: serialize_report with full report
# ---------------------------------------------------------------------------


class TestSerializeReportFull:
    """serialize_report with trade_log, fill_log, risk_log."""

    def test_returns_all_parquet_tables(self) -> None:
        report = _make_report(with_trades=True, with_fills=True, with_risk=True)
        _, parquet_tables = serialize_report(report)

        assert "nav" in parquet_tables
        assert "portfolio_stats" in parquet_tables
        assert "trade_log" in parquet_tables
        assert "fill_log" in parquet_tables

    def test_trade_log_dataframe_content(self) -> None:
        report = _make_report()
        _, parquet_tables = serialize_report(report)

        df = parquet_tables["trade_log"]
        assert len(df) == 1
        assert df[0, "instrument_id"] == 1
        assert df[0, "direction"] == "buy"

    def test_fill_log_dataframe_content(self) -> None:
        report = _make_report()
        _, parquet_tables = serialize_report(report)

        df = parquet_tables["fill_log"]
        assert len(df) == 1
        assert df[0, "instrument_id"] == 1
        assert df[0, "fill_price"] == 4.0


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestSerializeReportEdgeCases:
    """serialize_report edge cases."""

    def test_large_instrument_id(self) -> None:
        """Large integer instrument_id should serialize correctly."""
        report = _make_report(instrument_id=999999)
        json_bytes, parquet_tables = serialize_report(report)

        data = orjson.loads(json_bytes)
        assert data["run_id"] == "test-run-001"

        df = parquet_tables["trade_log"]
        assert len(df) == 1

    def test_no_trades_no_fills_empty_parquet_tables(self) -> None:
        """Empty trade/fill lists produce no corresponding parquet entries."""
        report = _make_report(with_trades=False, with_fills=False)
        _, parquet_tables = serialize_report(report)

        assert "trade_log" not in parquet_tables
        assert "fill_log" not in parquet_tables
        assert "nav" in parquet_tables
        assert "portfolio_stats" in parquet_tables
