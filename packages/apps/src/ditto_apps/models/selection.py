"""HTTP request and response models for industry and SelectionRun workspaces."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast

from ditto_kernel.identity import InstrumentId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

__all__ = [
    "CreateResearchCaseBody",
    "CreateSelectionRunBody",
    "EtfSelectionSpecRequest",
    "IndustryRotationContributionResponse",
    "IndustryRotationObservationRequest",
    "IndustryRotationRankResponse",
    "IndustryRotationResponse",
    "ResearchCaseResponse",
    "SelectionCandidateResponse",
    "SelectionExclusionChangeResponse",
    "SelectionExclusionResponse",
    "SelectionFactorContributionResponse",
    "SelectionFactorValueRequest",
    "SelectionFactorWeightRequest",
    "SelectionInstrumentRequest",
    "SelectionRankChangeResponse",
    "SelectionRunDiffResponse",
    "SelectionRunResponse",
    "SelectionWorkspaceReceiptResponse",
    "StockSelectionSpecRequest",
]

_REQUEST_CONFIG = ConfigDict(strict=True, extra="forbid")
_RESPONSE_CONFIG = ConfigDict(strict=True, frozen=True, from_attributes=True)


def _parse_http_array(value: object) -> object:
    if isinstance(value, list):
        return tuple(cast("list[object]", value))
    return value


CandidateInstrumentIds = Annotated[
    tuple[InstrumentId, ...], BeforeValidator(_parse_http_array)
]


class CreateResearchCaseBody(BaseModel):
    """User hypothesis bound to an optional subset of selected candidates."""

    model_config = _REQUEST_CONFIG

    objective: str = Field(min_length=1)
    candidate_instrument_ids: CandidateInstrumentIds = ()


class ResearchCaseResponse(BaseModel):
    """Content-addressed SelectionRun-to-research lineage response."""

    model_config = _RESPONSE_CONFIG

    case_id: str
    content_hash: str
    schema_version: int
    selection_run_id: str
    selection_run_hash: str
    selection_input_hash: str
    selection_spec_hash: str
    objective: str
    asset_kind: Literal["stock", "etf"]
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    universe_snapshot_id: str
    industry_rotation_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...]
    candidate_instrument_ids: tuple[InstrumentId, ...]
    selection_status: Literal["ready", "degraded"]
    missing_inputs: tuple[str, ...]


class IndustryRotationObservationRequest(BaseModel):
    """Normalized industry facts at one exact PIT cutoff."""

    model_config = _REQUEST_CONFIG

    industry_id: str = Field(min_length=1)
    industry_name: str = Field(min_length=1)
    relative_strength_5d: float | None
    relative_strength_20d: float | None
    relative_strength_60d: float | None
    advancing_count: int | None = Field(default=None, ge=0)
    declining_count: int | None = Field(default=None, ge=0)
    member_count: int | None = Field(default=None, ge=0)
    trend_score: float | None
    fundamental_score: float | None
    regime_alignment_score: float | None


class SelectionFactorWeightRequest(BaseModel):
    """One additive factor weight."""

    model_config = _REQUEST_CONFIG

    name: str = Field(min_length=1)
    weight: float = Field(ge=0.0, le=1.0)


class SelectionFactorValueRequest(BaseModel):
    """One normalized factor observation."""

    model_config = _REQUEST_CONFIG

    name: str = Field(min_length=1)
    value: float = Field(ge=-1.0, le=1.0)


type LimitStateRequest = Literal["normal", "limit_up", "limit_down"]


class StockSelectionSpecRequest(BaseModel):
    """Stock-specific saved selection policy."""

    model_config = _REQUEST_CONFIG

    asset_kind: Literal["stock"]
    spec_id: str = Field(min_length=1)
    spec_version: str = Field(min_length=1)
    top_k: int = Field(gt=0)
    min_average_turnover: float = Field(ge=0.0)
    min_listing_days: int = Field(gt=0)
    factor_weights: tuple[SelectionFactorWeightRequest, ...] = Field(min_length=1)
    excluded_limit_states: tuple[LimitStateRequest, ...] = (
        "limit_up",
        "limit_down",
    )


class EtfSelectionSpecRequest(BaseModel):
    """ETF-specific saved selection policy."""

    model_config = _REQUEST_CONFIG

    asset_kind: Literal["etf"]
    spec_id: str = Field(min_length=1)
    spec_version: str = Field(min_length=1)
    top_k: int = Field(gt=0)
    min_average_turnover: float = Field(ge=0.0)
    min_listing_days: int = Field(gt=0)
    factor_weights: tuple[SelectionFactorWeightRequest, ...] = Field(min_length=1)
    max_tracking_error: float | None = Field(default=None, ge=0.0)
    excluded_limit_states: tuple[LimitStateRequest, ...] = (
        "limit_up",
        "limit_down",
    )


type SelectionSpecRequest = Annotated[
    StockSelectionSpecRequest | EtfSelectionSpecRequest,
    Field(discriminator="asset_kind"),
]


class SelectionInstrumentRequest(BaseModel):
    """Normalized factor and hard-filter facts for one instrument."""

    model_config = _REQUEST_CONFIG

    instrument_id: InstrumentId = Field(gt=0)
    instrument_name: str = Field(min_length=1)
    industry_id: str | None = None
    factor_values: tuple[SelectionFactorValueRequest, ...]
    average_turnover: float | None = Field(default=None, ge=0.0)
    is_st: bool | None = None
    is_suspended: bool | None = None
    listing_days: int | None = Field(default=None, ge=0)
    limit_state: LimitStateRequest | None = None
    tracking_error: float | None = Field(default=None, ge=0.0)
    declared_missing_inputs: tuple[str, ...] = ()


class CreateSelectionRunBody(BaseModel):
    """One exact industry-rotation and stock/ETF selection mutation."""

    model_config = _REQUEST_CONFIG

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    rotation_source_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    market_context_feature_set_id: str | None = None
    membership_version: str = Field(min_length=1)
    rotation_algorithm_version: str = "industry-rotation-v1"
    industries: tuple[IndustryRotationObservationRequest, ...]
    rotation_missing_inputs: tuple[str, ...] = ()
    universe_snapshot_id: str = Field(min_length=1)
    selection_source_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    selection_spec: SelectionSpecRequest
    seed: int = Field(ge=0)
    instruments: tuple[SelectionInstrumentRequest, ...]


class IndustryRotationContributionResponse(BaseModel):
    """One additive industry score contribution."""

    model_config = _RESPONSE_CONFIG

    metric: str
    value: float | None
    weight: float
    contribution: float


class IndustryRotationRankResponse(BaseModel):
    """One ranked industry with exact score evidence."""

    model_config = _RESPONSE_CONFIG

    industry_id: str
    industry_name: str
    rank: int
    score: float
    contributions: tuple[IndustryRotationContributionResponse, ...]
    missing_inputs: tuple[str, ...]


class IndustryRotationResponse(BaseModel):
    """Content-addressed industry rotation snapshot."""

    model_config = _RESPONSE_CONFIG

    snapshot_id: str
    input_hash: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    market_context_feature_set_id: str | None
    membership_version: str
    algorithm_version: str
    status: Literal["ready", "degraded", "blocked"]
    rankings: tuple[IndustryRotationRankResponse, ...]
    missing_inputs: tuple[str, ...]


class SelectionFactorContributionResponse(BaseModel):
    """One additive selected-instrument score contribution."""

    model_config = _RESPONSE_CONFIG

    factor_name: str
    value: float
    weight: float
    contribution: float


class SelectionCandidateResponse(BaseModel):
    """One selected candidate and exact ranking evidence."""

    model_config = _RESPONSE_CONFIG

    instrument_id: InstrumentId
    instrument_name: str
    industry_id: str | None
    rank: int
    score: float
    factor_contributions: tuple[SelectionFactorContributionResponse, ...]


class SelectionExclusionResponse(BaseModel):
    """One stable why-out record."""

    model_config = _RESPONSE_CONFIG

    instrument_id: InstrumentId
    instrument_name: str
    reason_code: str
    stage: str
    detail: str


class SelectionRunResponse(BaseModel):
    """Exact saved SelectionRun response."""

    model_config = _RESPONSE_CONFIG

    run_id: str
    input_hash: str
    spec_hash: str
    asset_kind: Literal["stock", "etf"]
    spec_id: str
    spec_version: str
    seed: int
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    universe_snapshot_id: str
    industry_rotation_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...]
    status: Literal["ready", "degraded", "blocked"]
    candidates: tuple[SelectionCandidateResponse, ...]
    exclusions: tuple[SelectionExclusionResponse, ...]
    missing_inputs: tuple[str, ...]


class SelectionWorkspaceReceiptResponse(BaseModel):
    """Mutation response containing both exact artifacts."""

    model_config = _RESPONSE_CONFIG

    industry_rotation: IndustryRotationResponse
    selection_run: SelectionRunResponse


class SelectionRankChangeResponse(BaseModel):
    """Rank change for a candidate selected in both runs."""

    model_config = _RESPONSE_CONFIG

    instrument_id: InstrumentId
    before_rank: int
    after_rank: int


class SelectionExclusionChangeResponse(BaseModel):
    """Why-in/why-out change between two exact runs."""

    model_config = _RESPONSE_CONFIG

    instrument_id: InstrumentId
    before_reason: str | None
    after_reason: str | None


class SelectionRunDiffResponse(BaseModel):
    """Exact previous-run comparison response."""

    model_config = _RESPONSE_CONFIG

    before_run_id: str
    after_run_id: str
    data_changed: bool
    industry_rotation_changed: bool
    spec_changed: bool
    seed_changed: bool
    added_candidate_ids: tuple[InstrumentId, ...]
    removed_candidate_ids: tuple[InstrumentId, ...]
    rank_changes: tuple[SelectionRankChangeResponse, ...]
    exclusion_changes: tuple[SelectionExclusionChangeResponse, ...]
