"""Execution contracts type-checking tests."""

from typing import Protocol

from ditto_execution.contracts import OrderRouter, TradeAuditor


def test_order_router_is_protocol() -> None:
    assert issubclass(OrderRouter, Protocol)


def test_trade_auditor_is_protocol() -> None:
    assert issubclass(TradeAuditor, Protocol)
