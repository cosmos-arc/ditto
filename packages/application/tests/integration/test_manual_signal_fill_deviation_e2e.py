"""Manual signal -> fill -> position -> deviation integration test."""

from __future__ import annotations

import pytest
from ditto_application.commands.trade import RecordFillCommand, RecordFillHandler
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.processes.execution.position_reader import StoredPositionReader
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.queries.deviation import SignalDeviationQueryFacade
from ditto_application.queries.signal import SignalQueryFacade
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters
from ditto_execution.storage.sqlite.trade import (
    ACCOUNT_SNAPSHOTS_DDL,
    BROKER_EVENTS_DDL,
    FILLS_DDL,
    INTENTS_DDL,
    POSITIONS_DDL,
    AccountSnapshotReader,
    AccountSnapshotWriter,
    BrokerEventReader,
    BrokerEventWriter,
    FillReader,
    FillWriter,
    IntentReader,
    IntentWriter,
    PositionReader,
    PositionWriter,
    ensure_position_schema,
)
from ditto_execution.storage.sqlite.trade.service import TradeService
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_strategy.alpha.models import TargetPortfolio

STRATEGY_ID = "manual-loop-golden"
SIGNAL_DATE = "2026-04-10"


def _make_trade_service(client: SQLiteClient) -> TradeService:
    client.executescript(
        INTENTS_DDL
        + FILLS_DDL
        + POSITIONS_DDL
        + ACCOUNT_SNAPSHOTS_DDL
        + BROKER_EVENTS_DDL
    )
    ensure_position_schema(client)
    client.commit()
    return TradeService(
        readers=ExecutionReaders(
            intent=IntentReader(client),
            fill=FillReader(client),
            position=PositionReader(client),
            account=AccountSnapshotReader(client),
            broker_event=BrokerEventReader(client),
        ),
        writers=ExecutionWriters(
            intent=IntentWriter(client),
            fill=FillWriter(client),
            position=PositionWriter(client),
            account=AccountSnapshotWriter(client),
            broker_event=BrokerEventWriter(client),
        ),
    )


@pytest.mark.integration
def test_manual_signal_fill_position_deviation_loop() -> None:
    pool = SQLitePool(":memory:")
    try:
        service = _make_trade_service(SQLiteClient(pool))
        target = TargetPortfolio(
            trade_date=SIGNAL_DATE,
            strategy_id=STRATEGY_ID,
            run_id="manual-loop-run",
            positions={
                InstrumentId(510300): 0.6,
                InstrumentId(159915): 0.4,
            },
            cash_target=0.0,
        )
        signal_publisher = SignalPackagePublisher(
            position_reader=StoredPositionReader(position_port=service),
            intent_port=service,
        )

        signal_publisher.publish(target=target, threshold=0.0)
        latest_signals = SignalQueryFacade(intent_port=service).get_latest_intents(
            STRATEGY_ID
        )

        assert len(latest_signals) == 2
        filled_signal = next(
            signal for signal in latest_signals if signal.instrument_id == 510300
        )

        RecordFillHandler(
            intent_port=service,
            fill_port=service,
            position_port=service,
            manual_tracker=ManualTracker(
                trading_calendar=(SIGNAL_DATE, "2026-04-13"),
            ),
        ).handle(
            RecordFillCommand(
                fill_id="fill-510300",
                intent_id=filled_signal.intent_id,
                strategy_id=STRATEGY_ID,
                trade_date=SIGNAL_DATE,
                instrument_id=510300,
                direction="buy",
                quantity=100,
                fill_price=10.0,
                fee=1.0,
            )
        )

        positions = service.list_positions(
            strategy_id=STRATEGY_ID,
            snapshot_date=SIGNAL_DATE,
        )
        assert len(positions) == 1
        assert positions[0].instrument_id == 510300
        assert positions[0].quantity == 100
        assert positions[0].average_cost == pytest.approx(10.0)

        report = SignalDeviationQueryFacade(
            intent_port=service,
            fill_port=service,
            position_port=service,
        ).get_deviation(strategy_id=STRATEGY_ID, signal_date=SIGNAL_DATE)

        assert report.strategy_id == STRATEGY_ID
        assert report.signal_date == SIGNAL_DATE
        assert report.total_signals == 2
        assert report.filled == 1
        assert report.unfilled == 1

        items = {item.instrument_id: item for item in report.items}
        assert items[510300].fill_status == "filled"
        assert items[510300].actual_weight == pytest.approx(1.0)
        assert items[510300].deviation_bps == pytest.approx(4000.0)
        assert items[159915].fill_status == "unfilled"
        assert items[159915].actual_weight is None
        assert items[159915].deviation_bps is None
    finally:
        pool.close()
