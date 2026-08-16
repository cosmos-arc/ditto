from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest
from ditto_agent.contracts.approval import (
    CampaignAuthorization,
    CampaignBudget,
    CampaignGrant,
)
from ditto_agent.contracts.evidence import (
    EvidenceEnvelope,
    GroundedAnswer,
    GroundedClaim,
)
from ditto_agent.contracts.runtime import (
    AgentEvent,
    AgentManifest,
    AgentRun,
    AgentSession,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)

LOCAL = timezone(timedelta(hours=8))


def _temporal_context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 15, 0, tzinfo=LOCAL),
            knowledge_cutoff=datetime(2026, 8, 12, 14, 55, tzinfo=LOCAL),
            publication_cutoff=datetime(2026, 8, 12, 14, 50, tzinfo=LOCAL),
            source_snapshot_id="snapshot-20260812",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH", "510500.SH"),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def test_runtime_contracts_are_frozen_validated_and_utc_normalized() -> None:
    manifest = AgentManifest(
        manifest_id="manifest-r5-v1",
        agent_version="r5.0.0",
        prompt_version="prompt-v1",
        prompt_hash="a" * 64,
        tool_schema_version="tools-v1",
        tool_schema_hash="b" * 64,
        model_profile=ModelProfile.BALANCED,
        model_snapshot="gpt-5.6-terra-2026-08-01",
    )
    session = AgentSession(
        session_id="session-001",
        created_at=datetime(2026, 8, 12, 8, 0, tzinfo=LOCAL),
        retention_class=RetentionClass.STANDARD,
    )
    run = AgentRun(
        run_id="run-001",
        session_id=session.session_id,
        status=RunStatus.QUEUED,
        objective="explain the latest governed experiment",
        authority_hash="c" * 64,
        max_model_tokens=12_000,
        max_model_spend_usd=Decimal("0.25"),
        model_profile=ModelProfile.BALANCED,
        manifest_hash=manifest.manifest_hash,
        created_at=datetime(2026, 8, 12, 8, 1, tzinfo=LOCAL),
    )
    event = AgentEvent(
        event_id=1,
        run_id=run.run_id,
        event_type="run_queued",
        payload_hash="d" * 64,
        occurred_at=datetime(2026, 8, 12, 8, 2, tzinfo=LOCAL),
        prev_hash=None,
    )

    assert manifest.manifest_hash != manifest.prompt_hash
    assert session.created_at == datetime(2026, 8, 12, 0, 0, tzinfo=UTC)
    assert run.created_at.tzinfo is UTC
    assert event.occurred_at.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        run.status = RunStatus.RUNNING


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: AgentSession(
                session_id=" ",
                created_at=datetime.now(tz=UTC),
                retention_class=RetentionClass.STANDARD,
            ),
            "session_id",
        ),
        (
            lambda: AgentSession(
                session_id="session-001",
                created_at=datetime(2026, 8, 12, 0, 0),
                retention_class=RetentionClass.STANDARD,
            ),
            "offset-aware",
        ),
        (
            lambda: AgentEvent(
                event_id=0,
                run_id="run-001",
                event_type="run_queued",
                payload_hash="d" * 64,
                occurred_at=datetime.now(tz=UTC),
                prev_hash=None,
            ),
            "event_id",
        ),
        (
            lambda: AgentSession(
                session_id="session-001",
                created_at=datetime.now(tz=UTC),
                retention_class=cast(RetentionClass, "standard"),
            ),
            "RetentionClass",
        ),
    ],
)
def test_runtime_contracts_reject_invalid_identity_and_time(
    factory: Callable[[], object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


def test_temporal_context_is_host_constructed_complete_and_fail_closed() -> None:
    context = _temporal_context()

    assert context.decision_time == datetime(2026, 8, 12, 7, 0, tzinfo=UTC)
    assert context.knowledge_cutoff < context.decision_time
    assert context.publication_cutoff <= context.knowledge_cutoff
    assert context.allowed_universe == ("510300.SH", "510500.SH")
    constructor = cast(Callable[..., TemporalToolContext], TemporalToolContext)
    with pytest.raises(TypeError):
        constructor(
            decision_time=context.decision_time,
            knowledge_cutoff=context.knowledge_cutoff,
            publication_cutoff=context.publication_cutoff,
            source_snapshot_id=context.source_snapshot_id,
            execution_eligible_at="not_applicable",
            allowed_universe=context.allowed_universe,
            license_class=context.license_class,
            egress_class=context.egress_class,
        )
    with pytest.raises(ValueError, match="source_snapshot_id"):
        TemporalToolContext.from_host(
            TemporalContextInput(
                decision_time=context.decision_time,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_id="",
                execution_eligible_at="not_applicable",
                allowed_universe=context.allowed_universe,
                license_class=context.license_class,
                egress_class=context.egress_class,
            )
        )
    with pytest.raises(ValueError, match="campaign"):
        TemporalToolContext.from_host(
            TemporalContextInput(
                decision_time=context.decision_time,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_id=context.source_snapshot_id,
                execution_eligible_at="not_applicable",
                allowed_universe=context.allowed_universe,
                license_class=context.license_class,
                egress_class=context.egress_class,
                campaign_authorization_id="campaign-auth-001",
            )
        )


def test_evidence_and_grounded_answer_bind_every_claim_to_evidence() -> None:
    mutable_result = {
        "status": "completed",
        "detail": {"label": "cafe\N{COMBINING ACUTE ACCENT}"},
    }
    evidence = EvidenceEnvelope.seal(
        evidence_id="evidence-001",
        tool_name="experiment_summary",
        result=mutable_result,
        artifact_refs=("artifact://experiment/001",),
        temporal_context=_temporal_context(),
        lineage=("experiment-001", "fold-003"),
    )
    answer = GroundedAnswer(
        claims=(
            GroundedClaim(
                claim="The governed run completed.",
                evidence_refs=(evidence.evidence_id,),
            ),
        ),
        uncertainty="Metric uncertainty remains material.",
        missing_evidence=(),
        refusal_reason=None,
    )

    assert evidence.verify_integrity()
    mutable_result["status"] = "tampered"
    assert evidence.result["status"] == "completed"
    detail = cast(Mapping[str, object], evidence.result["detail"])
    assert detail["label"] == "café"
    with pytest.raises(TypeError):
        cast(dict[str, object], evidence.result)["status"] = "tampered"
    assert answer.claims[0].evidence_refs == ("evidence-001",)
    with pytest.raises(ValueError, match="evidence_refs"):
        GroundedClaim(claim="Ungrounded conclusion", evidence_refs=())
    with pytest.raises(ValueError, match="refusal"):
        GroundedAnswer(
            claims=(),
            uncertainty=None,
            missing_evidence=(),
            refusal_reason=None,
        )


def test_campaign_authorization_is_immutable_and_excludes_forbidden_actions() -> None:
    budget = CampaignBudget(
        max_generations=6,
        max_unique_candidates=128,
        max_fold_runs=384,
        max_concurrent_sandboxes=2,
        max_wall_time_seconds=14_400,
        max_temporary_storage_bytes=20 * 1024**3,
        max_model_spend_usd=Decimal("8.00"),
    )
    authorization = CampaignAuthorization.issue(
        authorization_id="campaign-auth-001",
        grant=CampaignGrant(
            campaign_manifest_hash="a" * 64,
            authority_hash="b" * 64,
            authorized_by="operator-001",
            authorized_at=datetime(2026, 8, 12, 8, 0, tzinfo=LOCAL),
            expires_at=datetime(2026, 8, 12, 12, 0, tzinfo=LOCAL),
            search_axis="lookback_days",
            allowed_tools=("candidate_generate", "fold_enqueue", "feedback_record"),
            source_snapshot_id="snapshot-20260812",
            budget=budget,
        ),
    )

    assert authorization.authorized_at.tzinfo is UTC
    assert authorization.expires_at > authorization.authorized_at
    assert authorization.verify_authorization_hash()
    with pytest.raises(FrozenInstanceError):
        authorization.search_axis = "threshold"
    with pytest.raises(ValueError, match="forbidden"):
        CampaignAuthorization.issue(
            authorization_id="campaign-auth-002",
            grant=CampaignGrant(
                campaign_manifest_hash="a" * 64,
                authority_hash="b" * 64,
                authorized_by="operator-001",
                authorized_at=datetime.now(tz=UTC),
                expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
                search_axis="lookback_days",
                allowed_tools=("holdout_evaluate",),
                source_snapshot_id="snapshot-20260812",
                budget=budget,
            ),
        )


def test_campaign_tool_guard_matches_capability_tokens_not_incidental_text() -> None:
    authorization = CampaignAuthorization.issue(
        authorization_id="campaign-auth-003",
        grant=CampaignGrant(
            campaign_manifest_hash="a" * 64,
            authority_hash="b" * 64,
            authorized_by="operator-001",
            authorized_at=datetime.now(tz=UTC),
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
            search_axis="lookback_days",
            allowed_tools=("candidate_ordering_score",),
            source_snapshot_id="snapshot-20260812",
            budget=CampaignBudget(
                max_generations=1,
                max_unique_candidates=1,
                max_fold_runs=1,
                max_concurrent_sandboxes=1,
                max_wall_time_seconds=60,
                max_temporary_storage_bytes=1024,
                max_model_spend_usd=Decimal("0"),
            ),
        ),
    )

    assert authorization.allowed_tools == ("candidate_ordering_score",)
