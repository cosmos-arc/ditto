"""Deterministic multi-horizon industry-rotation scoring service."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.errors import StrategySpecError
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationContribution,
    IndustryRotationIndustryInput,
    IndustryRotationInputBundle,
    IndustryRotationRank,
    IndustryRotationSnapshot,
    IndustryRotationStatus,
)

__all__ = ["IndustryRotationService"]

_ALGORITHM_VERSION = "industry-rotation-v1"
_WEIGHTS = (
    ("relative_strength_5d", 0.15),
    ("relative_strength_20d", 0.25),
    ("relative_strength_60d", 0.20),
    ("breadth", 0.15),
    ("trend", 0.10),
    ("fundamental", 0.10),
    ("regime_alignment", 0.05),
)


@dataclass(frozen=True, slots=True)
class _UnrankedIndustry:
    industry_id: str
    industry_name: str
    score: float
    contributions: tuple[IndustryRotationContribution, ...]
    missing_inputs: tuple[str, ...]


def _breadth(value: IndustryRotationIndustryInput) -> float | None:
    if (
        value.advancing_count is None
        or value.declining_count is None
        or value.member_count is None
        or value.member_count == 0
    ):
        return None
    return (value.advancing_count - value.declining_count) / value.member_count


def _metric_values(
    value: IndustryRotationIndustryInput,
) -> dict[str, float | None]:
    return {
        "relative_strength_5d": value.relative_strength_5d,
        "relative_strength_20d": value.relative_strength_20d,
        "relative_strength_60d": value.relative_strength_60d,
        "breadth": _breadth(value),
        "trend": value.trend_score,
        "fundamental": value.fundamental_score,
        "regime_alignment": value.regime_alignment_score,
    }


def _score(value: IndustryRotationIndustryInput) -> _UnrankedIndustry:
    values = _metric_values(value)
    contributions = tuple(
        IndustryRotationContribution(
            metric=metric,
            value=values[metric],
            weight=weight,
            contribution=(values[metric] or 0.0) * weight,
        )
        for metric, weight in _WEIGHTS
    )
    missing_inputs = tuple(
        f"industry:{value.industry_id}:{metric}"
        for metric, metric_value in values.items()
        if metric_value is None
    )
    score = sum(item.contribution for item in contributions)
    return _UnrankedIndustry(
        industry_id=value.industry_id,
        industry_name=value.industry_name,
        score=0.0 if score == 0.0 else score,
        contributions=contributions,
        missing_inputs=missing_inputs,
    )


class IndustryRotationService:
    """Rank normalized industry facts without importing data or features."""

    def run(self, value: IndustryRotationInputBundle) -> IndustryRotationSnapshot:
        """Produce a PIT-fenced, replayable rotation snapshot."""
        if value.algorithm_version != _ALGORITHM_VERSION:
            raise StrategySpecError(
                "unsupported industry rotation algorithm_version",
                details={
                    "reason": "unsupported_industry_rotation_algorithm",
                    "algorithm_version": value.algorithm_version,
                    "supported_algorithm_version": _ALGORITHM_VERSION,
                },
            )
        if not value.industries:
            return self._snapshot(
                value,
                status=IndustryRotationStatus.BLOCKED,
                rankings=(),
                missing_inputs=tuple(
                    sorted((*value.declared_missing_inputs, "industries"))
                ),
            )

        scored = sorted(
            (_score(item) for item in value.industries),
            key=lambda item: (-item.score, item.industry_id),
        )
        rankings = tuple(
            IndustryRotationRank(
                industry_id=item.industry_id,
                industry_name=item.industry_name,
                rank=index,
                score=item.score,
                contributions=item.contributions,
                missing_inputs=item.missing_inputs,
            )
            for index, item in enumerate(scored, start=1)
        )
        missing = set(value.declared_missing_inputs)
        if value.market_context_feature_set_id is None:
            missing.add("market_context_feature_set_id")
        for item in rankings:
            missing.update(item.missing_inputs)
        status = (
            IndustryRotationStatus.DEGRADED if missing else IndustryRotationStatus.READY
        )
        return self._snapshot(
            value,
            status=status,
            rankings=rankings,
            missing_inputs=tuple(sorted(missing)),
        )

    @staticmethod
    def _snapshot(
        value: IndustryRotationInputBundle,
        *,
        status: IndustryRotationStatus,
        rankings: tuple[IndustryRotationRank, ...],
        missing_inputs: tuple[str, ...],
    ) -> IndustryRotationSnapshot:
        return IndustryRotationSnapshot(
            input_hash=value.input_hash,
            as_of=value.as_of,
            knowledge_cutoff=value.knowledge_cutoff,
            publication_cutoff=value.publication_cutoff,
            source_snapshot_ids=value.source_snapshot_ids,
            market_context_feature_set_id=value.market_context_feature_set_id,
            membership_version=value.membership_version,
            algorithm_version=value.algorithm_version,
            status=status,
            rankings=rankings,
            missing_inputs=missing_inputs,
        )
