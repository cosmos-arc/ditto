"""O3: @traced span coverage on execution reconciliation critical paths.

Installs a capture trace handler and asserts the reconciliation entry points
(``reconcile`` / ``plan_repair``) emit their expected operation names. This
proves the backtest/execution ``@traced`` instrumentation is wired end-to-end
(not merely decorated) and that the span taxonomy is consistent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from ditto_execution.reconciliation.reconciler import reconcile
from ditto_execution.reconciliation.repair import plan_repair
from ditto_kernel.tracing import install_trace_handler, reset_trace_handler


@pytest.fixture(autouse=True)
def _reset_trace_handler() -> Iterator[None]:
    reset_trace_handler()
    yield
    reset_trace_handler()


def _capture_handler() -> tuple[list[str], Callable[..., Any]]:
    captured: list[str] = []

    def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        captured.append(operation)
        return fn(*args, **kwargs)

    return captured, handler


def test_reconcile_emits_execution_reconcile_span() -> None:
    """reconcile() must emit the ``execution.reconcile`` operation."""
    captured, handler = _capture_handler()
    install_trace_handler(handler)

    report = reconcile("rep-1", "acc-1", "2024-01-01", [], [])

    assert "execution.reconcile" in captured
    assert report.report_id == "rep-1"


def test_plan_repair_emits_execution_plan_repair_span() -> None:
    """plan_repair() must emit the ``execution.plan_repair`` operation."""
    captured, handler = _capture_handler()
    install_trace_handler(handler)

    report = reconcile("rep-2", "acc-1", "2024-01-01", [], [])
    captured.clear()
    plan_repair(report)

    assert "execution.plan_repair" in captured
