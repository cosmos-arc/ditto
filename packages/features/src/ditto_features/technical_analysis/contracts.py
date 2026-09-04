"""Immutable replay contracts for deterministic technical analysis."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

import orjson
from ditto_kernel.identity import InstrumentId

__all__ = [
    "TechnicalAnalysisInput",
    "TechnicalAnalysisSnapshot",
    "TechnicalAnalysisSpec",
    "TechnicalAnalysisStatus",
    "TechnicalBar",
    "TechnicalConflict",
    "TechnicalDirection",
    "TechnicalIndicatorParameter",
    "TechnicalIndicatorReading",
    "TechnicalIndicatorStatus",
    "TechnicalLevel",
    "TechnicalLevelKind",
    "TechnicalTimeframe",
    "TechnicalTimeframeSummary",
    "canonical_input_hash",
    "canonical_snapshot_hash",
    "canonical_snapshot_payload",
    "canonical_spec_hash",
]

type TechnicalAnalysisStatus = Literal["ready", "degraded", "blocked"]
type TechnicalDirection = Literal["bullish", "bearish", "neutral", "unknown"]

_MIN_SLOPE_WINDOW = 2


class TechnicalTimeframe(StrEnum):
    """Supported deterministic aggregation intervals."""

    DAILY = "daily"
    WEEKLY = "weekly"


class TechnicalIndicatorStatus(StrEnum):
    """Explicit result state for one indicator reading."""

    READY = "ready"
    WARMING_UP = "warming_up"
    UNAVAILABLE = "unavailable"


class TechnicalLevelKind(StrEnum):
    """Versioned price-level direction."""

    SUPPORT = "support"
    RESISTANCE = "resistance"


def _aware(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"technical analysis {field} must be timezone-aware")
    return value.astimezone(UTC)


def _text(value: str, *, field: str) -> str:
    if not value or value.strip() != value:
        raise ValueError(f"technical analysis {field} must be normalized text")
    return value


def _optional_text(value: str | None, *, field: str) -> str | None:
    return None if value is None else _text(value, field=field)


def _finite(value: float, *, field: str, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ValueError(f"technical analysis {field} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or (minimum is not None and normalized < minimum):
        raise ValueError(f"technical analysis {field} is invalid")
    return normalized


def _positive_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or value <= 0:
        raise ValueError(f"technical analysis {field} must be a positive integer")
    return value


def _canonical_bytes(payload: object) -> bytes:
    return orjson.dumps(
        payload,
        option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
    )


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisSpec:
    """Complete versioned parameter set for the v1 indicator registry."""

    spec_id: str
    spec_version: str
    algorithm_version: str
    timeframes: tuple[TechnicalTimeframe, ...]
    return_window: int = 20
    trend_window: int = 20
    slope_window: int = 5
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_window: int = 14
    volatility_window: int = 20
    volume_window: int = 20
    donchian_window: int = 20
    support_resistance_window: int = 60

    def __post_init__(self) -> None:
        """Normalize identity and reject incomplete algorithm declarations."""
        for field in ("spec_id", "spec_version", "algorithm_version"):
            object.__setattr__(self, field, _text(getattr(self, field), field=field))
        if self.algorithm_version != "technical-analysis.v1":
            raise ValueError("technical analysis algorithm_version is unsupported")
        if not self.timeframes:
            raise ValueError("technical analysis requires supported timeframes")
        if len(set(self.timeframes)) != len(self.timeframes):
            raise ValueError("technical analysis timeframes must be unique")
        object.__setattr__(
            self,
            "timeframes",
            tuple(sorted(self.timeframes, key=lambda item: item.value)),
        )
        for field in (
            "return_window",
            "trend_window",
            "slope_window",
            "rsi_window",
            "macd_fast",
            "macd_slow",
            "macd_signal",
            "atr_window",
            "volatility_window",
            "volume_window",
            "donchian_window",
            "support_resistance_window",
        ):
            _positive_int(getattr(self, field), field=field)
        if self.macd_fast >= self.macd_slow:
            raise ValueError("technical analysis MACD fast window must be smaller")
        if self.slope_window < _MIN_SLOPE_WINDOW:
            raise ValueError("technical analysis slope window must be at least two")

    def identity_payload(self) -> dict[str, object]:
        """Return all fields that determine indicator behavior."""
        return {
            "spec_id": self.spec_id,
            "spec_version": self.spec_version,
            "algorithm_version": self.algorithm_version,
            "timeframes": self.timeframes,
            "return_window": self.return_window,
            "trend_window": self.trend_window,
            "slope_window": self.slope_window,
            "rsi_window": self.rsi_window,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
            "atr_window": self.atr_window,
            "volatility_window": self.volatility_window,
            "volume_window": self.volume_window,
            "donchian_window": self.donchian_window,
            "support_resistance_window": self.support_resistance_window,
        }


@dataclass(frozen=True, slots=True)
class TechnicalBar:
    """One source-bound OHLCV observation with three explicit clocks."""

    occurred_at: datetime
    knowledge_at: datetime
    publication_at: datetime
    source_snapshot_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    adjustment_factor: float
    suspended: bool
    benchmark_close: float | None = None
    industry_close: float | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous time, impossible price bars, and invalid adjustments."""
        for field in ("occurred_at", "knowledge_at", "publication_at"):
            object.__setattr__(self, field, _aware(getattr(self, field), field=field))
        object.__setattr__(
            self,
            "source_snapshot_id",
            _text(self.source_snapshot_id, field="source snapshot ID"),
        )
        for field in ("open", "high", "low", "close"):
            object.__setattr__(
                self,
                field,
                _finite(getattr(self, field), field=field, minimum=0.0),
            )
        if (
            self.low > min(self.open, self.close)
            or self.high < max(self.open, self.close)
            or self.low > self.high
        ):
            raise ValueError("technical analysis OHLC values are inconsistent")
        for field in ("volume", "turnover"):
            object.__setattr__(
                self,
                field,
                _finite(getattr(self, field), field=field, minimum=0.0),
            )
        adjustment = _finite(
            self.adjustment_factor,
            field="adjustment_factor",
            minimum=0.0,
        )
        if adjustment == 0.0:
            raise ValueError("technical analysis adjustment_factor must be positive")
        object.__setattr__(self, "adjustment_factor", adjustment)
        if type(self.suspended) is not bool:
            raise ValueError("technical analysis suspended must be boolean")
        for field in ("benchmark_close", "industry_close"):
            value = getattr(self, field)
            if value is not None:
                normalized = _finite(value, field=field, minimum=0.0)
                if normalized == 0.0:
                    raise ValueError(f"technical analysis {field} must be positive")
                object.__setattr__(self, field, normalized)

    def identity_payload(self) -> dict[str, object]:
        """Return every source fact used in replay."""
        return {
            "occurred_at": self.occurred_at,
            "knowledge_at": self.knowledge_at,
            "publication_at": self.publication_at,
            "source_snapshot_id": self.source_snapshot_id,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "turnover": self.turnover,
            "adjustment_factor": self.adjustment_factor,
            "suspended": self.suspended,
            "benchmark_close": self.benchmark_close,
            "industry_close": self.industry_close,
        }


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisInput:
    """Exact PIT request and normalized bars supplied by an application adapter."""

    instrument_id: InstrumentId
    instrument_name: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    spec: TechnicalAnalysisSpec
    bars: tuple[TechnicalBar, ...]
    selection_run_id: str | None = None
    research_case_id: str | None = None
    portfolio_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        """Freeze ordering and validate temporal, lineage, and linkage boundaries."""
        _positive_int(self.instrument_id, field="instrument_id")
        object.__setattr__(
            self,
            "instrument_name",
            _text(self.instrument_name, field="instrument_name"),
        )
        for field in ("as_of", "knowledge_cutoff", "publication_cutoff"):
            object.__setattr__(self, field, _aware(getattr(self, field), field=field))
        if self.publication_cutoff > self.knowledge_cutoff:
            raise ValueError("technical analysis publication cutoff exceeds knowledge")
        if self.knowledge_cutoff > self.as_of:
            raise ValueError(
                "technical analysis knowledge cutoff exceeds decision time"
            )
        if not self.source_snapshot_ids or len(set(self.source_snapshot_ids)) != len(
            self.source_snapshot_ids
        ):
            raise ValueError("technical analysis requires unique source snapshot IDs")
        snapshots = tuple(
            sorted(
                _text(item, field="source snapshot ID")
                for item in self.source_snapshot_ids
            )
        )
        object.__setattr__(self, "source_snapshot_ids", snapshots)
        bars = tuple(sorted(self.bars, key=lambda item: item.occurred_at))
        if len({item.occurred_at for item in bars}) != len(bars):
            raise ValueError("technical analysis bars require unique occurrence times")
        if any(item.source_snapshot_id not in snapshots for item in bars):
            raise ValueError("technical analysis bar source snapshot is undeclared")
        object.__setattr__(self, "bars", bars)
        for field in (
            "selection_run_id",
            "research_case_id",
            "portfolio_snapshot_id",
        ):
            object.__setattr__(
                self,
                field,
                _optional_text(getattr(self, field), field=field),
            )


