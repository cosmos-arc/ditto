"""Industry-rotation domain contract and identity tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationIndustryInput,
    IndustryRotationInputBundle,
)
from ditto_strategy.industry_rotation.identity import (
    canonical_industry_rotation_input_hash,
)

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _industry(industry_id: str) -> IndustryRotationIndustryInput:
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


def _bundle(
    *,
    industries: tuple[IndustryRotationIndustryInput, ...] | None = None,
    source_snapshot_ids: tuple[str, ...] = ("source-b", "source-a"),
    algorithm_version: str = "industry-rotation-v1",
    membership_version: str = "sw-l1:2026-08-31",
    market_context_feature_set_id: str | None = "market-context:sha256:abc",
) -> IndustryRotationInputBundle:
    return IndustryRotationInputBundle(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_ids=source_snapshot_ids,
        market_context_feature_set_id=market_context_feature_set_id,
        membership_version=membership_version,
        algorithm_version=algorithm_version,
        industries=industries or (_industry("801010"), _industry("801020")),
        declared_missing_inputs=("optional-z", "optional-a"),
    )


def test_input_identity_normalizes_set_like_lineage_and_industry_order() -> None:
    first = _bundle()
    second = _bundle(
        industries=tuple(reversed(first.industries)),
        source_snapshot_ids=tuple(reversed(first.source_snapshot_ids)),
    )

    assert first.industries == second.industries
    assert first.source_snapshot_ids == ("source-a", "source-b")
    assert first.declared_missing_inputs == ("optional-a", "optional-z")
    assert canonical_industry_rotation_input_hash(first) == (
        canonical_industry_rotation_input_hash(second)
    )


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("algorithm_version", "industry-rotation-v2"),
        ("membership_version", "sw-l1:2026-09-01"),
        ("market_context_feature_set_id", "market-context:sha256:def"),
        ("source_snapshot_ids", ("source-a", "source-c")),
    ],
)
def test_input_identity_tracks_every_replay_boundary(
    field_name: str,
    changed_value: object,
) -> None:
    baseline = _bundle()

    assert canonical_industry_rotation_input_hash(
        replace(baseline, **{field_name: changed_value})
    ) != canonical_industry_rotation_input_hash(baseline)


def test_input_bundle_rejects_future_cutoffs_and_duplicate_industries() -> None:
    with pytest.raises(StrategySpecError, match="knowledge_cutoff"):
        replace(
            _bundle(),
            knowledge_cutoff=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
        )

    with pytest.raises(StrategySpecError, match="unique industry_id"):
        _bundle(industries=(_industry("801010"), _industry("801010")))


def test_contracts_are_immutable_and_defensively_copy_sequences() -> None:
    industries = [_industry("801020"), _industry("801010")]
    bundle = _bundle(industries=industries)  # type: ignore[arg-type]
    industries.append(_industry("801030"))

    assert tuple(row.industry_id for row in bundle.industries) == (
        "801010",
        "801020",
    )
    with pytest.raises(FrozenInstanceError):
        bundle.membership_version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.01, 1.01])
def test_normalized_factor_inputs_must_be_finite_unit_scores(value: float) -> None:
    with pytest.raises(StrategySpecError, match="relative_strength_5d"):
        replace(_industry("801010"), relative_strength_5d=value)
