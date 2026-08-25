"""Small deterministic statistics helpers for release evaluation."""

from __future__ import annotations

from decimal import Decimal


def nearest_rank(values: tuple[int, ...], percentile: int) -> int:
    """Return a nearest-rank percentile for integer observations."""
    if not values:
        return 0
    ordered = tuple(sorted(values))
    rank = (percentile * len(ordered) + 99) // 100
    return ordered[rank - 1]


def nearest_decimal(
    values: tuple[Decimal, ...],
    percentile: int,
) -> Decimal:
    """Return a nearest-rank percentile for exact decimal observations."""
    if not values:
        return Decimal(0)
    ordered = tuple(sorted(values))
    rank = (percentile * len(ordered) + 99) // 100
    return ordered[rank - 1]


__all__ = ["nearest_decimal", "nearest_rank"]