@dataclass(frozen=True, slots=True)
class TechnicalIndicatorParameter:
    """One canonical numeric parameter attached to an indicator reading."""

    name: str
    value: int


@dataclass(frozen=True, slots=True)
class TechnicalIndicatorReading:
    """One explicit indicator result, including warm-up/unavailable states."""

    name: str
    timeframe: TechnicalTimeframe
    indicator_version: str
    window: int | None
    parameters: tuple[TechnicalIndicatorParameter, ...]
    value: float | None
    status: TechnicalIndicatorStatus
    reason: str | None


@dataclass(frozen=True, slots=True)
class TechnicalLevel:
    """One replayable support or resistance level."""

    timeframe: TechnicalTimeframe
    kind: TechnicalLevelKind
    price: float
    confidence: float
    touches: int
    window: int
    algorithm_version: str


@dataclass(frozen=True, slots=True)
class TechnicalTimeframeSummary:
    """Compact state derived solely from recorded indicator readings."""

    timeframe: TechnicalTimeframe
    trend: TechnicalDirection
    momentum: TechnicalDirection
    breakout: TechnicalDirection


@dataclass(frozen=True, slots=True)
class TechnicalConflict:
    """One deterministic disagreement across timeframes."""

    dimension: Literal["trend", "momentum", "breakout"]
    daily: TechnicalDirection
    weekly: TechnicalDirection
    reason_code: str


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisSnapshot:
    """Content-addressed technical result for one instrument and exact PIT."""

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
    status: TechnicalAnalysisStatus
    last_visible_bar_at: datetime | None
    last_computed_bar_at: datetime | None
    readings: tuple[TechnicalIndicatorReading, ...]
    levels: tuple[TechnicalLevel, ...]
    timeframe_summaries: tuple[TechnicalTimeframeSummary, ...]
    conflicts: tuple[TechnicalConflict, ...]
    missing_inputs: tuple[str, ...]
    warnings: tuple[str, ...]
    selection_run_id: str | None
    research_case_id: str | None
    portfolio_snapshot_id: str | None


