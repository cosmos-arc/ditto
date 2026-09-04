"""Minimize and seal approved-research evidence for Q2/Q3 GLM briefs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids

__all__ = [
    "_FOCUS_INSTRUMENT_CODE",
    "_FOCUS_INSTRUMENT_ID",
    "_context",
    "_mapping",
    "_parse_datetime",
    "_required_text",
    "_seal_minimal",
    "_sequence",
    "_snapshot_ids",
    "minimal_market_payload",
    "minimal_selection_payload",
    "minimal_technical_payload",
]

_FOCUS_INSTRUMENT_ID = 1_003_251
_FOCUS_INSTRUMENT_CODE = "600519.SH"
_SELECTED_INDICATORS = frozenset(
    {"historical_volatility", "macd_histogram", "return", "rsi"}
)


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in cast("Mapping[object, object]", value)
    ):
        raise ValueError(f"{field} must be a string-keyed object")
    return cast("Mapping[str, object]", value)


def _sequence(value: object, *, field: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    return tuple(cast("Sequence[object]", value))


def _project_fields(value: object, fields: tuple[str, ...]) -> dict[str, object]:
    source = _mapping(value, field="projected evidence item")
    return {field: source[field] for field in fields if field in source}


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value


def _snapshot_ids(value: object) -> tuple[str, ...]:
    items = _sequence(value, field="source_snapshot_ids")
    if not items or not all(isinstance(item, str) and item for item in items):
        raise ValueError("source_snapshot_ids must contain identities")
    return cast("tuple[str, ...]", items)


def minimal_market_payload(market: Mapping[str, object]) -> dict[str, object]:
    """Keep only independently derived MarketContext facts and identities."""
    required = (
        "status",
        "regime_label",
        "regime_score",
        "metrics",
        "drivers",
        "impacts",
        "missing_inputs",
        "uncertainties",
        "source_snapshot_set_id",
        "source_snapshot_ids",
    )
    missing = tuple(field for field in required if field not in market)
    if missing:
        raise ValueError(f"market evidence fields are missing: {missing}")
    return {
        "status": market["status"],
        "regime_label": market["regime_label"],
        "regime_score": market["regime_score"],
        "metrics": tuple(
            _mapping(item, field="market metric")
            for item in _sequence(market["metrics"], field="metrics")
        ),
        "drivers": tuple(
            _mapping(item, field="market driver")
            for item in _sequence(market["drivers"], field="drivers")
        ),
        "impacts": tuple(
            _mapping(item, field="market impact")
            for item in _sequence(market["impacts"], field="impacts")
        ),
        "missing_inputs": _sequence(market["missing_inputs"], field="missing_inputs"),
        "uncertainties": _sequence(market["uncertainties"], field="uncertainties"),
        "source_snapshot_set_id": market["source_snapshot_set_id"],
        "source_snapshot_ids": _snapshot_ids(market["source_snapshot_ids"]),
    }


def minimal_selection_payload(selection: Mapping[str, object]) -> dict[str, object]:
    """Keep top-three derived candidates plus the exact Moutai exclusion."""
    candidates = _sequence(selection.get("candidates"), field="candidates")
    exclusions = _sequence(selection.get("exclusions"), field="exclusions")
    focus = next(
        (
            _mapping(item, field="selection exclusion")
            for item in exclusions
            if _mapping(item, field="selection exclusion").get("instrument_id")
            == _FOCUS_INSTRUMENT_ID
        ),
        None,
    )
    if focus is None:
        raise ValueError("selection evidence lacks the exact focus exclusion")
    candidate_fields = (
        "rank",
        "instrument_id",
        "instrument_name",
        "industry_id",
        "score",
        "factor_contributions",
    )
    exclusion_fields = (
        "instrument_id",
        "instrument_name",
        "reason_code",
        "stage",
        "detail",
    )
    return {
        "run_id": _required_text(selection.get("run_id"), field="selection run_id"),
        "status": selection.get("status"),
        "seed": selection.get("seed"),
        "candidate_count": len(candidates),
        "exclusion_count": len(exclusions),
        "top_candidates": tuple(
            _project_fields(item, candidate_fields) for item in candidates[:3]
        ),
        "focus_exclusion": _project_fields(focus, exclusion_fields),
        "source_snapshot_ids": _snapshot_ids(selection.get("source_snapshot_ids")),
    }


def minimal_technical_payload(technical: Mapping[str, object]) -> dict[str, object]:
    """Keep summaries, levels, conflicts, gaps, and four selected indicators."""
    readings = tuple(
        _mapping(item, field="technical reading")
        for item in _sequence(technical.get("readings"), field="readings")
    )
    selected_fields = ("timeframe", "name", "status", "value", "reason", "window")
    return {
        "snapshot_id": _required_text(
            technical.get("snapshot_id"), field="technical snapshot_id"
        ),
        "status": technical.get("status"),
        "instrument_id": technical.get("instrument_id"),
        "instrument_name": technical.get("instrument_name"),
        "selection_run_id": technical.get("selection_run_id"),
        "last_visible_bar_at": technical.get("last_visible_bar_at"),
        "source_snapshot_ids": _snapshot_ids(technical.get("source_snapshot_ids")),
        "timeframe_summaries": tuple(
            _mapping(item, field="technical timeframe summary")
            for item in _sequence(
                technical.get("timeframe_summaries"), field="timeframe_summaries"
            )
        ),
        "levels": tuple(
            _mapping(item, field="technical level")
            for item in _sequence(technical.get("levels"), field="levels")
        ),
        "conflicts": tuple(
            _mapping(item, field="technical conflict")
            for item in _sequence(technical.get("conflicts"), field="conflicts")
        ),
        "missing_inputs": _sequence(
            technical.get("missing_inputs"), field="missing_inputs"
        ),
        "selected_readings": tuple(
            _project_fields(item, selected_fields)
            for item in readings
            if item.get("name") in _SELECTED_INDICATORS
        ),
    }


def _parse_datetime(value: object, *, field: str) -> datetime:
    text = _required_text(value, field=field)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _context(
    *,
    decision_time: datetime,
    snapshot_ids: tuple[str, ...],
    allowed_universe: tuple[str, ...],
) -> TemporalToolContext:
    snapshot_set_id = aggregate_source_snapshot_ids(snapshot_ids)
    if snapshot_set_id is None:
        raise ValueError("live brief context requires source snapshots")
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_time,
            knowledge_cutoff=decision_time,
            publication_cutoff=decision_time,
            source_snapshot_id=snapshot_set_id,
            execution_eligible_at="not_applicable",
            allowed_universe=allowed_universe,
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _seal_minimal(
    *,
    tool_name: str,
    kind: str,
    payload: Mapping[str, object],
    context: TemporalToolContext,
    source_artifact_hash: str,
    lineage: tuple[str, ...],
) -> EvidenceEnvelope:
    result: Mapping[str, object] = {
        "schema_version": 1,
        "kind": kind,
        "redaction_profile": "approved-research-minimal-v1",
        "payload": payload,
    }
    artifact_refs = (
        f"artifact:{kind}:sha256:{source_artifact_hash}",
        f"minimal-egress:sha256:{canonical_sha256(payload)}",
    )
    evidence_hash = canonical_sha256(
        {
            "tool_name": tool_name,
            "result": result,
            "artifact_refs": artifact_refs,
            "context": context.canonical_payload(),
            "lineage": lineage,
        }
    )
    return EvidenceEnvelope.seal(
        evidence_id=f"evidence-{evidence_hash}",
        tool_name=tool_name,
        result=result,
        artifact_refs=artifact_refs,
        temporal_context=context,
        lineage=lineage,
    )
