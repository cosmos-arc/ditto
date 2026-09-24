"""Strict HTTP DTOs for three-portfolio comparison and read-only scenarios."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ditto_apps.models.account_ledger import (
    HistoryPointResponse,
    HistorySegmentResponse,
    LedgerRevisionResponse,
)

__all__ = [
    "ETFAllocationBody",
    "ETFAllocationReviewBody",
    "ETFAllocationVersionResponse",
    "ETFPaperAuthorizeBody",
    "ETFPaperAuthorizeResponse",
    "ETFPaperHandoffBody",
    "HistoryComparisonBenchmarkPointResponse",
    "HistoryComparisonBenchmarkResponse",
    "HistoryComparisonBenchmarkRunResponse",
    "HistoryComparisonLegResponse",
    "HistoryComparisonQueryParams",
    "HistoryComparisonResponse",
    "HistoryComparisonRunPointResponse",
    "HistoryComparisonRunResponse",
    "ModelHistoryQueryParams",
    "ModelHistoryResponse",
    "ModelTargetResponse",
    "NormalizedPortfolioResponse",
    "PortfolioComparisonQueryParams",
    "PortfolioComparisonResponse",
    "PortfolioScenarioBody",
    "PortfolioScenarioPreviewResponse",
]

_REQUEST_CONFIG = ConfigDict(strict=True, extra="forbid")
_RESPONSE_CONFIG = ConfigDict(strict=True, frozen=True, from_attributes=True)
_QUERY_CONFIG = ConfigDict(extra="forbid")


class ETFAllocationBody(BaseModel):
    """One explicit ETF research allocation revision."""

    model_config = ConfigDict(extra="forbid")

    parent_version_id: str | None = None
    asof: date
    knowledge_cutoff: datetime
    source_snapshot_id: str = Field(min_length=1)
    instrument_ids: tuple[int, ...] = Field(min_length=1)
    mode: Literal["equal", "manual"]
    cash_weight: Decimal
    max_position_weight: Decimal
    manual_weights: dict[int, Decimal] = Field(default_factory=dict)
    reason: str = Field(min_length=1)


class ETFAllocationVersionResponse(BaseModel):
    """Immutable saved target with explicit Paper review status."""

    model_config = _RESPONSE_CONFIG

    version_id: str
    allocation_id: str
    parent_version_id: str | None
    asof: str
    knowledge_cutoff: str
    source_snapshot_id: str
    mode: str
    weights: dict[int, str]
    cash_weight: str
    max_position_weight: str
    tracking_exposure: dict[str, str]
    reason: str
    rule_version: str
    paper_status: str
    review_status: str
    created_at: str


class ETFAllocationReviewBody(BaseModel):
    """Human decision bound to a saved ETF target and retry key."""

    action: Literal["submit", "approve", "reject"]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ETFPaperAuthorizeBody(BaseModel):
    """Separate explicit operator authorization for a reviewed target."""

    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    intended_trade_date: date


class ETFPaperAuthorizeResponse(BaseModel):
    """Durable authorization receipt identity for retry and handoff."""

    model_config = _RESPONSE_CONFIG

    version_id: str
    authorization_id: str


class ETFPaperHandoffBody(BaseModel):
    """Explicit PAPER account, session and current evidence identity."""

    model_config = ConfigDict(extra="forbid")

    authorization_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    signal_date: date
    decision_date: date
    intended_trade_date: date
    knowledge_cutoff: datetime
    source_snapshot_id: str = Field(min_length=1)


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


class ModelHistoryQueryParams(BaseModel):
    """
    GET query identity for one MODEL target replay.

    Query strings arrive as plain text, so coercion stays lax here; the
    application query still rejects every invalid identity fail-closed.
    """

    model_config = _QUERY_CONFIG

    strategy_id: str = Field(min_length=1)
    start_date: date = Field(strict=False)
    end_date: date = Field(strict=False)
    initial_capital: Decimal = Field(gt=0, strict=False)
    knowledge_cutoff: datetime = Field(strict=False)
    publication_cutoff: datetime = Field(strict=False)
    artifact_ids: tuple[str, ...] = Field(default=(), strict=False)


class ModelTargetResponse(BaseModel):
    """One replayed saved target and its verifiable identity."""

    model_config = _RESPONSE_CONFIG

    signal_date: str
    artifact_id: str
    checksum: str


class ModelHistoryResponse(BaseModel):
    """Complete replayable MODEL target-replay result."""

    model_config = _RESPONSE_CONFIG

    result_id: str
    strategy_id: str
    currency: Literal["CNY"]
    start_date: str
    end_date: str
    initial_capital: Decimal
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    empty_reason: str | None
    targets: tuple[ModelTargetResponse, ...]
    method: str
    valuation_policy_version: str
    points: tuple[HistoryPointResponse, ...]
    segments: tuple[HistorySegmentResponse, ...]


class HistoryComparisonQueryParams(BaseModel):
    """
    GET query identity for the three-leg common-window comparison.

    Query strings arrive as plain text, so coercion stays lax here; the
    application query still rejects every invalid identity fail-closed.
    Optional ledger revision pins (count + hash, both or neither per leg)
    replay that leg against a pinned append-order prefix; when omitted the
    server resolves the current revision. An optional benchmark declaration
    (symbol + type, both or neither) overlays one declared price series.
    """

    model_config = _QUERY_CONFIG

    strategy_id: str = Field(min_length=1)
    paper_account_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    manual_account_id: str = Field(min_length=1)
    start_date: date = Field(strict=False)
    end_date: date = Field(strict=False)
    model_initial_capital: Decimal = Field(gt=0, strict=False)
    knowledge_cutoff: datetime = Field(strict=False)
    publication_cutoff: datetime = Field(strict=False)
    source_snapshot_ids: tuple[str, ...] = Field(strict=False, min_length=1)
    model_artifact_ids: tuple[str, ...] = Field(default=(), strict=False)
    paper_ledger_event_count: int | None = Field(default=None, ge=1, strict=False)
    paper_ledger_hash: str | None = Field(default=None, min_length=1)
    manual_ledger_event_count: int | None = Field(default=None, ge=1, strict=False)
    manual_ledger_hash: str | None = Field(default=None, min_length=1)
    benchmark_symbol: str | None = Field(default=None, min_length=1)
    benchmark_type: str | None = Field(default=None, min_length=1)


class HistoryComparisonRunPointResponse(BaseModel):
    """One common date: growth anchors to 1 at the run start."""

    model_config = _RESPONSE_CONFIG

    on_date: str
    growth: dict[str, Decimal]
    assets: dict[str, Decimal]


class HistoryComparisonRunResponse(BaseModel):
    """One common continuous run with per-leg window returns."""

    model_config = _RESPONSE_CONFIG

    start_date: str
    end_date: str
    point_count: int
    points: tuple[HistoryComparisonRunPointResponse, ...]
    window_returns: dict[str, Decimal | None]


class HistoryComparisonLegResponse(BaseModel):
    """Per-leg provenance; identity stays the leg's own result_id."""

    model_config = _RESPONSE_CONFIG

    kind: Literal["model", "paper", "manual"]
    result_id: str
    currency: Literal["CNY"]
    empty_reason: str | None
    point_count: int
    valued_point_count: int
    gap_count: int
    segment_count: int
    first_valued_date: str | None
    last_valued_date: str | None
    ledger_revision: LedgerRevisionResponse | None
    target_count: int | None


