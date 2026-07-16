"""Real SQLite regressions for atomic account-baseline integrity."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from ditto_application.commands.account import (
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
    PositionBaselineInput,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.queries.account import AccountBaselineQuery
from ditto_execution.audit.execution_audit_service import ExecutionAuditService
from ditto_execution.models import AccountSnapshotRecord, PositionRecord
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters
from ditto_execution.storage.sqlite.trade import (
    ACCOUNT_SNAPSHOTS_DDL,
    BROKER_EVENTS_DDL,
    FILL_ADJUSTMENTS_DDL,
    FILLS_DDL,
    INTENTS_DDL,
    POSITIONS_DDL,
    AccountSnapshotReader,
    AccountSnapshotWriter,
    BrokerEventReader,
    BrokerEventWriter,
    FillAdjustmentReader,
    FillAdjustmentWriter,
    FillReader,
    FillWriter,
    IntentReader,
    IntentWriter,
    PositionReader,
    PositionWriter,
    ensure_position_schema,
)
from ditto_execution.storage.sqlite.trade.service import TradeService
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _stores(tmp_path: Path) -> tuple[SQLitePool, SQLiteClient, TradeService]:
    pool = SQLitePool(str(tmp_path / "account-baseline-integrity.db"))
    client = SQLiteClient(pool)
    client.executescript(
        INTENTS_DDL
        + FILLS_DDL
        + FILL_ADJUSTMENTS_DDL
        + POSITIONS_DDL
        + ACCOUNT_SNAPSHOTS_DDL
        + BROKER_EVENTS_DDL
    )
    ensure_position_schema(client)
    client.commit()
    audit_service = ExecutionAuditService(pool)
    audit_service.init_schema()
    service = TradeService(
        readers=ExecutionReaders(
            intent=IntentReader(client),
            fill=FillReader(client),
            position=PositionReader(client),
            account=AccountSnapshotReader(client),
            broker_event=BrokerEventReader(client),
            fill_adjustment=FillAdjustmentReader(client),
        ),
        writers=ExecutionWriters(
            intent=IntentWriter(client),
            fill=FillWriter(client),
            position=PositionWriter(client),
            account=AccountSnapshotWriter(client),
            broker_event=BrokerEventWriter(client),
            fill_adjustment=FillAdjustmentWriter(client),
        ),
        sqlite_client=client,
        audit_service=audit_service,
    )
    return pool, client, service


def _command() -> ImportAccountBaselineCommand:
    return ImportAccountBaselineCommand(
        account_id="paper-a",
        strategy_id="strategy-a",
        snapshot_date="2026-07-15",
        cash_available=60_000.0,
        cash_settled=60_000.0,
        cash_frozen=0.0,
        total_value=100_000.0,
        nav=1.0,
        positions=(
            PositionBaselineInput(
                instrument_id=510300,
                quantity=1000,
                available_quantity=1000,
                average_cost=39.0,
                market_value=40_000.0,
            ),
        ),
    )


def _account(
    snapshot_id: str,
    *,
    account_id: str = "paper-a",
    exposure: float = 100.0,
) -> AccountSnapshotRecord:
    return AccountSnapshotRecord(
        snapshot_id=snapshot_id,
        run_id=f"manual-{account_id}-strategy-a",
        strategy_id="strategy-a",
        account_id=account_id,
        snapshot_date="2026-07-15",
        cash_available=100.0,
        cash_settled=100.0,
        cash_frozen=0.0,
        total_value=100.0 + exposure,
        nav=1.0,
        exposure=exposure,
        created_at="2026-07-15T15:00:00+00:00",
    )


def _position(
    owner_snapshot_id: str,
    *,
    run_id: str = "manual-paper-a-strategy-a",
    instrument_id: int = 510300,
    market_value: float = 100.0,
) -> PositionRecord:
    return PositionRecord(
        snapshot_id=f"{owner_snapshot_id}-{instrument_id}",
        run_id=run_id,
        strategy_id="strategy-a",
        snapshot_date="2026-07-15",
        instrument_id=instrument_id,
        quantity=100,
        available_quantity=100,
        average_cost=1.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
        created_at="2026-07-15T15:00:00+00:00",
    )


@pytest.mark.integration
def test_sqlite_query_filters_pollution_and_replay_detects_missing_positions(
    tmp_path: Path,
) -> None:
    pool, client, service = _stores(tmp_path)
    try:
        command = _command()
        handler = ImportAccountBaselineHandler(
            account_port=service,
            position_port=service,
        )
        created = handler.handle(command)
        owned = service.list_positions(
            "strategy-a",
            snapshot_date="2026-07-15",
            run_id=created.sleeve_id,
        )[0]
        service.save_position(
            _position(
                f"{created.snapshot_id}-shadow",
                run_id=created.sleeve_id,
                instrument_id=159915,
                market_value=900_000.0,
            )
        )
        query = AccountBaselineQuery(
            account_port=service,
            position_port=service,
        )

        complete = query.get_latest(
            account_id="paper-a",
            strategy_id="strategy-a",
            signal_date="2026-07-15",
        )

        assert complete is not None
        assert [position.snapshot_id for position in complete.positions] == [
            owned.snapshot_id
        ]

        client.execute(
            "DELETE FROM actual_positions WHERE snapshot_id = ?",
            (owned.snapshot_id,),
        )
        client.commit()

        assert (
            query.get_latest(
                account_id="paper-a",
                strategy_id="strategy-a",
                signal_date="2026-07-15",
            )
            is None
        )
        with pytest.raises(AppCommandError, match=r"incomplete|inconsistent"):
            handler.handle(command)
    finally:
        pool.close()


@pytest.mark.integration
def test_sqlite_query_rejects_exposure_mismatch_but_accepts_empty_zero_exposure(
    tmp_path: Path,
) -> None:
    pool, _, service = _stores(tmp_path)
    try:
        mismatch = _account("mismatch")
        service.save_account_snapshot(mismatch)
        service.save_position(_position("mismatch", market_value=99.0))
        zero = _account("zero", account_id="paper-zero", exposure=0.0)
        service.save_account_snapshot(zero)
        query = AccountBaselineQuery(
            account_port=service,
            position_port=service,
        )

        assert (
            query.get_latest(
                account_id="paper-a",
                strategy_id="strategy-a",
                signal_date="2026-07-15",
            )
            is None
        )
        zero_result = query.get_latest(
            account_id="paper-zero",
            strategy_id="strategy-a",
            signal_date="2026-07-15",
        )

        assert zero_result is not None
        assert zero_result.account.snapshot_id == "zero"
        assert zero_result.positions == ()
    finally:
        pool.close()


@pytest.mark.integration
def test_sqlite_replacement_rolls_back_account_and_positions_as_one_aggregate(
    tmp_path: Path,
) -> None:
    pool, client, service = _stores(tmp_path)
    try:
        original = _account("original")
        original_position = _position("original")
        service.save_account_baseline(
            account=original,
            positions=(original_position,),
            audit_payload=None,
        )
        client.executescript(
            """
            CREATE TRIGGER fail_replacement_position
            BEFORE INSERT ON actual_positions
            WHEN NEW.snapshot_id = 'replacement-510300'
            BEGIN
                SELECT RAISE(ABORT, 'injected replacement failure');
            END;
            """
        )
        client.commit()
        replacement = replace(original, snapshot_id="replacement", exposure=200.0)
        replacement_position = replace(
            original_position,
            snapshot_id="replacement-510300",
            market_value=200.0,
        )

        with pytest.raises(
            sqlite3.IntegrityError,
            match="injected replacement failure",
        ):
            service.save_account_baseline(
                account=replacement,
                positions=(replacement_position,),
                audit_payload=None,
            )

        accounts = service.list_account_snapshots(
            original.run_id,
            strategy_id=original.strategy_id,
            account_id=original.account_id,
            snapshot_date=original.snapshot_date,
        )
        positions = service.list_positions(
            original.strategy_id,
            snapshot_date=original.snapshot_date,
            run_id=original.run_id,
        )
        assert accounts == [original]
        assert positions == [original_position]
    finally:
        pool.close()
