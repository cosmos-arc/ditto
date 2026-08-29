"""PIT and immutability tests for DecisionOpinion outcome feedback."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent._canonical import canonical_sha256
from ditto_agent.outcome_feedback import (
    DecisionOpinionAdoption,
    DecisionOutcomeFeedbackError,
    DecisionOutcomeLinker,
    DecisionOutcomeObservation,
    DecisionOutcomeObservationInput,
)
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionRecord,
)
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext

pytestmark = pytest.mark.pit


def _opinion() -> DecisionOpinionRecord:
    generated_at = datetime(2026, 8, 16, 8, 1, tzinfo=UTC)
    payload = {
        "schema_version": 1,
        "status": "completed",
        "v3_artifact_id": "daily-decision-v3:strategy-1:2026-08-15",
        "v3_evidence_hash": "a" * 64,
        "v3_readiness": "ready",
        "summary": "V3 remains authoritative.",
        "dissent": "Tail risk deserves review.",
        "uncertainty": "This is a shadow interpretation.",
        "evidence_refs": ("daily-decision-v3:strategy-1:2026-08-15",),
        "blocking_reasons": (),
        "reason_code": None,
        "model_profile": "balanced",
        "prompt_hash": "b" * 64,
        "provider_id": "scripted",
        "generated_at": generated_at,
    }
    opinion_hash = canonical_sha256(payload)
    return DecisionOpinionRecord(
        schema_version=1,
        opinion_id=f"decision-opinion-{opinion_hash}",
        shadow_outcome_id=f"decision-shadow-{opinion_hash}",
        status="completed",
        v3_artifact_id="daily-decision-v3:strategy-1:2026-08-15",
        v3_evidence_hash="a" * 64,
        v3_readiness="ready",
        summary="V3 remains authoritative.",
        dissent="Tail risk deserves review.",
        uncertainty="This is a shadow interpretation.",
        evidence_refs=("daily-decision-v3:strategy-1:2026-08-15",),
        blocking_reasons=(),
        reason_code=None,
        model_profile="balanced",
        prompt_hash="b" * 64,
        provider_id="scripted",
        generated_at=generated_at,
        opinion_hash=opinion_hash,
    )


def _observation(**changes: object) -> DecisionOutcomeObservation:
    values: dict[str, object] = {
        "opinion_id": _opinion().opinion_id,
        "shadow_outcome_id": _opinion().shadow_outcome_id,
        "outcome_kind": "next_session_review",
        "outcome_period_start": datetime(2026, 8, 17, 1, 30, tzinfo=UTC),
        "outcome_period_end": datetime(2026, 8, 17, 7, 0, tzinfo=UTC),
        "outcome_known_at": datetime(2026, 8, 17, 8, 0, tzinfo=UTC),
        "published_at": datetime(2026, 8, 17, 7, 30, tzinfo=UTC),
        "source_snapshot_id": "outcome-snapshot-1",
        "evidence_refs": ("outcome:strategy-1:2026-08-17",),
        "adoption": DecisionOpinionAdoption.REVIEWED,
        "accuracy_basis_points": 10_000,
        "calibration_basis_points": 9_000,
        "is_holdout": False,
    }
    values.update(changes)
    return DecisionOutcomeObservation.create(
        DecisionOutcomeObservationInput(
            opinion_id=cast(str, values["opinion_id"]),
            shadow_outcome_id=cast(str, values["shadow_outcome_id"]),
            outcome_kind=cast(str, values["outcome_kind"]),
            outcome_period_start=cast(datetime, values["outcome_period_start"]),
            outcome_period_end=cast(datetime, values["outcome_period_end"]),
            outcome_known_at=cast(datetime, values["outcome_known_at"]),
            published_at=cast(datetime, values["published_at"]),
            source_snapshot_id=cast(str, values["source_snapshot_id"]),
            evidence_refs=cast(tuple[str, ...], values["evidence_refs"]),
            adoption=cast(DecisionOpinionAdoption, values["adoption"]),
            accuracy_basis_points=cast(int, values["accuracy_basis_points"]),
            calibration_basis_points=cast(int, values["calibration_basis_points"]),
            is_holdout=cast(bool, values["is_holdout"]),
        )
    )


def _context(**changes: object) -> EvidenceTemporalContext:
    context = EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 17, 8, 30, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 17, 8, 0, tzinfo=UTC),
        source_snapshot_id="outcome-snapshot-1",
    )
    return replace(context, **changes)


def test_linker_records_pit_bound_metrics_without_memory_promotion() -> None:
    feedback = DecisionOutcomeLinker().link(
        opinion=_opinion(),
        observation=_observation(),
        context=_context(),
        linked_at=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
    )

    assert feedback.verify_integrity()
    assert feedback.feedback_id == f"decision-feedback-{feedback.feedback_hash}"
    assert feedback.adoption is DecisionOpinionAdoption.REVIEWED
    assert feedback.accuracy_basis_points == 10_000
    assert feedback.calibration_basis_points == 9_000
    assert feedback.memory_promotion == "none"
    assert feedback.outcome_known_at <= feedback.linked_at


@pytest.mark.parametrize(
    ("observation_changes", "context_changes", "reason_code"),
    [
        (
            {},
            {
                "knowledge_cutoff": datetime(2026, 8, 17, 7, 59, tzinfo=UTC),
                "publication_cutoff": datetime(2026, 8, 17, 7, 59, tzinfo=UTC),
            },
            "decision_outcome_not_yet_known",
        ),
        (
            {},
            {"publication_cutoff": datetime(2026, 8, 17, 7, 29, tzinfo=UTC)},
            "decision_outcome_not_yet_published",
        ),
        (
            {},
            {"source_snapshot_id": "future-snapshot"},
            "decision_outcome_snapshot_mismatch",
        ),
        (
            {"is_holdout": True},
            {},
            "decision_outcome_holdout_forbidden",
        ),
    ],
)
def test_linker_fails_closed_on_future_publication_snapshot_or_holdout(
    observation_changes: dict[str, object],
    context_changes: dict[str, object],
    reason_code: str,
) -> None:
    with pytest.raises(DecisionOutcomeFeedbackError) as exc_info:
        DecisionOutcomeLinker().link(
            opinion=_opinion(),
            observation=_observation(**observation_changes),
            context=_context(**context_changes),
            linked_at=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
        )

    assert exc_info.value.reason_code == reason_code


def test_same_day_return_cannot_be_linked_before_it_is_known() -> None:
    observation = _observation(
        outcome_period_start=datetime(2026, 8, 16, 8, 2, tzinfo=UTC),
        outcome_period_end=datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
        outcome_known_at=datetime(2026, 8, 16, 15, 30, tzinfo=UTC),
        published_at=datetime(2026, 8, 16, 15, 15, tzinfo=UTC),
    )

    with pytest.raises(DecisionOutcomeFeedbackError) as exc_info:
        DecisionOutcomeLinker().link(
            opinion=_opinion(),
            observation=observation,
            context=_context(
                decision_time=datetime(2026, 8, 16, 10, 0, tzinfo=UTC),
                knowledge_cutoff=datetime(2026, 8, 16, 9, 59, tzinfo=UTC),
                publication_cutoff=datetime(2026, 8, 16, 9, 59, tzinfo=UTC),
            ),
            linked_at=datetime(2026, 8, 16, 10, 0, tzinfo=UTC),
        )

    assert exc_info.value.reason_code == "decision_outcome_not_yet_known"


def test_linker_rejects_opinion_identity_tamper() -> None:
    with pytest.raises(DecisionOutcomeFeedbackError) as exc_info:
        DecisionOutcomeLinker().link(
            opinion=replace(_opinion(), opinion_hash="f" * 64),
            observation=_observation(),
            context=_context(),
            linked_at=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
        )

    assert exc_info.value.reason_code == "decision_outcome_opinion_invalid"


def test_feedback_contract_has_no_raw_return_prompt_or_promotion_surface() -> None:
    feedback = DecisionOutcomeLinker().link(
        opinion=_opinion(),
        observation=_observation(),
        context=_context(),
        linked_at=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
    )

    forbidden = {"return", "returns", "prompt", "memory_item", "promotion_action"}
    assert forbidden.isdisjoint(feedback.__dataclass_fields__)
    assert forbidden.isdisjoint(DecisionOutcomeObservation.__dataclass_fields__)
