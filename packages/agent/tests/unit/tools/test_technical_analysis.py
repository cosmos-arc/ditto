"""Instrument technical evidence and no-hallucinated-level tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.technical_analysis import (
    InstrumentTechnicalEvidenceTool,
    TechnicalAnalysisBriefDraft,
    validate_technical_analysis_brief,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    InstrumentTechnicalEvidenceQueryPort,
    InstrumentTechnicalEvidenceReadModel,
)

_SNAPSHOT_ID = "technical-analysis:sha256:" + "a" * 64


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_id="snapshot-stock",
            execution_eligible_at="not_applicable",
            allowed_universe=("600519.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


class _Facade:
    def get_evidence(
        self, *, query: object, context: EvidenceTemporalContext
    ) -> InstrumentTechnicalEvidenceReadModel:
        del query
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "snapshot_id": _SNAPSHOT_ID,
                "instrument_id": 600519,
                "instrument_name": "贵州茅台",
                "status": "ready",
                "source_snapshot_ids": ("snapshot-stock",),
                "readings": (),
                "levels": (
                    {
                        "timeframe": "daily",
                        "kind": "support",
                        "price": 97.5,
                        "confidence": 0.75,
                        "touches": 3,
                        "window": 60,
                        "algorithm_version": "support-resistance.v1",
                    },
                ),
                "timeframe_summaries": (),
                "conflicts": (),
            },
        )
        return InstrumentTechnicalEvidenceReadModel(
            snapshot_id=_SNAPSHOT_ID,
            instrument_id=600519,
            instrument_name="贵州茅台",
            status="ready",
            source_snapshot_ids=("snapshot-stock",),
            temporal_context=context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=_SNAPSHOT_ID,
                    artifact_kind="technical_analysis_snapshot",
                    content_hash="a" * 64,
                ),
            ),
            lineage=(_SNAPSHOT_ID, "snapshot:snapshot-stock"),
        )


def _tool() -> InstrumentTechnicalEvidenceTool:
    return InstrumentTechnicalEvidenceTool(
        facade=cast(InstrumentTechnicalEvidenceQueryPort, _Facade())
    )


def test_tool_returns_exact_levels_and_rejects_context_smuggling() -> None:
    envelope = _tool().invoke(
        arguments={
            "instrument_id": 600519,
            "instrument_name": "贵州茅台",
            "instrument_code": "600519.SH",
        },
        context=_context(),
    )

    assert envelope.result["payload"]["levels"][0]["price"] == 97.5
    assert envelope.verify_integrity()
    with pytest.raises(ValueError, match="unexpected arguments"):
        _tool().invoke(
            arguments={
                "instrument_id": 600519,
                "instrument_name": "贵州茅台",
                "instrument_code": "600519.SH",
                "source_snapshot_id": "future",
            },
            context=_context(),
        )


def test_brief_validation_rejects_a_level_not_present_in_evidence() -> None:
    envelope = _tool().invoke(
        arguments={
            "instrument_id": 600519,
            "instrument_name": "贵州茅台",
            "instrument_code": "600519.SH",
        },
        context=_context(),
    )

    accepted = validate_technical_analysis_brief(
        TechnicalAnalysisBriefDraft(
            summary="Daily support remains intact.",
            level_claims=(97.5,),
            evidence_refs=(envelope.evidence_id,),
        ),
        evidence=envelope,
    )
    assert accepted.level_claims == (97.5,)

    with pytest.raises(ValueError, match="unrecorded technical level"):
        validate_technical_analysis_brief(
            TechnicalAnalysisBriefDraft(
                summary="Invented resistance.",
                level_claims=(123.45,),
                evidence_refs=(envelope.evidence_id,),
            ),
            evidence=envelope,
        )
