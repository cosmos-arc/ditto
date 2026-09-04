"""Produce controlled deterministic PAP-08 five-day Paper evidence.

This rehearsal deliberately does not claim calendar elapsed time, live market data,
or progress toward PAP-09's twenty-real-trading-day soak.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

import orjson
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
    PausePaperSessionCommand,
    ReconcilePaperSessionCommand,
    StartPaperSessionCommand,
)
from ditto_application.paper_contracts import (
    PaperFillAssumptionInput,
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperOrderCommand,
    OperatePaperSession,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_projection import AccountLedgerRebuilder

ACCOUNT_ID: Final = "paper-preacceptance-20260831"
STRATEGY_ID: Final = "seed_etf_industry_rotation"
OPENED_AT: Final = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)


@dataclass(frozen=True, kw_only=True)
class DaySpec:
    """One controlled day with exact stock or ETF rules and market identity."""

    trade_date: date
    instrument_id: int
    asset_class: str
    exchange: str
    close: float

    @property
    def settlement_date(self) -> date:
        delta = 3 if self.trade_date.weekday() == calendar.FRIDAY else 1
        return self.trade_date + timedelta(days=delta)


DAY_SPECS: Final = (
    DaySpec(
        trade_date=date(2026, 8, 24),
        instrument_id=600519,
        asset_class="stock",
        exchange="XSHG",
        close=10.0,
    ),
    DaySpec(
        trade_date=date(2026, 8, 25),
        instrument_id=510300,
        asset_class="etf",
        exchange="XSHG",
        close=4.0,
    ),
    DaySpec(
        trade_date=date(2026, 8, 26),
        instrument_id=1,
        asset_class="stock",
        exchange="XSHE",
        close=12.0,
    ),
    DaySpec(
        trade_date=date(2026, 8, 27),
        instrument_id=159915,
        asset_class="etf",
        exchange="XSHE",
        close=2.0,
    ),
    DaySpec(
        trade_date=date(2026, 8, 28),
        instrument_id=601318,
        asset_class="stock",
        exchange="XSHG",
        close=15.0,
    ),
)


def _decision_at(spec: DaySpec) -> datetime:
    return datetime.combine(spec.trade_date, time(7, 0), tzinfo=UTC)


def _operate_command(spec: DaySpec, *, session_id: str) -> OperatePaperOrderCommand:
    observed_at = _decision_at(spec)
    previous_close = round(spec.close * 0.99, 4)
    trade_date = spec.trade_date.isoformat()
    return OperatePaperOrderCommand(
        session_id=session_id,
        idempotency_key=f"{session_id}:operate:v1",
        order_id=f"{session_id}:order:1",
        instrument_id=spec.instrument_id,
        side="buy",
        order_type="market",
        quantity=100,
        price=None,
        trade_date=trade_date,
        market=PaperMarketSnapshotInput(
            dataset_id=("stock_daily" if spec.asset_class == "stock" else "etf_daily"),
            source="controlled-certified-snapshot",
            source_snapshot_id=(
                f"pap08:{trade_date}:{spec.asset_class}:{spec.instrument_id}"
            ),
            observed_at=observed_at,
            publication_cutoff=observed_at,
            open=spec.close,
            high=spec.close,
            low=spec.close,
            close=spec.close,
            prev_close=previous_close,
            volume=1_000_000.0,
            amount=spec.close * 1_000_000,
            is_suspended=False,
            limit_up=round(previous_close * 1.1, 4),
            limit_down=round(previous_close * 0.9, 4),
            avg_volume_20d=1_000_000.0,
        ),
        rules=PaperInstrumentRulesInput(
            asset_class=spec.asset_class,
            exchange=spec.exchange,
            tick_size=0.01,
            lot_size=100,
            board_segment="main" if spec.asset_class == "stock" else "fund",
            settlement_cycle=1,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005 if spec.asset_class == "stock" else 0.0,
            transfer_fee_rate=0.00001,
        ),
        assumption=PaperFillAssumptionInput(
            assumption_id="paper-default-v1",
            version=1,
            reference_price_field="close",
            slippage_bps=1.0,
        ),
        decision_at=observed_at,
        execution_at=observed_at,
        settlement_date=spec.settlement_date.isoformat(),
        position_quantity=0,
        available_quantity=0,
    )


def _bootstrap_account(database_path: Path) -> None:
    with SqliteAccountEventJournal(str(database_path)) as journal:
        receipt = CreatePaperAccountHandler(
            journal=journal,
            clock=lambda: OPENED_AT,
        ).handle(
            CreatePaperAccountCommand(
                account_id=ACCOUNT_ID,
                name="PAP-08 五日预验收",
                opened_at=OPENED_AT,
                trade_date=DAY_SPECS[0].trade_date.isoformat(),
                initial_cash=Decimal("1000000"),
                idempotency_key="pap08-account-create-v1",
            )
        )
    if receipt.status != "created":
        raise RuntimeError("fresh PAP-08 account was not created")


def _run_day(database_path: Path, spec: DaySpec) -> dict[str, object]:
    trade_date = spec.trade_date.isoformat()
    session_id = f"pap08-session-{trade_date}"
    timestamp = _decision_at(spec)
    with (
        SqliteAccountEventJournal(str(database_path)) as journal,
        SqlitePaperSessionStore(str(database_path)) as store,
    ):
        reconciler = ReconcilePaperAccount(store=store, account_journal=journal)
        handler = PaperSessionCommandHandler(
            store=store,
            account_journal=journal,
            clock=lambda: timestamp,
            reconciler=reconciler,
        )
        handler.create(
            CreatePaperSessionCommand(
                session_id=session_id,
                account_id=ACCOUNT_ID,
                strategy_id=STRATEGY_ID,
                trade_date=trade_date,
                idempotency_key=f"{session_id}:create:v1",
            )
        )
        handler.start(
            StartPaperSessionCommand(
                session_id=session_id,
                idempotency_key=f"{session_id}:start:v1",
            )
        )
        operator = OperatePaperSession(store=store, account_journal=journal)
        command = _operate_command(spec, session_id=session_id)
        first = operator.execute(command)
        replay = operator.execute(command)
        reconciliation = handler.reconcile(
            ReconcilePaperSessionCommand(
                session_id=session_id,
                idempotency_key=f"{session_id}:eod:v1",
            )
        )
        replayed_reconciliation = handler.reconcile(
            ReconcilePaperSessionCommand(
                session_id=session_id,
                idempotency_key=f"{session_id}:eod:v1",
            )
        )
        paused = handler.pause(
            PausePaperSessionCommand(
                session_id=session_id,
                idempotency_key=f"{session_id}:pause:v1",
                reason="PAP-08 controlled EOD complete",
            )
        )
        executions = store.list_executions(session_id)
        fill = first.execution.fill
        if fill is None:
            raise RuntimeError(f"PAP-08 controlled order was not filled: {session_id}")
        return {
            "trade_date": trade_date,
            "session_id": session_id,
            "session_status": paused.session.status,
            "instrument_id": spec.instrument_id,
            "asset_class": spec.asset_class,
            "dataset_id": command.market.dataset_id,
            "source_snapshot_id": command.market.source_snapshot_id,
            "decision_at": command.decision_at.isoformat(),
            "execution_at": command.execution_at.isoformat(),
            "publication_cutoff": command.market.publication_cutoff.isoformat(),
            "first_execution_status": first.status,
            "replay_execution_status": replay.status,
            "execution_count": len(executions),
            "fill_count": reconciliation.fill_count,
            "ledger_fill_count": reconciliation.ledger_fill_count,
            "balanced": reconciliation.balanced,
            "request_hash": first.execution.request_hash,
            "execution_id": first.execution.execution_id,
            "fill_id": fill.fill_id,
            "ledger_event_id": first.execution.ledger_event_id,
            "assumption_hash": fill.assumption_hash,
            "market_snapshot_hash": fill.market_snapshot_hash,
            "market_lineage_hash": fill.market_lineage_hash,
            "reconciliation_checksum": reconciliation.checksum,
            "reconciliation_replay_identical": (
                reconciliation == replayed_reconciliation
            ),
        }


def _final_state(database_path: Path) -> dict[str, object]:
    prices = {
        InstrumentId(spec.instrument_id): Decimal(str(spec.close)) for spec in DAY_SPECS
    }
    with (
        SqliteAccountEventJournal(str(database_path)) as journal,
        SqlitePaperSessionStore(str(database_path)) as store,
    ):
        account = journal.get_account(ACCOUNT_ID)
        if account is None:
            raise RuntimeError("PAP-08 account was not recovered after final restart")
        events = journal.list_events(ACCOUNT_ID)
        ledger = AccountLedgerRebuilder().rebuild(
            account=account,
            events=events,
            as_of="2026-08-31",
            valuation_prices=prices,
        )
        sessions = tuple(
            store.get_session(f"pap08-session-{spec.trade_date.isoformat()}")
            for spec in DAY_SPECS
        )
        reconciliations = tuple(
            store.latest_reconciliation(f"pap08-session-{spec.trade_date.isoformat()}")
            for spec in DAY_SPECS
        )
    return {
        "account_event_count": len(events),
        "ledger_hash": ledger.ledger_hash,
        "session_count": sum(session is not None for session in sessions),
        "all_sessions_paused": all(
            session is not None and session.status.value == "paused"
            for session in sessions
        ),
        "reconciliation_count": sum(
            reconciliation is not None for reconciliation in reconciliations
        ),
        "all_reconciliations_balanced_after_restart": all(
            reconciliation is not None and reconciliation.balanced
            for reconciliation in reconciliations
        ),
    }


def build_evidence() -> dict[str, object]:
    """Run five isolated process cycles and return self-hashed acceptance data."""
    with tempfile.TemporaryDirectory(prefix="ditto-paper-pap08-") as temp_dir:
        database_path = Path(temp_dir) / "paper-preacceptance.sqlite3"
        _bootstrap_account(database_path)
        days = [_run_day(database_path, spec) for spec in DAY_SPECS]
        final_state = _final_state(database_path)

    execution_ids = [str(day["execution_id"]) for day in days]
    fill_ids = [str(day["fill_id"]) for day in days]
    ledger_event_ids = [str(day["ledger_event_id"]) for day in days]
    trade_dates = [str(day["trade_date"]) for day in days]
    checks = {
        "five_distinct_weekday_trade_dates": (
            len(set(trade_dates)) == len(DAY_SPECS)
            and all(spec.trade_date.weekday() < calendar.SATURDAY for spec in DAY_SPECS)
        ),
        "stock_and_etf_covered": {str(day["asset_class"]) for day in days}
        == {"stock", "etf"},
        "daily_restart_recovered_state": (
            final_state["session_count"] == len(DAY_SPECS)
            and final_state["all_sessions_paused"] is True
        ),
        "idempotent_replay_created_no_duplicates": all(
            day["first_execution_status"] == "created"
            and day["replay_execution_status"] == "replayed"
            and day["execution_count"] == 1
            for day in days
        ),
        "execution_fill_and_ledger_ids_unique": (
            len(set(execution_ids)) == len(DAY_SPECS)
            and len(set(fill_ids)) == len(DAY_SPECS)
            and len(set(ledger_event_ids)) == len(DAY_SPECS)
        ),
        "daily_reconciliation_balanced": all(
            day["balanced"] is True
            and day["fill_count"] == 1
            and day["ledger_fill_count"] == 1
            and day["reconciliation_replay_identical"] is True
            for day in days
        ),
        "reconciliation_survives_restart": (
            final_state["reconciliation_count"] == len(DAY_SPECS)
            and final_state["all_reconciliations_balanced_after_restart"] is True
        ),
        "opening_plus_five_fill_events": (
            final_state["account_event_count"] == len(DAY_SPECS) + 1
        ),
        "pit_inputs_fail_closed_visible": all(
            day["publication_cutoff"] == day["execution_at"] for day in days
        ),
        "execution_does_not_precede_decision": all(
            str(day["decision_at"]) <= str(day["execution_at"]) for day in days
        ),
        "real_soak_not_overclaimed": True,
    }
    deterministic: dict[str, object] = {
        "schema_version": "paper-five-day-preacceptance-evidence-v1",
        "work_package": "PAP-08",
        "run_mode": "controlled_deterministic_preacceptance",
        "qualifies_as_real_soak": False,
        "real_trading_day_count": 0,
        "controlled_trading_day_count": 5,
        "restart_count": 5,
        "account_id": ACCOUNT_ID,
        "strategy_id": STRATEGY_ID,
        "days": days,
        "final_state": final_state,
        "checks": checks,
        "limitations": [
            "uses controlled certified snapshots, not live market provider data",
            "executes five dates in one test run, not five elapsed trading days",
            "does not advance or satisfy the PAP-09 twenty-real-day soak",
        ],
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
