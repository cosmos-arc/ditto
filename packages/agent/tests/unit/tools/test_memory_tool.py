"""Agent research-memory tool scope and PIT boundary tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.memory import (
    ResearchMemoryTool,
    ResearchMemoryToolExecutionContext,
)
from ditto_analysis.experiments.models import ContentHash, ExperimentId, SnapshotId
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
)
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.queries.evidence_contracts import (
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)
from ditto_application.queries.research_memory import ResearchMemoryQueryFacade
from ditto_application.queries.research_memory_contracts import (
    ResearchMemoryReadModel,
    ResearchMemoryScope,
)

KNOWN_AT = datetime(2026, 8, 12, 8, tzinfo=UTC)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _knowledge() -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id="knowledge-visible",
        campaign_id=ExperimentId("campaign-current"),
        claim="A verified feature-decay claim.",
        scope=KnowledgeScope.CAMPAIGN_LOCAL,
        scope_ref=None,
        evidence_refs=(_hash("a"),),
        outcome_known_at=KNOWN_AT,
        snapshot_id=SnapshotId("snapshot-origin"),
        source=KnowledgeSource.HOST_VALIDATION,
        source_hash=_hash("b"),
        status=KnowledgeStatus.ACTIVE,
        promotion_receipt_hash=None,
        independent_evidence_hash=None,
    )


class _Reader:
    def list_knowledge_visible_for_scope(
        self,
        campaign_id: ExperimentId,
        strategy_family_ref: str | None,
        knowledge_cutoff: datetime,
    ) -> tuple[KnowledgeItem, ...]:
        assert campaign_id == ExperimentId("campaign-current")
        assert strategy_family_ref == "family-current"
        assert knowledge_cutoff == KNOWN_AT
        return (_knowledge(),)


class _InvalidEvidenceFacade:
    def list_visible(
        self,
        *,
        scope: ResearchMemoryScope,
        context: EvidenceTemporalContext,
    ) -> ResearchMemoryReadModel:
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "items": (
                    {
                        "knowledge_id": "knowledge-invalid",
                        "evidence_refs": (123,),
                    },
                )
            },
        )
        provisional = ResearchMemoryReadModel(
            scope=scope,
            temporal_context=context,
            payload=payload,
            result_hash="0" * 64,
        )
        return replace(
            provisional,
            result_hash=canonical_request_hash(provisional.canonical_payload()),
        )


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=KNOWN_AT + timedelta(hours=1),
            knowledge_cutoff=KNOWN_AT,
            publication_cutoff=KNOWN_AT - timedelta(hours=1),
            source_snapshot_id="snapshot-current",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def test_tool_injects_scope_and_seals_visible_memory() -> None:
    tool = ResearchMemoryTool(facade=ResearchMemoryQueryFacade(reader=_Reader()))

    evidence = tool.invoke(
        arguments={},
        context=_context(),
        execution=ResearchMemoryToolExecutionContext(
            campaign_id="campaign-current",
            strategy_family_ref="family-current",
        ),
    )

    assert evidence.tool_name == "research_memory"
    assert evidence.result["payload"]["items"][0]["knowledge_id"] == (
        "knowledge-visible"
    )
    assert evidence.verify_integrity()


def test_tool_rejects_model_supplied_scope_override() -> None:
    tool = ResearchMemoryTool(facade=ResearchMemoryQueryFacade(reader=_Reader()))

    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments={"campaign_id": "campaign-other"},
            context=_context(),
            execution=ResearchMemoryToolExecutionContext(
                campaign_id="campaign-current",
                strategy_family_ref="family-current",
            ),
        )

    assert "campaign_id" not in tool.spec.input_schema["properties"]
    assert "strategy_family_ref" not in tool.spec.input_schema["properties"]


def test_tool_fails_closed_on_non_hash_evidence_reference() -> None:
    tool = ResearchMemoryTool(facade=_InvalidEvidenceFacade())

    with pytest.raises(ValueError, match="evidence refs are invalid"):
        tool.invoke(
            arguments={},
            context=_context(),
            execution=ResearchMemoryToolExecutionContext(
                campaign_id="campaign-current",
                strategy_family_ref="family-current",
            ),
        )
