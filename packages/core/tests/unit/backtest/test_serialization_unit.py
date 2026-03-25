"""Tests for BacktestReportSerializer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import orjson
import polars as pl
from ditto_core.accounting.fills import FillEvent
from ditto_core.backtest.audit.records import PreTradeDecisionRecord, RiskScanRecord
from ditto_core.backtest.risk.post_trade import RiskActionType, RiskSeverity
from ditto_core.backtest.serialization import serialize
from ditto_core.backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    PortfolioStatistics,
    TradeStatistics,
)
from ditto_core.execution.trade_builder import TradeRecord
from ditto_kernel.enums import OrderSide

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
# Tests: serialize with minimal report (no trades/fills)
# ---------------------------------------------------------------------------


class TestSerializeMinimal:
    """serialize with empty trade_log and fill_log."""

    def test_produces_json_and_nav_parquet(self, tmp_path: Path) -> None:
        report = _make_report(with_trades=False, with_fills=False)
        result = serialize(report, tmp_path)

        assert result.name == "backtest_report.json"
        assert result.parent == tmp_path

        # JSON exists and contains expected keys
        data = orjson.loads(result.read_bytes())
        assert data["run_id"] == "test-run-001"
        assert data["initial_cash"] == 1_000_000.0
        assert data["final_nav"] == 1_005_000.0

        # nav.parquet exists
        nav_path = tmp_path / "nav.parquet"
        assert nav_path.exists()
        df = pl.read_parquet(nav_path)
        assert len(df) == 2
        assert "trade_date" in df.columns
        assert "nav" in df.columns

        # portfolio_stats.parquet exists
        ps_path = tmp_path / "portfolio_stats.parquet"
        assert ps_path.exists()
        df = pl.read_parquet(ps_path)
        assert len(df) == 2

        # trade_log.parquet should NOT exist (empty)
        assert not (tmp_path / "trade_log.parquet").exists()

        # fill_log.parquet should NOT exist (empty)
        assert not (tmp_path / "fill_log.parquet").exists()

    def test_json_contains_aggregated_and_alpha_stats(self, tmp_path: Path) -> None:
        report = _make_report(with_trades=False, with_fills=False)
        result = serialize(report, tmp_path)
        data = orjson.loads(result.read_bytes())

        agg = data["aggregated_trade_stats"]
        assert agg["total_trades"] == 1
        assert agg["win_rate"] == 0.0
        assert data["alpha_stats"]["sharpe_ratio"] == 0.5


# ---------------------------------------------------------------------------
# Tests: serialize with full report
# ---------------------------------------------------------------------------


class TestSerializeFull:
    """serialize with trade_log, fill_log, risk_log."""

    def test_produces_all_files(self, tmp_path: Path) -> None:
        report = _make_report(with_trades=True, with_fills=True, with_risk=True)
        serialize(report, tmp_path)

        assert (tmp_path / "backtest_report.json").exists()
        assert (tmp_path / "nav.parquet").exists()
        assert (tmp_path / "portfolio_stats.parquet").exists()
        assert (tmp_path / "trade_log.parquet").exists()
        assert (tmp_path / "fill_log.parquet").exists()

    def test_trade_log_parquet_content(self, tmp_path: Path) -> None:
        report = _make_report()
        serialize(report, tmp_path)

        df = pl.read_parquet(tmp_path / "trade_log.parquet")
        assert len(df) == 1
        assert df[0, "instrument_id"] == 1
        assert df[0, "direction"] == "buy"

    def test_fill_log_parquet_content(self, tmp_path: Path) -> None:
        report = _make_report()
        serialize(report, tmp_path)

        df = pl.read_parquet(tmp_path / "fill_log.parquet")
        assert len(df) == 1
        assert df[0, "instrument_id"] == 1
        assert df[0, "fill_price"] == 4.0

    def test_nav_series_content(self, tmp_path: Path) -> None:
        report = _make_report()
        serialize(report, tmp_path)

        df = pl.read_parquet(tmp_path / "nav.parquet")
        assert len(df) == 2
        assert df[0, "trade_date"] == "2026-03-20"
        assert df[0, "nav"] == 1_010_000.0
        assert df[1, "trade_date"] == "2026-03-21"
        assert df[1, "nav"] == 1_005_000.0


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestSerializeEdgeCases:
    """serialize edge cases."""

    def test_large_instrument_id(self, tmp_path: Path) -> None:
        """Large integer instrument_id should serialize correctly."""
        report = _make_report(instrument_id=999999)
        result = serialize(report, tmp_path)

        data = orjson.loads(result.read_bytes())
        assert data["run_id"] == "test-run-001"

        df = pl.read_parquet(tmp_path / "trade_log.parquet")
        assert len(df) == 1

    def test_output_dir_created_if_not_exists(self, tmp_path: Path) -> None:
        nested = tmp_path / "nested" / "output"
        report = _make_report(with_trades=False, with_fills=False)
        result = serialize(report, nested)

        assert result.exists()
        assert (nested / "backtest_report.json").exists()
