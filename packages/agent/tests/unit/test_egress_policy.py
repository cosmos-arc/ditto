from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import EgressClass, TemporalContextInput
from ditto_agent.runtime.egress_policy import (
    EvidenceEgressPolicy,
    EvidenceEgressPolicyError,
)
from ditto_agent.runtime.temporal_context import TemporalContextFactory

DECISION_TIME = datetime(2026, 8, 16, 7, 0, tzinfo=UTC)


def _context(
    *,
    egress_class: EgressClass = EgressClass.CLOUD_ALLOWED,
    license_class: str = "redistribution_reviewed",
    snapshot_id: str = "snapshot-20260816",
):
    return TemporalContextFactory().build(
        TemporalContextInput(
            decision_time=DECISION_TIME,
            knowledge_cutoff=DECISION_TIME - timedelta(minutes=5),
            publication_cutoff=DECISION_TIME - timedelta(minutes=10),
            source_snapshot_id=snapshot_id,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class=license_class,
            egress_class=egress_class,
        )
    )


def _evidence(*, context=None) -> EvidenceEnvelope:
    return EvidenceEnvelope.seal(
        evidence_id="evidence-001",
        tool_name="experiment_summary",
        result={"status": "completed", "metric": "host-computed"},
        artifact_refs=("artifact://experiment/001",),
        temporal_context=context or _context(),
        lineage=("experiment-001", "fold-001"),
    )


@pytest.mark.parametrize(
    ("egress_class", "reason_code"),
    [
        (EgressClass.LOCAL_ONLY, "evidence_egress_not_cloud_allowed"),
        (EgressClass.PROHIBITED, "evidence_egress_not_cloud_allowed"),
    ],
)
def test_non_cloud_evidence_is_rejected_before_model_payload(
    egress_class: EgressClass,
    reason_code: str,
) -> None:
    context = _context(egress_class=egress_class)
    policy = EvidenceEgressPolicy(approved_license_classes=("redistribution_reviewed",))

    with pytest.raises(EvidenceEgressPolicyError) as exc_info:
        policy.prepare_for_model((_evidence(context=context),), context=context)

    assert exc_info.value.reason_code == reason_code


def test_cloud_evidence_requires_explicit_license_allowlist() -> None:
    context = _context()
    evidence = _evidence(context=context)

    with pytest.raises(EvidenceEgressPolicyError) as exc_info:
        EvidenceEgressPolicy.deny_all().prepare_for_model((evidence,), context=context)

    assert exc_info.value.reason_code == "evidence_license_not_approved"


def test_policy_rejects_tampered_or_cross_context_evidence_atomically() -> None:
    context = _context()
    evidence = _evidence(context=context)
    policy = EvidenceEgressPolicy(approved_license_classes=("redistribution_reviewed",))

    with pytest.raises(EvidenceEgressPolicyError) as tamper_info:
        policy.prepare_for_model(
            (replace(evidence, integrity_hash="0" * 64),),
            context=context,
        )
    with pytest.raises(EvidenceEgressPolicyError) as context_info:
        policy.prepare_for_model(
            (evidence,),
            context=_context(snapshot_id="snapshot-20260815"),
        )

    assert tamper_info.value.reason_code == "evidence_integrity_invalid"
    assert context_info.value.reason_code == "evidence_temporal_context_mismatch"


def test_approved_cloud_evidence_produces_stable_minimal_model_payload() -> None:
    context = _context()
    evidence = _evidence(context=context)
    policy = EvidenceEgressPolicy(approved_license_classes=("redistribution_reviewed",))

    first = policy.prepare_for_model((evidence,), context=context)
    second = policy.prepare_for_model((evidence,), context=context)

    assert first == second
    assert len(first) == 1
    assert first[0].evidence_id == evidence.evidence_id
    assert first[0].result == evidence.result
    assert first[0].integrity_hash == evidence.integrity_hash
    assert first[0].verify_payload_hash()
    assert not hasattr(first[0], "license_notes")


def test_approved_research_selection_evidence_excludes_full_universe() -> None:
    context = _context(license_class="approved-research")
    candidates = tuple(
        {
            "instrument_id": index,
            "instrument_name": f"candidate-{index}",
            "rank": index,
            "score": 1.0 / index,
            "factor_contributions": ({"factor_name": "momentum", "value": index},),
        }
        for index in range(1, 6)
    )
    exclusions = (
        {
            "instrument_id": 10,
            "reason_code": "insufficient_liquidity",
            "stage": "hard_filter",
            "detail": "average_turnover_below_minimum",
        },
        {
            "instrument_id": 11,
            "reason_code": "insufficient_liquidity",
            "stage": "hard_filter",
            "detail": "average_turnover_below_minimum",
        },
        {
            "instrument_id": 12,
            "reason_code": "below_top_k",
            "stage": "ranking",
            "detail": "eligible_score_below_top_k",
        },
    )
    evidence = EvidenceEnvelope.seal(
        evidence_id="evidence-selection-001",
        tool_name="selection_run_evidence",
        result={
            "schema_version": 1,
            "kind": "selection_run",
            "run_id": "selection-run:sha256:" + "a" * 64,
            "status": "ready",
            "payload_schema_version": 1,
            "payload_hash": "b" * 64,
            "payload": {
                "run_id": "selection-run:sha256:" + "a" * 64,
                "status": "ready",
                "seed": 20260902,
                "candidates": candidates,
                "exclusions": exclusions,
                "missing_inputs": ("industry_mapping",),
                "source_snapshot_ids": ("snapshot-1", "snapshot-2"),
            },
            "artifacts": (),
        },
        artifact_refs=("selection-run:sha256:" + "a" * 64,),
        temporal_context=context,
        lineage=("selection-run:sha256:" + "a" * 64,),
    )

    payload = EvidenceEgressPolicy(
        approved_license_classes=("approved-research",)
    ).prepare_for_model((evidence,), context=context)[0]

    assert payload.result["redaction_profile"] == "approved-research-minimal-v1"
    projected = payload.result["payload"]
    assert projected["candidate_count"] == 5
    assert projected["exclusion_count"] == 3
    assert len(projected["top_candidates"]) == 3
    assert projected["top_candidates"][0]["factor_contributions"] == (
        {"factor_name": "momentum", "value": 1},
    )
    assert projected["exclusion_summary"] == (
        {"stage": "hard_filter", "reason_code": "insufficient_liquidity", "count": 2},
        {"stage": "ranking", "reason_code": "below_top_k", "count": 1},
    )
    assert "candidates" not in projected
    assert "exclusions" not in projected
    assert payload.integrity_hash == evidence.integrity_hash
    assert any(
        item.startswith("minimal-egress:sha256:") for item in payload.artifact_refs
    )
    assert payload.verify_payload_hash()
