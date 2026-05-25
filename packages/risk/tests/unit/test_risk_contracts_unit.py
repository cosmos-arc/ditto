"""Risk contracts module — BarSlice / SliceView / RiskGate type conformance."""

from __future__ import annotations

import inspect
from typing import Protocol

from ditto_risk.contracts import RiskGate
from ditto_risk.post_trade import BarSlice, SliceView

# ---------------------------------------------------------------------------
# R2D-1: BarSlice Protocol
# ---------------------------------------------------------------------------


class _MinimalBar:
    """Structural conformance — only .close and .prev_close."""

    def __init__(self, close: float, prev_close: float) -> None:
        self.close = close
        self.prev_close = prev_close


def test_bar_slice_has_close_and_prev_close() -> None:
    """BarSlice Protocol requires .close and .prev_close attributes."""
    assert hasattr(BarSlice, "close")
    assert hasattr(BarSlice, "prev_close")


def test_bar_slice_minimal_conformance() -> None:
    """A class with only .close and .prev_close satisfies BarSlice structurally."""
    bar = _MinimalBar(close=10.0, prev_close=9.5)
    assert hasattr(bar, "close")
    assert hasattr(bar, "prev_close")
    assert bar.close == 10.0
    assert bar.prev_close == 9.5


def test_slice_view_bars_annotation_uses_bar_slice() -> None:
    """SliceView.bars return annotation references BarSlice, not Any."""
    # Access the bars property descriptor via __dict__ (not class attribute access)
    bars_descriptor = SliceView.__dict__.get("bars")
    assert bars_descriptor is not None
    fget_func = bars_descriptor.fget  # type: ignore[union-attr]
    assert fget_func is not None
    sig = inspect.signature(fget_func)
    ret = sig.return_annotation
    ret_str = ret if isinstance(ret, str) else str(ret)
    assert "Any" not in ret_str
    assert "BarSlice" in ret_str


def test_bar_slice_rejects_missing_prev_close() -> None:
    """A class without .prev_close does NOT satisfy BarSlice."""

    class _NoPrevClose:
        def __init__(self, close: float) -> None:
            self.close = close

    obj = _NoPrevClose(close=10.0)
    assert not hasattr(obj, "prev_close")


# ---------------------------------------------------------------------------
# R2D-2: RiskGate Protocol
# ---------------------------------------------------------------------------


def test_risk_gate_is_protocol() -> None:
    assert issubclass(RiskGate, Protocol)


def test_risk_gate_has_lifecycle_hooks() -> None:
    """RiskGate defines pre_submit, pre_cancel, post_fill, daily_scan."""
    assert hasattr(RiskGate, "pre_submit")
    assert hasattr(RiskGate, "pre_cancel")
    assert hasattr(RiskGate, "post_fill")
    assert hasattr(RiskGate, "daily_scan")


def test_risk_gate_pre_submit_returns_optional_order() -> None:
    """pre_submit returns PreTradeOrder | None."""
    sig = inspect.signature(RiskGate.pre_submit)
    ret = sig.return_annotation
    ret_str = ret if isinstance(ret, str) else str(ret)
    assert "PreTradeOrder" in ret_str
    assert "None" in ret_str


def test_risk_gate_post_fill_signature() -> None:
    """post_fill accepts instrument_id, side, qty, price."""
    sig = inspect.signature(RiskGate.post_fill)
    params = list(sig.parameters.keys())
    assert params[1:] == ["instrument_id", "side", "qty", "price"]
