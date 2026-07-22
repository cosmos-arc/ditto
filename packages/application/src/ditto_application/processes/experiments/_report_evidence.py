"""Canonical backtest-report evidence hashing for R3 comparisons."""

from __future__ import annotations

from ditto_analysis.experiments import ContentHash, canonical_payload
from ditto_backtest.statistics import BacktestReport as _BacktestReport
from ditto_portfolio.accounting import FillEvent as _FillEvent

from ditto_application.processes.experiments._evidence_values import (
    comparison_error,
)


def backtest_report_content_hash(report: _BacktestReport) -> ContentHash:
    """Hash every report field used to recompute R3 comparison evidence."""
    if type(report) is not _BacktestReport or any(
        type(fill) is not _FillEvent for fill in report.fill_log
    ):
        comparison_error("invalid_backtest_report")
    payload = {
        "artifact_schema": {
            "id": "ditto.r3.backtest-report-evidence",
            "version": 1,
        },
        "fill_log": [
            {
                "correlation_id": fill.correlation_id,
                "cumulative_quantity": fill.cumulative_quantity,
                "direction": fill.direction.value,
                "event_time": fill.event_time.isoformat(),
                "fee": fill.fee,
                "fill_id": fill.fill_id,
                "fill_price": fill.fill_price,
                "filled_quantity": fill.filled_quantity,
                "instrument_id": str(fill.instrument_id),
                "leaves_quantity": fill.leaves_quantity,
                "order_id": fill.order_id,
                "slippage": fill.slippage,
            }
            for fill in report.fill_log
        ],
        "final_nav": report.final_nav,
        "initial_cash": report.initial_cash,
        "nav_series": [list(item) for item in report.nav_series],
        "period": list(report.period),
        "run_id": report.run_id,
    }
    return canonical_payload(payload).content_hash
