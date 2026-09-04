"""Exact technical evidence tool and deterministic brief claim guard."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ditto_application.queries.evidence_contracts import (
    InstrumentTechnicalEvidenceQuery,
    InstrumentTechnicalEvidenceQueryPort,
)
from ditto_kernel.identity import InstrumentId

from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import (
    Arguments,
    application_context,
    function_spec,
    seal_instrument_technical_evidence,
)

_TEXT = {"type": "string", "minLength": 1}


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisBriefDraft:
    """Untrusted model draft whose factual identifiers require host validation."""

    summary: str
    level_claims: tuple[float, ...]
    evidence_refs: tuple[str, ...]
    indicator_claims: tuple[str, ...] = ()
    timeframe_alignment: str | None = None
    conditions: tuple[str, ...] = ()
    invalidations: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisBrief:
    """A snapshot-bound brief after level and indicator subset validation."""

    snapshot_id: str
    summary: str
    level_claims: tuple[float, ...]
    indicator_claims: tuple[str, ...]
    timeframe_alignment: str | None
    conditions: tuple[str, ...]
    invalidations: tuple[str, ...]
    uncertainties: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    guardrail_status: str = "passed"


def _texts(values: tuple[str, ...], *, field: str) -> tuple[str, ...]:
    normalized = tuple(normalized_text(item, field=field) for item in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def _payload_sequence(
    payload: Mapping[str, object],
    field: str,
) -> tuple[Mapping[str, object], ...]:
    raw = payload.get(field)
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError(f"technical analysis evidence {field} is invalid")
    values = tuple(cast("Sequence[object]", raw))
    if not all(isinstance(item, Mapping) for item in values):
        raise ValueError(f"technical analysis evidence {field} is invalid")
    return cast("tuple[Mapping[str, object], ...]", values)


def validate_technical_analysis_brief(
    draft: TechnicalAnalysisBriefDraft,
    *,
    evidence: EvidenceEnvelope,
) -> TechnicalAnalysisBrief:
    """Reject every level or indicator absent from the authenticated snapshot."""
    if not evidence.verify_integrity():
        raise ValueError("technical analysis evidence integrity failed")
    if evidence.tool_name != "instrument_technical_evidence":
        raise ValueError("technical analysis evidence tool mismatch")
    evidence_refs = _texts(draft.evidence_refs, field="evidence_ref")
    if evidence_refs != (evidence.evidence_id,):
        raise ValueError("technical analysis brief evidence reference mismatch")
    payload = evidence.result.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("technical analysis evidence payload is invalid")
    available_levels = {
        float(value)
        for item in _payload_sequence(cast("Mapping[str, object]", payload), "levels")
        if isinstance((value := item.get("price")), (float, int))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    }
    level_claims = tuple(float(item) for item in draft.level_claims)
    if any(not math.isfinite(item) for item in level_claims):
        raise ValueError("technical analysis brief level must be finite")
    unrecorded = tuple(item for item in level_claims if item not in available_levels)
    if unrecorded:
        raise ValueError(f"unrecorded technical level: {unrecorded}")
    readings = _payload_sequence(cast("Mapping[str, object]", payload), "readings")
    available_indicators = {
        name for item in readings if isinstance((name := item.get("name")), str)
    }
    indicator_claims = _texts(draft.indicator_claims, field="indicator_claim")
    unknown_indicators = tuple(
        item for item in indicator_claims if item not in available_indicators
    )
    if unknown_indicators:
        raise ValueError(f"unrecorded technical indicator: {unknown_indicators}")
    snapshot_id = evidence.result.get("snapshot_id")
    if not isinstance(snapshot_id, str):
        raise ValueError("technical analysis evidence snapshot identity is invalid")
    return TechnicalAnalysisBrief(
        snapshot_id=snapshot_id,
        summary=normalized_text(draft.summary, field="summary", maximum=4096),
        level_claims=level_claims,
        indicator_claims=indicator_claims,
        timeframe_alignment=(
            None
            if draft.timeframe_alignment is None
            else normalized_text(
                draft.timeframe_alignment,
                field="timeframe_alignment",
                maximum=1024,
            )
        ),
        conditions=_texts(draft.conditions, field="condition"),
        invalidations=_texts(draft.invalidations, field="invalidation"),
        uncertainties=_texts(draft.uncertainties, field="uncertainty"),
        evidence_refs=evidence_refs,
    )


class InstrumentTechnicalEvidenceTool:
    """Compute one exact technical snapshot inside trusted host boundaries."""

    spec: ModelToolSpec = function_spec(
        name="instrument_technical_evidence",
        description=(
            "Read deterministic indicators, multi-timeframe conflicts, and only "
            "the versioned support/resistance levels recorded for one instrument."
        ),
        properties={
            "instrument_id": {"type": "integer", "minimum": 1},
            "instrument_name": _TEXT,
            "instrument_code": _TEXT,
            "selection_run_id": {"type": ["string", "null"], "minLength": 1},
            "research_case_id": {"type": ["string", "null"], "minLength": 1},
            "portfolio_snapshot_id": {
                "type": ["string", "null"],
                "minLength": 1,
            },
        },
        required=("instrument_id", "instrument_name", "instrument_code"),
    )

    def __init__(self, *, facade: InstrumentTechnicalEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Return exact evidence without accepting source snapshots from the model."""
        parsed = Arguments(
            arguments,
            required=("instrument_id", "instrument_name", "instrument_code"),
            optional=(
                "selection_run_id",
                "research_case_id",
                "portfolio_snapshot_id",
            ),
        )
        instrument_code = parsed.text("instrument_code")
        if instrument_code not in context.allowed_universe:
            raise ValueError("instrument_code is outside the host allowed universe")
        result = self._facade.get_evidence(
            query=InstrumentTechnicalEvidenceQuery(
                instrument_id=InstrumentId(parsed.positive_integer("instrument_id")),
                instrument_name=parsed.text("instrument_name"),
                instrument_code=instrument_code,
                selection_run_id=parsed.optional_text("selection_run_id"),
                research_case_id=parsed.optional_text("research_case_id"),
                portfolio_snapshot_id=parsed.optional_text("portfolio_snapshot_id"),
            ),
            context=application_context(context),
        )
        return seal_instrument_technical_evidence(
            tool_name=self.spec.name,
            read_model=result,
            context=context,
        )


__all__ = [
    "InstrumentTechnicalEvidenceTool",
    "TechnicalAnalysisBrief",
    "TechnicalAnalysisBriefDraft",
    "validate_technical_analysis_brief",
]
