from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.market_context import MarketContextEvidenceTool
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    MarketContextEvidenceQueryPort,
    MarketContextEvidenceReadModel,
)


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_id="snapshot-set:sha256:market-context",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


class _Facade:
    def __init__(self) -> None:
        self.contexts: list[EvidenceTemporalContext] = []

    def get_evidence(
        self,
        *,
        context: EvidenceTemporalContext,
    ) -> MarketContextEvidenceReadModel:
        self.contexts.append(context)
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "status": "ready",
                "source_snapshot_set_id": context.source_snapshot_id,
                "source_snapshot_ids": ("snapshot-stock", "snapshot-index"),
                "regime_label": "risk_on",
                "regime_score": 0.28,
                "metrics": (
                    {
                        "name": "advance_decline_breadth",
                        "value": 0.42,
                        "evidence_ref": "dataset://stock_daily/breadth@2026-08-31",
                    },
                ),
                "evidence_refs": ("dataset://stock_daily/breadth@2026-08-31",),
            },
        )
        return MarketContextEvidenceReadModel(
            status="ready",
            source_snapshot_set_id=context.source_snapshot_id,
            source_snapshot_ids=("snapshot-stock", "snapshot-index"),
            temporal_context=context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id="report-market-context",
                    artifact_kind="dataset_certification",
                    content_hash="a" * 64,
                ),
            ),
            lineage=(
                "snapshot:snapshot-stock",
                "snapshot:snapshot-index",
                "dataset://stock_daily/breadth@2026-08-31",
            ),
        )


def test_market_context_tool_hides_temporal_and_snapshot_arguments() -> None:
    context = _context()
    facade = _Facade()
    tool = MarketContextEvidenceTool(
        facade=cast(MarketContextEvidenceQueryPort, facade)
    )

    envelope = tool.invoke(arguments={}, context=context)

    assert tool.spec.input_schema["properties"] == {}
    assert envelope.result["kind"] == "market_context"
    assert envelope.result["status"] == "ready"
    assert envelope.result["source_snapshot_ids"] == (
        "snapshot-stock",
        "snapshot-index",
    )
    assert envelope.result["payload"]["metrics"][0]["value"] == 0.42
    assert envelope.artifact_refs == (
        f"market-context:sha256:{envelope.result['payload_hash']}",
        f"artifact:dataset_certification:report-market-context:sha256:{'a' * 64}",
    )
    assert envelope.verify_integrity()
    assert facade.contexts == [
        EvidenceTemporalContext(
            decision_time=context.decision_time,
            knowledge_cutoff=context.knowledge_cutoff,
            publication_cutoff=context.publication_cutoff,
            source_snapshot_id=context.source_snapshot_id,
        )
    ]

    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments={"source_snapshot_ids": ["snapshot-future"]},
            context=context,
        )
