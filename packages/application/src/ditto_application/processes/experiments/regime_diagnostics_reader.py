"""PIT-safe regime diagnostics over one exact frozen research bars artifact."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from itertools import pairwise
from typing import Protocol, cast

import polars as pl
from ditto_strategy.alpha.builtins.regime.regime_engine import RegimeScoreEngine
from ditto_strategy.alpha.builtins.regime.regime_indicators import MomentumIndicator
from ditto_strategy.alpha.builtins.regime.regime_types import (
    RegimeConfig,
    RegimeLabel,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._execution_bundle_inputs import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    VerifiedResearchFrame,
)
from ditto_application.processes.experiments.research_snapshot_manifest import (
    VerifiedResearchSnapshotManifest,
)

__all__ = [
    "FrozenResearchArtifactReader",
    "RegimeDiagnosticsReader",
    "RegimeDiagnosticsScope",
    "RegimeDiagnosticsView",
    "RegimeIndicatorValue",
    "RegimeObservation",
    "RegimeTransition",
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = "momentum-20d-v1"
_LOOKBACK = 20
_BULL_THRESHOLD = 0.65
_BEAR_THRESHOLD = 0.35
_REQUIRED_BAR_COLUMNS = frozenset(
    {"trade_date", "instrument_id", "close", "source_snapshot_id"}
)


def _error(
    reason: str, *, unavailable: bool = False, **details: object
) -> AppProcessError:
    return AppProcessError(
        "regime diagnostics evidence is unavailable"
        if unavailable
        else "regime diagnostics scope is invalid",
        details={
            "code": (
                "REGIME_DIAGNOSTICS_UNAVAILABLE"
                if unavailable
                else "REGIME_DIAGNOSTICS_INVALID"
            ),
            "reason": reason,
            **details,
        },
    )


def _canonical_text(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error("invalid_regime_identity", field=field)
    return value


@dataclass(frozen=True, slots=True)
class RegimeDiagnosticsScope:
    """Complete immutable data and time scope for one EOD regime read."""

    snapshot_id: str
    snapshot_manifest_hash: str
    benchmark_instrument_id: int
    start_date: date
    end_date: date
    knowledge_cutoff: date

    def __post_init__(self) -> None:
        """Reject latest-data fallbacks and same-day close visibility."""
        _canonical_text(self.snapshot_id, field="snapshot_id")
        if (
            type(self.snapshot_manifest_hash) is not str
            or _SHA256.fullmatch(self.snapshot_manifest_hash) is None
        ):
            raise _error("invalid_regime_snapshot_manifest_hash")
        if (
            type(self.benchmark_instrument_id) is not int
            or self.benchmark_instrument_id <= 0
        ):
            raise _error("invalid_regime_benchmark_instrument")
        if any(
            type(value) is not date
            for value in (self.start_date, self.end_date, self.knowledge_cutoff)
        ):
            raise _error("invalid_regime_date_scope")
        if self.end_date < self.start_date:
            raise _error("regime_end_before_start")
        if self.end_date >= self.knowledge_cutoff:
            raise _error("regime_end_not_before_cutoff")


class FrozenResearchArtifactReader(Protocol):
    """Read exact bytes addressed by an immutable research input identity."""

    def read_frozen_research_input_bytes(self, artifact_id: str) -> bytes:
        """Return the exact stored bytes for ``artifact_id`` without latest lookup."""
        ...


@dataclass(frozen=True, slots=True)
class RegimeIndicatorValue:
    """One normalized domain indicator value used in a regime observation."""

    name: str
    normalized_score: float


@dataclass(frozen=True, slots=True)
class RegimeObservation:
    """One point-in-time EOD regime score."""

    observed_at: date
    score: float
    label: RegimeLabel
    position_ratio: float
    indicators: tuple[RegimeIndicatorValue, ...]


@dataclass(frozen=True, slots=True)
class RegimeTransition:
    """A label transition derived from consecutive eligible observations."""

    observed_at: date
    from_label: RegimeLabel
    to_label: RegimeLabel


@dataclass(frozen=True, slots=True)
class RegimeDiagnosticsView:
    """Complete regime output plus the immutable evidence identity that produced it."""

    snapshot_id: str
    snapshot_manifest_hash: str
    dataset_id: str
    source_snapshot_ids: tuple[str, ...]
    builder_version: str
    known_at_policy: str
    benchmark_instrument_id: int
    start_date: date
    end_date: date
    knowledge_cutoff: date
    model_id: str
    lookback_observations: int
    bear_threshold: float
    bull_threshold: float
    bars_input_id: str
    bars_content_hash: str
    bars_schema_hash: str
    observations: tuple[RegimeObservation, ...]
    transitions: tuple[RegimeTransition, ...]

    def __post_init__(self) -> None:
        """Reject an empty projection rather than inventing a current state."""
        if not self.observations:
            raise _error("regime_observations_empty", unavailable=True)

    @property
    def current(self) -> RegimeObservation:
        """Return the latest observation within the exact requested interval."""
        return self.observations[-1]


@dataclass(frozen=True, slots=True)
class RegimeDiagnosticsReader:
    """Project regime observations from one verified immutable bars artifact."""

    artifacts: FrozenResearchArtifactReader

    def read(self, scope: RegimeDiagnosticsScope) -> RegimeDiagnosticsView:
        """Read one exact snapshot and score only bars visible before cutoff."""
        if type(scope) is not RegimeDiagnosticsScope:
            raise _error("invalid_regime_scope_type")
        exact_snapshot = ExactResearchSnapshot(
            snapshot_id=scope.snapshot_id,
            manifest_hash=scope.snapshot_manifest_hash,
        )
        manifest_bytes = self.artifacts.read_frozen_research_input_bytes(
            scope.snapshot_id
        )
        manifest = VerifiedResearchSnapshotManifest(
            exact_snapshot=exact_snapshot,
            manifest_bytes=manifest_bytes,
        )
        binding = manifest.snapshot_binding
        bars_evidence = _single_bars_evidence(binding.inputs)
        bars_bytes = self.artifacts.read_frozen_research_input_bytes(
            bars_evidence.input_id
        )
        source_snapshot_ids = _source_snapshot_ids(bars_bytes)
        bars = VerifiedResearchFrame(
            input_evidence=bars_evidence,
            source_snapshot_ids=source_snapshot_ids,
            artifact_bytes=bars_bytes,
        )
        if not set(bars.source_snapshot_ids).issubset(binding.source_snapshot_ids):
            raise _error("regime_bars_source_snapshot_drift", unavailable=True)

        observations = _observations(bars.frame, scope)
        transitions = tuple(
            RegimeTransition(
                observed_at=current.observed_at,
                from_label=previous.label,
                to_label=current.label,
            )
            for previous, current in pairwise(observations)
            if previous.label is not current.label
        )
        return RegimeDiagnosticsView(
            snapshot_id=binding.exact_snapshot.snapshot_id,
            snapshot_manifest_hash=binding.exact_snapshot.manifest_hash,
            dataset_id=binding.dataset_id,
            source_snapshot_ids=bars.source_snapshot_ids,
            builder_version=binding.builder_version,
            known_at_policy=binding.known_at_policy,
            benchmark_instrument_id=scope.benchmark_instrument_id,
            start_date=scope.start_date,
            end_date=scope.end_date,
            knowledge_cutoff=scope.knowledge_cutoff,
            model_id=_MODEL_ID,
            lookback_observations=_LOOKBACK,
            bear_threshold=_BEAR_THRESHOLD * 100,
            bull_threshold=_BULL_THRESHOLD * 100,
            bars_input_id=bars_evidence.input_id,
            bars_content_hash=bars.verified_content_hash,
            bars_schema_hash=bars.verified_schema_hash,
            observations=observations,
            transitions=transitions,
        )


def _single_bars_evidence(
    inputs: tuple[ContentAddressedResearchInput, ...],
) -> ContentAddressedResearchInput:
    matches = tuple(item for item in inputs if item.artifact_kind == "bars")
    if len(matches) != 1:
        raise _error("regime_bars_evidence_missing_or_ambiguous", unavailable=True)
    return matches[0]


def _source_snapshot_ids(artifact_bytes: bytes) -> tuple[str, ...]:
    try:
        frame = pl.read_parquet(BytesIO(artifact_bytes))
    except (OSError, ValueError, pl.exceptions.PolarsError):
        raise _error("invalid_regime_bars_artifact", unavailable=True) from None
    missing = _REQUIRED_BAR_COLUMNS.difference(frame.columns)
    if missing:
        raise _error(
            "regime_bars_columns_missing",
            unavailable=True,
            missing_columns=tuple(sorted(missing)),
        )
    raw_sources = frame["source_snapshot_id"].unique().sort().to_list()
    if not raw_sources or any(
        type(item) is not str or not item or item != item.strip()
        for item in raw_sources
    ):
        raise _error("invalid_regime_bars_source_snapshot", unavailable=True)
    return tuple(cast("list[str]", raw_sources))


def _observations(
    frame: pl.DataFrame,
    scope: RegimeDiagnosticsScope,
) -> tuple[RegimeObservation, ...]:
    if frame.schema.get("trade_date") != pl.Date:
        raise _error("regime_trade_date_must_be_date", unavailable=True)
    scoped = (
        frame.filter(
            (pl.col("instrument_id") == scope.benchmark_instrument_id)
            & (pl.col("trade_date") < scope.knowledge_cutoff)
            & (pl.col("trade_date") <= scope.end_date)
        )
        .select("trade_date", "close")
        .sort("trade_date")
    )
    if scoped["trade_date"].n_unique() != scoped.height:
        raise _error("duplicate_regime_benchmark_bar", unavailable=True)

    engine = RegimeScoreEngine(
        RegimeConfig(
            indicators=(MomentumIndicator(lookback=_LOOKBACK),),
            bull_threshold=_BULL_THRESHOLD,
            bear_threshold=_BEAR_THRESHOLD,
        )
    )
    results: list[RegimeObservation] = []
    for index in range(_LOOKBACK, scoped.height):
        observed_at = cast("date", scoped["trade_date"][index])
        if observed_at < scope.start_date:
            continue
        window = scoped.slice(index - _LOOKBACK, _LOOKBACK + 1)
        result = engine.score(window)
        results.append(
            RegimeObservation(
                observed_at=observed_at,
                score=result.score,
                label=result.label,
                position_ratio=result.position_ratio,
                indicators=tuple(
                    RegimeIndicatorValue(name=name, normalized_score=value)
                    for name, value in sorted(result.indicator_values.items())
                ),
            )
        )
    if not results:
        raise _error(
            "regime_history_insufficient",
            unavailable=True,
            required_observations=_LOOKBACK + 1,
        )
    return tuple(results)
