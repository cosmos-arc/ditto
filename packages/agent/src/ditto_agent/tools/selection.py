"""Read-only exact industry-rotation and SelectionRun evidence tools."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_application.queries.evidence_contracts import (
    IndustryRotationEvidenceQueryPort,
    SelectionRunEvidenceQueryPort,
)

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import (
    Arguments,
    application_context,
    function_spec,
    seal_industry_rotation_evidence,
    seal_selection_run_evidence,
)

_TEXT = {"type": "string", "minLength": 1}


class IndustryRotationEvidenceTool:
    """Read one exact persisted industry ranking selected by artifact ID."""

    spec: ModelToolSpec = function_spec(
        name="industry_rotation_evidence",
        description=(
            "Read one exact persisted industry ranking with factor contributions, "
            "missing inputs, algorithm identity, and PIT lineage."
        ),
        properties={"snapshot_id": _TEXT},
        required=("snapshot_id",),
    )

    def __init__(self, *, facade: IndustryRotationEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Read the requested immutable artifact under host temporal authority."""
        parsed = Arguments(arguments, required=("snapshot_id",))
        result = self._facade.get_evidence(
            snapshot_id=parsed.text("snapshot_id"),
            context=application_context(context),
        )
        return seal_industry_rotation_evidence(
            tool_name=self.spec.name,
            read_model=result,
            context=context,
        )


class SelectionRunEvidenceTool:
    """Read exact candidate ranks, factors, and hard-filter exclusions."""

    spec: ModelToolSpec = function_spec(
        name="selection_run_evidence",
        description=(
            "Read one exact saved SelectionRun including candidates, factor "
            "contributions, exclusions, reason codes, seed, and PIT lineage."
        ),
        properties={"run_id": _TEXT},
        required=("run_id",),
    )

    def __init__(self, *, facade: SelectionRunEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Return immutable run evidence without accepting trusted boundaries."""
        parsed = Arguments(arguments, required=("run_id",))
        result = self._facade.get_evidence(
            run_id=parsed.text("run_id"),
            context=application_context(context),
        )
        return seal_selection_run_evidence(
            tool_name=self.spec.name,
            read_model=result,
            context=context,
        )


__all__ = ["IndustryRotationEvidenceTool", "SelectionRunEvidenceTool"]
