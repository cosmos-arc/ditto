"""Strict HTTP DTOs for three-portfolio comparison and read-only scenarios."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "NormalizedPortfolioResponse",
    "PortfolioComparisonQueryParams",
    "PortfolioComparisonResponse",
    "PortfolioScenarioBody",
    "PortfolioScenarioPreviewResponse",
]

_REQUEST_CONFIG = ConfigDict(strict=True, extra="forbid")
_RESPONSE_CONFIG = ConfigDict(strict=True, frozen=True, from_attributes=True)


class NormalizedPortfolioPositionResponse(BaseModel):
    """One normalized valued holding."""

    model_config = _RESPONSE_CONFIG

    instrument_id: int
    quantity: Decimal
    last_price: Decimal
    market_value: Decimal
    weight: Decimal
    average_cost_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    industry: str | None


class NormalizedPortfolioResponse(BaseModel):
    """One column of the unified portfolio comparison."""

    model_config = _RESPONSE_CONFIG

    portfolio_id: str
    portfolio_kind: Literal["model", "paper", "manual"]
    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    currency: Literal["CNY"]
    cash: Decimal
    cash_weight: Decimal
    total_value: Decimal
    invested_weight: Decimal
    positions: tuple[NormalizedPortfolioPositionResponse, ...]
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    pending_event_count: int
    alert_codes: tuple[str, ...]


class PortfolioAttributionResponse(BaseModel):
    """Mutually meaningful Paper execution or Manual user-choice attribution."""

    model_config = _RESPONSE_CONFIG

    unfilled_bps: Decimal
    slippage_amount: Decimal
    fee_amount: Decimal
    risk_blocked_bps: Decimal
    user_choice_bps: Decimal


class PortfolioDriftItemResponse(BaseModel):
    """Instrument-level pairwise weight drift."""

    model_config = _RESPONSE_CONFIG

    instrument_id: int
    baseline_weight: Decimal
    observed_weight: Decimal
    drift_weight: Decimal
    drift_bps: Decimal


class PortfolioDriftResponse(BaseModel):
    """One pairwise portfolio drift surface."""

    model_config = _RESPONSE_CONFIG

    comparison_kind: Literal[
        "model_vs_paper",
        "model_vs_manual",
        "paper_vs_manual",
    ]
    baseline_portfolio_id: str
    observed_portfolio_id: str
    total_abs_drift_bps: Decimal
    cash_drift_bps: Decimal
    items: tuple[PortfolioDriftItemResponse, ...]
    attribution: PortfolioAttributionResponse


class PortfolioComparisonResponse(BaseModel):
    """Unified same-snapshot MODEL/PAPER/MANUAL read model."""

    model_config = _RESPONSE_CONFIG

    strategy_id: str
    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    model: NormalizedPortfolioResponse
    paper: NormalizedPortfolioResponse
    manual: NormalizedPortfolioResponse
    model_vs_paper: PortfolioDriftResponse
    model_vs_manual: PortfolioDriftResponse
    paper_vs_manual: PortfolioDriftResponse


class PortfolioComparisonQueryParams(BaseModel):
    """GET query identity for an exact three-portfolio comparison."""

    strategy_id: str = Field(min_length=1)
    model_portfolio_id: str = Field(min_length=1)
    paper_account_id: str = Field(min_length=1)
    manual_account_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    as_of: date
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    valuation_snapshot_id: str | None = None


class PortfolioScenarioBody(BaseModel):
    """Exact comparison identity plus user-owned constraints and shocks."""

    model_config = _REQUEST_CONFIG

    strategy_id: str = Field(min_length=1)
    model_portfolio_id: str = Field(min_length=1)
    paper_account_id: str = Field(min_length=1)
    manual_account_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    as_of: date = Field(strict=False)
    knowledge_cutoff: datetime = Field(strict=False)
    publication_cutoff: datetime = Field(strict=False)
    source_snapshot_ids: tuple[str, ...] = Field(strict=False, min_length=1)
    valuation_snapshot_id: str | None = None
    baseline_kind: Literal["model", "paper", "manual"]
    excluded_instrument_ids: tuple[int, ...] = Field(default=(), strict=False)
    max_position_weight: Decimal = Field(strict=False, gt=0, le=1)
    cash_reserve_weight: Decimal = Field(strict=False, ge=0, lt=1)
    market_shock: float = 0.0
    industry_shocks: dict[str, float] = Field(default_factory=dict)


class ScenarioExposureResponse(BaseModel):
    """Before or after deterministic risk exposure."""

    model_config = _RESPONSE_CONFIG

    gross_exposure: float
    cash_weight: float
    industry_exposure: dict[str, float]
    stressed_return: float


class ScenarioRiskPreviewResponse(BaseModel):
    """Risk-owned scenario result."""

    model_config = _RESPONSE_CONFIG

    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    before: ScenarioExposureResponse
    after: ScenarioExposureResponse
    turnover: float
    constraint_findings: tuple[str, ...]


class PortfolioScenarioPreviewResponse(BaseModel):
    """Unapplied proposed weights and their deterministic risk preview."""

    model_config = _RESPONSE_CONFIG

    baseline_kind: Literal["model", "paper", "manual"]
    proposed_weights: dict[int, Decimal]
    risk: ScenarioRiskPreviewResponse
    applied_constraints: tuple[str, ...]
