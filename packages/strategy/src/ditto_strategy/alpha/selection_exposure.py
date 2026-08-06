"""Strategy-owned contracts for lane-specific selection exposure evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from math import isfinite
from typing import cast

from ditto_strategy.errors import StrategySpecError

__all__ = [
    "SelectionExposureApplicability",
    "SelectionExposureDeclaration",
    "SelectionExposureEvidence",
    "SelectionExposureLane",
    "SelectionExposurePolicy",
    "SelectionExposureSizeBucket",
]

type ExposureInstrumentId = int | str


def _evidence_error(
    message: str,
    *,
    reason: str,
    **details: object,
) -> StrategySpecError:
    payload: dict[str, object] = {"reason": reason}
    payload.update(details)
    return StrategySpecError(message, details=payload)


def _validate_trade_date(value: object) -> None:
    if not isinstance(value, str):
        raise _evidence_error(
            "selection evidence trade_date must be an ISO date",
            reason="invalid_evidence_trade_date",
            trade_date=value,
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _evidence_error(
            "selection evidence trade_date must be an ISO date",
            reason="invalid_evidence_trade_date",
            trade_date=value,
        ) from exc
    if parsed.isoformat() != value:
        raise _evidence_error(
            "selection evidence trade_date must use YYYY-MM-DD",
            reason="invalid_evidence_trade_date",
            trade_date=value,
        )


def _validate_instrument_id(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError("instrument_id must be a non-boolean int or non-empty str")
    if isinstance(value, str) and not value:
        raise ValueError("instrument_id must be a non-empty str")


def _validate_text(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _validate_finite_number(value: object, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a finite number")
    if not isfinite(float(value)):
        raise ValueError(f"{field_name} must be a finite number")


class SelectionExposureApplicability(StrEnum):
    """Whether stock-style exposure evidence applies to a strategy lane."""

    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SelectionExposureLane(StrEnum):
    """Stable lane identity carried by every exposure declaration."""

    STOCK_LANE = "STOCK_LANE"
    ETF_LANE = "ETF_LANE"


class SelectionExposureSizeBucket(StrEnum):
    """Canonical equal-count market-cap buckets for selected instruments."""

    SMALL = "SMALL"
    MID = "MID"
    LARGE = "LARGE"


@dataclass(frozen=True, slots=True)
class SelectionExposurePolicy:
    """Strategy-owned source-column and applicability policy."""

    applicability: SelectionExposureApplicability
    lane: SelectionExposureLane
    industry_column: str | None
    size_column: str | None
    size_bucket_method: str | None

    def __post_init__(self) -> None:
        """Validate the lane-specific exposure source semantics."""
        if (
            type(cast("object", self.applicability))
            is not SelectionExposureApplicability
        ):
            raise TypeError("applicability must be SelectionExposureApplicability")
        if type(cast("object", self.lane)) is not SelectionExposureLane:
            raise TypeError("lane must be SelectionExposureLane")
        if self.applicability is SelectionExposureApplicability.APPLICABLE:
            if self.lane is not SelectionExposureLane.STOCK_LANE:
                raise ValueError("applicable exposure is restricted to STOCK_LANE")
            _validate_text(self.industry_column, field_name="industry_column")
            _validate_text(self.size_column, field_name="size_column")
            _validate_text(
                self.size_bucket_method,
                field_name="size_bucket_method",
            )
            return
        if self.lane is not SelectionExposureLane.ETF_LANE:
            raise ValueError("not-applicable exposure is restricted to ETF_LANE")
        if any(
            value is not None
            for value in (
                self.industry_column,
                self.size_column,
                self.size_bucket_method,
            )
        ):
            raise ValueError("not-applicable exposure cannot declare stock columns")

    @classmethod
    def stock(cls) -> SelectionExposurePolicy:
        """Return the frozen stock exposure contract."""
        return cls(
            applicability=SelectionExposureApplicability.APPLICABLE,
            lane=SelectionExposureLane.STOCK_LANE,
            industry_column="sector_id",
            size_column="market_cap",
            size_bucket_method="selected_market_cap_tertiles_v1",
        )

    @classmethod
    def etf(cls) -> SelectionExposurePolicy:
        """Return the explicit ETF not-applicable contract."""
        return cls(
            applicability=SelectionExposureApplicability.NOT_APPLICABLE,
            lane=SelectionExposureLane.ETF_LANE,
            industry_column=None,
            size_column=None,
            size_bucket_method=None,
        )


@dataclass(frozen=True, slots=True)
class SelectionExposureDeclaration:
    """One rebalance's immutable exposure applicability declaration."""

    trade_date: str
    applicability: SelectionExposureApplicability
    lane: SelectionExposureLane
    industry_column: str | None
    size_column: str | None
    size_bucket_method: str | None

    def __post_init__(self) -> None:
        """Validate the dated exposure applicability declaration."""
        _validate_trade_date(self.trade_date)
        SelectionExposurePolicy(
            applicability=self.applicability,
            lane=self.lane,
            industry_column=self.industry_column,
            size_column=self.size_column,
            size_bucket_method=self.size_bucket_method,
        )

    @classmethod
    def from_policy(
        cls,
        trade_date: str,
        policy: SelectionExposurePolicy,
    ) -> SelectionExposureDeclaration:
        """Bind a validated policy to one rebalance date."""
        if type(cast("object", policy)) is not SelectionExposurePolicy:
            raise TypeError("policy must be SelectionExposurePolicy")
        return cls(
            trade_date=trade_date,
            applicability=policy.applicability,
            lane=policy.lane,
            industry_column=policy.industry_column,
            size_column=policy.size_column,
            size_bucket_method=policy.size_bucket_method,
        )


@dataclass(frozen=True, slots=True)
class SelectionExposureEvidence:
    """Raw selected weight, industry, and size evidence for one instrument."""

    trade_date: str
    instrument_id: ExposureInstrumentId
    selected_weight: float
    industry_id: int | str
    size_value: float
    size_bucket: SelectionExposureSizeBucket

    def __post_init__(self) -> None:
        """Validate one selected instrument's exposure dimensions."""
        _validate_trade_date(self.trade_date)
        _validate_instrument_id(self.instrument_id)
        _validate_finite_number(self.selected_weight, field_name="selected_weight")
        if self.selected_weight < 0:
            raise ValueError("selected_weight must be non-negative")
        _validate_instrument_id(self.industry_id)
        _validate_finite_number(self.size_value, field_name="size_value")
        if self.size_value <= 0:
            raise ValueError("size_value must be positive")
        if type(cast("object", self.size_bucket)) is not SelectionExposureSizeBucket:
            raise TypeError("size_bucket must be SelectionExposureSizeBucket")
