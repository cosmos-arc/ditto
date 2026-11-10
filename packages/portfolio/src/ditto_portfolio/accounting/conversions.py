"""
Maintenance-declared exchange-traded fund share conversions (#762).

A conversion rescales existing holdings by a declared ratio (4.0 means one
old share becomes four new shares). It is not a distribution: there is no
cash leg, no tax and no independent listing date. The issuer announcement is
the only authority; adjustment-factor jumps can verify a declared event but
can never create one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isfinite

from ditto_kernel.identity import InstrumentId

__all__ = ["ShareConversion", "validate_share_conversions"]


@dataclass(frozen=True)
class ShareConversion:
    """Declared ETF share split or merge effective before the session open."""

    instrument_id: InstrumentId
    effective_date: date
    ratio: float
    announcement_date: date
    source_snapshot_id: str
    source_ticker: str = ""
    rounding_note: str = ""

    def __post_init__(self) -> None:
        """Require a declared, knowable and economically meaningful ratio."""
        if not (
            self.instrument_id > 0
            and date(2013, 1, 1) <= self.announcement_date
            and self.announcement_date < self.effective_date
            and isfinite(self.ratio)
            and self.ratio > 0
            and self.ratio != 1
            and self.source_snapshot_id
        ):
            raise ValueError("unknown/invalid share conversion")
        object.__setattr__(self, "ratio", float(self.ratio))

    def converted(self, quantity: int) -> int:
        """Holder-level conversions must stay whole; rounding needs a rule."""
        shares = Decimal(str(self.ratio)) * quantity
        if shares != shares.to_integral_value():
            raise ValueError(
                f"fractional conversion requires evidence: {self.identity} "
                + f"({quantity} held shares * {self.ratio})"
            )
        return int(shares)

    @property
    def identity(self) -> str:
        """One conversion per security and effective date; conflicts rejected."""
        return f"{self.instrument_id}:{self.effective_date.isoformat()}"


def validate_share_conversions(
    conversions: tuple[ShareConversion, ...],
) -> tuple[ShareConversion, ...]:
    """Collapse identical declarations and reject conflicting identities."""
    unique: dict[str, ShareConversion] = {}
    for conversion in conversions:
        previous = unique.setdefault(conversion.identity, conversion)
        if previous != conversion:
            raise ValueError(f"conflicting conversion revision: {conversion.identity}")
    return tuple(sorted(unique.values(), key=lambda c: c.identity))
