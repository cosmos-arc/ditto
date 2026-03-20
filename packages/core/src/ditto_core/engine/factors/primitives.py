"""Primitive features shared across multiple factor categories."""

from __future__ import annotations

from ditto_core.engine.factors.spec import FactorSpec

__all__ = ["PRIMITIVES"]

PRIMITIVES: dict[str, FactorSpec] = {
    "returns_1": FactorSpec(
        id="returns_1",
        expression="ts_pct_change(market.close, 1)",
        dependencies=("market.close",),
        description="1-day price return (close-to-close percentage change)",
    ),
    "prev_close": FactorSpec(
        id="prev_close",
        expression="ts_delay(market.close, 1)",
        dependencies=("market.close",),
        description="Previous day closing price",
    ),
    "tr": FactorSpec(
        id="tr",
        expression=(
            "max2(market.high - market.low, "
            "max2(abs(market.high - prev_close), "
            "abs(market.low - prev_close)))"
        ),
        dependencies=("market.high", "market.low", "prev_close"),
        description="True Range: max of high-low, |high-prev_close|, |low-prev_close|",
    ),
}
