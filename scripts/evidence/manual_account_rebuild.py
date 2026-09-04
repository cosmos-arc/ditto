"""Produce deterministic MAN-08 fresh-journal rebuild evidence."""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

import orjson
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)
from ditto_portfolio.account_projection import AccountLedgerRebuilder, PortfolioSnapshot

ACCOUNT_ID: Final = "manual-rebuild-rehearsal-20260831"
AS_OF: Final = "2026-08-31"
RECORDED_AT: Final = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
INSTRUMENT_ID: Final = InstrumentId(42)


@dataclass(frozen=True, kw_only=True)
class EventSpec:
    """Compact deterministic input for one rehearsal event."""

    event_id: str
    event_type: AccountEventType
    trade_date: str
    settlement_date: str | None = None
    instrument_id: InstrumentId | None = None
    quantity: str = "0"
    price: str = "0"
    gross_amount: str = "0"
    fees: str = "0"
    tax: str = "0"
    reverses_event_id: str | None = None
    corrects_event_id: str | None = None
    replacement_event_type: AccountEventType | None = None


def _event(account: AccountDefinition, spec: EventSpec) -> AccountEvent:
    return create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_id=spec.event_id,
            event_type=spec.event_type,
            trade_date=spec.trade_date,
            settlement_date=spec.settlement_date or spec.trade_date,
            recorded_at=RECORDED_AT,
            idempotency_key=f"{ACCOUNT_ID}:{spec.event_id}",
            actor="evidence:manual-rebuild",
            source=AccountEventSource.MANUAL_ENTRY,
            instrument_id=spec.instrument_id,
            quantity=Decimal(spec.quantity),
            price=Decimal(spec.price),
            gross_amount=Decimal(spec.gross_amount),
            fees=Decimal(spec.fees),
            tax=Decimal(spec.tax),
            note=f"MAN-08 {spec.event_id}",
            attachment_refs=(f"evidence:{spec.event_id}",),
            reverses_event_id=spec.reverses_event_id,
            corrects_event_id=spec.corrects_event_id,
            replacement_event_type=spec.replacement_event_type,
        ),
    )


def _scenario() -> tuple[AccountDefinition, tuple[AccountEvent, ...]]:
    account = AccountDefinition(
        account_id=ACCOUNT_ID,
        kind=AccountKind.MANUAL,
        name="MAN-08 完整重建演练",
        opened_at=RECORDED_AT,
    )
    events = (
        _event(
            account,
            EventSpec(
                event_id="opening-cash",
                event_type=AccountEventType.OPENING_CASH,
                trade_date="2026-08-01",
                gross_amount="100000",
            ),
        ),
        _event(
            account,
            EventSpec(
                event_id="opening-position",
                event_type=AccountEventType.OPENING_POSITION,
                trade_date="2026-08-01",
                instrument_id=INSTRUMENT_ID,
                quantity="100",
                price="10",
                gross_amount="1000",
            ),
        ),
        _event(
            account,
            EventSpec(
                event_id="buy-original",
                event_type=AccountEventType.BUY,
                trade_date="2026-08-04",
                settlement_date="2026-08-05",
                instrument_id=INSTRUMENT_ID,
                quantity="100",
                price="12",
                fees="5",
            ),
        ),
        _event(
            account,
            EventSpec(
                event_id="buy-correction",
                event_type=AccountEventType.CORRECTION,
                trade_date="2026-08-04",
                settlement_date="2026-08-05",
                instrument_id=INSTRUMENT_ID,
                quantity="100",
                price="11.8",
                fees="5",
                corrects_event_id="buy-original",
                replacement_event_type=AccountEventType.BUY,
            ),
        ),
        _event(
            account,
            EventSpec(
                event_id="deposit-original",
                event_type=AccountEventType.DEPOSIT,
                trade_date="2026-08-10",
                gross_amount="5000",
            ),
        ),
        _event(
            account,
            EventSpec(
                event_id="deposit-reversal",
                event_type=AccountEventType.REVERSAL,
                trade_date="2026-08-11",
                reverses_event_id="deposit-original",
            ),
        ),
        _event(
            account,
            EventSpec(
                event_id="partial-sell",
                event_type=AccountEventType.SELL,
                trade_date="2026-08-20",
                settlement_date="2026-08-21",
                instrument_id=INSTRUMENT_ID,
                quantity="50",
                price="15",
                fees="5",
                tax="0.75",
            ),
        ),
    )
    return account, events