def canonical_spec_hash(value: TechnicalAnalysisSpec) -> str:
    """Hash the complete technical-analysis policy."""
    return _sha256(value.identity_payload())


def canonical_input_hash(
    value: TechnicalAnalysisInput,
    *,
    visible_bars: tuple[TechnicalBar, ...] | None = None,
) -> str:
    """Hash only the exact visible replay input used by the service."""
    bars = value.bars if visible_bars is None else visible_bars
    return _sha256(
        {
            "instrument_id": value.instrument_id,
            "instrument_name": value.instrument_name,
            "as_of": value.as_of,
            "knowledge_cutoff": value.knowledge_cutoff,
            "publication_cutoff": value.publication_cutoff,
            "source_snapshot_ids": value.source_snapshot_ids,
            "spec": value.spec.identity_payload(),
            "bars": tuple(item.identity_payload() for item in bars),
            "selection_run_id": value.selection_run_id,
            "research_case_id": value.research_case_id,
            "portfolio_snapshot_id": value.portfolio_snapshot_id,
        }
    )


def canonical_snapshot_payload(value: TechnicalAnalysisSnapshot) -> dict[str, object]:
    """Return every snapshot field except its derived ID."""
    return {
        "input_hash": value.input_hash,
        "spec_hash": value.spec_hash,
        "registry_version": value.registry_version,
        "instrument_id": value.instrument_id,
        "instrument_name": value.instrument_name,
        "as_of": value.as_of,
        "knowledge_cutoff": value.knowledge_cutoff,
        "publication_cutoff": value.publication_cutoff,
        "source_snapshot_ids": value.source_snapshot_ids,
        "status": value.status,
        "last_visible_bar_at": value.last_visible_bar_at,
        "last_computed_bar_at": value.last_computed_bar_at,
        "readings": value.readings,
        "levels": value.levels,
        "timeframe_summaries": value.timeframe_summaries,
        "conflicts": value.conflicts,
        "missing_inputs": value.missing_inputs,
        "warnings": value.warnings,
        "selection_run_id": value.selection_run_id,
        "research_case_id": value.research_case_id,
        "portfolio_snapshot_id": value.portfolio_snapshot_id,
    }


def canonical_snapshot_hash(value: TechnicalAnalysisSnapshot) -> str:
    """Hash a complete technical-analysis result."""
    return _sha256(canonical_snapshot_payload(value))
