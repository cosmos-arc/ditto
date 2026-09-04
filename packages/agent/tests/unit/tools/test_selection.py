"""Industry rotation and SelectionRun evidence tool tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.selection import (
    IndustryRotationEvidenceTool,
    SelectionRunEvidenceTool,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    IndustryRotationEvidenceQueryPort,
    IndustryRotationEvidenceReadModel,
    SelectionRunEvidenceQueryPort,
    SelectionRunEvidenceReadModel,
)

_SNAPSHOT_ID = "industry-rotation:sha256:" + "a" * 64
_RUN_ID = "selection-run:sha256:" + "b" * 64


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_id="snapshot-set:sha256:selection",
            execution_eligible_at="not_applicable",
            allowed_universe=("600000.SH", "600001.SH"),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _application_context() -> EvidenceTemporalContext:
    context = _context()
    return EvidenceTemporalContext(
        decision_time=context.decision_time,
        knowledge_cutoff=context.knowledge_cutoff,
        publication_cutoff=context.publication_cutoff,
        source_snapshot_id=context.source_snapshot_id,
    )


class _RotationFacade:
    def get_evidence(
        self,
        *,
        snapshot_id: str,
        context: EvidenceTemporalContext,
    ) -> IndustryRotationEvidenceReadModel:
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "snapshot_id": snapshot_id,
                "status": "ready",
                "rankings": (
                    {
                        "industry_id": "801010",
                        "rank": 1,
                        "score": 0.5,
                        "contributions": (
                            {"metric": "relative_strength_20d", "contribution": 0.2},
                        ),
                    },
                ),
            },
        )
        return IndustryRotationEvidenceReadModel(
            snapshot_id=snapshot_id,
            status="ready",
            temporal_context=context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=snapshot_id,
                    artifact_kind="industry_rotation_snapshot",
                    content_hash="a" * 64,
                ),
            ),
            lineage=(snapshot_id,),
        )


class _SelectionFacade:
    def get_evidence(
        self,
        *,
        run_id: str,
        context: EvidenceTemporalContext,
    ) -> SelectionRunEvidenceReadModel:
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "run_id": run_id,
                "status": "ready",
                "candidates": ({"instrument_id": "600000.SH", "rank": 1},),
                "exclusions": (
                    {
                        "instrument_id": "600001.SH",
                        "reason_code": "insufficient_liquidity",
                    },
                ),
            },
        )
        return SelectionRunEvidenceReadModel(
            run_id=run_id,
            status="ready",
            temporal_context=context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=run_id,
                    artifact_kind="selection_run",
                    content_hash="b" * 64,
                ),
            ),
            lineage=(run_id, _SNAPSHOT_ID),
        )


def test_tools_preserve_exact_rank_and_exclusion_evidence() -> None:
    rotation = IndustryRotationEvidenceTool(
        facade=cast(IndustryRotationEvidenceQueryPort, _RotationFacade())
    ).invoke(arguments={"snapshot_id": _SNAPSHOT_ID}, context=_context())
    selection = SelectionRunEvidenceTool(
        facade=cast(SelectionRunEvidenceQueryPort, _SelectionFacade())
    ).invoke(arguments={"run_id": _RUN_ID}, context=_context())

    assert rotation.result["payload"]["rankings"][0]["rank"] == 1
    assert selection.result["payload"]["exclusions"][0]["reason_code"] == (
        "insufficient_liquidity"
    )
    assert rotation.verify_integrity()
    assert selection.verify_integrity()


def test_tools_reject_model_controlled_context_or_extra_arguments() -> None:
    tool = SelectionRunEvidenceTool(
        facade=cast(SelectionRunEvidenceQueryPort, _SelectionFacade())
    )

    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments={"run_id": _RUN_ID, "source_snapshot_id": "future"},
            context=_context(),
        )
