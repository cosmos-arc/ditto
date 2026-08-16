"""PIT-safe, exact-scope research memory application query."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import ExperimentId
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeStatus,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.queries.evidence_contracts import (
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)
from ditto_application.queries.research_memory_contracts import (
    ResearchMemoryReadModel,
    ResearchMemoryScope,
)

_MAX_VISIBLE_MEMORY_ITEMS = 256


def _error(reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"research memory query failed closed: {reason}",
        details={"code": "RESEARCH_MEMORY_QUERY_INVALID", "reason": reason, **details},
    )


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class ResearchMemoryReader(Protocol):
    """Narrow Analysis reader required by the memory query."""

    def list_knowledge_visible_for_scope(
        self,
        campaign_id: ExperimentId,
        strategy_family_ref: str | None,
        knowledge_cutoff: datetime,
    ) -> tuple[KnowledgeItem, ...]:
        """Return PIT-projected items inside the supplied scope."""
        ...


def _in_scope(item: KnowledgeItem, scope: ResearchMemoryScope) -> bool:
    if item.scope is KnowledgeScope.CAMPAIGN_LOCAL:
        return str(item.campaign_id) == scope.campaign_id
    if item.scope is KnowledgeScope.STRATEGY_FAMILY:
        return (
            scope.strategy_family_ref is not None
            and item.scope_ref == scope.strategy_family_ref
        )
    return item.scope is KnowledgeScope.GLOBAL


def _item_payload(item: KnowledgeItem) -> dict[str, object]:
    return {
        "knowledge_id": item.knowledge_id,
        "origin_campaign_id": str(item.campaign_id),
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


class ResearchMemoryQueryFacade:
    """Read visible structured memory through a host-owned exact scope."""

    def __init__(self, *, reader: ResearchMemoryReader) -> None:
        self._reader = reader

    def list_visible(
        self,
        *,
        scope: ResearchMemoryScope,
        context: EvidenceTemporalContext,
    ) -> ResearchMemoryReadModel:
        """Return active memory known by the cutoff, failing closed on leakage."""
        if type(scope) is not ResearchMemoryScope or type(context) is not (
            EvidenceTemporalContext
        ):
            raise _error("research_memory_query_invalid")
        items = self._reader.list_knowledge_visible_for_scope(
            ExperimentId(scope.campaign_id),
            scope.strategy_family_ref,
            context.knowledge_cutoff,
        )
        if len(items) > _MAX_VISIBLE_MEMORY_ITEMS:
            raise _error("research_memory_result_too_large")
        for item in items:
            if type(item) is not KnowledgeItem or not _in_scope(item, scope):
                raise _error("research_memory_scope_leak")
            try:
                item.require_visible_at(context.knowledge_cutoff)
            except ExperimentSpecError as exc:
                raise _error("research_memory_future_leak") from exc
        visible = tuple(
            sorted(
                (item for item in items if item.status is KnowledgeStatus.ACTIVE),
                key=lambda item: (item.outcome_known_at, item.knowledge_id),
            )
        )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={"items": tuple(_item_payload(item) for item in visible)},
        )
        provisional = ResearchMemoryReadModel(
            scope=scope,
            temporal_context=context,
            payload=payload,
            result_hash="0" * 64,
        )
        return ResearchMemoryReadModel(
            scope=scope,
            temporal_context=context,
            payload=payload,
            result_hash=canonical_request_hash(provisional.canonical_payload()),
        )


__all__ = [
    "ResearchMemoryQueryFacade",
    "ResearchMemoryReader",
]
