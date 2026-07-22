"""Typed provenance for versioned R3 factor-diagnostic projections."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import cast

__all__ = [
    "R3FactorDiagnosticsProvenance",
]

_EVALUATION_PERIOD_SIZE = 2


def _identity_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty unpadded string")
    return value


def _identity_period(value: object) -> tuple[str, str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("evaluation period must have exact start and end dates")
    period = tuple(cast("Sequence[object]", value))
    if len(period) != _EVALUATION_PERIOD_SIZE:
        raise ValueError("evaluation period must have exact start and end dates")
    try:
        start, end = (date.fromisoformat(cast("str", item)) for item in period)
    except (TypeError, ValueError) as exc:
        raise ValueError("evaluation period must contain ISO calendar dates") from exc
    if start > end or tuple(item.isoformat() for item in (start, end)) != period:
        raise ValueError("evaluation period must be ordered canonical ISO dates")
    return cast("tuple[str, str]", period)


@dataclass(frozen=True, slots=True)
class R3FactorDiagnosticsProvenance:
    """Every source field bound into a diagnostic projection content hash."""

    factor_id: str
    factor_version: int
    evaluation_period: tuple[str, str]
    dataset_id: str
    catalog_snapshot_id: str
    universe: str
    cost_bps: float

    def __post_init__(self) -> None:
        """Validate factor, dataset, period, universe, and cost identity."""
        for field_name in (
            "factor_id",
            "dataset_id",
            "catalog_snapshot_id",
            "universe",
        ):
            object.__setattr__(
                self,
                field_name,
                _identity_text(getattr(self, field_name), field_name),
            )
        if type(self.factor_version) is not int or self.factor_version <= 0:
            raise ValueError("factor_version must be a positive integer")
        object.__setattr__(
            self, "evaluation_period", _identity_period(self.evaluation_period)
        )
        if (
            type(self.cost_bps) not in {int, float}
            or isinstance(self.cost_bps, bool)
            or not math.isfinite(self.cost_bps)
            or self.cost_bps < 0.0
        ):
            raise ValueError("cost_bps must be a finite non-negative number")
        object.__setattr__(self, "cost_bps", float(self.cost_bps))

    def canonical_payload(self) -> dict[str, object]:
        """Return the features-owned factor evaluation provenance payload."""
        return {
            "catalog_snapshot_id": self.catalog_snapshot_id,
            "cost_bps": self.cost_bps,
            "dataset_id": self.dataset_id,
            "evaluation_period": list(self.evaluation_period),
            "factor_id": self.factor_id,
            "factor_version": self.factor_version,
            "universe": self.universe,
        }
