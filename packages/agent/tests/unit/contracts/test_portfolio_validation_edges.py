from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.portfolio import (
    PortfolioDiagnosticDraft,
    PortfolioNumericClaim,
    validate_portfolio_diagnostic,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)

HASH_A = "a" * 64


def _context() -> TemporalToolContext:
    now = datetime(2026, 8, 31, 7, tzinfo=UTC)
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=now,
            knowledge_cutoff=now,
            publication_cutoff=now,
            source_snapshot_id="snapshot-set:sha256:" + HASH_A,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _evidence(
    *,
    evidence_id: str = "evidence-comparison",
    tool_name: str = "portfolio_comparison_evidence",
    payload: object = None,
) -> EvidenceEnvelope:
    effective_payload = (
        {
            "totals": {"value": "100000.00", "drawdown": -0.125},
            "rows": [{"weight": "0.55"}],
        }
        if payload is None
        else payload
    )
    return EvidenceEnvelope.seal(
        evidence_id=evidence_id,
        tool_name=tool_name,
        result={"payload": effective_payload},
        artifact_refs=("portfolio:model",),
        temporal_context=_context(),
        lineage=("snapshot:portfolio",),
    )


def _draft(
    *,
    claims: tuple[PortfolioNumericClaim, ...] | None = None,
    facts: tuple[str, ...] = ("组合总值为 100000。",),
    evidence_refs: tuple[str, ...] = ("evidence-comparison",),
) -> PortfolioDiagnosticDraft:
    return PortfolioDiagnosticDraft(
        summary="组合估值与模型证据一致。",
        facts=facts,
        interpretations=("当前偏差需要继续观察。",),
        uncertainties=("下一交易日价格未知。",),
        numeric_claims=(
            PortfolioNumericClaim(
                evidence_ref="evidence-comparison",
                path="totals.value",
                value="100000.00",
            ),
        )
        if claims is None
        else claims,
        evidence_refs=evidence_refs,
    )


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("totals..value", "1", "empty segment"),
        ("totals.value", "not-a-number", "not numeric"),
        ("totals.value", "NaN", "finite"),
    ],
)
def test_numeric_claim_rejects_ambiguous_path_or_number(
    path: str,
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        PortfolioNumericClaim(
            evidence_ref="evidence-comparison",
            path=path,
            value=value,
        )


def test_diagnostic_rejects_missing_tampered_or_wrong_tool_evidence() -> None:
    draft = _draft()
    with pytest.raises(ValueError, match="integrity"):
        validate_portfolio_diagnostic(draft, evidence=())

    evidence = _evidence()
    with pytest.raises(ValueError, match="integrity"):
        validate_portfolio_diagnostic(
            draft,
            evidence=(replace(evidence, integrity_hash=HASH_A),),
        )

    wrong_tool = _evidence(tool_name="research_evidence")
    with pytest.raises(ValueError, match="tool mismatch"):
        validate_portfolio_diagnostic(draft, evidence=(wrong_tool,))


def test_diagnostic_requires_unique_ordered_evidence_references() -> None:
    evidence = _evidence()
    with pytest.raises(ValueError, match="IDs must be unique"):
        validate_portfolio_diagnostic(
            replace(
                _draft(),
                evidence_refs=(evidence.evidence_id, evidence.evidence_id),
            ),
            evidence=(evidence, evidence),
        )

    with pytest.raises(ValueError, match="evidence_ref must not contain duplicates"):
        validate_portfolio_diagnostic(
            replace(
                _draft(),
                evidence_refs=(evidence.evidence_id, evidence.evidence_id),
            ),
            evidence=(evidence,),
        )

    with pytest.raises(ValueError, match="reference mismatch"):
        validate_portfolio_diagnostic(
            replace(_draft(), evidence_refs=("evidence-other",)),
            evidence=(evidence,),
        )


def test_numeric_claim_requires_known_mapping_evidence_and_unique_path() -> None:
    evidence = _evidence()
    unknown = PortfolioNumericClaim(
        evidence_ref="evidence-other",
        path="totals.value",
        value="100000",
    )
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_portfolio_diagnostic(
            _draft(claims=(unknown,), evidence_refs=(evidence.evidence_id,)),
            evidence=(evidence,),
        )

    invalid_payload = _evidence(payload=[])
    with pytest.raises(ValueError, match="payload is invalid"):
        validate_portfolio_diagnostic(_draft(), evidence=(invalid_payload,))

    claim = _draft().numeric_claims[0]
    with pytest.raises(ValueError, match="must not duplicate"):
        validate_portfolio_diagnostic(
            _draft(claims=(claim, claim)),
            evidence=(evidence,),
        )


@pytest.mark.parametrize(
    "path",
    [
        "totals.missing",
        "rows.not-an-index",
        "rows.2",
        "rows.0.missing",
        "totals.value.extra",
    ],
)
def test_numeric_claim_path_fails_closed_for_every_missing_shape(path: str) -> None:
    evidence = _evidence()
    claim = PortfolioNumericClaim(
        evidence_ref=evidence.evidence_id,
        path=path,
        value="1",
    )

    with pytest.raises(ValueError, match="path is absent"):
        validate_portfolio_diagnostic(_draft(claims=(claim,)), evidence=(evidence,))


def test_numeric_claim_rejects_nonnumeric_or_mismatched_evidence_value() -> None:
    nonnumeric = _evidence(payload={"totals": {"value": True}})
    with pytest.raises(ValueError, match="not numeric"):
        validate_portfolio_diagnostic(_draft(), evidence=(nonnumeric,))

    nonfinite = _evidence(payload={"totals": {"value": "Infinity"}})
    with pytest.raises(ValueError, match="finite"):
        validate_portfolio_diagnostic(_draft(), evidence=(nonfinite,))

    mismatch = PortfolioNumericClaim(
        evidence_ref="evidence-comparison",
        path="totals.value",
        value="99999",
    )
    with pytest.raises(ValueError, match="does not match"):
        validate_portfolio_diagnostic(
            _draft(claims=(mismatch,)),
            evidence=(_evidence(),),
        )


def test_facts_require_citations_and_accept_percentage_and_sequence_paths() -> None:
    evidence = _evidence()
    with pytest.raises(ValueError, match="uncited number"):
        validate_portfolio_diagnostic(
            _draft(facts=("未引用的回撤为 12.5%。",)),
            evidence=(evidence,),
        )

    claims = (
        PortfolioNumericClaim(
            evidence_ref=evidence.evidence_id,
            path="totals.drawdown",
            value="-0.125",
        ),
        PortfolioNumericClaim(
            evidence_ref=evidence.evidence_id,
            path="rows.0.weight",
            value="0.55",
        ),
    )
    accepted = validate_portfolio_diagnostic(
        _draft(
            claims=claims,
            facts=("当前回撤为 -12.5%。", "首行权重为 55%。"),
        ),
        evidence=(evidence,),
    )

    assert accepted.numeric_claims == claims


def test_diagnostic_prose_sections_are_canonical_and_unique() -> None:
    evidence = _evidence()
    duplicate = replace(
        _draft(),
        facts=("重复事实。", "重复事实。"),
    )

    with pytest.raises(ValueError, match="fact must not contain duplicates"):
        validate_portfolio_diagnostic(duplicate, evidence=(evidence,))
