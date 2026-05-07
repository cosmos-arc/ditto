"""Risk contracts type-checking tests."""

from typing import Protocol

from ditto_risk.contracts import PostTradeGuard


def test_post_trade_guard_is_protocol() -> None:
    assert issubclass(PostTradeGuard, Protocol)
