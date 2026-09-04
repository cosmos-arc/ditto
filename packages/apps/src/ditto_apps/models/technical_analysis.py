"""HTTP contracts for exact deterministic technical-analysis snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast

from ditto_kernel.identity import InstrumentId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

__all__ = [
    "TechnicalAnalysisConflictResponse",
    "TechnicalAnalysisIndicatorParameterResponse",
    "TechnicalAnalysisIndicatorResponse",
    "TechnicalAnalysisLevelResponse",
    "TechnicalAnalysisQueryBody",
    "TechnicalAnalysisSnapshotResponse",
    "TechnicalAnalysisSpecRequest",
    "TechnicalAnalysisTimeframeResponse",
]

_REQUEST_CONFIG = ConfigDict(strict=True, extra="forbid")
_RESPONSE_CONFIG = ConfigDict(strict=True, frozen=True, from_attributes=True)

type Timeframe = Literal["daily", "weekly"]
type Direction = Literal["bullish", "bearish", "neutral", "unknown"]


def _parse_http_datetime(value: object) -> object:
    if not isinstance(value, str):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_http_array(value: object) -> object:
    if isinstance(value, list):
        return tuple(cast("list[object]", value))
    return value


HttpDateTime = Annotated[datetime, BeforeValidator(_parse_http_datetime)]
Timeframes = Annotated[tuple[Timeframe, ...], BeforeValidator(_parse_http_array)]
SnapshotIds = Annotated[tuple[str, ...], BeforeValidator(_parse_http_array)]


class TechnicalAnalysisSpecRequest(BaseModel):
    """Complete versioned v1 technical-indicator parameter set."""

    model_config = _REQUEST_CONFIG

    spec_id: str = Field(min_length=1)
    spec_version: str = Field(min_length=1)
    algorithm_version: Literal["technical-analysis.v1"] = "technical-analysis.v1"
    timeframes: Timeframes = Field(min_length=1)
    return_window: int = Field(default=20, gt=0)
    trend_window: int = Field(default=20, gt=0)
    slope_window: int = Field(default=5, ge=2)
    rsi_window: int = Field(default=14, gt=0)
    macd_fast: int = Field(default=12, gt=0)
    macd_slow: int = Field(default=26, gt=0)
    macd_signal: int = Field(default=9, gt=0)
    atr_window: int = Field(default=14, gt=0)
    volatility_window: int = Field(default=20, gt=0)
    volume_window: int = Field(default=20, gt=0)
    donchian_window: int = Field(default=20, gt=0)
    support_resistance_window: int = Field(default=60, gt=0)


class TechnicalAnalysisQueryBody(BaseModel):
    """One exact read request; source facts remain server-owned."""

    model_config = _REQUEST_CONFIG

    instrument_id: InstrumentId = Field(gt=0)
    instrument_name: str = Field(min_length=1)
    instrument_code: str = Field(min_length=1)
    as_of: HttpDateTime
    knowledge_cutoff: HttpDateTime
    publication_cutoff: HttpDateTime
    source_snapshot_ids: SnapshotIds = Field(min_length=1)
    spec: TechnicalAnalysisSpecRequest
    selection_run_id: str | None = None
    research_case_id: str | None = None
    portfolio_snapshot_id: str | None = None


class TechnicalAnalysisIndicatorParameterResponse(BaseModel):
    """One canonical numeric indicator parameter."""

    model_config = _RESPONSE_CONFIG

    name: str
    value: int


class TechnicalAnalysisIndicatorResponse(BaseModel):
    """One indicator result with explicit warm-up or unavailable state."""

    model_config = _RESPONSE_CONFIG

    name: str
    timeframe: Timeframe
    indicator_version: str
    window: int | None
    parameters: tuple[TechnicalAnalysisIndicatorParameterResponse, ...]
    value: float | None
    status: Literal["ready", "warming_up", "unavailable"]
    reason: str | None


class TechnicalAnalysisLevelResponse(BaseModel):
    """One versioned support or resistance level."""

    model_config = _RESPONSE_CONFIG

    timeframe: Timeframe
    kind: Literal["support", "resistance"]
    price: float
    confidence: float
    touches: int
    window: int
    algorithm_version: str


class TechnicalAnalysisTimeframeResponse(BaseModel):
    """Compact technical state for one timeframe."""

    model_config = _RESPONSE_CONFIG

    timeframe: Timeframe
    trend: Direction
    momentum: Direction
    breakout: Direction


class TechnicalAnalysisConflictResponse(BaseModel):
    """One deterministic daily/weekly disagreement."""

    model_config = _RESPONSE_CONFIG

    dimension: Literal["trend", "momentum", "breakout"]
    daily: Direction
    weekly: Direction
    reason_code: str


class TechnicalAnalysisSnapshotResponse(BaseModel):
    """Content-addressed exact technical-analysis result."""

    model_config = _RESPONSE_CONFIG

    snapshot_id: str
    input_hash: str
    spec_hash: str
    registry_version: str
    instrument_id: InstrumentId
    instrument_name: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    status: Literal["ready", "degraded", "blocked"]
    last_visible_bar_at: datetime | None
    last_computed_bar_at: datetime | None
    readings: tuple[TechnicalAnalysisIndicatorResponse, ...]
    levels: tuple[TechnicalAnalysisLevelResponse, ...]
    timeframe_summaries: tuple[TechnicalAnalysisTimeframeResponse, ...]
    conflicts: tuple[TechnicalAnalysisConflictResponse, ...]
    missing_inputs: tuple[str, ...]
    warnings: tuple[str, ...]
    selection_run_id: str | None
    research_case_id: str | None
    portfolio_snapshot_id: str | None