class HistoryComparisonBenchmarkPointResponse(BaseModel):
    """One common date's benchmark growth; missing prices stay null."""

    model_config = _RESPONSE_CONFIG

    on_date: str
    growth: Decimal | None


class HistoryComparisonBenchmarkRunResponse(BaseModel):
    """One run's benchmark overlay, anchored to 1 at the run start."""

    model_config = _RESPONSE_CONFIG

    start_date: str
    end_date: str
    window_return: Decimal | None
    points: tuple[HistoryComparisonBenchmarkPointResponse, ...]


class HistoryComparisonBenchmarkResponse(BaseModel):
    """Declared benchmark price series aligned onto the comparison's runs."""

    model_config = _RESPONSE_CONFIG

    symbol: str
    type: Literal["price"]
    currency: Literal["CNY"]
    empty_reason: str | None
    runs: tuple[HistoryComparisonBenchmarkRunResponse, ...]


class HistoryComparisonResponse(BaseModel):
    """Complete replayable common-window comparison result."""

    model_config = _RESPONSE_CONFIG

    result_id: str
    strategy_id: str
    paper_account_id: str
    paper_session_id: str
    manual_account_id: str
    model_initial_capital: Decimal
    currency: Literal["CNY"]
    method: str
    valuation_policy_version: str
    comparison_policy_version: str
    status: Literal["comparable", "single_common_point", "incomparable"]
    empty_reason: str | None
    start_date: str
    end_date: str
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    runs: tuple[HistoryComparisonRunResponse, ...]
    legs: tuple[HistoryComparisonLegResponse, ...]
    benchmark: HistoryComparisonBenchmarkResponse | None = None
