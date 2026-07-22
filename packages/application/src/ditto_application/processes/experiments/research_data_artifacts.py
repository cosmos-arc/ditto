"""Verified immutable frame artifacts consumed by the R3 research feed."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO

import orjson
import polars as pl

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)

__all__ = [
    "FrozenResearchDataFrames",
    "ResearchDataEvidenceManifest",
    "ResearchFrameEvidenceManifest",
    "ResearchFrameKind",
    "VerifiedResearchFrame",
    "research_artifact_content_hash",
    "research_frame_schema_hash",
]


def research_data_error(
    message: str,
    reason: str,
    **details: object,
) -> AppProcessError:
    return AppProcessError(
        message,
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def research_artifact_content_hash(artifact_bytes: bytes) -> str:
    """Hash the exact immutable Parquet bytes consumed by research execution."""
    raw: object = artifact_bytes
    if type(raw) is not bytes or not raw:
        raise research_data_error(
            "research artifact must be non-empty exact bytes",
            "invalid_research_artifact_bytes",
        )
    return hashlib.sha256(raw).hexdigest()


def research_frame_schema_hash(frame: pl.DataFrame) -> str:
    """Hash ordered column names and exact Polars dtypes canonically."""
    if type(frame) is not pl.DataFrame:
        raise research_data_error(
            "research schema hash requires an eager Polars DataFrame",
            "invalid_research_frame",
        )
    fields = tuple((name, str(dtype)) for name, dtype in frame.schema.items())
    return hashlib.sha256(orjson.dumps(fields)).hexdigest()


class ResearchFrameKind(StrEnum):
    """Stable artifact kinds consumed by the research data feed."""

    BARS = "bars"
    CALENDAR = "calendar"
    MEMBERSHIP = "membership"
    FUNDAMENTAL = "fundamental"
    CLASSIFICATION = "classification"


REQUIRED_COLUMNS: dict[ResearchFrameKind, frozenset[str]] = {
    ResearchFrameKind.BARS: frozenset(
        {
            "trade_date",
            "instrument_id",
            "open",
            "high",
            "low",
            "close",
            "prev_close",
            "volume",
            "amount",
            "is_suspended",
            "limit_up",
            "limit_down",
            "avg_volume_20d",
            "source_snapshot_id",
        },
    ),
    ResearchFrameKind.CALENDAR: frozenset(
        {"trade_date", "is_open", "source_snapshot_id"},
    ),
    ResearchFrameKind.MEMBERSHIP: frozenset(
        {
            "trade_date",
            "instrument_id",
            "is_member",
            "known_at",
            "source_snapshot_id",
        },
    ),
    ResearchFrameKind.FUNDAMENTAL: frozenset(
        {
            "instrument_id",
            "known_at",
            "roe",
            "net_margin",
            "eps",
            "source_snapshot_id",
        },
    ),
    ResearchFrameKind.CLASSIFICATION: frozenset(
        {"instrument_id", "known_at", "sector_id", "source_snapshot_id"},
    ),
}

NUMERIC_COLUMNS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "prev_close",
        "volume",
        "amount",
        "limit_up",
        "limit_down",
        "avg_volume_20d",
        "roe",
        "net_margin",
        "eps",
    },
)
BOOLEAN_COLUMNS = frozenset({"is_open", "is_member", "is_suspended"})
STRING_COLUMNS = frozenset({"source_snapshot_id", "sector_id"})
DATE_COLUMNS = frozenset({"trade_date", "known_at"})
KEY_COLUMNS: dict[ResearchFrameKind, tuple[str, ...]] = {
    ResearchFrameKind.BARS: ("trade_date", "instrument_id"),
    ResearchFrameKind.CALENDAR: ("trade_date",),
    ResearchFrameKind.MEMBERSHIP: ("trade_date", "instrument_id"),
    ResearchFrameKind.FUNDAMENTAL: ("instrument_id", "known_at"),
    ResearchFrameKind.CLASSIFICATION: ("instrument_id", "known_at"),
}


@dataclass(frozen=True, slots=True)
class VerifiedResearchFrame:
    """One exact Parquet artifact verified and parsed inside the trust boundary."""

    input_evidence: ContentAddressedResearchInput
    source_snapshot_ids: tuple[str, ...]
    artifact_bytes: bytes = field(repr=False)
    verified_content_hash: str = field(init=False)
    verified_schema_hash: str = field(init=False)
    frame: pl.DataFrame = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Verify bytes and schema before exposing the parsed frozen frame."""
        if type(self.input_evidence) is not ContentAddressedResearchInput:
            raise research_data_error(
                "research frame requires exact content-addressed input evidence",
                "invalid_frame_evidence",
            )
        content_hash = research_artifact_content_hash(self.artifact_bytes)
        if content_hash != self.input_evidence.content_hash:
            raise research_data_error(
                "exact Parquet bytes differ from frozen input evidence",
                "frame_content_hash_mismatch",
                input_id=self.input_evidence.input_id,
            )
        try:
            frame = pl.read_parquet(BytesIO(self.artifact_bytes))
        except (OSError, ValueError, pl.exceptions.PolarsError):
            raise research_data_error(
                "research artifact is not a readable exact Parquet frame",
                "invalid_research_parquet_artifact",
                input_id=self.input_evidence.input_id,
            ) from None
        schema_hash = research_frame_schema_hash(frame)
        if schema_hash != self.input_evidence.schema_hash:
            raise research_data_error(
                "parsed Parquet schema differs from frozen input evidence",
                "frame_schema_hash_mismatch",
                input_id=self.input_evidence.input_id,
            )
        raw_sources: object = self.source_snapshot_ids
        if type(raw_sources) is not tuple or not raw_sources:
            raise research_data_error(
                "research frame requires source snapshot evidence",
                "missing_frame_source_snapshot",
            )
        if any(
            type(item) is not str or not item or item != item.strip()
            for item in raw_sources
        ):
            raise research_data_error(
                "research frame source snapshot identities are invalid",
                "invalid_frame_source_snapshot",
            )
        sources = tuple(sorted(raw_sources))
        if len(set(sources)) != len(sources):
            raise research_data_error(
                "research frame source snapshot identities must be unique",
                "duplicate_frame_source_snapshot",
            )
        object.__setattr__(self, "source_snapshot_ids", sources)
        object.__setattr__(self, "verified_content_hash", content_hash)
        object.__setattr__(self, "verified_schema_hash", schema_hash)
        object.__setattr__(self, "frame", frame)


