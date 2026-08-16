"""Governed research-memory write and promotion command tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from ditto_analysis.experiments.campaign import SearchAxis
from ditto_analysis.experiments.campaign_persistence import CampaignManifestRecord
from ditto_analysis.experiments.models import ContentHash, ExperimentId, SnapshotId
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
    KnowledgeStatusEvent,
)
from ditto_application.commands.research_memory import ResearchMemoryCommandFacade
from ditto_application.exceptions import AppCommandError
from ditto_application.processes.experiments.autonomous_campaign import (
    CampaignAuthorizationProof,
)
from ditto_application.providers_research_memory import AppResearchMemoryProvider
from ditto_application.research_memory_approval_contracts import (
    CAMPAIGN_RECORD_RESEARCH_MEMORY,
    RESEARCH_MEMORY_PROMOTE,
    RESEARCH_MEMORY_REVOKE,
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


def _campaign() -> CampaignManifestRecord:
    payload = json.dumps(
        {
            "campaign_id": "campaign-current",
            "lineage_root": "d" * 64,
            "schema_id": "r5-research-campaign-manifest",
            "schema_version": 1,
            "search_axis": SearchAxis.FACTOR_CODE.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return CampaignManifestRecord(
        campaign_id=ExperimentId("campaign-current"),
        manifest_hash=ContentHash(hashlib.sha256(payload).hexdigest()),
        manifest_payload=payload,
        search_axis=SearchAxis.FACTOR_CODE,
        lineage_root=_hash("d"),
        created_at_epoch_us=1,
    )


def _local() -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id="knowledge-local",
        campaign_id=ExperimentId("campaign-current"),
        claim="The feature decays after ten sessions.",
        scope=KnowledgeScope.CAMPAIGN_LOCAL,
        scope_ref=None,
        evidence_refs=(_hash("a"),),
        outcome_known_at=NOW - timedelta(hours=1),
        snapshot_id=SnapshotId("snapshot-current"),
        source=KnowledgeSource.HOST_VALIDATION,
        source_hash=_hash("b"),
        status=KnowledgeStatus.ACTIVE,
        promotion_receipt_hash=None,
        independent_evidence_hash=None,
    )


def _authorization() -> CampaignAuthorizationProof:
    return CampaignAuthorizationProof.issue(
        authorization_id="campaign-auth",
        authorization_hash="1" * 64,
        authority_hash="2" * 64,
        authorized_by="operator",
        authorized_at=NOW - timedelta(hours=2),
        expires_at=NOW + timedelta(hours=2),
        campaign_manifest_hash=str(_campaign().manifest_hash),
        search_axis=SearchAxis.FACTOR_CODE.value,
        allowed_tools=(CAMPAIGN_RECORD_RESEARCH_MEMORY,),
        source_snapshot_id="snapshot-current",
        candidate_limit=2,
        fold_run_limit=4,
        generation_limit=2,
        concurrent_sandbox_limit=1,
        wall_time_limit_seconds=60,
        temporary_storage_limit_bytes=1024,
        model_spend_limit_usd_micros=1,
    )


class _Reader:
    def __init__(self, item: KnowledgeItem | None = None) -> None:
        self.item = item
        self.events: list[KnowledgeStatusEvent] = []

    def get_campaign(self, campaign_id: ExperimentId) -> CampaignManifestRecord | None:
        return _campaign() if campaign_id == _campaign().campaign_id else None

    def get_knowledge_visible_at(
        self,
        knowledge_id: str,
        knowledge_cutoff: datetime,
    ) -> KnowledgeItem | None:
        if (
            self.item is None
            or self.item.knowledge_id != knowledge_id
            or self.item.outcome_known_at > knowledge_cutoff
        ):
            return None
        status = self.events[-1].status if self.events else self.item.status
        return replace(self.item, status=status)

    def list_knowledge_status_events(
        self,
        knowledge_id: str,
    ) -> tuple[KnowledgeStatusEvent, ...]:
        return tuple(
            event for event in self.events if event.knowledge_id == knowledge_id
        )


class _Writer:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.knowledge: list[KnowledgeItem] = []

    def add_knowledge(self, item: KnowledgeItem) -> None:
        if item not in self.knowledge:
            self.knowledge.append(item)

    def append_knowledge_status_event(self, event: KnowledgeStatusEvent) -> None:
        if event not in self.reader.events:
            self.reader.events.append(event)


class _Verifier:
    def __init__(self, *, approved: bool = True, drift: bool = False) -> None:
        self.approved = approved
        self.drift = drift

    def verify(
        self,
        check: ResearchMemoryApprovalCheck,
    ) -> VerifiedResearchMemoryApproval:
        proof = VerifiedResearchMemoryApproval.issue(
            check=check,
            approval_id="approval-memory",
            action_hash="3" * 64,
            operator_id="operator",
            approved_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=1),
            approved=self.approved,
        )
        return replace(proof, call_id="call-drift") if self.drift else proof


def _facade(
    item: KnowledgeItem | None = None,
    *,
    verifier: _Verifier | None = None,
) -> tuple[ResearchMemoryCommandFacade, _Reader, _Writer]:
    reader = _Reader(item)
    writer = _Writer(reader)
    return (
        ResearchMemoryCommandFacade(
            reader=reader,
            writer=writer,
            approval_verifier=verifier or _Verifier(),
        ),
        reader,
        writer,
    )


def _promotion() -> PromoteResearchKnowledgeCommand:
    return PromoteResearchKnowledgeCommand(
        source_knowledge_id="knowledge-local",
        promoted_knowledge_id="knowledge-family",
        target_scope=KnowledgeScope.STRATEGY_FAMILY,
        strategy_family_ref="family-current",
        independent_evidence_hash=_hash("c"),
        independent_evidence_known_at=NOW - timedelta(minutes=2),
        run_id="run-memory",
        episode_id="episode-run-memory",
        call_id="call-promote",
    )


def test_approval_check_deep_freezes_arguments() -> None:
    arguments: dict[str, object] = {"selection": {"knowledge_ids": ["knowledge-local"]}}
    check = ResearchMemoryApprovalCheck(
        run_id="run-memory",
        episode_id="episode-run-memory",
        call_id="call-freeze",
        tool_name=RESEARCH_MEMORY_PROMOTE,
        arguments=arguments,
    )
    arguments_hash = check.arguments_hash

    cast("dict[str, list[str]]", arguments["selection"])["knowledge_ids"].append(
        "knowledge-drift"
    )
    frozen_selection = cast("dict[str, object]", check.arguments["selection"])
    with pytest.raises(TypeError):
        frozen_selection["knowledge_ids"] = []
    frozen_ids = cast("list[str]", frozen_selection["knowledge_ids"])
    with pytest.raises(AttributeError):
        frozen_ids.append("knowledge-drift")

    assert check.arguments_hash == arguments_hash


def test_campaign_authorization_can_write_only_host_validated_local_memory() -> None:
    facade, _reader, writer = _facade()

    result = facade.record_local(
        _local(),
        authorization=_authorization(),
        occurred_at=NOW,
    )

    assert result == _local()
    assert writer.knowledge == [_local()]
    with pytest.raises(AppCommandError) as exc_info:
        facade.record_local(
            replace(
                _local(),
                scope=KnowledgeScope.GLOBAL,
                promotion_receipt_hash=_hash("4"),
                independent_evidence_hash=_hash("5"),
            ),
            authorization=_authorization(),
            occurred_at=NOW,
        )
    assert exc_info.value.details["reason"] == "research_memory_local_write_invalid"


def test_approved_promotion_creates_append_only_item_and_receipt() -> None:
    facade, _reader, writer = _facade(_local())

    receipt = facade.promote(_promotion(), occurred_at=NOW)

    promoted = writer.knowledge[0]
    assert promoted.scope is KnowledgeScope.STRATEGY_FAMILY
    assert promoted.scope_ref == "family-current"
    assert promoted.source is KnowledgeSource.HUMAN_REVIEW
    assert promoted.outcome_known_at == NOW
    assert promoted.independent_evidence_hash == _hash("c")
    assert promoted.promotion_receipt_hash == ContentHash(receipt.approval_receipt_hash)
    assert receipt.operation == RESEARCH_MEMORY_PROMOTE
    assert receipt.result_identity == promoted.knowledge_id
    assert receipt.verify_integrity()


@pytest.mark.parametrize(
    ("verifier", "reason"),
    [
        (_Verifier(approved=False), "research_memory_approval_required"),
        (_Verifier(drift=True), "research_memory_approval_invalid"),
    ],
)
def test_promotion_fails_closed_without_exact_approval(
    verifier: _Verifier,
    reason: str,
) -> None:
    facade, _reader, _writer = _facade(_local(), verifier=verifier)

    with pytest.raises(AppCommandError) as exc_info:
        facade.promote(_promotion(), occurred_at=NOW)

    assert exc_info.value.details["reason"] == reason


def test_revoke_appends_status_and_exact_replay_returns_same_receipt() -> None:
    facade, reader, _writer = _facade(_local())
    command = RevokeResearchKnowledgeCommand(
        knowledge_id="knowledge-local",
        event_id="knowledge-revoked",
        evidence_hash=_hash("e"),
        outcome_known_at=NOW,
        run_id="run-memory",
        episode_id="episode-run-memory",
        call_id="call-revoke",
    )

    first = facade.revoke(command, occurred_at=NOW)
    replay = facade.revoke(command, occurred_at=NOW)

    assert first == replay
    assert first.operation == RESEARCH_MEMORY_REVOKE
    assert first.verify_integrity()
    assert reader.events == [
        KnowledgeStatusEvent(
            event_id="knowledge-revoked",
            knowledge_id="knowledge-local",
            previous_status=KnowledgeStatus.ACTIVE,
            status=KnowledgeStatus.REVOKED,
            outcome_known_at=NOW,
            evidence_hash=_hash("e"),
        )
    ]


def test_application_provider_wires_memory_command_leaf_port() -> None:
    reader = _Reader(_local())
    writer = _Writer(reader)
    provider = AppResearchMemoryProvider()

    facade = provider.research_memory_command_facade(reader, writer, _Verifier())

    assert isinstance(facade, ResearchMemoryCommandFacade)
    assert provider.research_memory_command_port(facade) is facade
