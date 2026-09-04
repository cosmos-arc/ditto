"""Grounded structured output for three-portfolio diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.evidence import EvidenceEnvelope

__all__ = [
    "PortfolioDiagnostic",
    "PortfolioDiagnosticDraft",
    "PortfolioNumericClaim",
    "validate_portfolio_diagnostic",
]

_PORTFOLIO_TOOL_NAMES = frozenset(
    {"portfolio_comparison_evidence", "portfolio_scenario_preview"}
)
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?%?")


def _texts(values: tuple[str, ...], *, field: str) -> tuple[str, ...]:
    normalized = tuple(
        normalized_text(value, field=field, maximum=4096) for value in values
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


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


@dataclass(frozen=True, slots=True)
class PortfolioNumericClaim:
    """One model claim pinned to an exact field in a sealed evidence envelope."""

    evidence_ref: str
    path: str
    value: str

    def __post_init__(self) -> None:
        """Reject ambiguous references, paths, and number encodings."""
        object.__setattr__(
            self,
            "evidence_ref",
            normalized_text(self.evidence_ref, field="evidence_ref"),
        )
        path = normalized_text(self.path, field="numeric_claim path", maximum=1024)
        if any(not item for item in path.split(".")):
            raise ValueError("numeric_claim path contains an empty segment")
        object.__setattr__(self, "path", path)
        value = normalized_text(self.value, field="numeric_claim value", maximum=128)
        _decimal(value, field="numeric_claim value")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class PortfolioDiagnosticDraft:
    """Untrusted model-authored prose and explicit numeric citations."""

    summary: str
    facts: tuple[str, ...]
    interpretations: tuple[str, ...]
    uncertainties: tuple[str, ...]
    numeric_claims: tuple[PortfolioNumericClaim, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioDiagnostic:
    """Portfolio diagnostic after evidence and numerical-claim validation."""

    summary: str
    facts: tuple[str, ...]
    interpretations: tuple[str, ...]
    uncertainties: tuple[str, ...]
    numeric_claims: tuple[PortfolioNumericClaim, ...]
    evidence_refs: tuple[str, ...]
    guardrail_status: str = "passed"


def _at_path(payload: Mapping[str, object], path: str) -> object:
    value: object = payload
    for segment in path.split("."):
        if isinstance(value, Mapping):
            mapping = cast("Mapping[object, object]", value)
            if segment not in mapping:
                raise ValueError(f"numeric claim path is absent: {path}")
            value = mapping[segment]
            continue
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            try:
                index = int(segment)
                value = cast("Sequence[object]", value)[index]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"numeric claim path is absent: {path}") from exc
            continue
        raise ValueError(f"numeric claim path is absent: {path}")
    return value


def _validate_claims(
    claims: tuple[PortfolioNumericClaim, ...],
    evidence: Mapping[str, EvidenceEnvelope],
) -> tuple[Decimal, ...]:
    keys: set[tuple[str, str]] = set()
    values: list[Decimal] = []
    for claim in claims:
        key = (claim.evidence_ref, claim.path)
        if key in keys:
            raise ValueError("numeric claims must not duplicate an evidence path")
        keys.add(key)
        envelope = evidence.get(claim.evidence_ref)
        if envelope is None:
            raise ValueError("numeric claim references unknown evidence")
        payload = envelope.result.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("portfolio evidence payload is invalid")
        actual = _decimal(
            _at_path(cast("Mapping[str, object]", payload), claim.path),
            field="sealed evidence value",
        )
        claimed = _decimal(claim.value, field="numeric claim")
        if claimed != actual:
            raise ValueError("numeric claim does not match sealed evidence")
        values.append(claimed)
    return tuple(values)


def _fact_numbers(facts: tuple[str, ...]) -> tuple[Decimal, ...]:
    result: list[Decimal] = []
    for fact in facts:
        for match in _NUMBER.findall(fact):
            is_percent = match.endswith("%")
            value = _decimal(match.removesuffix("%"), field="fact number")
            result.append(value / Decimal("100") if is_percent else value)
    return tuple(result)


def validate_portfolio_diagnostic(
    draft: PortfolioDiagnosticDraft,
    *,
    evidence: tuple[EvidenceEnvelope, ...],
) -> PortfolioDiagnostic:
    """Reject unsealed evidence, missing citations, and fabricated fact numbers."""
    if not evidence or any(not item.verify_integrity() for item in evidence):
        raise ValueError("portfolio diagnostic evidence integrity failed")
    if any(item.tool_name not in _PORTFOLIO_TOOL_NAMES for item in evidence):
        raise ValueError("portfolio diagnostic evidence tool mismatch")
    index = {item.evidence_id: item for item in evidence}
    if len(index) != len(evidence):
        raise ValueError("portfolio diagnostic evidence IDs must be unique")
    evidence_refs = _texts(draft.evidence_refs, field="evidence_ref")
    if evidence_refs != tuple(item.evidence_id for item in evidence):
        raise ValueError("portfolio diagnostic evidence reference mismatch")
    claims = tuple(draft.numeric_claims)
    claim_values = _validate_claims(claims, index)
    facts = _texts(draft.facts, field="fact")
    if any(value not in claim_values for value in _fact_numbers(facts)):
        raise ValueError("portfolio fact contains an uncited number")
    return PortfolioDiagnostic(
        summary=normalized_text(draft.summary, field="summary", maximum=4096),
        facts=facts,
        interpretations=_texts(draft.interpretations, field="interpretation"),
        uncertainties=_texts(draft.uncertainties, field="uncertainty"),
        numeric_claims=claims,
        evidence_refs=evidence_refs,
    )
