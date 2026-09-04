"""Immutable strategy-owned industry-rotation contracts."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

import orjson

from ditto_strategy.errors import StrategySpecError

__all__ = [
    "IndustryRotationContribution",
    "IndustryRotationIndustryInput",
    "IndustryRotationInputBundle",
    "IndustryRotationRank",
    "IndustryRotationSnapshot",
    "IndustryRotationStatus",
    "canonical_input_hash",
    "canonical_snapshot_hash",
    "canonical_snapshot_payload",
]

_SCHEMA_VERSION = 1
_SHA256_HEX_LENGTH = 64


def _error(message: str, *, reason: str, **details: object) -> StrategySpecError:
    return StrategySpecError(message, details={"reason": reason, **details})


def _normalized_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise _error(
            f"industry rotation {field_name} must be normalized non-empty text",
            reason="invalid_industry_rotation_text",
            field_name=field_name,
        )
    return value


def _optional_normalized_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalized_text(value, field_name=field_name)


def _aware(value: object, *, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise _error(
            f"industry rotation {field_name} must be timezone-aware",
            reason="invalid_industry_rotation_time",
            field_name=field_name,
        )
    return value


def _unit_score(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _error(
            f"industry rotation {field_name} must be a finite unit score",
            reason="invalid_industry_rotation_score",
            field_name=field_name,
        )
    normalized = float(value)
    if not math.isfinite(normalized) or not -1.0 <= normalized <= 1.0:
        raise _error(
            f"industry rotation {field_name} must be a finite unit score",
            reason="invalid_industry_rotation_score",
            field_name=field_name,
        )
    return 0.0 if normalized == 0.0 else normalized


def _non_negative_count(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _error(
            f"industry rotation {field_name} must be a non-negative integer",
            reason="invalid_industry_rotation_count",
            field_name=field_name,
        )
    return value


def _ordered_sequence[ItemT](
    value: object,
    *,
    item_type: type[ItemT],
    field_name: str,
) -> tuple[ItemT, ...]:
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
        raise _error(
            f"industry rotation {field_name} must be an ordered sequence",
            reason="invalid_industry_rotation_sequence",
            field_name=field_name,
        )
    copied = tuple(cast("Sequence[object]", value))
    if any(not isinstance(item, item_type) for item in copied):
        raise _error(
            f"industry rotation {field_name} contains an invalid item",
            reason="invalid_industry_rotation_sequence_item",
            field_name=field_name,
        )
    return cast("tuple[ItemT, ...]", copied)


def _normalized_text_set(value: object, *, field_name: str) -> tuple[str, ...]:
    copied = _ordered_sequence(value, item_type=str, field_name=field_name)
    normalized = tuple(_normalized_text(item, field_name=field_name) for item in copied)
    if len(set(normalized)) != len(normalized):
        raise _error(
            f"industry rotation {field_name} must be unique",
            reason="duplicate_industry_rotation_identity",
            field_name=field_name,
        )
    return tuple(sorted(normalized))


class IndustryRotationStatus(StrEnum):
    """Completeness of one fail-closed rotation result."""

    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class IndustryRotationIndustryInput:
    """One normalized industry observation supplied by application."""

    industry_id: str
    industry_name: str
    relative_strength_5d: float | None
    relative_strength_20d: float | None
    relative_strength_60d: float | None
    advancing_count: int | None
    declining_count: int | None
    member_count: int | None
    trend_score: float | None
    fundamental_score: float | None
    regime_alignment_score: float | None

    def __post_init__(self) -> None:
        """Normalize score spelling and reject incoherent breadth counts."""
        object.__setattr__(
            self,
            "industry_id",
            _normalized_text(self.industry_id, field_name="industry_id"),
        )
        object.__setattr__(
            self,
            "industry_name",
            _normalized_text(self.industry_name, field_name="industry_name"),
        )
        for field_name in (
            "relative_strength_5d",
            "relative_strength_20d",
            "relative_strength_60d",
            "trend_score",
            "fundamental_score",
            "regime_alignment_score",
        ):
            object.__setattr__(
                self,
                field_name,
                _unit_score(getattr(self, field_name), field_name=field_name),
            )
        for field_name in ("advancing_count", "declining_count", "member_count"):
            object.__setattr__(
                self,
                field_name,
                _non_negative_count(getattr(self, field_name), field_name=field_name),
            )
        if (
            self.advancing_count is not None
            and self.declining_count is not None
            and self.member_count is not None
            and self.advancing_count + self.declining_count > self.member_count
        ):
            raise _error(
                "industry rotation breadth counts exceed member_count",
                reason="invalid_industry_rotation_breadth",
                industry_id=self.industry_id,
            )


@dataclass(frozen=True, slots=True)
class IndustryRotationInputBundle:
    """PIT-fenced input identity for one deterministic rotation run."""

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    market_context_feature_set_id: str | None
    membership_version: str
    algorithm_version: str
    industries: tuple[IndustryRotationIndustryInput, ...]
    declared_missing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Freeze set-like inputs and reject future-visible evidence."""
        for field_name in ("as_of", "knowledge_cutoff", "publication_cutoff"):
            _aware(getattr(self, field_name), field_name=field_name)
        if self.publication_cutoff > self.knowledge_cutoff:
            raise _error(
                "industry rotation publication_cutoff exceeds knowledge_cutoff",
                reason="invalid_industry_rotation_cutoff",
            )
        if self.knowledge_cutoff > self.as_of:
            raise _error(
                "industry rotation knowledge_cutoff exceeds as_of",
                reason="invalid_industry_rotation_cutoff",
            )
        object.__setattr__(
            self,
            "source_snapshot_ids",
            _normalized_text_set(
                self.source_snapshot_ids,
                field_name="source_snapshot_ids",
            ),
        )
        if not self.source_snapshot_ids:
            raise _error(
                "industry rotation requires source_snapshot_ids",
                reason="missing_industry_rotation_lineage",
            )
        object.__setattr__(
            self,
            "market_context_feature_set_id",
            _optional_normalized_text(
                self.market_context_feature_set_id,
                field_name="market_context_feature_set_id",
            ),
        )
        for field_name in ("membership_version", "algorithm_version"):
            object.__setattr__(
                self,
                field_name,
                _normalized_text(getattr(self, field_name), field_name=field_name),
            )
        industries = _ordered_sequence(
            self.industries,
            item_type=IndustryRotationIndustryInput,
            field_name="industries",
        )
        industry_ids = tuple(item.industry_id for item in industries)
        if len(set(industry_ids)) != len(industry_ids):
            raise _error(
                "industry rotation requires unique industry_id values",
                reason="duplicate_industry_rotation_industry",
            )
        object.__setattr__(
            self,
            "industries",
            tuple(sorted(industries, key=lambda item: item.industry_id)),
        )
        object.__setattr__(
            self,
            "declared_missing_inputs",
            _normalized_text_set(
                self.declared_missing_inputs,
                field_name="declared_missing_inputs",
            ),
        )

    @property
    def input_hash(self) -> str:
        """Return the canonical replay identity of this bundle."""
        return _canonical_input_hash(self)


