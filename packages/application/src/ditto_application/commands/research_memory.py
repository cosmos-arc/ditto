"""Governed local write, promotion, and revocation of research memory."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from ditto_analysis.experiments.campaign_persistence import CampaignManifestRecord
from ditto_analysis.experiments.models import ContentHash, ExperimentId
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
    KnowledgeStatusEvent,
)

from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.processes.experiments.autonomous_campaign import (
    CampaignAuthorizationProof,
)
from ditto_application.research_memory_approval_contracts import (
    CAMPAIGN_RECORD_RESEARCH_MEMORY,
    RESEARCH_MEMORY_PROMOTE,
    RESEARCH_MEMORY_REVOKE,
    ResearchMemoryApprovalCheck,
    ResearchMemoryApprovalVerifier,
    VerifiedResearchMemoryApproval,
)
from ditto_application.research_memory_contracts import (
    PromoteResearchKnowledgeCommand,
    ResearchMemoryCommandReceipt,
    RevokeResearchKnowledgeCommand,
)


def _error(reason: str, message: str) -> AppCommandError:
    return AppCommandError(
        message,
        details={"code": "RESEARCH_MEMORY_COMMAND_INVALID", "reason": reason},
    )


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _error("research_memory_command_invalid", f"{field} is invalid")
    return value


def _utc(value: object, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error("research_memory_command_invalid", f"{field} must be UTC-aware")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash(value: object, field: str) -> ContentHash:
    if type(value) is not ContentHash:
        raise _error("research_memory_command_invalid", f"{field} must be ContentHash")
    return value


class _Reader(Protocol):
    def get_campaign(
        self,
        campaign_id: ExperimentId,
    ) -> CampaignManifestRecord | None: ...

    def get_knowledge_visible_at(
        self,
        knowledge_id: str,
        knowledge_cutoff: datetime,
    ) -> KnowledgeItem | None: ...

    def list_knowledge_status_events(
        self,
        knowledge_id: str,
    ) -> tuple[KnowledgeStatusEvent, ...]: ...


class _Writer(Protocol):
    def add_knowledge(self, item: KnowledgeItem) -> None: ...

    def append_knowledge_status_event(self, event: KnowledgeStatusEvent) -> None: ...


def _knowledge_payload(item: KnowledgeItem) -> dict[str, object]:
    return {
        "knowledge_id": item.knowledge_id,
        "campaign_id": str(item.campaign_id),
        "claim": item.claim,
        "scope": item.scope.value,
        "scope_ref": item.scope_ref,
        "evidence_refs": [str(value) for value in item.evidence_refs],
        "outcome_known_at": _utc_text(item.outcome_known_at),
        "snapshot_id": str(item.snapshot_id),
        "source": item.source.value,
        "source_hash": str(item.source_hash),
        "status": item.status.value,
        "promotion_receipt_hash": (
            None
            if item.promotion_receipt_hash is None
            else str(item.promotion_receipt_hash)
        ),
        "independent_evidence_hash": (
            None
            if item.independent_evidence_hash is None
            else str(item.independent_evidence_hash)
        ),
    }


def _event_payload(event: KnowledgeStatusEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "knowledge_id": event.knowledge_id,
        "previous_status": event.previous_status.value,
        "status": event.status.value,
        "outcome_known_at": _utc_text(event.outcome_known_at),
        "evidence_hash": str(event.evidence_hash),
    }


class ResearchMemoryCommandFacade:
    """Enforce Campaign authority and per-action HITL at physical writes."""

    def __init__(
        self,
        *,
        reader: _Reader,
        writer: _Writer,
        approval_verifier: ResearchMemoryApprovalVerifier,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._approval_verifier = approval_verifier

    def record_local(
        self,
        item: KnowledgeItem,
        *,
        authorization: CampaignAuthorizationProof,
        occurred_at: datetime,
    ) -> KnowledgeItem:
        """Write only host-validated local memory under exact Campaign authority."""
        now = _utc(occurred_at, "occurred_at")
        if (
            type(item) is not KnowledgeItem
            or item.scope is not KnowledgeScope.CAMPAIGN_LOCAL
            or item.status is not KnowledgeStatus.ACTIVE
            or item.source is not KnowledgeSource.HOST_VALIDATION
            or item.outcome_known_at > now
        ):
            raise _error(
                "research_memory_local_write_invalid",
                "Campaign memory writes must be visible host-validated local facts",
            )
        campaign = self._reader.get_campaign(item.campaign_id)
        if (
            campaign is None
            or type(authorization) is not CampaignAuthorizationProof
            or not authorization.verify_integrity()
            or authorization.campaign_manifest_hash != str(campaign.manifest_hash)
            or authorization.source_snapshot_id != str(item.snapshot_id)
            or CAMPAIGN_RECORD_RESEARCH_MEMORY not in authorization.allowed_tools
            or not authorization.authorized_at <= now <= authorization.expires_at
        ):
            raise _error(
                "research_memory_campaign_authority_invalid",
                "Campaign memory authority is absent, expired, or mismatched",
            )
        self._writer.add_knowledge(item)
        return item

    def _approved(
        self,
        check: ResearchMemoryApprovalCheck,
        occurred_at: datetime,
    ) -> VerifiedResearchMemoryApproval:
        try:
            proof = self._approval_verifier.verify(check)
        except AppCommandError:
            raise
        except (TypeError, ValueError) as exc:
            raise _error(
                "research_memory_approval_invalid",
                "Research memory approval could not be verified",
            ) from exc
        if (
            type(proof) is not VerifiedResearchMemoryApproval
            or not proof.verify_integrity()
            or not proof.matches(check)
            or not proof.approved_at <= occurred_at <= proof.expires_at
        ):
            raise _error(
                "research_memory_approval_invalid",
                "Research memory approval is invalid or mismatched",
            )
        if not proof.approved:
            raise _error(
                "research_memory_approval_required",
                "Research memory mutation requires operator approval",
            )
        return proof

    @staticmethod
    def _receipt(
        *,
        operation: str,
        result_identity: str,
        result_hash: str,
        proof: VerifiedResearchMemoryApproval,
    ) -> ResearchMemoryCommandReceipt:
        provisional = ResearchMemoryCommandReceipt(
            operation=operation,
            result_identity=result_identity,
            result_hash=result_hash,
            approval_id=proof.approval_id,
            approval_receipt_hash=proof.verification_hash,
            action_hash=proof.action_hash,
            operator_id=proof.operator_id,
            approved_at=proof.approved_at,
            run_id=proof.run_id,
            episode_id=proof.episode_id,
            receipt_hash="0" * 64,
        )
        return replace(
            provisional,
            receipt_hash=canonical_request_hash(provisional.canonical_payload()),
        )

    def promote(
        self,
        command: PromoteResearchKnowledgeCommand,
        *,
        occurred_at: datetime,
    ) -> ResearchMemoryCommandReceipt:
        """Append a family/global item after independent evidence and exact HITL."""
        now = _utc(occurred_at, "occurred_at")
        if type(command) is not PromoteResearchKnowledgeCommand:
            raise _error(
                "research_memory_command_invalid", "Promotion command is invalid"
            )
        source_id = _text(command.source_knowledge_id, "source_knowledge_id")
        promoted_id = _text(command.promoted_knowledge_id, "promoted_knowledge_id")
        evidence_hash = _hash(
            command.independent_evidence_hash,
            "independent_evidence_hash",
        )
        evidence_known_at = _utc(
            command.independent_evidence_known_at,
            "independent_evidence_known_at",
        )
        source = self._reader.get_knowledge_visible_at(source_id, now)
        if (
            source is None
            or source.scope is not KnowledgeScope.CAMPAIGN_LOCAL
            or source.status is not KnowledgeStatus.ACTIVE
            or source.source is not KnowledgeSource.HOST_VALIDATION
        ):
            raise _error(
                "research_memory_source_not_promotable",
                "Only active visible host-validated local memory can be promoted",
            )
        if evidence_known_at > now:
            raise _error(
                "research_memory_independent_evidence_future",
                "Independent evidence is not visible at promotion time",
            )
        if command.target_scope not in {
            KnowledgeScope.STRATEGY_FAMILY,
            KnowledgeScope.GLOBAL,
        }:
            raise _error(
                "research_memory_promotion_scope_invalid",
                "Promotion target must be strategy-family or global",
            )
        family_ref = command.strategy_family_ref
        if command.target_scope is KnowledgeScope.STRATEGY_FAMILY:
            family_ref = _text(family_ref, "strategy_family_ref")
        elif family_ref is not None:
            raise _error(
                "research_memory_promotion_scope_invalid",
                "Global promotion cannot carry a strategy family",
            )
        arguments = {
            "source_knowledge_id": source_id,
            "source_knowledge_hash": canonical_request_hash(_knowledge_payload(source)),
            "promoted_knowledge_id": promoted_id,
            "target_scope": command.target_scope.value,
            "strategy_family_ref": family_ref,
            "independent_evidence_hash": str(evidence_hash),
            "independent_evidence_known_at": _utc_text(evidence_known_at),
        }
        check = ResearchMemoryApprovalCheck(
            run_id=command.run_id,
            episode_id=command.episode_id,
            call_id=command.call_id,
            tool_name=RESEARCH_MEMORY_PROMOTE,
            arguments=arguments,
        )
        proof = self._approved(check, now)
        references = tuple(sorted((*source.evidence_refs, evidence_hash), key=str))
        promoted = KnowledgeItem(
            knowledge_id=promoted_id,
            campaign_id=source.campaign_id,
            claim=source.claim,
            scope=command.target_scope,
            scope_ref=family_ref,
            evidence_refs=references,
            outcome_known_at=now,
            snapshot_id=source.snapshot_id,
            source=KnowledgeSource.HUMAN_REVIEW,
            source_hash=ContentHash(proof.verification_hash),
            status=KnowledgeStatus.ACTIVE,
            promotion_receipt_hash=ContentHash(proof.verification_hash),
            independent_evidence_hash=evidence_hash,
        )
        self._writer.add_knowledge(promoted)
        result_hash = canonical_request_hash(_knowledge_payload(promoted))
        return self._receipt(
            operation=RESEARCH_MEMORY_PROMOTE,
            result_identity=promoted.knowledge_id,
            result_hash=result_hash,
            proof=proof,
        )

    def revoke(
        self,
        command: RevokeResearchKnowledgeCommand,
        *,
        occurred_at: datetime,
    ) -> ResearchMemoryCommandReceipt:
        """Append or exactly replay one approved terminal revocation."""
        now = _utc(occurred_at, "occurred_at")
        if type(command) is not RevokeResearchKnowledgeCommand:
            raise _error(
                "research_memory_command_invalid", "Revocation command is invalid"
            )
        knowledge_id = _text(command.knowledge_id, "knowledge_id")
        event_id = _text(command.event_id, "event_id")
        evidence_hash = _hash(command.evidence_hash, "evidence_hash")
        outcome_known_at = _utc(command.outcome_known_at, "outcome_known_at")
        if outcome_known_at > now:
            raise _error(
                "research_memory_revocation_future",
                "Revocation evidence is not visible at command time",
            )
        check = ResearchMemoryApprovalCheck(
            run_id=command.run_id,
            episode_id=command.episode_id,
            call_id=command.call_id,
            tool_name=RESEARCH_MEMORY_REVOKE,
            arguments={
                "knowledge_id": knowledge_id,
                "event_id": event_id,
                "evidence_hash": str(evidence_hash),
                "outcome_known_at": _utc_text(outcome_known_at),
            },
        )
        proof = self._approved(check, now)
        existing = next(
            (
                event
                for event in self._reader.list_knowledge_status_events(knowledge_id)
                if event.event_id == event_id
            ),
            None,
        )
        if existing is not None:
            if (
                existing.knowledge_id != knowledge_id
                or existing.status is not KnowledgeStatus.REVOKED
                or existing.outcome_known_at != outcome_known_at
                or existing.evidence_hash != evidence_hash
            ):
                raise _error(
                    "research_memory_revocation_conflict",
                    "Revocation event identity is bound to different content",
                )
            return self._receipt(
                operation=RESEARCH_MEMORY_REVOKE,
                result_identity=existing.event_id,
                result_hash=canonical_request_hash(_event_payload(existing)),
                proof=proof,
            )
        item = self._reader.get_knowledge_visible_at(knowledge_id, now)
        if item is None or item.status is KnowledgeStatus.REVOKED:
            raise _error(
                "research_memory_revocation_invalid",
                "Knowledge is absent, future, or already revoked",
            )
        if outcome_known_at < item.outcome_known_at:
            raise _error(
                "research_memory_revocation_predates_knowledge",
                "Revocation cannot predate the knowledge item",
            )
        event = KnowledgeStatusEvent(
            event_id=event_id,
            knowledge_id=knowledge_id,
            previous_status=item.status,
            status=KnowledgeStatus.REVOKED,
            outcome_known_at=outcome_known_at,
            evidence_hash=evidence_hash,
        )
        self._writer.append_knowledge_status_event(event)
        return self._receipt(
            operation=RESEARCH_MEMORY_REVOKE,
            result_identity=event.event_id,
            result_hash=canonical_request_hash(_event_payload(event)),
            proof=proof,
        )


__all__ = ["ResearchMemoryCommandFacade"]
