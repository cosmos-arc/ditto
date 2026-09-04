"""Deterministic industry-rotation scoring golden cases."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationIndustryInput,
    IndustryRotationInputBundle,
    IndustryRotationStatus,
)
from ditto_strategy.industry_rotation.identity import (
    canonical_industry_rotation_snapshot_hash,
)
from ditto_strategy.industry_rotation.service import IndustryRotationService

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _industry(industry_id: str, score: float) -> IndustryRotationIndustryInput:
    advancing = 10 if score == 1.0 else 0 if score == -1.0 else 5
    declining = 0 if score == 1.0 else 10 if score == -1.0 else 5
    return IndustryRotationIndustryInput(
        industry_id=industry_id,
        industry_name=f"Industry {industry_id}",
        relative_strength_5d=score,
        relative_strength_20d=score,
        relative_strength_60d=score,
        advancing_count=advancing,
        declining_count=declining,
        member_count=10,
        trend_score=score,
        fundamental_score=score,
        regime_alignment_score=score,
    )


def _bundle(
    industries: tuple[IndustryRotationIndustryInput, ...],
    *,
    market_context_feature_set_id: str | None = "market-context:sha256:abc",
) -> IndustryRotationInputBundle:
    return IndustryRotationInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_ids=("source-a", "source-b"),
        market_context_feature_set_id=market_context_feature_set_id,
        membership_version="sw-l1:2026-08-31",
        algorithm_version="industry-rotation-v1",
        industries=industries,
    )


def test_v1_golden_case_scores_all_required_dimensions_and_ranks() -> None:
    snapshot = IndustryRotationService().run(
        _bundle(
            (
                _industry("801030", -1.0),
                _industry("801010", 1.0),
                _industry("801020", 0.0),
            )
        )
    )

    assert snapshot.status is IndustryRotationStatus.READY
    assert [(row.industry_id, row.rank, row.score) for row in snapshot.rankings] == [
        ("801010", 1, 1.0),
        ("801020", 2, 0.0),
        ("801030", 3, -1.0),
    ]
    assert [item.metric for item in snapshot.rankings[0].contributions] == [
        "relative_strength_5d",
        "relative_strength_20d",
        "relative_strength_60d",
        "breadth",
        "trend",
        "fundamental",
        "regime_alignment",
    ]
    assert sum(
        item.contribution for item in snapshot.rankings[0].contributions
    ) == pytest.approx(snapshot.rankings[0].score)


def test_exact_replay_has_the_same_input_and_snapshot_identity() -> None:
    service = IndustryRotationService()
    value = _bundle((_industry("801010", 0.5), _industry("801020", 0.5)))

    first = service.run(value)
    second = service.run(value)

    assert first == second
    assert first.input_hash == value.input_hash
    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_id == (
        f"industry-rotation:sha256:{canonical_industry_rotation_snapshot_hash(first)}"
    )
    assert [row.industry_id for row in first.rankings] == ["801010", "801020"]


def test_missing_dimension_is_explicit_and_degrades_without_fabricating_value() -> None:
    incomplete = IndustryRotationIndustryInput(
        industry_id="801010",
        industry_name="Industry 801010",
        relative_strength_5d=0.5,
        relative_strength_20d=0.5,
        relative_strength_60d=0.5,
        advancing_count=6,
        declining_count=4,
        member_count=10,
        trend_score=0.5,
        fundamental_score=None,
        regime_alignment_score=None,
    )

    snapshot = IndustryRotationService().run(
        _bundle((incomplete,), market_context_feature_set_id=None)
    )

    assert snapshot.status is IndustryRotationStatus.DEGRADED
    assert snapshot.missing_inputs == (
        "industry:801010:fundamental",
        "industry:801010:regime_alignment",
        "market_context_feature_set_id",
    )
    contribution_by_metric = {
        item.metric: item for item in snapshot.rankings[0].contributions
    }
    assert contribution_by_metric["fundamental"].value is None
    assert contribution_by_metric["fundamental"].contribution == 0.0
    assert contribution_by_metric["regime_alignment"].value is None


def test_empty_industry_universe_fails_closed_as_blocked() -> None:
    snapshot = IndustryRotationService().run(_bundle(()))

    assert snapshot.status is IndustryRotationStatus.BLOCKED
    assert snapshot.rankings == ()
    assert snapshot.missing_inputs == ("industries",)


def test_service_rejects_an_unimplemented_algorithm_version() -> None:
    value = _bundle((_industry("801010", 0.5),))

    with pytest.raises(StrategySpecError, match="unsupported"):
        IndustryRotationService().run(
            IndustryRotationInputBundle(
                as_of=value.as_of,
                knowledge_cutoff=value.knowledge_cutoff,
                publication_cutoff=value.publication_cutoff,
                source_snapshot_ids=value.source_snapshot_ids,
                market_context_feature_set_id=value.market_context_feature_set_id,
                membership_version=value.membership_version,
                algorithm_version="industry-rotation-v2",
                industries=value.industries,
            )
        )
