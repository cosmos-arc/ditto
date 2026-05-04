"""Reconciliation — 交易对账。"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ReconciliationReport"]


@dataclass(frozen=True)
class ReconciliationReport:
    """Summary of expected versus actual execution records."""

    report_id: str
    account_id: str
    trade_date: str
    expected_count: int
    actual_count: int
    unmatched_count: int = 0
    status: str = "pending"
