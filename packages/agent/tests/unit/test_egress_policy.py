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
