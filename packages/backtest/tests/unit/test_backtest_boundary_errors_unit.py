"""Backtest simulation boundary error tests."""

from __future__ import annotations

from pathlib import Path

from ditto_execution.errors import FillProcessingError


def test_brokerage_uses_fill_processing_error_for_fill_contract_violation() -> None:
    """Backtest brokerage fill-contract violations use the fill domain error."""
    text = Path("packages/backtest/src/ditto_backtest/brokerage.py").read_text(
        encoding="utf-8"
    )

    assert f"raise {FillProcessingError.__name__}(" in text
