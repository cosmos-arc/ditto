"""Deterministic validation edges for the Q5 live portfolio runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_apps.operations.q4_live_account_acceptance import canonical_hash
from ditto_apps.registry.live import q5_live_portfolio_acceptance_runtime as runtime


class _Decision(StrEnum):
    APPROVED = "approved"


@dataclass(frozen=True)
class _Evidence:
    amount: Decimal
    decision: _Decision


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("value", "value"),
        (1, 1),
        (1.5, 1.5),
        (True, True),
        (Decimal("1.25"), "1.25"),
        (datetime(2026, 9, 4, tzinfo=UTC), "2026-09-04T00:00:00Z"),
        (_Decision.APPROVED, "approved"),
        (
            _Evidence(Decimal("2.50"), _Decision.APPROVED),
            {"amount": "2.50", "decision": "approved"},
        ),
        ({1: (Decimal("3.75"),)}, {"1": ["3.75"]}),
    ],
)
def test_json_value_projects_only_closed_evidence_types(
    value: object,
    expected: object,
) -> None:
    assert runtime._json_value(value) == expected


def test_json_value_rejects_unsupported_evidence_type() -> None:
    with pytest.raises(TypeError, match="unsupported evidence value: set"):
        runtime._json_value({"unsupported"})


def test_date_text_normalizes_temporal_and_text_values() -> None:
    assert runtime._date_text(date(2026, 9, 4), field="date") == "2026-09-04"
    assert (
        runtime._date_text(datetime(2026, 9, 4, 8, 30, tzinfo=UTC), field="time")
        == "2026-09-04T08:30:00+00:00"
    )
    assert runtime._date_text("2026-09-04", field="date") == "2026-09-04"
    with pytest.raises(ValueError, match="canonical string"):
        runtime._date_text(" 2026-09-04 ", field="date")


def test_configured_path_requires_an_explicit_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DITTO_TEST_ROOT", raising=False)
    with pytest.raises(ValueError, match="must be explicitly configured"):
        runtime._configured_path("DITTO_TEST_ROOT")

    monkeypatch.setenv("DITTO_TEST_ROOT", str(tmp_path))
    assert runtime._configured_path("DITTO_TEST_ROOT") == tmp_path.resolve()


def _provider_row(
    *,
    instrument_id: int = 2_001_724,
    ticker: str = "518880.SH",
    close: float = 14.42,
) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "source_ticker": ticker,
        "trade_date": "2026-09-02",
        "knowledge_date": "2026-09-02",
        "open": 14.20,
        "high": 14.50,
        "low": 14.10,
        "close": close,
        "pre_close": 14.10,
        "volume": 1000.0,
        "amount": 14_420.0,
        "pct_change": 2.27,
    }


def _approved_rows(rows: tuple[dict[str, object], ...]) -> object:
    return cast(
        "object",
        SimpleNamespace(
            raw_provider_row_count=len(rows),
            provider_rows=rows,
        ),
    )


def _provider_frame(rows: tuple[dict[str, object], ...]) -> pl.DataFrame:
    frame_rows = [
        {
            **row,
            "trade_date": date.fromisoformat(cast(str, row["trade_date"])),
            "knowledge_date": date.fromisoformat(cast(str, row["knowledge_date"])),
        }
        for row in rows
    ]
    return pl.DataFrame(frame_rows)


def test_live_rows_normalizes_approved_provider_payload() -> None:
    rows = (
        _provider_row(instrument_id=2, ticker="159915.SZ", close=2.31),
        _provider_row(instrument_id=1, ticker="518880.SH"),
    )

    result = runtime._live_rows(
        _provider_frame(rows),
        cast("runtime.ApprovedLivePortfolioAcceptance", _approved_rows(rows)),
    )

    assert tuple(row["instrument_id"] for row in result) == (1, 2)
    assert all(row["trade_date"] == "2026-09-02" for row in result)


def test_live_rows_rejects_count_universe_and_payload_drift() -> None:
    rows = (_provider_row(),)
    approved = cast(
        "runtime.ApprovedLivePortfolioAcceptance",
        _approved_rows(rows),
    )
    with pytest.raises(ValueError, match="row count drifted"):
        runtime._live_rows(pl.DataFrame(), approved)

    foreign = (_provider_row(ticker="510300.SH"),)
    with pytest.raises(ValueError, match="universe drifted"):
        runtime._live_rows(_provider_frame(foreign), approved)

    drifted = (_provider_row(close=15.00),)
    with pytest.raises(ValueError, match="payload drifted"):
        runtime._live_rows(_provider_frame(drifted), approved)


def _approved_receipt(tmp_path: Path) -> runtime.ApprovedLivePortfolioAcceptance:
    return cast(
        "runtime.ApprovedLivePortfolioAcceptance",
        SimpleNamespace(
            signal_date="2026-09-02",
            evidence_root=tmp_path,
            request_hash="a" * 64,
            provider_snapshot_id="snapshot-live",
        ),
    )


def _receipt_body() -> dict[str, object]:
    return {
        "schema": "ditto.q5-live-portfolio-acceptance.v1",
        "generated_at": "2026-09-04T00:00:00Z",
        "passed": True,
        "status": "passed",
        "request_hash": "a" * 64,
        "operator_id": "operator",
        "provider": {"snapshot_id": "snapshot-live"},
        "strategy_run": {
            "strategy_id": "seed_etf_industry_rotation",
            "strategy_version": 1,
        },
        "signal_package": {},
        "manual_execution_baseline": {},
        "comparison_request": {},
        "comparison": {"as_of": "2026-09-02"},
        "daily_decision_v2": {},
        "ui08": {},
        "safety": {
            "broker_connections": 0,
            "real_orders": 0,
            "paper_or_manual_journal_mutations": 0,
            "strategy_governance_mutations": 0,
            "agent_write_tools": 0,
        },
    }


def _write_receipt(
    approved: runtime.ApprovedLivePortfolioAcceptance,
    body: dict[str, object],
    *,
    evidence_hash: str | None = None,
) -> Path:
    path = runtime._receipt_path(approved)
    payload = {
        **body,
        "evidence_hash": evidence_hash or canonical_hash(body),
    }
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))
    return path


def test_existing_receipt_returns_none_then_accepts_authenticated_evidence(
    tmp_path: Path,
) -> None:
    approved = _approved_receipt(tmp_path)
    assert runtime._existing_receipt(approved) is None

    body = _receipt_body()
    _write_receipt(approved, body)

    assert runtime._existing_receipt(approved) == {
        **body,
        "evidence_hash": canonical_hash(body),
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "wrong"),
        ("status", "failed"),
        ("passed", False),
        ("request_hash", "0" * 64),
        ("provider", {"snapshot_id": "wrong"}),
        (
            "strategy_run",
            {"strategy_id": "wrong", "strategy_version": 1},
        ),
        (
            "strategy_run",
            {"strategy_id": "seed_etf_industry_rotation", "strategy_version": 2},
        ),
        ("comparison", {"as_of": "2026-09-01"}),
        ("safety", {}),
    ],
)
def test_existing_receipt_rejects_each_identity_drift(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    approved = _approved_receipt(tmp_path)
    body = _receipt_body()
    body[field] = value
    _write_receipt(approved, body)

    with pytest.raises(ValueError, match="receipt is invalid"):
        runtime._existing_receipt(approved)


def test_existing_receipt_rejects_hash_and_nested_shape_drift(
    tmp_path: Path,
) -> None:
    approved = _approved_receipt(tmp_path)
    body = _receipt_body()
    _write_receipt(approved, body, evidence_hash="0" * 64)
    with pytest.raises(ValueError, match="receipt is invalid"):
        runtime._existing_receipt(approved)

    body["signal_package"] = []
    _write_receipt(approved, body)
    with pytest.raises(ValueError, match="receipt is invalid"):
        runtime._existing_receipt(approved)


class _Container:
    def __init__(self, services: dict[type[object], object]) -> None:
        self.services = services

    def get(self, dependency_type: type[object]) -> object:
        return self.services[dependency_type]


def _account_validation_approved(tmp_path: Path) -> object:
    evidence_path = tmp_path / "account.json"
    evidence_path.write_bytes(
        orjson.dumps(
            {
                "evidence_identity": {
                    "manual_ledger_hash": "manual-hash",
                    "paper_ledger_hash": "paper-hash",
                }
            }
        )
    )
    return cast(
        "object",
        SimpleNamespace(
            strategy_spec_hash="spec-hash",
            strategy_universe="etf_industry",
            account_evidence_path=evidence_path,
            signal_date="2026-09-02",
        ),
    )


def _validation_container(
    *,
    active: object | None = None,
    detail: object | None = None,
    manual_hash: str = "manual-hash",
    paper_hash: str = "paper-hash",
    session: object | None = None,
) -> _Container:
    active_value = active or SimpleNamespace(
        version=1,
        spec_json={"universe": "etf_industry"},
    )
    detail_value = detail or SimpleNamespace(state="published", spec_hash="spec-hash")
    session_value = session or SimpleNamespace(
        account_id="paper-pap09-owner-acceptance",
        strategy_id="seed_etf_industry_rotation",
        trade_date="2026-09-02",
    )
    return _Container(
        {
            runtime.StrategyQueryFacade: SimpleNamespace(
                get_active_published=lambda _strategy_id: active_value,
                get_version_detail=lambda _strategy_id, _version: detail_value,
            ),
            runtime.AccountLedgerQuery: SimpleNamespace(
                get_manual=lambda **_kwargs: SimpleNamespace(
                    snapshot=SimpleNamespace(ledger_hash=manual_hash)
                ),
                get_paper=lambda **_kwargs: SimpleNamespace(
                    snapshot=SimpleNamespace(ledger_hash=paper_hash)
                ),
            ),
            runtime.PaperSessionStorePort: SimpleNamespace(
                get_session=lambda _session_id: session_value
            ),
        }
    )


def test_strategy_and_account_validation_accepts_exact_approved_state(
    tmp_path: Path,
) -> None:
    runtime._validate_strategy_and_accounts(
        cast("runtime._Container", _validation_container()),
        cast(
            "runtime.ApprovedLivePortfolioAcceptance",
            _account_validation_approved(tmp_path),
        ),
    )


@pytest.mark.parametrize(
    ("active", "detail"),
    [
        (False, SimpleNamespace(state="published", spec_hash="spec-hash")),
        (
            SimpleNamespace(version=2, spec_json={"universe": "etf_industry"}),
            SimpleNamespace(state="published", spec_hash="spec-hash"),
        ),
        (SimpleNamespace(version=1, spec_json={"universe": "etf_industry"}), False),
        (
            SimpleNamespace(version=1, spec_json={"universe": "etf_industry"}),
            SimpleNamespace(state="draft", spec_hash="spec-hash"),
        ),
        (
            SimpleNamespace(version=1, spec_json={"universe": "etf_industry"}),
            SimpleNamespace(state="published", spec_hash="wrong"),
        ),
        (
            SimpleNamespace(version=1, spec_json={"universe": "wrong"}),
            SimpleNamespace(state="published", spec_hash="spec-hash"),
        ),
    ],
)
def test_strategy_validation_rejects_each_identity_drift(
    tmp_path: Path,
    active: object,
    detail: object,
) -> None:
    container = _validation_container(
        active=None if active is False else active,
        detail=None if detail is False else detail,
    )
    if active is False:
        cast(
            SimpleNamespace, container.services[runtime.StrategyQueryFacade]
        ).get_active_published = lambda _strategy_id: None
    if detail is False:
        cast(
            SimpleNamespace, container.services[runtime.StrategyQueryFacade]
        ).get_version_detail = lambda _strategy_id, _version: None

    with pytest.raises(ValueError, match="strategy identity drifted"):
        runtime._validate_strategy_and_accounts(
            cast("runtime._Container", container),
            cast(
                "runtime.ApprovedLivePortfolioAcceptance",
                _account_validation_approved(tmp_path),
            ),
        )


def test_account_validation_rejects_evidence_ledger_and_session_drift(
    tmp_path: Path,
) -> None:
    approved = cast(
        "runtime.ApprovedLivePortfolioAcceptance",
        _account_validation_approved(tmp_path),
    )
    approved.account_evidence_path.write_bytes(orjson.dumps({"evidence_identity": []}))
    with pytest.raises(ValueError, match="evidence identity is invalid"):
        runtime._validate_strategy_and_accounts(
            cast("runtime._Container", _validation_container()),
            approved,
        )

    approved = cast(
        "runtime.ApprovedLivePortfolioAcceptance",
        _account_validation_approved(tmp_path),
    )
    for container in (
        _validation_container(manual_hash="wrong"),
        _validation_container(paper_hash="wrong"),
    ):
        with pytest.raises(ValueError, match="account ledger drifted"):
            runtime._validate_strategy_and_accounts(
                cast("runtime._Container", container),
                approved,
            )

    invalid_sessions = (
        False,
        SimpleNamespace(
            account_id="wrong",
            strategy_id="seed_etf_industry_rotation",
            trade_date="2026-09-02",
        ),
        SimpleNamespace(
            account_id="paper-pap09-owner-acceptance",
            strategy_id="wrong",
            trade_date="2026-09-02",
        ),
        SimpleNamespace(
            account_id="paper-pap09-owner-acceptance",
            strategy_id="seed_etf_industry_rotation",
            trade_date="2026-09-01",
        ),
    )
    for session in invalid_sessions:
        container = _validation_container(session=None if session is False else session)
        if session is False:
            cast(
                SimpleNamespace,
                container.services[runtime.PaperSessionStorePort],
            ).get_session = lambda _session_id: None
        with pytest.raises(ValueError, match="Paper session drifted"):
            runtime._validate_strategy_and_accounts(
                cast("runtime._Container", container),
                approved,
            )


def test_sizing_contexts_cover_held_new_and_zero_nav_positions() -> None:
    approved = cast(
        "runtime.ApprovedLivePortfolioAcceptance",
        SimpleNamespace(
            target_positions={1: 0.6, 2: 0.4},
            provider_rows=(
                _provider_row(instrument_id=1, ticker="518880.SH"),
                _provider_row(instrument_id=2, ticker="159915.SZ", close=2.31),
            ),
        ),
    )
    held = SimpleNamespace(
        instrument_id=1,
        market_value=Decimal("60"),
        quantity=Decimal("4"),
        available_quantity=Decimal("3"),
    )
    snapshot = cast(
        "runtime.PortfolioSnapshot",
        SimpleNamespace(
            positions=(held,),
            total_value=Decimal("100"),
            cash=SimpleNamespace(available=Decimal("40")),
        ),
    )

    contexts = runtime._sizing_contexts(approved, snapshot)

    assert contexts[1].current_quantity == 4
    assert contexts[1].available_quantity == 3
    assert contexts[1].current_weight == 0.6
    assert contexts[2].current_quantity == 0
    assert contexts[2].available_quantity == 0
    assert contexts[2].current_weight == 0.0

    zero_nav = cast(
        "runtime.PortfolioSnapshot",
        SimpleNamespace(
            positions=(held,),
            total_value=Decimal("0"),
            cash=SimpleNamespace(available=Decimal("0")),
        ),
    )
    assert runtime._sizing_contexts(approved, zero_nav)[1].current_weight == 0.0


def test_approved_snapshot_reconstruction_requires_exact_snapshot_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = cast(
        "runtime.ApprovedLivePortfolioAcceptance",
        SimpleNamespace(
            signal_date="2026-09-02",
            strategy_universe="etf_industry",
            provider_payload_checksum="a" * 64,
            observed_at=datetime(2026, 9, 2, 8, tzinfo=UTC),
            raw_provider_row_count=1,
            provider_rows=(_provider_row(),),
            provider_snapshot_id="snapshot-approved",
        ),
    )
    monkeypatch.setattr(
        runtime.ProviderSnapshot,
        "create",
        staticmethod(lambda _draft: SimpleNamespace(snapshot_id="snapshot-approved")),
    )
    assert (
        runtime._approved_provider_snapshot(approved).snapshot_id == "snapshot-approved"
    )

    monkeypatch.setattr(
        runtime.ProviderSnapshot,
        "create",
        staticmethod(lambda _draft: SimpleNamespace(snapshot_id="snapshot-drifted")),
    )
    with pytest.raises(ValueError, match="cannot be reconstructed"):
        runtime._approved_provider_snapshot(approved)
