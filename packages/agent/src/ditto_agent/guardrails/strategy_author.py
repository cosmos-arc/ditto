"""Strategy Author proposal validation over exact context and preview evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from ditto_agent.contracts.business_outputs import (
    BusinessOutput,
    BusinessOutputDraft,
    BusinessOutputKind,
    validate_business_output,
)
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext

_SHA256_HEX_LENGTH = 64

__all__ = ["validate_strategy_draft_proposal"]

_SELECTION_TOOL = "selection_run_evidence"
_RESEARCH_TOOLS = frozenset(
    {
        "research_experiment_evidence",
        "research_factor_evidence",
        "research_strategy_evidence",
        "research_backtest_evidence",
    }
)
_AUTHOR_PREVIEWS = {
    "author_draft_strategy": "draft",
    "author_compile_expression": "compile",
    "author_validate_strategy": "validate",
    "author_diff_strategy": "diff",
}


def _contains_holdout(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            "holdout" in str(key).casefold() or _contains_holdout(item)
            for key, item in cast(Mapping[object, object], value).items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_holdout(item) for item in cast(Sequence[object], value))
    return False


def _tool_index(
    evidence: tuple[EvidenceEnvelope, ...],
) -> dict[str, EvidenceEnvelope]:
    index: dict[str, EvidenceEnvelope] = {}
    for item in evidence:
        if not item.verify_integrity():
            raise ValueError("Strategy Author evidence integrity failed")
        if item.tool_name in index:
            raise ValueError("Strategy Author evidence tools must be unique")
        if _contains_holdout(item.result):
            raise ValueError("holdout evidence is forbidden in Strategy Author context")
        index[item.tool_name] = item
    return index


def _require_context_and_previews(index: Mapping[str, EvidenceEnvelope]) -> None:
    if _SELECTION_TOOL not in index:
        raise ValueError("Strategy Author requires exact SelectionRun evidence")
    if not _RESEARCH_TOOLS.intersection(index):
        raise ValueError("Strategy Author requires exact Research evidence")
    missing = tuple(name for name in _AUTHOR_PREVIEWS if name not in index)
    if missing:
        raise ValueError(f"Strategy Author requires preview evidence: {missing}")


def _preview_hashes(index: Mapping[str, EvidenceEnvelope]) -> tuple[str, ...]:
    hashes: list[str] = []
    for tool_name, expected_kind in _AUTHOR_PREVIEWS.items():
        result = index[tool_name].result
        if (
            result.get("kind") != "authoring_preview"
            or result.get("preview_kind") != expected_kind
            or result.get("valid") is not True
            or result.get("publishable") is not False
        ):
            raise ValueError("Strategy Author requires every valid preview result")
        payload = result.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("Strategy Author preview payload is invalid")
        payload_mapping = cast(Mapping[object, object], payload)
        canonical_hash = payload_mapping.get("canonical_hash")
        if expected_kind != "compile":
            if (
                not isinstance(canonical_hash, str)
                or len(canonical_hash) != _SHA256_HEX_LENGTH
            ):
                raise ValueError("Strategy Author canonical hash is missing")
            hashes.append(canonical_hash)
    return tuple(hashes)


def validate_strategy_draft_proposal(
    draft: BusinessOutputDraft,
    *,
    evidence: tuple[EvidenceEnvelope, ...],
    expected_context: TemporalToolContext,
) -> BusinessOutput:
    """Seal one declarative proposal only after all context previews agree."""
    if draft.output_kind is not BusinessOutputKind.STRATEGY_DRAFT_PROPOSAL:
        raise ValueError("Strategy Author requires a StrategyDraftProposal output")
    if draft.context_type != "strategy_author":
        raise ValueError("Strategy Author requires the strategy_author context profile")
    index = _tool_index(evidence)
    _require_context_and_previews(index)
    hashes = _preview_hashes(index)
    if len(set(hashes)) != 1:
        raise ValueError("Strategy Author preview canonical hash conflict")
    return validate_business_output(
        draft,
        evidence=evidence,
        expected_context=expected_context,
        allowed_tool_names=tuple(index),
    )
