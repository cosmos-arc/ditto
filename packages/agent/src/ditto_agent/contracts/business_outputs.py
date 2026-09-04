"""Canonical, evidence-grounded contracts for six product Agent outputs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    freeze_json,
    normalized_text,
    utc_datetime,
)
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext

__all__ = [
    "BUSINESS_OUTPUT_DISCLAIMER",
    "BusinessAction",
    "BusinessOutput",
    "BusinessOutputDraft",
    "BusinessOutputKind",
    "CompletenessStatus",
    "FreshnessStatus",
    "GuardrailStatus",
    "NumericEvidenceClaim",
    "business_output_schema",
    "validate_business_output",
]

BUSINESS_OUTPUT_DISCLAIMER = (
    "This output is not a real order and is not an authoritative ledger fact."
)
_SCHEMA_VERSION = 1
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?%?")
_FORBIDDEN_SPEC_FIELDS = frozenset(
    {"code", "python_code", "source_code", "executable", "script"}
)


class BusinessOutputKind(StrEnum):
    """Closed set of product-facing outputs delivered in the I12 workflow."""

    EVIDENCE_BRIEF = "evidence_brief"
    SELECTION_MEMO = "selection_memo"
    TECHNICAL_ANALYSIS_BRIEF = "technical_analysis_brief"
    RESEARCH_MEMO = "research_memo"
    PORTFOLIO_DIAGNOSTIC = "portfolio_diagnostic"
    STRATEGY_DRAFT_PROPOSAL = "strategy_draft_proposal"


class GuardrailStatus(StrEnum):
    """Host validation outcome attached to a product output."""

    PASSED = "passed"
    BLOCKED = "blocked"


class FreshnessStatus(StrEnum):
    """Evidence freshness state computed outside the model."""

    CURRENT = "current"
    STALE = "stale"


class CompletenessStatus(StrEnum):
    """Evidence coverage state computed outside the model."""

    COMPLETE = "complete"
    PARTIAL = "partial"


class BusinessAction(StrEnum):
    """Non-authoritative UI intents that cannot execute financial actions."""

    OPEN_CONTEXT = "open_context"
    REQUEST_USER_REVIEW = "request_user_review"
    SAVE_DRAFT_WITH_APPROVAL = "save_draft_with_approval"
    SUBMIT_REVIEW_WITH_APPROVAL = "submit_review_with_approval"
    RUN_BACKTEST_PREVIEW = "run_backtest_preview"


_DETAIL_FIELDS: Mapping[BusinessOutputKind, tuple[str, ...]] = {
    BusinessOutputKind.EVIDENCE_BRIEF: (
        "market_changes",
        "drivers",
        "risks",
        "watch_items",
    ),
    BusinessOutputKind.SELECTION_MEMO: (
        "inclusions",
        "exclusions",
        "comparisons",
        "research_gaps",
    ),
    BusinessOutputKind.TECHNICAL_ANALYSIS_BRIEF: (
        "timeframe_alignment",
        "levels",
        "conditions",
        "invalidations",
    ),
    BusinessOutputKind.RESEARCH_MEMO: (
        "findings",
        "methodology_notes",
        "limitations",
        "research_gaps",
    ),
    BusinessOutputKind.PORTFOLIO_DIAGNOSTIC: (
        "drift",
        "exposure",
        "pnl_attribution",
        "scenario_references",
    ),
    BusinessOutputKind.STRATEGY_DRAFT_PROPOSAL: (
        "spec_diff",
        "validation",
        "tests",
        "open_assumptions",
        "spec_json",
    ),
}


@dataclass(frozen=True, slots=True)
class NumericEvidenceClaim:
    """One numeric value pinned to an exact path in one sealed envelope."""

    evidence_ref: str
    path: str
    value: str

    def __post_init__(self) -> None:
        """Normalize the detached citation without trusting its value."""
        object.__setattr__(
            self,
            "evidence_ref",
            normalized_text(self.evidence_ref, field="numeric evidence_ref"),
        )
        path = normalized_text(self.path, field="numeric claim path", maximum=1024)
        if any(not segment for segment in path.split(".")):
            raise ValueError("numeric claim path contains an empty segment")
        object.__setattr__(self, "path", path)
        value = normalized_text(self.value, field="numeric claim value", maximum=128)
        _decimal(value, field="numeric claim value")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class BusinessOutputDraft:
    """Untrusted model draft plus host-provided provenance fields."""

    output_kind: BusinessOutputKind
    schema_version: int
    run_id: str
    context_type: str
    context_id: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    source_snapshot_ids: tuple[str, ...]
    facts: tuple[str, ...]
    interpretations: tuple[str, ...]
    uncertainties: tuple[str, ...]
    conflicts: tuple[str, ...]
    recommended_next_steps: tuple[str, ...]
    numeric_claims: tuple[NumericEvidenceClaim, ...]
    action_intents: tuple[BusinessAction, ...]
    model_version: str
    prompt_version: str
    tool_versions: Mapping[str, str]
    policy_version: str
    guardrail_status: GuardrailStatus
    freshness: FreshnessStatus
    completeness: CompletenessStatus
    disclaimer: str
    details: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class BusinessOutput:
    """Validated immutable business output with a canonical content identity."""

    output_kind: BusinessOutputKind
    schema_version: int
    run_id: str
    context_type: str
    context_id: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    source_snapshot_ids: tuple[str, ...]
    facts: tuple[str, ...]
    interpretations: tuple[str, ...]
    uncertainties: tuple[str, ...]
    conflicts: tuple[str, ...]
    recommended_next_steps: tuple[str, ...]
    numeric_claims: tuple[NumericEvidenceClaim, ...]
    action_intents: tuple[BusinessAction, ...]
    model_version: str
    prompt_version: str
    tool_versions: Mapping[str, str]
    policy_version: str
    guardrail_status: GuardrailStatus
    freshness: FreshnessStatus
    completeness: CompletenessStatus
    disclaimer: str
    details: Mapping[str, object]
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Derive immutable identity from every validated output field."""
        object.__setattr__(
            self, "content_hash", canonical_sha256(self.canonical_payload())
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return all semantic output fields in a canonical-hashable payload."""
        return {
            "output_kind": self.output_kind,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "context_type": self.context_type,
            "context_id": self.context_id,
            "as_of": self.as_of,
            "knowledge_cutoff": self.knowledge_cutoff,
            "publication_cutoff": self.publication_cutoff,
            "evidence_refs": self.evidence_refs,
            "artifact_refs": self.artifact_refs,
            "source_snapshot_ids": self.source_snapshot_ids,
            "facts": self.facts,
            "interpretations": self.interpretations,
            "uncertainties": self.uncertainties,
            "conflicts": self.conflicts,
            "recommended_next_steps": self.recommended_next_steps,
            "numeric_claims": self.numeric_claims,
            "action_intents": self.action_intents,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "tool_versions": self.tool_versions,
            "policy_version": self.policy_version,
            "guardrail_status": self.guardrail_status,
            "freshness": self.freshness,
            "completeness": self.completeness,
            "disclaimer": self.disclaimer,
            "details": self.details,
        }

    def verify_content_hash(self) -> bool:
        """Detect any semantic drift after construction."""
        return self.content_hash == canonical_sha256(self.canonical_payload())


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{field} is not numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} is not numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _texts(
    values: object,
    *,
    field_name: str,
    required: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    normalized = tuple(
        normalized_text(item, field=f"{field_name} item", maximum=4096)
        for item in cast(tuple[str, ...], values)
    )
    if required and not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _at_path(payload: Mapping[str, object], path: str) -> object:
    value: object = payload
    for segment in path.split("."):
        if isinstance(value, Mapping):
            mapping = cast(Mapping[object, object], value)
            if segment not in mapping:
                raise ValueError(f"numeric claim path is absent: {path}")
            value = mapping[segment]
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            try:
                value = cast(Sequence[object], value)[int(segment)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"numeric claim path is absent: {path}") from exc
        else:
            raise ValueError(f"numeric claim path is absent: {path}")
    return value


def _validated_numeric_claims(
    claims: object,
    *,
    evidence: Mapping[str, EvidenceEnvelope],
) -> tuple[NumericEvidenceClaim, ...]:
    if not isinstance(claims, tuple):
        raise ValueError("numeric_claims must contain NumericEvidenceClaim values")
    raw_claims = cast(tuple[object, ...], claims)
    if any(type(item) is not NumericEvidenceClaim for item in raw_claims):
        raise ValueError("numeric_claims must contain NumericEvidenceClaim values")
    typed = cast(tuple[NumericEvidenceClaim, ...], raw_claims)
    seen: set[tuple[str, str]] = set()
    for claim in typed:
        key = (claim.evidence_ref, claim.path)
        if key in seen:
            raise ValueError("numeric claims must not duplicate an evidence path")
        seen.add(key)
        envelope = evidence.get(claim.evidence_ref)
        if envelope is None:
            raise ValueError("numeric claim references unknown evidence")
        payload = envelope.result.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("numeric evidence payload is invalid")
        actual = _decimal(
            _at_path(cast(Mapping[str, object], payload), claim.path),
            field="sealed evidence value",
        )
        if _decimal(claim.value, field="numeric claim") != actual:
            raise ValueError("numeric claim does not match sealed evidence")
    return typed


def _prose_numbers(values: tuple[str, ...]) -> tuple[Decimal, ...]:
    numbers: list[Decimal] = []
    for value in values:
        for match in _NUMBER.findall(value):
            percent = match.endswith("%")
            number = _decimal(match.removesuffix("%"), field="business output number")
            numbers.append(number / Decimal(100) if percent else number)
    return tuple(numbers)


def _declarative_strategy_spec(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in cast(Mapping[object, object], value).items():
            if not isinstance(key, str):
                raise ValueError("StrategySpec proposal keys must be strings")
            if key.casefold() in _FORBIDDEN_SPEC_FIELDS:
                raise ValueError("StrategySpec proposal must remain declarative")
            _declarative_strategy_spec(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in cast(Sequence[object], value):
            _declarative_strategy_spec(item)


def _details(
    kind: BusinessOutputKind,
    raw: object,
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        raise ValueError("details must be an object")
    mapping = cast(Mapping[object, object], raw)
    required = _DETAIL_FIELDS[kind]
    if set(mapping) != set(required) or any(
        not isinstance(key, str) for key in mapping
    ):
        raise ValueError("details fields do not match the output kind schema")
    normalized: dict[str, object] = {}
    prose: list[str] = []
    for field_name in required:
        value = mapping[field_name]
        if field_name == "spec_json":
            if not isinstance(value, Mapping):
                raise ValueError("StrategyDraftProposal spec_json must be an object")
            _declarative_strategy_spec(cast(Mapping[object, object], value))
            normalized[field_name] = value
            continue
        texts = _texts(value, field_name=f"details.{field_name}")
        normalized[field_name] = texts
        prose.extend(texts)
    frozen = freeze_json(normalized, field="details")
    if not isinstance(frozen, Mapping):
        raise TypeError("normalized details must be a mapping")
    return cast(Mapping[str, object], frozen), tuple(prose)


def _tool_versions(
    raw: object,
    *,
    tool_names: tuple[str, ...],
) -> Mapping[str, str]:
    if not isinstance(raw, Mapping):
        raise ValueError("tool_versions must be an object")
    mapping = cast(Mapping[object, object], raw)
    if set(mapping) != set(tool_names) or any(
        not isinstance(key, str) for key in mapping
    ):
        raise ValueError("tool_versions must cover the exact evidence tool set")
    normalized = {
        name: normalized_text(version, field=f"tool_versions.{name}")
        for name, version in mapping.items()
        if isinstance(version, str)
    }
    if len(normalized) != len(mapping):
        raise ValueError("tool_versions values must be strings")
    frozen = freeze_json(normalized, field="tool_versions")
    return cast(Mapping[str, str], frozen)


def _evidence_index(
    evidence: object,
    *,
    expected_context: TemporalToolContext,
    allowed_tool_names: tuple[str, ...],
) -> tuple[dict[str, EvidenceEnvelope], tuple[str, ...], tuple[str, ...]]:
    if not isinstance(evidence, tuple) or not evidence:
        raise ValueError("business output requires sealed evidence")
    if len(set(allowed_tool_names)) != len(allowed_tool_names):
        raise ValueError("allowed_tool_names must be unique")
    index: dict[str, EvidenceEnvelope] = {}
    artifact_refs: list[str] = []
    tool_names: list[str] = []
    for item in cast(tuple[EvidenceEnvelope, ...], evidence):
        if type(item) is not EvidenceEnvelope or not item.verify_integrity():
            raise ValueError("business output evidence integrity failed")
        if item.temporal_context != expected_context:
            raise ValueError("business output evidence temporal context mismatch")
        if item.tool_name not in allowed_tool_names:
            raise ValueError("evidence tool is outside the context allowlist")
        if item.evidence_id in index:
            raise ValueError("business output evidence IDs must be unique")
        index[item.evidence_id] = item
        artifact_refs.extend(item.artifact_refs)
        if item.tool_name not in tool_names:
            tool_names.append(item.tool_name)
    return index, tuple(dict.fromkeys(artifact_refs)), tuple(tool_names)


def _actions(value: object) -> tuple[BusinessAction, ...]:
    if not isinstance(value, tuple):
        raise ValueError(
            "action_intents must contain only approved BusinessAction values"
        )
    raw_actions = cast(tuple[object, ...], value)
    if any(type(item) is not BusinessAction for item in raw_actions):
        raise ValueError(
            "action_intents must contain only approved BusinessAction values"
        )
    typed = cast(tuple[BusinessAction, ...], raw_actions)
    if len(set(typed)) != len(typed):
        raise ValueError("action_intents must not contain duplicates")
    return typed


@dataclass(frozen=True, slots=True)
class _NormalizedSections:
    facts: tuple[str, ...]
    interpretations: tuple[str, ...]
    uncertainties: tuple[str, ...]
    conflicts: tuple[str, ...]
    next_steps: tuple[str, ...]
    details: Mapping[str, object]
    numeric_claims: tuple[NumericEvidenceClaim, ...]


def _validated_header(
    draft: BusinessOutputDraft,
    expected_context: TemporalToolContext,
) -> tuple[datetime, datetime, datetime]:
    if type(draft.output_kind) is not BusinessOutputKind:
        raise ValueError("output_kind must be a BusinessOutputKind")
    if type(draft.schema_version) is not int or draft.schema_version != _SCHEMA_VERSION:
        raise ValueError("unsupported business output schema_version")
    if draft.guardrail_status is not GuardrailStatus.PASSED:
        raise ValueError("a completed business output requires passed guardrail status")
    if type(draft.freshness) is not FreshnessStatus:
        raise ValueError("freshness must be a FreshnessStatus")
    if type(draft.completeness) is not CompletenessStatus:
        raise ValueError("completeness must be a CompletenessStatus")
    if draft.disclaimer != BUSINESS_OUTPUT_DISCLAIMER:
        raise ValueError("business output disclaimer is host controlled")
    timestamps = (
        utc_datetime(draft.as_of, field="as_of"),
        utc_datetime(draft.knowledge_cutoff, field="knowledge_cutoff"),
        utc_datetime(draft.publication_cutoff, field="publication_cutoff"),
    )
    expected = (
        expected_context.decision_time,
        expected_context.knowledge_cutoff,
        expected_context.publication_cutoff,
    )
    if timestamps != expected:
        raise ValueError("business output temporal context mismatch")
    return timestamps


def _validated_references(
    draft: BusinessOutputDraft,
    *,
    index: Mapping[str, EvidenceEnvelope],
    artifact_refs: tuple[str, ...],
    expected_context: TemporalToolContext,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    evidence_refs = _texts(
        draft.evidence_refs, field_name="evidence_refs", required=True
    )
    if evidence_refs != tuple(index):
        raise ValueError("business output evidence reference mismatch")
    normalized_artifacts = _texts(
        draft.artifact_refs, field_name="artifact_refs", required=True
    )
    if normalized_artifacts != artifact_refs:
        raise ValueError("business output artifact reference mismatch")
    snapshots = _texts(
        draft.source_snapshot_ids,
        field_name="source_snapshot_ids",
        required=True,
    )
    if snapshots != (expected_context.source_snapshot_id,):
        raise ValueError("business output source snapshot mismatch")
    return evidence_refs, normalized_artifacts, snapshots


def _normalized_sections(
    draft: BusinessOutputDraft,
    *,
    evidence: Mapping[str, EvidenceEnvelope],
) -> _NormalizedSections:
    facts = _texts(draft.facts, field_name="facts", required=True)
    interpretations = _texts(draft.interpretations, field_name="interpretations")
    uncertainties = _texts(draft.uncertainties, field_name="uncertainties")
    conflicts = _texts(draft.conflicts, field_name="conflicts")
    next_steps = _texts(
        draft.recommended_next_steps,
        field_name="recommended_next_steps",
    )
    details, detail_prose = _details(draft.output_kind, draft.details)
    numeric_claims = _validated_numeric_claims(
        draft.numeric_claims,
        evidence=evidence,
    )
    claim_values = tuple(
        _decimal(item.value, field="numeric claim") for item in numeric_claims
    )
    prose_numbers = _prose_numbers(
        (
            *facts,
            *interpretations,
            *uncertainties,
            *conflicts,
            *next_steps,
            *detail_prose,
        )
    )
    if any(value not in claim_values for value in prose_numbers):
        raise ValueError("business output contains an uncited number")
    return _NormalizedSections(
        facts=facts,
        interpretations=interpretations,
        uncertainties=uncertainties,
        conflicts=conflicts,
        next_steps=next_steps,
        details=details,
        numeric_claims=numeric_claims,
    )


def validate_business_output(
    draft: BusinessOutputDraft,
    *,
    evidence: tuple[EvidenceEnvelope, ...],
    expected_context: TemporalToolContext,
    allowed_tool_names: tuple[str, ...],
) -> BusinessOutput:
    """Validate model prose against host context, evidence, and action policy."""
    timestamps = _validated_header(draft, expected_context)
    index, artifact_refs, tool_names = _evidence_index(
        evidence,
        expected_context=expected_context,
        allowed_tool_names=allowed_tool_names,
    )
    evidence_refs, normalized_artifacts, snapshots = _validated_references(
        draft,
        index=index,
        artifact_refs=artifact_refs,
        expected_context=expected_context,
    )
    sections = _normalized_sections(draft, evidence=index)
    return BusinessOutput(
        output_kind=draft.output_kind,
        schema_version=draft.schema_version,
        run_id=normalized_text(draft.run_id, field="run_id"),
        context_type=normalized_text(
            draft.context_type, field="context_type", maximum=128
        ),
        context_id=normalized_text(draft.context_id, field="context_id", maximum=1024),
        as_of=timestamps[0],
        knowledge_cutoff=timestamps[1],
        publication_cutoff=timestamps[2],
        evidence_refs=evidence_refs,
        artifact_refs=normalized_artifacts,
        source_snapshot_ids=snapshots,
        facts=sections.facts,
        interpretations=sections.interpretations,
        uncertainties=sections.uncertainties,
        conflicts=sections.conflicts,
        recommended_next_steps=sections.next_steps,
        numeric_claims=sections.numeric_claims,
        action_intents=_actions(draft.action_intents),
        model_version=normalized_text(draft.model_version, field="model_version"),
        prompt_version=normalized_text(draft.prompt_version, field="prompt_version"),
        tool_versions=_tool_versions(draft.tool_versions, tool_names=tool_names),
        policy_version=normalized_text(draft.policy_version, field="policy_version"),
        guardrail_status=draft.guardrail_status,
        freshness=draft.freshness,
        completeness=draft.completeness,
        disclaimer=draft.disclaimer,
        details=sections.details,
    )


def business_output_schema(kind: BusinessOutputKind) -> Mapping[str, object]:
    """Return the closed provider-facing JSON schema for one output kind."""
    if type(kind) is not BusinessOutputKind:
        raise ValueError("kind must be a BusinessOutputKind")
    detail_properties = {
        field_name: (
            {"type": "object"}
            if field_name == "spec_json"
            else {"type": "array", "items": {"type": "string"}, "uniqueItems": True}
        )
        for field_name in _DETAIL_FIELDS[kind]
    }
    properties: dict[str, object] = {
        "output_kind": {"const": kind.value},
        "schema_version": {"const": _SCHEMA_VERSION},
        "run_id": {"type": "string", "minLength": 1},
        "context_type": {"type": "string", "minLength": 1},
        "context_id": {"type": "string", "minLength": 1},
        "as_of": {"type": "string", "format": "date-time"},
        "knowledge_cutoff": {"type": "string", "format": "date-time"},
        "publication_cutoff": {"type": "string", "format": "date-time"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "artifact_refs": {"type": "array", "items": {"type": "string"}},
        "source_snapshot_ids": {"type": "array", "items": {"type": "string"}},
        "facts": {"type": "array", "items": {"type": "string"}},
        "interpretations": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "conflicts": {"type": "array", "items": {"type": "string"}},
        "recommended_next_steps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "numeric_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "evidence_ref": {"type": "string"},
                    "path": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ("evidence_ref", "path", "value"),
                "additionalProperties": False,
            },
        },
        "action_intents": {
            "type": "array",
            "items": {"enum": tuple(item.value for item in BusinessAction)},
        },
        "model_version": {"type": "string"},
        "prompt_version": {"type": "string"},
        "tool_versions": {"type": "object", "additionalProperties": {"type": "string"}},
        "policy_version": {"type": "string"},
        "guardrail_status": {"const": GuardrailStatus.PASSED.value},
        "freshness": {"enum": tuple(item.value for item in FreshnessStatus)},
        "completeness": {"enum": tuple(item.value for item in CompletenessStatus)},
        "disclaimer": {"const": BUSINESS_OUTPUT_DISCLAIMER},
        "details": {
            "type": "object",
            "properties": detail_properties,
            "required": _DETAIL_FIELDS[kind],
            "additionalProperties": False,
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": tuple(properties),
        "additionalProperties": False,
    }
