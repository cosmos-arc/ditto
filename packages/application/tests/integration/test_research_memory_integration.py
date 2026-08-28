"""Durable governed research-memory command and PIT query integration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ditto_analysis.experiments.campaign import SearchAxis
from ditto_analysis.experiments.campaign_persistence import CampaignManifestRecord
from ditto_analysis.experiments.models import ContentHash, ExperimentId, SnapshotId
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
)
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteCampaignReader,
    SQLiteCampaignWriter,
)
from ditto_application.commands.research_memory import ResearchMemoryCommandFacade
from ditto_application.processes.experiments.autonomous_campaign import (
    CampaignAuthorizationProof,
)
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.research_memory import (
    ResearchMemoryQueryFacade,
)
from ditto_application.queries.research_memory_contracts import ResearchMemoryScope
from ditto_application.research_memory_approval_contracts import (
    CAMPAIGN_RECORD_RESEARCH_MEMORY,
    RESEARCH_MEMORY_PROMOTE,
    ResearchMemoryApprovalCheck,
    VerifiedResearchMemoryApproval,
)
from ditto_application.research_memory_contracts import (
    PromoteResearchKnowledgeCommand,
    RevokeResearchKnowledgeCommand,
)

NOW = datetime(2026, 8, 12, 9, tzinfo=UTC)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _campaign(campaign_id: str) -> CampaignManifestRecord:
    payload = json.dumps(
        {
            "campaign_id": campaign_id,
            "lineage_root": "d" * 64,
            "schema_id": "r5-research-campaign-manifest",
            "schema_version": 1,
            "search_axis": SearchAxis.FACTOR_CODE.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return CampaignManifestRecord(
        campaign_id=ExperimentId(campaign_id),
        manifest_hash=ContentHash(hashlib.sha256(payload).hexdigest()),
        manifest_payload=payload,
        search_axis=SearchAxis.FACTOR_CODE,
        lineage_root=_hash("d"),
        created_at_epoch_us=1_786_521_600_000_000,
    )


class _Approved:
    def verify(
        self,
        check: ResearchMemoryApprovalCheck,
    ) -> VerifiedResearchMemoryApproval:
        return VerifiedResearchMemoryApproval.issue(
            check=check,
            approval_id=f"approval-{check.call_id}",
            action_hash="3" * 64,
            operator_id="integration-operator",
            approved_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
            approved=True,
        )


def _authorization(campaign: CampaignManifestRecord) -> CampaignAuthorizationProof:
    return CampaignAuthorizationProof.issue(
        authorization_id="campaign-memory-authorization",
        authorization_hash="1" * 64,
        authority_hash="2" * 64,
        authorized_by="integration-operator",
        authorized_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        campaign_manifest_hash=str(campaign.manifest_hash),
        search_axis=SearchAxis.FACTOR_CODE.value,
        allowed_tools=(CAMPAIGN_RECORD_RESEARCH_MEMORY,),
        source_snapshot_id="snapshot-memory",
        candidate_limit=2,
        fold_run_limit=4,
        generation_limit=2,
        concurrent_sandbox_limit=1,
        wall_time_limit_seconds=60,
        temporary_storage_limit_bytes=1024,
        model_spend_limit_usd_micros=1,
    )


def test_memory_promotion_and_revocation_are_durable_and_pit_safe(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteCampaignReader(database)
    writer = SQLiteCampaignWriter(database)
    source_campaign = _campaign("campaign-source")
    consumer_campaign = _campaign("campaign-consumer")
    writer.add_campaign(source_campaign)
    writer.add_campaign(consumer_campaign)
    command_facade = ResearchMemoryCommandFacade(
        reader=reader,
        writer=writer,
        approval_verifier=_Approved(),
    )
    local = KnowledgeItem(
        knowledge_id="knowledge-local",
        campaign_id=source_campaign.campaign_id,
        claim="The feature decays after ten sessions.",
        scope=KnowledgeScope.CAMPAIGN_LOCAL,
        scope_ref=None,
        evidence_refs=(_hash("a"),),
        outcome_known_at=NOW - timedelta(minutes=5),
        snapshot_id=SnapshotId("snapshot-memory"),
        source=KnowledgeSource.HOST_VALIDATION,
        source_hash=_hash("b"),
        status=KnowledgeStatus.ACTIVE,
        promotion_receipt_hash=None,
        independent_evidence_hash=None,
    )
    command_facade.record_local(
        local,
        authorization=_authorization(source_campaign),
        occurred_at=NOW,
    )
    promotion = PromoteResearchKnowledgeCommand(
        source_knowledge_id=local.knowledge_id,
        promoted_knowledge_id="knowledge-family",
        target_scope=KnowledgeScope.STRATEGY_FAMILY,
        strategy_family_ref="family-current",
        independent_evidence_hash=_hash("c"),
        independent_evidence_known_at=NOW - timedelta(minutes=1),
        run_id="run-memory",
        episode_id="episode-run-memory",
        call_id="call-promote",
    )

    first_promotion = command_facade.promote(promotion, occurred_at=NOW)
    assert command_facade.promote(promotion, occurred_at=NOW) == first_promotion
    cross_campaign = reader.list_knowledge_visible_for_scope(
        consumer_campaign.campaign_id,
        "family-current",
        NOW + timedelta(seconds=30),
        NOW + timedelta(seconds=30),
        "snapshot-memory",
    )
    assert tuple(item.knowledge_id for item in cross_campaign) == ("knowledge-family",)

    revocation_time = NOW + timedelta(minutes=1)
    revocation = RevokeResearchKnowledgeCommand(
        knowledge_id="knowledge-family",
        event_id="knowledge-family-revoked",
        evidence_hash=_hash("e"),
        outcome_known_at=revocation_time,
        run_id="run-memory",
        episode_id="episode-run-memory",
        call_id="call-revoke",
    )
    first_revocation = command_facade.revoke(
        revocation,
        occurred_at=revocation_time,
    )
    assert (
        command_facade.revoke(
            revocation,
            occurred_at=revocation_time,
        )
        == first_revocation
    )
    before = reader.get_knowledge_visible_at(
        "knowledge-family",
        revocation_time - timedelta(microseconds=1),
    )
    after = reader.get_knowledge_visible_at("knowledge-family", revocation_time)
    assert before is not None
    assert before.status is KnowledgeStatus.ACTIVE
    assert after is not None
    assert after.status is KnowledgeStatus.REVOKED

    query = ResearchMemoryQueryFacade(reader=reader)
    result = query.list_visible(
        scope=ResearchMemoryScope(
            campaign_id=str(consumer_campaign.campaign_id),
            strategy_family_ref="family-current",
        ),
        context=EvidenceTemporalContext(
            decision_time=revocation_time,
            knowledge_cutoff=revocation_time,
            publication_cutoff=NOW - timedelta(days=1),
            source_snapshot_id="snapshot-memory",
        ),
    )
    assert result.verify_integrity()
    assert result.payload.value["items"] == ()
    assert first_promotion.operation == RESEARCH_MEMORY_PROMOTE