@dataclass(frozen=True, slots=True)
class IndustryRotationContribution:
    """One versioned additive score component."""

    metric: str
    value: float | None
    weight: float
    contribution: float

    def __post_init__(self) -> None:
        """Reject non-canonical contribution values."""
        object.__setattr__(
            self,
            "metric",
            _normalized_text(self.metric, field_name="metric"),
        )
        object.__setattr__(self, "value", _unit_score(self.value, field_name="value"))
        weight = _unit_score(self.weight, field_name="weight")
        contribution = _unit_score(self.contribution, field_name="contribution")
        if weight is None or weight < 0.0:
            raise _error(
                "industry rotation weight must be a non-negative unit score",
                reason="invalid_industry_rotation_weight",
            )
        if contribution is None:
            raise _error(
                "industry rotation contribution is required",
                reason="invalid_industry_rotation_contribution",
            )
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "contribution", contribution)


@dataclass(frozen=True, slots=True)
class IndustryRotationRank:
    """One ranked industry with complete score attribution."""

    industry_id: str
    industry_name: str
    rank: int
    score: float
    contributions: tuple[IndustryRotationContribution, ...]
    missing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate rank identity and additive attribution."""
        object.__setattr__(
            self,
            "industry_id",
            _normalized_text(self.industry_id, field_name="industry_id"),
        )
        object.__setattr__(
            self,
            "industry_name",
            _normalized_text(self.industry_name, field_name="industry_name"),
        )
        if type(self.rank) is not int or self.rank < 1:
            raise _error(
                "industry rotation rank must be a positive integer",
                reason="invalid_industry_rotation_rank",
            )
        score = _unit_score(self.score, field_name="score")
        if score is None:
            raise _error(
                "industry rotation score is required",
                reason="invalid_industry_rotation_score",
            )
        object.__setattr__(self, "score", score)
        contributions = _ordered_sequence(
            self.contributions,
            item_type=IndustryRotationContribution,
            field_name="contributions",
        )
        metrics = tuple(item.metric for item in contributions)
        if len(set(metrics)) != len(metrics):
            raise _error(
                "industry rotation contribution metrics must be unique",
                reason="duplicate_industry_rotation_metric",
            )
        if not math.isclose(
            sum(item.contribution for item in contributions),
            score,
            abs_tol=1e-12,
        ):
            raise _error(
                "industry rotation score does not match contributions",
                reason="invalid_industry_rotation_score_total",
            )
        object.__setattr__(self, "contributions", contributions)
        object.__setattr__(
            self,
            "missing_inputs",
            _normalized_text_set(self.missing_inputs, field_name="missing_inputs"),
        )


@dataclass(frozen=True, slots=True)
class IndustryRotationSnapshot:
    """Deterministic ranked output bound to exact data and algorithm inputs."""

    input_hash: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    market_context_feature_set_id: str | None
    membership_version: str
    algorithm_version: str
    status: IndustryRotationStatus
    rankings: tuple[IndustryRotationRank, ...]
    missing_inputs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject malformed output ordering and detached replay identity."""
        if (
            not isinstance(self.input_hash, str)
            or len(self.input_hash) != _SHA256_HEX_LENGTH
            or any(char not in "0123456789abcdef" for char in self.input_hash)
        ):
            raise _error(
                "industry rotation input_hash must be lowercase SHA-256",
                reason="invalid_industry_rotation_input_hash",
            )
        for field_name in ("as_of", "knowledge_cutoff", "publication_cutoff"):
            _aware(getattr(self, field_name), field_name=field_name)
        if self.publication_cutoff > self.knowledge_cutoff:
            raise _error(
                "industry rotation publication_cutoff exceeds knowledge_cutoff",
                reason="invalid_industry_rotation_cutoff",
            )
        if self.knowledge_cutoff > self.as_of:
            raise _error(
                "industry rotation knowledge_cutoff exceeds as_of",
                reason="invalid_industry_rotation_cutoff",
            )
        object.__setattr__(
            self,
            "source_snapshot_ids",
            _normalized_text_set(
                self.source_snapshot_ids,
                field_name="source_snapshot_ids",
            ),
        )
        object.__setattr__(
            self,
            "market_context_feature_set_id",
            _optional_normalized_text(
                self.market_context_feature_set_id,
                field_name="market_context_feature_set_id",
            ),
        )
        for field_name in ("membership_version", "algorithm_version"):
            object.__setattr__(
                self,
                field_name,
                _normalized_text(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.status, IndustryRotationStatus):
            raise _error(
                "industry rotation status must be IndustryRotationStatus",
                reason="invalid_industry_rotation_status",
            )
        rankings = _ordered_sequence(
            self.rankings,
            item_type=IndustryRotationRank,
            field_name="rankings",
        )
        if tuple(item.rank for item in rankings) != tuple(range(1, len(rankings) + 1)):
            raise _error(
                "industry rotation rankings must be contiguous and ordered",
                reason="invalid_industry_rotation_rank_order",
            )
        industry_ids = tuple(item.industry_id for item in rankings)
        if len(set(industry_ids)) != len(industry_ids):
            raise _error(
                "industry rotation rankings require unique industry_id values",
                reason="duplicate_industry_rotation_industry",
            )
        object.__setattr__(self, "rankings", rankings)
        object.__setattr__(
            self,
            "missing_inputs",
            _normalized_text_set(self.missing_inputs, field_name="missing_inputs"),
        )

    @property
    def snapshot_id(self) -> str:
        """Return the canonical content-addressed snapshot identity."""
        return f"industry-rotation:sha256:{_canonical_snapshot_hash(self)}"


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _industry_payload(value: IndustryRotationIndustryInput) -> dict[str, object]:
    return {
        "advancing_count": value.advancing_count,
        "declining_count": value.declining_count,
        "fundamental_score": value.fundamental_score,
        "industry_id": value.industry_id,
        "industry_name": value.industry_name,
        "member_count": value.member_count,
        "regime_alignment_score": value.regime_alignment_score,
        "relative_strength_20d": value.relative_strength_20d,
        "relative_strength_5d": value.relative_strength_5d,
        "relative_strength_60d": value.relative_strength_60d,
        "trend_score": value.trend_score,
    }


def _canonical_input_payload(value: IndustryRotationInputBundle) -> dict[str, object]:
    return {
        "algorithm_version": value.algorithm_version,
        "as_of": _timestamp(value.as_of),
        "declared_missing_inputs": list(value.declared_missing_inputs),
        "industries": [_industry_payload(item) for item in value.industries],
        "knowledge_cutoff": _timestamp(value.knowledge_cutoff),
        "market_context_feature_set_id": value.market_context_feature_set_id,
        "membership_version": value.membership_version,
        "publication_cutoff": _timestamp(value.publication_cutoff),
        "schema_version": _SCHEMA_VERSION,
        "source_snapshot_ids": list(value.source_snapshot_ids),
    }


def _canonical_input_hash(value: IndustryRotationInputBundle) -> str:
    payload = orjson.dumps(_canonical_input_payload(value), option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(payload).hexdigest()


def _contribution_payload(value: IndustryRotationContribution) -> dict[str, object]:
    return {
        "contribution": value.contribution,
        "metric": value.metric,
        "value": value.value,
        "weight": value.weight,
    }


def _rank_payload(value: IndustryRotationRank) -> dict[str, object]:
    return {
        "contributions": [_contribution_payload(item) for item in value.contributions],
        "industry_id": value.industry_id,
        "industry_name": value.industry_name,
        "missing_inputs": list(value.missing_inputs),
        "rank": value.rank,
        "score": value.score,
    }


def _canonical_snapshot_payload(value: IndustryRotationSnapshot) -> dict[str, object]:
    return {
        "algorithm_version": value.algorithm_version,
        "as_of": _timestamp(value.as_of),
        "input_hash": value.input_hash,
        "knowledge_cutoff": _timestamp(value.knowledge_cutoff),
        "market_context_feature_set_id": value.market_context_feature_set_id,
        "membership_version": value.membership_version,
        "missing_inputs": list(value.missing_inputs),
        "publication_cutoff": _timestamp(value.publication_cutoff),
        "rankings": [_rank_payload(item) for item in value.rankings],
        "schema_version": _SCHEMA_VERSION,
        "source_snapshot_ids": list(value.source_snapshot_ids),
        "status": value.status.value,
    }


def _canonical_snapshot_hash(value: IndustryRotationSnapshot) -> str:
    payload = orjson.dumps(
        _canonical_snapshot_payload(value),
        option=orjson.OPT_SORT_KEYS,
    )
    return hashlib.sha256(payload).hexdigest()


canonical_input_hash = _canonical_input_hash
canonical_snapshot_payload = _canonical_snapshot_payload
canonical_snapshot_hash = _canonical_snapshot_hash
