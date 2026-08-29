"""PIT-safe, scope-bounded research memory query tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ditto_analysis.experiments.models import (
    ContentHash,
    ExperimentId,
    SnapshotId,
)
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.providers_research_memory import AppResearchMemoryProvider
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.research_memory import (
    ResearchMemoryQueryFacade,
)
from ditto_application.queries.research_memory_contracts import ResearchMemoryScope

KNOWN_AT = datetime(2026, 8, 12, 8, tzinfo=UTC)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _knowledge(
    knowledge_id: str,
    *,
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE,
    known_at: datetime = KNOWN_AT,
    snapshot_id: str = "snapshot-query",
) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        campaign_id=ExperimentId("campaign-current"),
        claim=f"Verified claim {knowledge_id}",
        scope=KnowledgeScope.CAMPAIGN_LOCAL,
        scope_ref=None,
        evidence_refs=(_hash("a"),),
        outcome_known_at=known_at,
        snapshot_id=SnapshotId(snapshot_id),
        source=KnowledgeSource.HOST_VALIDATION,
        source_hash=_hash("b"),
        status=status,
        promotion_receipt_hash=None,
        independent_evidence_hash=None,
    )


class _Reader:
    def __init__(self, items: tuple[KnowledgeItem, ...]) -> None:
        self.items = items
        self.calls: list[tuple[ExperimentId, str | None, datetime, datetime, str]] = []

    def list_knowledge_visible_for_scope(
        self,
        campaign_id: ExperimentId,
        strategy_family_ref: str | None,
        knowledge_cutoff: datetime,
        publication_cutoff: datetime,
        source_snapshot_id: str,
    ) -> tuple[KnowledgeItem, ...]:
        self.calls.append(
            (
                campaign_id,
                strategy_family_ref,
                knowledge_cutoff,
                publication_cutoff,
                source_snapshot_id,
            )
        )
        return self.items


def _context() -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=KNOWN_AT + timedelta(hours=2),
        knowledge_cutoff=KNOWN_AT + timedelta(hours=1),
        publication_cutoff=KNOWN_AT,
        source_snapshot_id="snapshot-query",
    )


def test_query_uses_exact_host_scope_and_returns_only_active_visible_items() -> None:
    reader = _Reader(
        (
            _knowledge("active"),
            _knowledge("revoked", status=KnowledgeStatus.REVOKED),
        )
    )
    facade = ResearchMemoryQueryFacade(reader=reader)
    scope = ResearchMemoryScope(
        campaign_id="campaign-current",
        strategy_family_ref="strategy-family-1",
    )

    result = facade.list_visible(scope=scope, context=_context())

    assert [item["knowledge_id"] for item in result.payload.value["items"]] == [
        "active"
    ]
    assert result.scope == scope
    assert result.temporal_context == _context()
    assert reader.calls == [
        (
            ExperimentId("campaign-current"),
            "strategy-family-1",
            _context().knowledge_cutoff,
            _context().publication_cutoff,
            _context().source_snapshot_id,
        )
    ]
    assert result.verify_integrity()


def test_query_rejects_reader_that_returns_future_memory() -> None:
    reader = _Reader((_knowledge("future", known_at=KNOWN_AT + timedelta(days=1)),))
    facade = ResearchMemoryQueryFacade(reader=reader)

    with pytest.raises(AppQueryError) as exc_info:
        facade.list_visible(
            scope=ResearchMemoryScope(
                campaign_id="campaign-current",
                strategy_family_ref=None,
            ),
            context=_context(),
        )

    assert exc_info.value.details["reason"] == "research_memory_future_leak"


def test_query_rejects_memory_published_after_publication_cutoff() -> None:
    reader = _Reader(
        (_knowledge("late-publication", known_at=KNOWN_AT + timedelta(minutes=30)),)
    )
    facade = ResearchMemoryQueryFacade(reader=reader)

    with pytest.raises(AppQueryError) as exc_info:
        facade.list_visible(
            scope=ResearchMemoryScope(
                campaign_id="campaign-current",
                strategy_family_ref=None,
            ),
            context=_context(),
        )

    assert exc_info.value.details["reason"] == "research_memory_publication_leak"


def test_query_rejects_memory_from_another_source_snapshot() -> None:
    reader = _Reader((_knowledge("wrong-snapshot", snapshot_id="snapshot-origin"),))
    facade = ResearchMemoryQueryFacade(reader=reader)

    with pytest.raises(AppQueryError) as exc_info:
        facade.list_visible(
            scope=ResearchMemoryScope(
                campaign_id="campaign-current",
                strategy_family_ref=None,
            ),
            context=_context(),
        )

    assert exc_info.value.details["reason"] == "research_memory_snapshot_mismatch"


def test_application_provider_wires_research_memory_query() -> None:
    reader = _Reader(())

    facade = AppResearchMemoryProvider().research_memory_query_facade(reader)

    assert isinstance(facade, ResearchMemoryQueryFacade)
