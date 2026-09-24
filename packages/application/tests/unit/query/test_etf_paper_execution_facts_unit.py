"""Admitted ETF Paper facts retain both date identities and reject future rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_application.etf_paper_contracts import ETFPaperExecutionRequest
from ditto_application.exceptions import AppProcessError
from ditto_application.paper_contracts import PaperMarketSnapshotInput
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.etf_paper_execution_facts import (
    LiveETFPaperExecutionFacts,
)
from ditto_portfolio.account_ledger import ledger_hash

SIGNAL = datetime(2026, 9, 1, 7, 10, tzinfo=UTC)
EXECUTION = datetime(2026, 9, 2, 8, tzinfo=UTC)


def _candidate(day: str, cutoff: datetime, snapshot: str) -> ETFCandidate:
    values: dict[str, str | float] = {
        "price_close": 10.0,
        "asset_class": "etf",
        "trading_currency": "CNY",
        "trading_restriction": "none",
        "lot_size": 100.0,
        "tick_size": 0.001,
        "settlement_cycle": 1.0,
        "price_limit_pct": 0.1,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_duty_rate": 0.0,
        "transfer_fee_rate": 0.0,
    }
    return ETFCandidate(
        instrument_id=1,
        ticker="510300",
        name="recorded ETF",
        exchange="XSHG",
        is_active=True,
        fields={
            name: ETFField(
                value=value,
                unit=None,
                observed_on=day,
                published_at=cutoff.isoformat(),
                source="recorded",
                source_snapshot_id=snapshot,
                eligibility="PAPER_ADMITTED",
                missing_reason=None,
            )
            for name, value in values.items()
        },
    )


def _facts() -> tuple[LiveETFPaperExecutionFacts, MagicMock, MagicMock]:
    metadata = MagicMock()
    metadata.list_etf_candidates.side_effect = lambda **kwargs: [
        _candidate(
            kwargs["asof"],
            SIGNAL if kwargs["asof"] == "2026-09-01" else EXECUTION,
            kwargs["source_snapshot_id"],
        )
    ]
    metadata.list_trading_days.return_value = ["2026-09-02", "2026-09-03"]
    metadata.resolve_source_ticker.return_value = "510300.SH"
    admission = MagicMock()
    admission.assess.return_value = SimpleNamespace(allowed=True)
    snapshots = MagicMock()
    snapshots.get_snapshot.side_effect = lambda snapshot_id: SimpleNamespace(
        snapshot_id=snapshot_id,
        dataset_id="etf_daily" if snapshot_id == "bar" else "etf_reference",
        created_at=SIGNAL if snapshot_id == "signal" else EXECUTION,
        payload_retained=True,
        schema_version="market.etf_daily.v1",
        source="recorded",
    )
    account = SimpleNamespace(
        events=(),
        snapshot=SimpleNamespace(
            valuation_complete=True,
            total_value=Decimal("100000"),
            cash=SimpleNamespace(available=Decimal("100000")),
            positions=(),
        ),
        ledger_revision=SimpleNamespace(event_count=0, ledger_hash=ledger_hash(())),
    )
    ledger = MagicMock()
    ledger.get_paper.return_value = account
    bars = MagicMock()
    bars.load_paper_market.return_value = PaperMarketSnapshotInput(
        dataset_id="etf_daily",
        source="recorded",
        source_snapshot_id="bar",
        observed_at=EXECUTION,
        publication_cutoff=EXECUTION,
        open=10.0,
        high=10.2,
        low=9.9,
        close=10.1,
        prev_close=10.0,
        volume=1000.0,
        amount=10000.0,
        limit_up=11.0,
        limit_down=9.0,
    )
    return (
        LiveETFPaperExecutionFacts(
            metadata=metadata,
            admission=admission,
            snapshots=snapshots,
            bars=bars,
            ledger=ledger,
        ),
        metadata,
        bars,
        ledger,
    )


def _request() -> ETFPaperExecutionRequest:
    return ETFPaperExecutionRequest(
        allocation_id="demo",
        version_id="version",
        authorization_id="authorization",
        account_id="paper",
        session_id="session",
        signal_date="2026-09-01",
        intended_trade_date="2026-09-02",
        execution_cutoff=EXECUTION,
        reference_snapshot_id="reference",
        market_snapshot_id="bar",
        idempotency_key="once",
    )


@pytest.mark.pit
def test_etf_paper_facts_resolve_both_dates_and_signal_ledger() -> None:
    facts, metadata, bars, ledger = _facts()
    resolved = facts.resolve(
        _request(), instrument_id=1, signal_snapshot_id="signal", signal_cutoff=SIGNAL
    )
    assert resolved.signal_ledger_hash == ledger_hash(())
    assert resolved.execution_ledger_hash == ledger_hash(())
    assert resolved.signal_nav == 100000
    assert resolved.signal_rules.lot_size == 100
    assert resolved.execution_rules.commission_rate == 0.0003
    assert resolved.settlement_date == "2026-09-03"
    assert [
        call.kwargs["asof"] for call in metadata.list_etf_candidates.call_args_list
    ] == [
        "2026-09-01",
        "2026-09-02",
    ]
    assert [
        call.kwargs["recorded_through"] for call in ledger.get_paper.call_args_list
    ] == [SIGNAL, SIGNAL, EXECUTION]
    assert bars.load_paper_market.call_args.args[0].snapshot_for(
        "etf_daily"
    ).source_snapshot_ids == ("bar",)
    assert bars.load_paper_market.call_args.kwargs["instrument_code"] == "510300.SH"


@pytest.mark.pit
def test_etf_paper_facts_reject_future_execution_fee() -> None:
    facts, metadata, bars, _ledger = _facts()
    original = metadata.list_etf_candidates.side_effect

    def future_fee(**kwargs: object) -> list[ETFCandidate]:
        candidate = original(**kwargs)
        if kwargs["asof"] == "2026-09-02":
            value = candidate[0]
            fee = value.fields["commission_rate"]
            return [
                replace(
                    value,
                    fields={
                        **value.fields,
                        "commission_rate": replace(
                            fee,
                            published_at=(EXECUTION + timedelta(seconds=1)).isoformat(),
                        ),
                    },
                )
            ]
        return candidate

    metadata.list_etf_candidates.side_effect = future_fee
    with pytest.raises(AppProcessError, match="commission_rate"):
        facts.resolve(
            _request(),
            instrument_id=1,
            signal_snapshot_id="signal",
            signal_cutoff=SIGNAL,
        )
    bars.load_paper_market.assert_not_called()
