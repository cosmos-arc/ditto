"""Adversarial validation tests for industry-rotation contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationContribution,
    IndustryRotationIndustryInput,
    IndustryRotationInputBundle,
    IndustryRotationRank,
    IndustryRotationSnapshot,
    IndustryRotationStatus,
)

_NOW = datetime(2026, 9, 4, tzinfo=UTC)


def _industry(industry_id: str = "801010") -> IndustryRotationIndustryInput:
    return IndustryRotationIndustryInput(
        industry_id=industry_id,
        industry_name=f"Industry {industry_id}",
        relative_strength_5d=0.1,
        relative_strength_20d=0.2,
        relative_strength_60d=0.3,
        advancing_count=6,
        declining_count=4,
        member_count=10,
        trend_score=0.4,
        fundamental_score=0.5,
        regime_alignment_score=0.6,
    )


def _bundle() -> IndustryRotationInputBundle:
    return IndustryRotationInputBundle(
        as_of=_NOW,
        knowledge_cutoff=_NOW,
        publication_cutoff=_NOW,
        source_snapshot_ids=("source-1",),
        market_context_feature_set_id="market-context:sha256:abc",
        membership_version="sw-l1:2026-09-04",
        algorithm_version="industry-rotation-v1",
        industries=(_industry(),),
    )


def _contribution(
    metric: str = "momentum",
    *,
    contribution: float = 0.25,
) -> IndustryRotationContribution:
    return IndustryRotationContribution(
        metric=metric,
        value=0.5,
        weight=0.5,
        contribution=contribution,
    )


def _rank(
    industry_id: str = "801010",
    *,
    rank: int = 1,
    score: float = 0.25,
    contributions: tuple[IndustryRotationContribution, ...] | None = None,
) -> IndustryRotationRank:
    return IndustryRotationRank(
        industry_id=industry_id,
        industry_name="Agriculture",
        rank=rank,
        score=score,
        contributions=(_contribution(),) if contributions is None else contributions,
    )


def _snapshot() -> IndustryRotationSnapshot:
    return IndustryRotationSnapshot(
        input_hash="a" * 64,
        as_of=_NOW,
        knowledge_cutoff=_NOW,
        publication_cutoff=_NOW,
        source_snapshot_ids=("source-1",),
        market_context_feature_set_id=None,
        membership_version="sw-l1:2026-09-04",
        algorithm_version="industry-rotation-v1",
        status=IndustryRotationStatus.READY,
        rankings=(_rank(),),
        missing_inputs=(),
    )


@pytest.mark.parametrize("rank", [1.5, "1"])
def test_rank_requires_an_exact_positive_integer(rank: object) -> None:
    with pytest.raises(StrategySpecError, match="positive integer"):
        replace(_rank(), rank=cast("int", rank))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("input_hash", 7), ("status", "ready")],
)
def test_snapshot_rejects_untyped_identity_and_status(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(StrategySpecError):
        replace(_snapshot(), **{field_name: value})


@pytest.mark.parametrize(
    ("target", "field_name", "value"),
    [
        (_industry(), "industry_id", ""),
        (_industry(), "industry_name", " padded "),
        (_bundle(), "market_context_feature_set_id", " padded "),
        (_bundle(), "membership_version", cast("str", 7)),
    ],
)
def test_text_fields_require_normalized_non_empty_strings(
    target: IndustryRotationIndustryInput | IndustryRotationInputBundle,
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(target, **{field_name: value})

    assert exc_info.value.details["reason"] == "invalid_industry_rotation_text"


@pytest.mark.parametrize(
    "field_name", ["as_of", "knowledge_cutoff", "publication_cutoff"]
)
def test_input_times_must_be_timezone_aware(field_name: str) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_bundle(), **{field_name: datetime(2026, 9, 4)})

    assert exc_info.value.details == {
        "reason": "invalid_industry_rotation_time",
        "field_name": field_name,
    }


@pytest.mark.parametrize("value", [True, "0.5"])
def test_industry_scores_reject_non_numeric_values(value: object) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_industry(), relative_strength_5d=cast("float", value))

    assert exc_info.value.details["reason"] == "invalid_industry_rotation_score"


def test_industry_counts_allow_explicitly_missing_values() -> None:
    industry = replace(
        _industry(),
        advancing_count=None,
        declining_count=None,
        member_count=None,
    )

    assert industry.advancing_count is None
    assert industry.declining_count is None
    assert industry.member_count is None


@pytest.mark.parametrize("value", [True, -1, 1.5])
def test_industry_counts_reject_non_integer_or_negative_values(value: object) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_industry(), advancing_count=cast("int", value))

    assert exc_info.value.details["reason"] == "invalid_industry_rotation_count"


def test_industry_breadth_cannot_exceed_membership() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_industry(), advancing_count=7, declining_count=4)

    assert exc_info.value.details["reason"] == "invalid_industry_rotation_breadth"


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("industries", "801010", "invalid_industry_rotation_sequence"),
        (
            "industries",
            (cast("IndustryRotationIndustryInput", "801010"),),
            "invalid_industry_rotation_sequence_item",
        ),
        (
            "source_snapshot_ids",
            ("source-1", "source-1"),
            "duplicate_industry_rotation_identity",
        ),
        ("source_snapshot_ids", (), "missing_industry_rotation_lineage"),
    ],
)
def test_input_bundle_rejects_invalid_sequences_and_lineage(
    field_name: str,
    value: object,
    reason: str,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_bundle(), **{field_name: value})

    assert exc_info.value.details["reason"] == reason


@pytest.mark.pit
def test_input_bundle_rejects_future_visible_cutoffs_but_allows_boundary() -> None:
    boundary = _bundle()
    future = datetime(2026, 9, 4, 0, 0, 1, tzinfo=UTC)

    assert boundary.publication_cutoff == boundary.knowledge_cutoff == boundary.as_of
    with pytest.raises(StrategySpecError) as publication_exc:
        replace(boundary, publication_cutoff=future)
    with pytest.raises(StrategySpecError) as knowledge_exc:
        replace(boundary, knowledge_cutoff=future)

    assert publication_exc.value.details["reason"] == (
        "invalid_industry_rotation_cutoff"
    )
    assert knowledge_exc.value.details["reason"] == "invalid_industry_rotation_cutoff"


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("weight", None, "invalid_industry_rotation_weight"),
        ("weight", -0.1, "invalid_industry_rotation_weight"),
        ("contribution", None, "invalid_industry_rotation_contribution"),
    ],
)
def test_contribution_requires_weight_and_contribution(
    field_name: str,
    value: object,
    reason: str,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        replace(_contribution(), **{field_name: value})

    assert exc_info.value.details["reason"] == reason


def test_rank_requires_score_unique_metrics_and_exact_additive_total() -> None:
    with pytest.raises(StrategySpecError) as score_exc:
        replace(_rank(), score=cast("float", None))
    with pytest.raises(StrategySpecError) as duplicate_exc:
        replace(
            _rank(),
            contributions=(
                _contribution(contribution=0.1),
                _contribution(contribution=0.15),
            ),
        )
    with pytest.raises(StrategySpecError) as total_exc:
        replace(_rank(), score=0.5)

    assert score_exc.value.details["reason"] == "invalid_industry_rotation_score"
    assert duplicate_exc.value.details["reason"] == (
        "duplicate_industry_rotation_metric"
    )
    assert total_exc.value.details["reason"] == (
        "invalid_industry_rotation_score_total"
    )


def test_snapshot_rejects_noncanonical_hash_and_unaware_time() -> None:
    with pytest.raises(StrategySpecError) as hash_exc:
        replace(_snapshot(), input_hash="A" * 64)
    with pytest.raises(StrategySpecError) as time_exc:
        replace(_snapshot(), as_of=datetime(2026, 9, 4))

    assert hash_exc.value.details["reason"] == "invalid_industry_rotation_input_hash"
    assert time_exc.value.details["reason"] == "invalid_industry_rotation_time"


@pytest.mark.pit
def test_snapshot_rejects_future_visible_cutoffs() -> None:
    future = datetime(2026, 9, 4, 0, 0, 1, tzinfo=UTC)

    with pytest.raises(StrategySpecError) as publication_exc:
        replace(_snapshot(), publication_cutoff=future)
    with pytest.raises(StrategySpecError) as knowledge_exc:
        replace(_snapshot(), knowledge_cutoff=future)

    assert publication_exc.value.details["reason"] == (
        "invalid_industry_rotation_cutoff"
    )
    assert knowledge_exc.value.details["reason"] == "invalid_industry_rotation_cutoff"


def test_snapshot_rejects_noncontiguous_and_duplicate_industry_rankings() -> None:
    with pytest.raises(StrategySpecError) as order_exc:
        replace(_snapshot(), rankings=(_rank(rank=2),))
    with pytest.raises(StrategySpecError) as duplicate_exc:
        replace(
            _snapshot(),
            rankings=(
                _rank(),
                _rank(
                    rank=2,
                    contributions=(_contribution("trend"),),
                ),
            ),
        )

    assert order_exc.value.details["reason"] == "invalid_industry_rotation_rank_order"
    assert duplicate_exc.value.details["reason"] == (
        "duplicate_industry_rotation_industry"
    )
