"""Application-owned contracts for governed research-memory mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.research_memory import KnowledgeScope

from ditto_application.mutation_idempotency import canonical_request_hash


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class PromoteResearchKnowledgeCommand:
    """Promote one local claim using independent evidence and HITL."""

    source_knowledge_id: str
    promoted_knowledge_id: str
    target_scope: KnowledgeScope
    strategy_family_ref: str | None
    independent_evidence_hash: ContentHash
    independent_evidence_known_at: datetime
    run_id: str
    episode_id: str
    call_id: str


@dataclass(frozen=True, slots=True)
class RevokeResearchKnowledgeCommand:
    """Append one approved revocation to an immutable knowledge item."""

    knowledge_id: str
    event_id: str
    evidence_hash: ContentHash
    outcome_known_at: datetime
    run_id: str
    episode_id: str
    call_id: str


@dataclass(frozen=True, slots=True)
class ResearchMemoryCommandReceipt:
    """Content-addressed approval and result receipt."""

    operation: str
    result_identity: str
    result_hash: str
    approval_id: str
    approval_receipt_hash: str
    action_hash: str
    operator_id: str
    approved_at: datetime
    run_id: str
    episode_id: str
    receipt_hash: str

    def canonical_payload(self) -> dict[str, object]:
        """Return the immutable receipt body."""
        return {
            "schema_version": 1,
            "kind": "research_memory_command_receipt",
            "operation": self.operation,
            "result_identity": self.result_identity,
            "result_hash": self.result_hash,
            "approval_id": self.approval_id,
            "approval_receipt_hash": self.approval_receipt_hash,
            "action_hash": self.action_hash,
            "operator_id": self.operator_id,
            "approved_at": _utc_text(self.approved_at),
            "run_id": self.run_id,
            "episode_id": self.episode_id,
        }

    def verify_integrity(self) -> bool:
        """Detect result or approval drift after issuance."""
        return canonical_request_hash(self.canonical_payload()) == self.receipt_hash


class ResearchMemoryCommandPort(Protocol):
    """Leaf application surface for approved long-term memory changes."""

    def promote(
        self,
        command: PromoteResearchKnowledgeCommand,
        *,
        occurred_at: datetime,
    ) -> ResearchMemoryCommandReceipt:
        """Promote one local claim under exact approval."""
        ...

    def revoke(
        self,
        command: RevokeResearchKnowledgeCommand,
        *,
        occurred_at: datetime,
    ) -> ResearchMemoryCommandReceipt:
        """Append one approved terminal revocation."""
        ...


__all__ = [
    "PromoteResearchKnowledgeCommand",
    "ResearchMemoryCommandPort",
    "ResearchMemoryCommandReceipt",
    "RevokeResearchKnowledgeCommand",
]