@dataclass(frozen=True, slots=True)
class FrozenResearchDataFrames:
    """Exact frame set required by one research backtest."""

    bars: VerifiedResearchFrame
    calendar: VerifiedResearchFrame
    membership: VerifiedResearchFrame
    fundamental: VerifiedResearchFrame | None = None
    classification: VerifiedResearchFrame | None = None

    def items(self) -> tuple[tuple[ResearchFrameKind, VerifiedResearchFrame], ...]:
        """Return present frames in stable artifact-kind order."""
        result = [
            (ResearchFrameKind.BARS, self.bars),
            (ResearchFrameKind.CALENDAR, self.calendar),
            (ResearchFrameKind.MEMBERSHIP, self.membership),
        ]
        if self.fundamental is not None:
            result.append((ResearchFrameKind.FUNDAMENTAL, self.fundamental))
        if self.classification is not None:
            result.append((ResearchFrameKind.CLASSIFICATION, self.classification))
        return tuple(result)


@dataclass(frozen=True, slots=True)
class ResearchFrameEvidenceManifest:
    """Hash and source identities for one feed frame."""

    frame_kind: ResearchFrameKind
    input_id: str
    content_hash: str
    schema_hash: str
    source_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchDataEvidenceManifest:
    """Exact snapshot and verified input evidence exposed to the worker."""

    snapshot_id: str
    snapshot_manifest_hash: str
    source_snapshot_ids: tuple[str, ...]
    frames: tuple[ResearchFrameEvidenceManifest, ...]
    canonical_hash: str
