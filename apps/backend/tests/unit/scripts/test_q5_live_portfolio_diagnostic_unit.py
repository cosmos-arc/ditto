"""Minimal egress and numeric grounding tests for the live portfolio diagnostic."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_apps.scripts import q5_live_portfolio_diagnostic as diagnostic_script
from ditto_apps.scripts.q5_live_portfolio_diagnostic import (
    LivePortfolioDiagnosticError,
    minimal_portfolio_payload,
    validate_model_portfolio_diagnostic,
)


def _context() -> TemporalToolContext:
    decision_time = datetime(2026, 9, 2, 12, tzinfo=UTC)
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_time,
            knowledge_cutoff=decision_time,
            publication_cutoff=decision_time,
            source_snapshot_id="snapshot-set:sha256:" + "a" * 64,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH", "518880.SH"),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _full_payload() -> dict[str, object]:
    portfolio = {
        "portfolio_id": "model-main",
        "portfolio_kind": "model",
        "total_value": "100000.00",
        "cash_weight": "0.40",
        "invested_weight": "0.60",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "fees": "0",
        "pending_event_count": 0,
        "alert_codes": [],
        "positions": [
            {
                "instrument_id": 2_001_724,
                "quantity": "3369",
                "market_value": "29995.84",
                "weight": "0.30",
                "unrealized_pnl": "0",
                "fees": "0",
                "secret_note": "must not egress",
            }
        ],
        "journal_events": ["must not egress"],
    }
    return {
        "as_of": "2026-09-02",
        "valuation_snapshot_id": "portfolio-valuation:sha256:" + "b" * 64,
        "source_snapshot_ids": ["snapshot:tushare:etf_daily:sha256:" + "c" * 64],
        "model": portfolio,
        "paper": {**portfolio, "portfolio_id": "paper-main", "portfolio_kind": "paper"},
        "manual": {
            **portfolio,
            "portfolio_id": "manual-main",
            "portfolio_kind": "manual",
        },
        "model_vs_paper": {
            "total_abs_drift_bps": "6000",
            "cash_drift_bps": "5991",
            "items": [],
            "attribution": {
                "unfilled_bps": "300",
                "slippage_amount": "0",
                "fee_amount": "5.01",
                "risk_blocked_bps": "0",
                "user_choice_bps": "0",
            },
        },
        "model_vs_manual": {
            "total_abs_drift_bps": "6000",
            "cash_drift_bps": "5900",
            "items": [],
            "attribution": {
                "unfilled_bps": "0",
                "slippage_amount": "0",
                "fee_amount": "0",
                "risk_blocked_bps": "0",
                "user_choice_bps": "6000",
            },
        },
        "paper_vs_manual": {
            "total_abs_drift_bps": "100",
            "cash_drift_bps": "91",
            "items": [],
            "attribution": {
                "unfilled_bps": "0",
                "slippage_amount": "0",
                "fee_amount": "0",
                "risk_blocked_bps": "0",
                "user_choice_bps": "0",
            },
        },
        "raw_provider_rows": ["must not egress"],
    }


def _envelope() -> EvidenceEnvelope:
    payload = minimal_portfolio_payload(_full_payload())
    return EvidenceEnvelope.seal(
        evidence_id="evidence-portfolio-live",
        tool_name="portfolio_comparison_evidence",
        result={
            "schema_version": 1,
            "kind": "portfolio_comparison",
            "payload": payload,
        },
        artifact_refs=("artifact:portfolio-comparison:sha256:" + "d" * 64,),
        temporal_context=_context(),
        lineage=("redaction:approved-research-portfolio-minimal-v1",),
    )


def test_minimal_portfolio_payload_excludes_raw_rows_events_and_free_text() -> None:
    payload = minimal_portfolio_payload(_full_payload())

    assert set(payload) == {
        "as_of",
        "valuation_snapshot_id",
        "source_snapshot_ids",
        "model",
        "paper",
        "manual",
        "model_vs_paper",
        "model_vs_manual",
        "paper_vs_manual",
    }
    model = payload["model"]
    assert isinstance(model, dict)
    assert "journal_events" not in model
    positions = model["positions"]
    assert isinstance(positions, tuple)
    assert "secret_note" not in positions[0]


def test_model_diagnostic_requires_exact_numeric_paths_and_values() -> None:
    evidence = _envelope()
    content = {
        "summary": "Paper 偏差来自未成交与费用。Manual 偏差属于用户选择。",
        "facts": [
            "Paper 未成交偏差为 300 bps。",
            "Paper 费用为 5.01 元。",
            "Manual 用户选择偏差为 6000 bps。",
        ],
        "interpretations": ["执行链完整。目标与账户状态仍有显著差异。"],
        "uncertainties": ["后续交易日的成交状态尚未发生。"],
        "numeric_claims": [
            {
                "evidence_ref": evidence.evidence_id,
                "path": "model_vs_paper.attribution.unfilled_bps",
                "value": "300",
            },
            {
                "evidence_ref": evidence.evidence_id,
                "path": "model_vs_paper.attribution.fee_amount",
                "value": "5.01",
            },
            {
                "evidence_ref": evidence.evidence_id,
                "path": "model_vs_manual.attribution.user_choice_bps",
                "value": "6000",
            },
        ],
        "evidence_refs": [evidence.evidence_id],
    }

    accepted = validate_model_portfolio_diagnostic(
        orjson.dumps(content).decode(),
        evidence=evidence,
    )

    assert accepted.guardrail_status == "passed"
    assert len(accepted.numeric_claims) == 3

    content["numeric_claims"][0]["value"] = "301"  # type: ignore[index]
    with pytest.raises(ValueError, match="does not match sealed evidence"):
        validate_model_portfolio_diagnostic(
            orjson.dumps(content).decode(),
            evidence=evidence,
        )


def test_model_objective_closes_collection_types_for_diagnostic_fields() -> None:
    objective = diagnostic_script._objective(
        {
            "strategy_id": "seed_etf_industry_rotation",
            "model_portfolio_id": "model-main",
            "paper_account_id": "paper-main",
            "manual_account_id": "manual-main",
            "paper_session_id": "paper-session",
        },
        "evidence-portfolio-live",
    )

    assert (
        "facts, interpretations, uncertainties, numeric_claims, and evidence_refs "
        "must each be JSON arrays, even when empty"
    ) in objective
    assert (
        "claims must be a JSON array containing exactly one object with exactly "
        "claim and evidence_refs"
    ) in objective
    assert "uncertainty must be a JSON string or null" in objective


def test_report_writer_normalizes_deeply_frozen_evidence(tmp_path: Path) -> None:
    output = tmp_path / "diagnostic.json"

    diagnostic_script._write(
        output,
        {
            "schema": "ditto.q5-live-portfolio-diagnostic.v1",
            "egress": {"payload": _envelope().integrity_payload()},
        },
    )

    decoded = orjson.loads(output.read_bytes())
    assert decoded["egress"]["payload"]["result"]["kind"] == ("portfolio_comparison")


@pytest.mark.pit
def test_live_diagnostic_rejects_future_snapshot_drift_before_model_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = _full_payload()
    acceptance: dict[str, object] = {
        "schema": "ditto.q5-live-portfolio-acceptance.v1",
        "generated_at": "2026-09-02T13:00:00Z",
        "status": "passed",
        "passed": True,
        "provider": {"observed_at": "2026-09-02T12:00:00Z"},
        "comparison_request": {
            "strategy_id": "seed_etf_industry_rotation",
            "model_portfolio_id": "signal-package-live",
            "paper_account_id": "paper-pap09-owner-acceptance",
            "manual_account_id": "manual-q4-owner-acceptance",
            "paper_session_id": "pap09-session-2026-09-02",
            "source_snapshot_ids": frozen["source_snapshot_ids"],
        },
        "comparison": frozen,
    }
    acceptance["evidence_hash"] = diagnostic_script.canonical_hash(acceptance)
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_bytes(orjson.dumps(acceptance))

    future = _full_payload()
    future["source_snapshot_ids"] = ["snapshot:tushare:etf_daily:sha256:" + "f" * 64]
    context, _arguments = diagnostic_script._context_and_arguments(acceptance)
    future_evidence = EvidenceEnvelope.seal(
        evidence_id="evidence-portfolio-future-sentinel",
        tool_name="portfolio_comparison_evidence",
        result={
            "schema_version": 1,
            "kind": "portfolio_comparison",
            "payload": minimal_portfolio_payload(future),
        },
        artifact_refs=("artifact:portfolio-comparison:sha256:" + "e" * 64,),
        temporal_context=context,
        lineage=("future-snapshot-sentinel",),
    )

    class _Container:
        def get(self, dependency: object) -> object:
            return object()

        def close(self) -> None:
            return None

    class _Tool:
        def __init__(self, *, facade: object) -> None:
            del facade

        def invoke(self, **kwargs: object) -> EvidenceEnvelope:
            del kwargs
            return future_evidence

    monkeypatch.setattr(diagnostic_script, "make_app_container", _Container)
    monkeypatch.setattr(diagnostic_script, "PortfolioComparisonEvidenceTool", _Tool)
    monkeypatch.setattr(
        diagnostic_script,
        "build_agent_database",
        lambda path: (_ for _ in ()).throw(
            AssertionError(f"model runtime reached for {path}")
        ),
    )

    with pytest.raises(LivePortfolioDiagnosticError, match="drifted"):
        asyncio.run(
            diagnostic_script._execute(
                model_id="glm-5.3",
                api_key="test-key",
                agent_data_root=tmp_path / "agent",
                acceptance_path=acceptance_path,
            )
        )


def test_approved_cli_preloads_saved_credential_before_provider_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "diagnostic.json"
    monkeypatch.delenv("DITTO_AGENT_GLM_VALIDATION_API_KEY", raising=False)
    preloaded = False

    def _preload() -> None:
        nonlocal preloaded
        preloaded = True
        os.environ["DITTO_AGENT_GLM_VALIDATION_API_KEY"] = "test-glm-key"

    async def _execute(**kwargs: object) -> dict[str, object]:
        assert kwargs["api_key"] == "test-glm-key"
        return {"schema": "ditto.q5-live-portfolio-diagnostic.v1", "status": "passed"}

    monkeypatch.setattr(diagnostic_script, "preload_runtime_secrets", _preload)
    monkeypatch.setattr(diagnostic_script, "_execute", _execute)

    result = diagnostic_script.main(
        [
            "--model",
            "glm-5.3",
            "--approval-a4",
            "--agent-data-root",
            str(tmp_path / "agent"),
            "--portfolio-acceptance",
            str(tmp_path / "acceptance.json"),
            "--output",
            str(output),
        ],
        environment=os.environ,
    )

    assert result == 0
    assert preloaded is True
    assert orjson.loads(output.read_bytes())["report_hash"]


def test_unapproved_cli_does_not_preload_saved_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preloaded = False

    def _preload() -> None:
        nonlocal preloaded
        preloaded = True

    monkeypatch.setattr(diagnostic_script, "preload_runtime_secrets", _preload)

    result = diagnostic_script.main(
        [
            "--model",
            "glm-5.3",
            "--agent-data-root",
            str(tmp_path / "agent"),
            "--portfolio-acceptance",
            str(tmp_path / "acceptance.json"),
            "--output",
            str(tmp_path / "diagnostic.json"),
        ],
        environment=os.environ,
    )

    assert result == 5
    assert preloaded is False
