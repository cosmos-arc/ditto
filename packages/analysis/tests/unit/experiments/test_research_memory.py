"""R5 PIT-safe research memory domain contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    SnapshotId,
)
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
    KnowledgeStatusEvent,
    ResearchFeedback,
)

KNOWN_AT = datetime(2026, 8, 12, 8, tzinfo=UTC)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _knowledge(
    *,
    scope: KnowledgeScope = KnowledgeScope.CAMPAIGN_LOCAL,
    source: KnowledgeSource = KnowledgeSource.HOST_VALIDATION,
) -> KnowledgeItem:
    promoted = scope is not KnowledgeScope.CAMPAIGN_LOCAL
    return KnowledgeItem(
        knowledge_id="knowledge-1",
        campaign_id=ExperimentId("campaign-1"),
        claim="The reversal feature decays after ten sessions.",
        scope=scope,
        scope_ref=(
            "strategy-family-1" if scope is KnowledgeScope.STRATEGY_FAMILY else None
        ),
        evidence_refs=(_hash("a"),),
        outcome_known_at=KNOWN_AT,
        snapshot_id=SnapshotId("snapshot-1"),
        source=source,
        source_hash=_hash("b"),
        status=KnowledgeStatus.ACTIVE,
        promotion_receipt_hash=_hash("c") if promoted else None,
        independent_evidence_hash=_hash("d") if promoted else None,
    )


def test_knowledge_is_visible_only_at_or_after_outcome_known_at() -> None:
    knowledge = _knowledge()

    with pytest.raises(ExperimentSpecError) as exc_info:
        knowledge.require_visible_at(datetime(2026, 8, 12, 7, 59, tzinfo=UTC))

    assert exc_info.value.details["reason_code"] == "research_memory_not_yet_known"
    assert knowledge.require_visible_at(KNOWN_AT) is knowledge


def test_knowledge_rejects_naive_known_at_and_cutoff() -> None:
    with pytest.raises(ExperimentSpecError) as known_at_exc:
        replace(_knowledge(), outcome_known_at=datetime(2026, 8, 12, 8))
    with pytest.raises(ExperimentSpecError) as cutoff_exc:
        _knowledge().require_visible_at(datetime(2026, 8, 12, 9))

    assert known_at_exc.value.details["reason_code"] == "datetime_not_utc"
    assert cutoff_exc.value.details["reason_code"] == "datetime_not_utc"


@pytest.mark.parametrize(
    "source",
    [
        KnowledgeSource.MODEL_SELF_EVALUATION,
        KnowledgeSource.UNVERIFIED_EXPLANATION,
        KnowledgeSource.HOLDOUT_RESULT,
    ],
)
def test_long_term_memory_rejects_untrusted_or_holdout_sources(
    source: KnowledgeSource,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _knowledge(source=source)

    assert exc_info.value.details["reason_code"] == "prohibited_research_memory_source"


@pytest.mark.parametrize(
    "scope",
    [KnowledgeScope.STRATEGY_FAMILY, KnowledgeScope.GLOBAL],
)
def test_non_local_memory_requires_human_promotion_and_independent_evidence(
    scope: KnowledgeScope,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            _knowledge(scope=scope),
            promotion_receipt_hash=None,
        )

    assert exc_info.value.details["reason_code"] == "research_memory_promotion_unproven"


def test_scope_reference_is_exact_for_local_family_and_global_memory() -> None:
    assert _knowledge().scope_ref is None
    assert _knowledge(scope=KnowledgeScope.STRATEGY_FAMILY).scope_ref == (
        "strategy-family-1"
    )
    assert _knowledge(scope=KnowledgeScope.GLOBAL).scope_ref is None

    with pytest.raises(ExperimentSpecError) as local_exc:
        replace(_knowledge(), scope_ref="strategy-family-1")
    with pytest.raises(ExperimentSpecError) as family_exc:
        replace(_knowledge(scope=KnowledgeScope.STRATEGY_FAMILY), scope_ref=None)

    assert local_exc.value.details["reason_code"] == "invalid_research_memory_scope"
    assert family_exc.value.details["reason_code"] == "invalid_research_memory_scope"


def test_feedback_rejects_holdout_input_and_obeys_known_at() -> None:
    feedback = ResearchFeedback(
        campaign_id=ExperimentId("campaign-1"),
        candidate_id=CandidateId("candidate-1"),
        evaluation_result_hash=_hash("e"),
        summary="Validation turnover exceeded the preregistered constraint.",
        evidence_refs=(_hash("f"),),
        outcome_known_at=KNOWN_AT,
        snapshot_id=SnapshotId("snapshot-1"),
        source=KnowledgeSource.HOST_VALIDATION,
    )

    assert feedback.require_visible_at(KNOWN_AT) is feedback
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(feedback, source=KnowledgeSource.HOLDOUT_RESULT)

    assert (
        exc_info.value.details["reason_code"] == "prohibited_research_feedback_source"
    )


def test_knowledge_status_event_cannot_restore_active_state() -> None:
    event = KnowledgeStatusEvent(
        event_id="knowledge-event-1",
        knowledge_id="knowledge-1",
        previous_status=KnowledgeStatus.ACTIVE,
        status=KnowledgeStatus.CONTRADICTED,
        outcome_known_at=KNOWN_AT,
        evidence_hash=_hash("1"),
    )

    assert event.status is KnowledgeStatus.CONTRADICTED
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            event,
            previous_status=KnowledgeStatus.CONTRADICTED,
            status=KnowledgeStatus.ACTIVE,
        )

    assert (
        exc_info.value.details["reason_code"] == "invalid_knowledge_status_transition"
    )


def test_knowledge_status_can_progress_monotonically_to_revoked() -> None:
    event = KnowledgeStatusEvent(
        event_id="knowledge-event-2",
        knowledge_id="knowledge-1",
        previous_status=KnowledgeStatus.CONTRADICTED,
        status=KnowledgeStatus.REVOKED,
        outcome_known_at=KNOWN_AT,
        evidence_hash=_hash("2"),
    )

    assert event.status is KnowledgeStatus.REVOKED
