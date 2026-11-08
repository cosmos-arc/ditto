"""Exchange tick rounding shared by simulated execution paths."""

from decimal import ROUND_HALF_UP, Decimal
from math import isfinite


def round_to_tick(price: float | Decimal, tick_size: float) -> float:
    """Round half up to the actual instrument's tick size."""
    if not isfinite(price) or not isfinite(tick_size) or tick_size <= 0:
        raise ValueError("price must be finite and tick_size positive/finite")
    tick = Decimal(str(tick_size))
    ticks = (Decimal(str(price)) / tick).quantize(Decimal("1"), ROUND_HALF_UP)
    return float(ticks * tick)
