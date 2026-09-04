"""Exact approval and PIT identity tests for the Q5 portfolio closure."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_apps.operations.q4_live_account_acceptance import (
    canonical_bar,
    canonical_hash,
)
from ditto_apps.operations.q5_live_portfolio_acceptance import (
    LivePortfolioAcceptanceProposalInput,
    approved_live_portfolio_acceptance_request,
    build_live_portfolio_acceptance_proposal,
)
from ditto_apps.registry.live.q5_live_portfolio_acceptance_runtime import (
    run_live_portfolio_acceptance,
)

_OBSERVED_AT = datetime(2026, 9, 2, 11, 45, tzinfo=UTC)


def _row(
    instrument_id: int, ticker: str, close: float, pre_close: float
) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "source_ticker": ticker,
        "trade_date": "2026-09-02",
        "knowledge_date": "2026-09-03",
        "open": close,
        "high": close + 0.01,
        "low": close - 0.01,
        "close": close,
        "pre_close": pre_close,
        "volume": 1000.0 + instrument_id,
        "amount": 10000.0 + instrument_id,
        "pct_change": (close / pre_close - 1.0) * 100.0,
    }


def _inputs(tmp_path: Path) -> tuple[Path, Path, tuple[dict[str, object], ...]]:
    rows = (
        _row(2_001_724, "518880.SH", 8.902, 9.118),
        _row(2_001_001, "510001.SH", 1.2, 1.0),
        _row(2_001_002, "510002.SH", 1.3, 1.0),
        _row(2_001_003, "510003.SH", 1.4, 1.0),
        _row(2_001_004, "510004.SH", 1.5, 1.0),
    )
    q3 = tmp_path / "q3.json"
    q3.write_bytes(
        orjson.dumps(
            {
                "schema": "ditto.q3-live-discovery.v1",
                "passed": True,
                "etf_selection": {
                    "run_id": "selection-run:sha256:" + "1" * 64,
                    "as_of": "2026-09-01T15:57:47Z",
                    "candidates": [
                        {
                            "rank": 1,
                            "instrument_id": 2_001_724,
                            "instrument_name": "华安易富黄金ETF",
                            "score": 0.88,
                        }
                    ],
                },
            }
        )
    )
    account = tmp_path / "account.json"
    paper_alias = "snapshot:tushare:etf_daily:sha256:" + canonical_hash(
        canonical_bar(rows[0])
    )
    account.write_bytes(
        orjson.dumps(
            {
                "schema": "ditto.personal-workstation.ui08-account-acceptance.v1",
                "status": "partial_pass",
                "evidence_identity": {
                    "trade_date": "2026-09-02",
                    "paper_account_id": "paper-pap09-owner-acceptance",
                    "paper_session_id": "pap09-session-2026-09-02",
                    "manual_account_id": "manual-q4-owner-acceptance",
                    "strategy_id": "seed_etf_industry_rotation",
                    "instrument_id": 2_001_724,
                    "provider_snapshot_id": paper_alias,
                    "paper_ledger_hash": "account-ledger:sha256:" + "2" * 64,
                    "manual_ledger_hash": "account-ledger:sha256:" + "3" * 64,
                },
                "steps": [
                    {"step": 7, "state": "passed"},
                    {"step": 8, "state": "passed"},
                ],
                "safety": {"broker_connections": 0, "real_orders": 0},
            }
        )
    )
    return q3, account, rows


def _proposal(tmp_path: Path) -> dict[str, object]:
    q3, account, rows = _inputs(tmp_path)
    return build_live_portfolio_acceptance_proposal(
        LivePortfolioAcceptanceProposalInput(
            data_root=tmp_path / "data-root",
            trading_database=tmp_path / "trading.sqlite",
            evidence_root=tmp_path / "evidence",
            generated_at=_OBSERVED_AT,
            q3_evidence_path=q3,
            account_evidence_path=account,
            provider_rows=rows,
            raw_provider_row_count=2110,
            strategy_spec_hash="4" * 64,
            strategy_universe="csi_etf_broad",
            target_positions={
                2_001_001: 0.2,
                2_001_002: 0.2,
                2_001_003: 0.2,
                2_001_004: 0.2,
                2_001_724: 0.2,
            },
            factor_values={
                row["instrument_id"]: {
                    "signal_value": cast(float, row["pct_change"]) / 100
                }
                for row in rows
                if row["instrument_id"] != 2_001_724
            }
            | {2_001_724: {"signal_value": cast(float, rows[0]["pct_change"]) / 100}},
            cash_target=0.0,
        )
    )


def _approval_hash(proposal: dict[str, object]) -> str:
    request = cast("dict[str, object]", proposal["exact_acceptance_request"])
    return cast("str", request["approval_hash"])


@pytest.mark.pit
def test_proposal_binds_real_observation_strategy_output_and_account_alias(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approved = approved_live_portfolio_acceptance_request(
        proposal,
        approved_request_hash=_approval_hash(proposal),
    )

    arguments = cast("dict[str, object]", proposal["exact_acceptance_request"])[
        "arguments"
    ]
    assert approved.provider_snapshot_id.startswith(
        "snapshot:tushare:etf_daily:sha256:"
    )
    assert approved.paper_snapshot_alias != approved.provider_snapshot_id
    assert approved.signal_date == "2026-09-02"
    assert approved.intended_trade_date == "2026-09-03"
    assert len(approved.provider_rows) == 5
    assert cast("dict[str, object]", arguments)["writes"] == {
        "provider_payload_and_snapshot": True,
        "derived_manual_execution_baseline": True,
        "recommendation_run_and_signal_package": True,
        "acceptance_evidence": True,
    }
    assert proposal["safety"] == {
        "broker_connections": 0,
        "real_orders": 0,
        "paper_or_manual_journal_mutations": 0,
        "strategy_governance_mutations": 0,
        "agent_write_tools": 0,
    }


def test_wrong_hash_and_approved_payload_tamper_fail_closed(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    with pytest.raises(ValueError, match="approval hash"):
        approved_live_portfolio_acceptance_request(
            proposal,
            approved_request_hash="f" * 64,
        )

    request = cast("dict[str, object]", proposal["exact_acceptance_request"])
    arguments = cast("dict[str, object]", request["arguments"])
    target = cast("dict[str, object]", arguments["expected_strategy_output"])
    target["cash_target"] = 0.5
    with pytest.raises(ValueError, match="approval hash"):
        approved_live_portfolio_acceptance_request(
            proposal,
            approved_request_hash=_approval_hash(_proposal(tmp_path)),
        )


def test_approved_paths_cannot_be_redirected_after_proposal(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    redirected_root = tmp_path / "evidence"
    redirected_root.mkdir()
    (tmp_path / "data-root").symlink_to(redirected_root, target_is_directory=True)

    with pytest.raises(ValueError, match="path changed after approval"):
        approved_live_portfolio_acceptance_request(
            proposal,
            approved_request_hash=approval_hash,
        )


@pytest.mark.pit
def test_runtime_rejects_provider_drift_before_any_approved_write(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    _q3, _account, rows = _inputs(tmp_path)

    class DriftedSource:
        def fetch_etf_daily(self, **kwargs: object) -> pl.DataFrame:
            assert kwargs == {"trade_date": "2026-09-02"}
            return pl.DataFrame(rows)

    def no_container() -> object:
        raise AssertionError("container must not open before provider preflight")

    with pytest.raises(ValueError, match="provider row count drifted"):
        run_live_portfolio_acceptance(
            proposal,
            approved_request_hash=_approval_hash(proposal),
            operator_id="workspace-user",
            executed_at=_OBSERVED_AT,
            source=DriftedSource(),
            container_factory=no_container,
        )

    assert not (tmp_path / "data-root").exists()
    assert not (tmp_path / "trading.sqlite").exists()


@pytest.mark.pit
def test_runtime_accepts_exact_frozen_rows_before_persistence_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal(tmp_path)
    _q3, _account, frozen_rows = _inputs(tmp_path)
    filler_rows = tuple(
        _row(3_000_000 + index, f"{index:06d}.SH", 1.0, 1.0)
        for index in range(2110 - len(frozen_rows))
    )

    class ExactSource:
        def fetch_etf_daily(self, **kwargs: object) -> pl.DataFrame:
            assert kwargs == {"trade_date": "2026-09-02"}
            return pl.DataFrame((*frozen_rows, *filler_rows))

    monkeypatch.setenv("DITTO_DATA_ROOT", str(tmp_path / "wrong-data-root"))

    def no_container() -> object:
        raise AssertionError("persistence must not open before path preflight")

    with pytest.raises(ValueError, match="DITTO_DATA_ROOT"):
        run_live_portfolio_acceptance(
            proposal,
            approved_request_hash=_approval_hash(proposal),
            operator_id="workspace-user",
            executed_at=_OBSERVED_AT,
            source=ExactSource(),
            container_factory=no_container,
        )

    assert not (tmp_path / "data-root").exists()
    assert not (tmp_path / "trading.sqlite").exists()


def test_completed_acceptance_replay_returns_immutable_receipt_without_new_io(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    request = cast("dict[str, object]", proposal["exact_acceptance_request"])
    arguments = cast("dict[str, object]", request["arguments"])
    provider = cast("dict[str, object]", arguments["provider"])
    receipt: dict[str, object] = {
        "schema": "ditto.q5-live-portfolio-acceptance.v1",
        "generated_at": "2026-09-02T12:00:00Z",
        "passed": True,
        "status": "passed",
        "request_hash": approval_hash,
        "operator_id": "workspace-user",
        "provider": {"snapshot_id": provider["snapshot_id"]},
        "strategy_run": {
            "strategy_id": "seed_etf_industry_rotation",
            "strategy_version": 1,
        },
        "signal_package": {"artifact_id": "signal-package-test"},
        "manual_execution_baseline": {"status": "created"},
        "comparison_request": {"strategy_id": "seed_etf_industry_rotation"},
        "comparison": {"as_of": "2026-09-02"},
        "daily_decision_v2": {"readiness": {"status": "ready"}},
        "ui08": {"step_9": "ready", "step_10": "ready"},
        "safety": {
            "broker_connections": 0,
            "real_orders": 0,
            "paper_or_manual_journal_mutations": 0,
            "strategy_governance_mutations": 0,
            "agent_write_tools": 0,
        },
    }
    receipt["evidence_hash"] = canonical_hash(receipt)
    evidence = tmp_path / "evidence" / "live-portfolio-acceptance-20260902.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(orjson.dumps(receipt))

    class NoSecondProviderCall:
        def fetch_etf_daily(self, **kwargs: object) -> pl.DataFrame:
            del kwargs
            raise AssertionError("completed acceptance must not call the provider")

    def no_second_container() -> object:
        raise AssertionError("completed acceptance must not reopen persistence")

    replay = run_live_portfolio_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        executed_at=_OBSERVED_AT,
        source=NoSecondProviderCall(),
        container_factory=no_second_container,
    )

    assert replay == receipt
    assert orjson.loads(evidence.read_bytes()) == receipt


def test_incomplete_completed_receipt_fails_closed_before_new_io(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    receipt: dict[str, object] = {
        "schema": "ditto.q5-live-portfolio-acceptance.v1",
        "generated_at": "2026-09-02T12:00:00Z",
        "passed": True,
        "status": "passed",
        "request_hash": approval_hash,
        "operator_id": "workspace-user",
    }
    receipt["evidence_hash"] = canonical_hash(receipt)
    evidence = tmp_path / "evidence" / "live-portfolio-acceptance-20260902.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(orjson.dumps(receipt))

    class NoSecondProviderCall:
        def fetch_etf_daily(self, **kwargs: object) -> pl.DataFrame:
            del kwargs
            raise AssertionError("invalid receipt must fail before provider I/O")

    def no_second_container() -> object:
        raise AssertionError("invalid receipt must fail before persistence I/O")

    with pytest.raises(ValueError, match="receipt is invalid"):
        run_live_portfolio_acceptance(
            proposal,
            approved_request_hash=approval_hash,
            operator_id="workspace-user",
            executed_at=_OBSERVED_AT,
            source=NoSecondProviderCall(),
            container_factory=no_second_container,
        )
