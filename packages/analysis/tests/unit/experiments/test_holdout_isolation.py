"""Holdout isolation remains outside Campaign authority and research memory."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.campaign import (
    ExperimentPlan,
    ResearchCampaignManifest,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    SnapshotId,
)
from ditto_analysis.experiments.research_memory import (
    KnowledgeSource,
    ResearchFeedback,
)


def test_campaign_contracts_have_no_holdout_authority_or_result_surface() -> None:
    manifest_fields = {item.name for item in fields(ResearchCampaignManifest)}
    plan_fields = {item.name for item in fields(ExperimentPlan)}

    assert not any("holdout" in name for name in manifest_fields | plan_fields)


def test_holdout_result_cannot_become_next_generation_feedback() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ResearchFeedback(
            campaign_id=ExperimentId("campaign-holdout-isolation"),
            candidate_id=CandidateId("candidate-holdout-isolation"),
            evaluation_result_hash=ContentHash("a" * 64),
            summary="The sealed holdout passed.",
            evidence_refs=(ContentHash("b" * 64),),
            outcome_known_at=datetime(2026, 8, 16, tzinfo=UTC),
            snapshot_id=SnapshotId("snapshot-holdout-isolation"),
            source=KnowledgeSource.HOLDOUT_RESULT,
        )

    assert (
        exc_info.value.details["reason_code"] == "prohibited_research_feedback_source"
    )