def _snapshot_payload(snapshot: PortfolioSnapshot) -> dict[str, object]:
    return {
        "account_id": snapshot.account_id,
        "account_kind": snapshot.account_kind.value,
        "as_of": snapshot.as_of,
        "cash": {
            "available": format(snapshot.cash.available, "f"),
            "settled": format(snapshot.cash.settled, "f"),
            "frozen": format(snapshot.cash.frozen, "f"),
        },
        "positions": [
            {
                "instrument_id": int(position.instrument_id),
                "quantity": format(position.quantity, "f"),
                "available_quantity": format(position.available_quantity, "f"),
                "average_cost": format(position.average_cost, "f"),
                "last_price": format(position.last_price, "f"),
                "market_value": format(position.market_value, "f"),
                "realized_pnl": format(position.realized_pnl, "f"),
                "unrealized_pnl": format(position.unrealized_pnl, "f"),
                "total_fees": format(position.total_fees, "f"),
            }
            for position in snapshot.positions
        ],
        "total_value": format(snapshot.total_value, "f"),
        "realized_pnl": format(snapshot.realized_pnl, "f"),
        "unrealized_pnl": format(snapshot.unrealized_pnl, "f"),
        "total_fees": format(snapshot.total_fees, "f"),
        "event_count": snapshot.event_count,
        "ledger_hash": snapshot.ledger_hash,
        "valuation_complete": snapshot.valuation_complete,
    }


def build_evidence() -> dict[str, object]:
    """Persist, reopen, replay twice, and compare against an independent ledger."""
    account, events = _scenario()
    with tempfile.TemporaryDirectory(prefix="ditto-manual-rebuild-") as temp_dir:
        database_path = Path(temp_dir) / "fresh-account-journal.sqlite3"
        with SqliteAccountEventJournal(str(database_path)) as journal:
            journal.create_account(account)
            journal.append_many(events)

        with SqliteAccountEventJournal(str(database_path)) as reopened:
            recovered_account = reopened.get_account(account.account_id)
            recovered_events = reopened.list_events(account.account_id)

        if recovered_account is None:
            raise RuntimeError("persisted account was not recovered")
        rebuilder = AccountLedgerRebuilder()
        prices = {INSTRUMENT_ID: Decimal("14")}
        first = rebuilder.rebuild(
            account=recovered_account,
            events=recovered_events,
            as_of=AS_OF,
            valuation_prices=prices,
        )
        second = rebuilder.rebuild(
            account=recovered_account,
            events=recovered_events,
            as_of=AS_OF,
            valuation_prices=prices,
        )

    actual = _snapshot_payload(first)
    expected: dict[str, object] = {
        "cash_available": "99559.25",
        "cash_settled": "99559.25",
        "position_quantity": "150",
        "position_available_quantity": "150",
        "position_average_cost": "10.9250",
        "position_market_value": "2100.00",
        "realized_pnl": "198.00",
        "unrealized_pnl": "461.25",
        "total_fees": "10.75",
        "total_value": "101659.25",
        "event_count": 7,
    }
    position = first.position(INSTRUMENT_ID)
    observed: dict[str, object] = {
        "cash_available": format(first.cash.available, "f"),
        "cash_settled": format(first.cash.settled, "f"),
        "position_quantity": format(position.quantity, "f"),
        "position_available_quantity": format(position.available_quantity, "f"),
        "position_average_cost": format(position.average_cost, "f"),
        "position_market_value": format(position.market_value, "f"),
        "realized_pnl": format(first.realized_pnl, "f"),
        "unrealized_pnl": format(first.unrealized_pnl, "f"),
        "total_fees": format(first.total_fees, "f"),
        "total_value": format(first.total_value, "f"),
        "event_count": first.event_count,
    }
    checks = {
        "fresh_sqlite_reopened": recovered_account == account,
        "all_events_round_trip_exactly": recovered_events == events,
        "repeat_replay_is_identical": first == second,
        "repeat_ledger_hash_is_identical": first.ledger_hash == second.ledger_hash,
        "manual_reconciliation_matches": observed == expected,
        "valuation_uses_explicit_price": first.valuation_complete,
    }
    deterministic = {
        "schema_version": "manual-account-rebuild-evidence-v1",
        "work_package": "MAN-08",
        "account_id": ACCOUNT_ID,
        "as_of": AS_OF,
        "event_ids": [event.event_id for event in events],
        "event_hashes": [event.event_hash for event in events],
        "ledger_hash": first.ledger_hash,
        "expected": expected,
        "observed": observed,
        "snapshot": actual,
        "checks": checks,
        "result": "PASS" if all(checks.values()) else "FAIL",
    }
    evidence_hash = hashlib.sha256(
        orjson.dumps(deterministic, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    return {
        **deterministic,
        "evidence_hash": f"sha256:{evidence_hash}",
        "generated_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    evidence = build_evidence()
    option = orjson.OPT_SORT_KEYS
    if not args.compact:
        option |= orjson.OPT_INDENT_2
    print(orjson.dumps(evidence, option=option).decode())
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
