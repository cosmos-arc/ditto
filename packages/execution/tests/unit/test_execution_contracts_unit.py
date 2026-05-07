"""Execution contracts type-checking tests."""

from typing import Protocol

from ditto_execution.contracts import FillReceiver, OrderRouter, TradeAuditor


def test_order_router_is_protocol() -> None:
    assert issubclass(OrderRouter, Protocol)


def test_fill_receiver_is_protocol() -> None:
    assert issubclass(FillReceiver, Protocol)


def test_trade_auditor_is_protocol() -> None:
    assert issubclass(TradeAuditor, Protocol)
