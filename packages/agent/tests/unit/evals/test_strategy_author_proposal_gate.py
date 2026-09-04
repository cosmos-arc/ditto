"""Author proposals require Selection/Research lineage and every safe preview."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_agent.contracts.business_outputs import (
    BUSINESS_OUTPUT_DISCLAIMER,
    BusinessAction,
    BusinessOutputDraft,
    BusinessOutputKind,
    CompletenessStatus,
    FreshnessStatus,
    GuardrailStatus,
)
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.guardrails.strategy_author import validate_strategy_draft_proposal

_SPEC_HASH = "a" * 64


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 6, 30, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 6, tzinfo=UTC),
            source_snapshot_id="selection-research-snapshot-set",
            execution_eligible_at="not_applicable",
            allowed_universe=("600519.SH", "510300.SH"),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _envelope(
    tool_name: str,
    *,
    result: dict[str, object],
) -> EvidenceEnvelope:
    return EvidenceEnvelope.seal(
        evidence_id=f"evidence-{tool_name}",
        tool_name=tool_name,
        result=result,
        artifact_refs=(f"{tool_name}:sha256:" + tool_name[0] * 64,),
        temporal_context=_context(),
        lineage=(f"lineage:{tool_name}",),
    )


def _selection() -> EvidenceEnvelope:
    return _envelope(
        "selection_run_evidence",
        result={
            "kind": "selection_run",
            "run_id": "selection-run-1",
            "payload": {"candidate_ids": (600519,)},
        },
    )


def _research() -> EvidenceEnvelope:
    return _envelope(
        "research_backtest_evidence",
        result={
            "kind": "backtest",
            "subject_id": "research-case-1",
            "payload": {"reproduction_fingerprint": "b" * 64},
        },
    )


def _preview(tool_name: str, kind: str) -> EvidenceEnvelope:
    return _envelope(
        tool_name,
        result={
            "kind": "authoring_preview",
            "preview_kind": kind,
            "subject_id": "selection-research-strategy",
            "subject_version": "3",
            "valid": True,
            "changed": kind == "diff",
            "publishable": False,
            "payload": {
                "operation": kind,
                "valid": True,
                "publishable": False,
                "canonical_hash": _SPEC_HASH if kind != "compile" else None,
            },
        },
    )


def _evidence() -> tuple[EvidenceEnvelope, ...]:
    return (
        _selection(),
        _research(),
        _preview("author_draft_strategy", "draft"),
        _preview("author_compile_expression", "compile"),
        _preview("author_validate_strategy", "validate"),
        _preview("author_diff_strategy", "diff"),
    )


def _draft(evidence: tuple[EvidenceEnvelope, ...] | None = None) -> BusinessOutputDraft:
    items = evidence or _evidence()
    return BusinessOutputDraft(
        output_kind=BusinessOutputKind.STRATEGY_DRAFT_PROPOSAL,
        schema_version=1,
        run_id="run-author-1",
        context_type="strategy_author",
        context_id="research-case-1",
        as_of=_context().decision_time,
        knowledge_cutoff=_context().knowledge_cutoff,
        publication_cutoff=_context().publication_cutoff,
        evidence_refs=tuple(item.evidence_id for item in items),
        artifact_refs=tuple(
            reference for item in items for reference in item.artifact_refs
        ),
        source_snapshot_ids=("selection-research-snapshot-set",),
        facts=("The candidate is inside the exact SelectionRun.",),
        interpretations=("The draft is suitable for deterministic review.",),
        uncertainties=("Research budget still requires user approval.",),
        conflicts=(),
        recommended_next_steps=("Review the detached proposal in Strategy Studio.",),
        numeric_claims=(),
        action_intents=(BusinessAction.REQUEST_USER_REVIEW,),
        model_version="fake-author-v1",
        prompt_version="strategy-author-v1",
        tool_versions={item.tool_name: "1" for item in items},
        policy_version="strategy-author-policy-v1",
        guardrail_status=GuardrailStatus.PASSED,
        freshness=FreshnessStatus.CURRENT,
        completeness=CompletenessStatus.COMPLETE,
        disclaimer=BUSINESS_OUTPUT_DISCLAIMER,
        details={
            "spec_diff": ("Selector parameter changed.",),
            "validation": ("Detached StrategySpec is valid.",),
            "tests": ("Draft, compile, validate, and diff previews passed.",),
            "open_assumptions": ("Experiment budget is not authorized.",),
            "spec_json": {
                "schema_version": 2,
                "strategy_family_id": "selection-research-strategy",
            },
        },
    )


def test_fake_author_proposal_requires_complete_context_and_preview_evidence() -> None:
    evidence = _evidence()

    output = validate_strategy_draft_proposal(
        _draft(evidence),
        evidence=evidence,
        expected_context=_context(),
    )

    assert output.output_kind is BusinessOutputKind.STRATEGY_DRAFT_PROPOSAL
    assert output.verify_content_hash()
    assert output.action_intents == (BusinessAction.REQUEST_USER_REVIEW,)


@pytest.mark.parametrize(
    "remove_tool",
    [
        "selection_run_evidence",
        "research_backtest_evidence",
        "author_draft_strategy",
        "author_compile_expression",
        "author_validate_strategy",
        "author_diff_strategy",
    ],
)
def test_missing_context_or_preview_evidence_fails_closed(remove_tool: str) -> None:
    evidence = tuple(item for item in _evidence() if item.tool_name != remove_tool)

    with pytest.raises(ValueError, match="requires"):
        validate_strategy_draft_proposal(
            _draft(evidence),
            evidence=evidence,
            expected_context=_context(),
        )


def test_invalid_preview_or_hash_conflict_fails_closed() -> None:
    evidence = _evidence()
    invalid_result = {**evidence[4].result, "valid": False}
    invalid = EvidenceEnvelope.seal(
        evidence_id=evidence[4].evidence_id,
        tool_name=evidence[4].tool_name,
        result=invalid_result,
        artifact_refs=evidence[4].artifact_refs,
        temporal_context=evidence[4].temporal_context,
        lineage=evidence[4].lineage,
    )
    conflicting = _preview("author_diff_strategy", "diff")
    conflicting_result = dict(conflicting.result)
    payload = dict(conflicting_result["payload"])
    payload["canonical_hash"] = "f" * 64
    conflicting_result["payload"] = payload
    conflicting = EvidenceEnvelope.seal(
        evidence_id=conflicting.evidence_id,
        tool_name=conflicting.tool_name,
        result=conflicting_result,
        artifact_refs=conflicting.artifact_refs,
        temporal_context=conflicting.temporal_context,
        lineage=conflicting.lineage,
    )

    with pytest.raises(ValueError, match="valid preview"):
        validate_strategy_draft_proposal(
            _draft((*evidence[:4], invalid, *evidence[5:])),
            evidence=(*evidence[:4], invalid, *evidence[5:]),
            expected_context=_context(),
        )
    with pytest.raises(ValueError, match="canonical hash"):
        validate_strategy_draft_proposal(
            _draft((*evidence[:-1], conflicting)),
            evidence=(*evidence[:-1], conflicting),
            expected_context=_context(),
        )


def test_holdout_payload_is_never_allowed_into_author_context() -> None:
    evidence = _evidence()
    unsafe = _envelope(
        "research_backtest_evidence",
        result={
            "kind": "backtest",
            "subject_id": "research-case-1",
            "payload": {"holdout_metrics": {"sharpe": "1.5"}},
        },
    )
    items = (evidence[0], unsafe, *evidence[2:])

    with pytest.raises(ValueError, match="holdout"):
        validate_strategy_draft_proposal(
            _draft(items),
            evidence=items,
            expected_context=_context(),
        )
