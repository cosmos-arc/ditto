"""Risk contracts — 类型化参数验证."""

from typing import Protocol, get_type_hints

from ditto_risk.contracts import PostTradeGuard, RiskSlice


def test_post_trade_guard_scan_has_typed_params() -> None:
    hints = get_type_hints(PostTradeGuard.scan)
    # account_view 不应是裸 object
    assert "AccountView" in str(hints.get("account_view", ""))
    # slice_ 应是 RiskSlice
    assert hints["slice_"] is RiskSlice


def test_risk_slice_is_protocol() -> None:
    assert issubclass(RiskSlice, Protocol)
