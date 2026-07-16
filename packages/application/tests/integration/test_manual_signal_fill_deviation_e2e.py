"""Manual signal -> fill -> position -> deviation integration test."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_application.commands.trade import (
    ProjectedFillCorrectionAdapter,
    RecordFillCommand,
    RecordFillHandler,
    ReplaceFillCommand,
    ReplaceFillHandler,
    VoidFillCommand,
    VoidFillHandler,
)
from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppProcessError,
)
from ditto_application.execution_dto import ActualPositionSnapshot, ManualExecutionFill
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContext,
    ManualSizingService,
)
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.processes.execution.position_reader import StoredPositionReader
from ditto_application.processes.execution.signal_package import (
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.deviation import SignalDeviationQueryFacade
from ditto_application.queries.opening_baseline import OpeningBaselineResolver
from ditto_application.queries.signal import SignalQueryFacade
from ditto_execution.models import (
    AccountSnapshotRecord,
    FillAdjustmentRecord,
    FillRecord,
    SignalRecord,
)
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
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)

STRATEGY_ID = "manual-loop-golden"
SIGNAL_DATE = "2026-04-10"
EXECUTION_DATE = "2026-04-13"


def _make_trade_service(client: SQLiteClient) -> TradeService:
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
    return TradeService(
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
    )


def _opening_resolver(
    pool: SQLitePool,
    service: TradeService,
    intent_id: str,
) -> OpeningBaselineResolver:
    """Persist and resolve a real zero-position opening aggregate for one intent."""
    account_id = "integration-paper"
    sleeve_id = f"manual-{account_id}-{STRATEGY_ID}"
    service.save_account_snapshot(
        AccountSnapshotRecord(
            snapshot_id=f"baseline-{intent_id}",
            run_id=sleeve_id,
            strategy_id=STRATEGY_ID,
            account_id=account_id,
            snapshot_date=SIGNAL_DATE,
            cash_available=10_000.0,
            cash_settled=10_000.0,
            cash_frozen=0.0,
            total_value=10_000.0,
            nav=1.0,
            exposure=0.0,
        )
    )
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    artifacts = StrategyArtifactService(
        reader=SQLiteStrategyArtifactReader(pool),
        writer=writer,
    )
    artifacts.save_artifact(
        StrategyArtifactRecord(
            artifact_id=f"package-{intent_id}",
            strategy_id=STRATEGY_ID,
            run_id=f"eod-{SIGNAL_DATE}-{intent_id}",
            artifact_type=ArtifactKind.SIGNAL_PACKAGE,
            file_path="",
            metadata={
                "account_id": account_id,
                "sleeve_id": sleeve_id,
                "signal_date": SIGNAL_DATE,
                "strategy_id": STRATEGY_ID,
                "intents": [{"intent_id": intent_id}],
            },
            status="active",
        )
    )
    return OpeningBaselineResolver(
        account_query=AccountBaselineQuery(
            account_port=service,
            position_port=service,
        ),
        package_reader=artifacts,
    )


class _FailingProjectionTracker(ManualTracker):
    def compute_positions(
        self,
        fills: list[ManualExecutionFill],
        strategy_id: str,
        snapshot_date: str,
        market_prices: dict[int, float] | None = None,
        opening_positions: tuple[ActualPositionSnapshot, ...] = (),
    ) -> list[ActualPositionSnapshot]:
        del fills, strategy_id, snapshot_date, market_prices, opening_positions
        raise AppProcessError("forced projection rebuild failure")


@pytest.mark.integration
def test_manual_signal_fill_position_deviation_loop() -> None:
    pool = SQLitePool(":memory:")
    try:
        service = _make_trade_service(SQLiteClient(pool))
        artifact_writer = SQLiteStrategyArtifactWriter(pool)
        artifact_writer.init_schema()
        artifact_service = StrategyArtifactService(
            reader=SQLiteStrategyArtifactReader(pool),
            writer=artifact_writer,
        )
        target = TargetPortfolio(
            trade_date=SIGNAL_DATE,
            strategy_id=STRATEGY_ID,
            run_id=f"eod-{SIGNAL_DATE}-{STRATEGY_ID}-1",
            positions={
                InstrumentId(510300): 0.6,
                InstrumentId(159915): 0.4,
            },
            cash_target=0.0,
        )
        signal_publisher = SignalPackagePublisher(
            snapshot_process=SignalSnapshotProcess(
                position_reader=StoredPositionReader(position_port=service),
                sizing_service=ManualSizingService(),
            ),
            intent_port=service,
            fill_port=service,
            date_resolver=AShareTradeDateResolver(
                trading_days=(SIGNAL_DATE, EXECUTION_DATE)
            ),
            artifact_service=artifact_service,
        )

        signal_publisher.publish(
            SignalPackagePublishRequest(
                target=target,
                strategy_version="1",
                account_id="paper-a",
                sleeve_id=f"manual-paper-a-{STRATEGY_ID}",
                sizing_contexts={
                    510300: ManualSizingContext(
                        nav=10_000.0,
                        current_quantity=0,
                        available_quantity=0,
                        cash_available=10_000.0,
                        reference_price=10.0,
                        current_weight=0.0,
                    ),
                    159915: ManualSizingContext(
                        nav=10_000.0,
                        current_quantity=0,
                        available_quantity=0,
                        cash_available=10_000.0,
                        reference_price=10.0,
                        current_weight=0.0,
                    ),
                },
                decision_date=SIGNAL_DATE,
                intended_trade_date=EXECUTION_DATE,
                required_datasets=(),
                required_dataset_states=(),
                threshold=0.0,
            )
        )
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
                trading_calendar=(SIGNAL_DATE, EXECUTION_DATE, "2026-04-14"),
            ),
            opening_baseline_resolver=_opening_resolver(
                pool,
                service,
                filled_signal.intent_id,
            ),
        ).handle(
            RecordFillCommand(
                fill_id="fill-510300",
                intent_id=filled_signal.intent_id,
                strategy_id=STRATEGY_ID,
                trade_date=EXECUTION_DATE,
                instrument_id=510300,
                direction="buy",
                quantity=100,
                fill_price=10.0,
                fee=1.0,
            )
        )

        positions = service.list_positions(
            strategy_id=STRATEGY_ID,
            snapshot_date=EXECUTION_DATE,
        )
        assert len(positions) == 1
        assert positions[0].instrument_id == 510300
        assert positions[0].quantity == 100
        assert positions[0].average_cost == pytest.approx(10.0)

        report = SignalDeviationQueryFacade(
            intent_port=service,
            fill_port=service,
            position_port=service,
        ).get_deviation(
            strategy_id=STRATEGY_ID,
            signal_date=SIGNAL_DATE,
            execution_date=EXECUTION_DATE,
            intent_ids=tuple(signal.intent_id for signal in latest_signals),
        )

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


@pytest.mark.integration
def test_void_only_buy_clears_position_and_reopens_intent() -> None:
    pool = SQLitePool(":memory:")
    try:
        service = _make_trade_service(SQLiteClient(pool))
        service.save_intent(
            SignalRecord(
                intent_id="intent-only-buy",
                strategy_id=STRATEGY_ID,
                signal_date=SIGNAL_DATE,
                instrument_id=510300,
                direction="buy",
                target_weight=1.0,
                current_weight=0.0,
                delta_weight=1.0,
                quantity=100,
                status="pending",
            )
        )
        tracker = ManualTracker(
            trading_calendar=(SIGNAL_DATE, EXECUTION_DATE, "2026-04-14")
        )
        opening = _opening_resolver(pool, service, "intent-only-buy")
        RecordFillHandler(service, service, service, tracker, opening).handle(
            RecordFillCommand(
                fill_id="fill-only-buy",
                intent_id="intent-only-buy",
                strategy_id=STRATEGY_ID,
                trade_date=EXECUTION_DATE,
                instrument_id=510300,
                direction="buy",
                quantity=100,
                fill_price=10.0,
                fee=1.0,
            )
        )

        result = VoidFillHandler(service, service, service, tracker, opening).handle(
            VoidFillCommand(
                adjustment_id="adj-void-only-buy",
                fill_id="fill-only-buy",
                reason="duplicate manual entry",
            )
        )

        assert result.adjustment_type == "void"
        assert [fill.fill_id for fill in service.list_fills(STRATEGY_ID)] == [
            "fill-only-buy"
        ]
        assert service.list_effective_fills(STRATEGY_ID) == []
        assert (
            service.list_positions(
                STRATEGY_ID,
                snapshot_date=EXECUTION_DATE,
                run_id="",
            )
            == []
        )
        intent = service.get_intent("intent-only-buy")
        assert intent is not None
        assert intent.status == "pending"
    finally:
        pool.close()


@pytest.mark.integration
def test_replacement_projection_failure_rolls_back_entire_ledger_change() -> None:
    pool = SQLitePool(":memory:")
    try:
        service = _make_trade_service(SQLiteClient(pool))
        service.save_intent(
            SignalRecord(
                intent_id="intent-atomic-replace",
                strategy_id=STRATEGY_ID,
                signal_date=SIGNAL_DATE,
                instrument_id=510300,
                direction="buy",
                target_weight=1.0,
                current_weight=0.0,
                delta_weight=1.0,
                quantity=100,
                status="pending",
            )
        )
        tracker = ManualTracker(
            trading_calendar=(SIGNAL_DATE, EXECUTION_DATE, "2026-04-14")
        )
        opening = _opening_resolver(pool, service, "intent-atomic-replace")
        RecordFillHandler(service, service, service, tracker, opening).handle(
            RecordFillCommand(
                fill_id="fill-original",
                intent_id="intent-atomic-replace",
                strategy_id=STRATEGY_ID,
                trade_date=EXECUTION_DATE,
                instrument_id=510300,
                direction="buy",
                quantity=100,
                fill_price=10.0,
            )
        )

        with pytest.raises(AppProcessError, match="forced projection rebuild failure"):
            ReplaceFillHandler(
                service,
                service,
                service,
                _FailingProjectionTracker(),
                opening,
            ).handle(
                ReplaceFillCommand(
                    adjustment_id="adj-atomic-replace",
                    fill_id="fill-original",
                    replacement_fill_id="fill-replacement",
                    trade_date=EXECUTION_DATE,
                    quantity=50,
                    fill_price=10.1,
                    reason="correct quantity",
                )
            )

        assert service.get_fill("fill-replacement") is None
        assert service.get_fill_adjustment("adj-atomic-replace") is None
        assert [fill.fill_id for fill in service.list_effective_fills(STRATEGY_ID)] == [
            "fill-original"
        ]
        intent = service.get_intent("intent-atomic-replace")
        assert intent is not None
        assert intent.status == "filled"
        positions = service.list_positions(
            STRATEGY_ID,
            snapshot_date=EXECUTION_DATE,
            run_id="",
        )
        assert len(positions) == 1
        assert positions[0].quantity == 100
    finally:
        pool.close()


@pytest.mark.integration
def test_reconciliation_adapter_updates_effective_status_and_position_atomically() -> (
    None
):
    """Reconciliation 必须复用 projected correction，不能只追加 raw ledger。"""
    pool = SQLitePool(":memory:")
    try:
        service = _make_trade_service(SQLiteClient(pool))
        service.save_intent(
            SignalRecord(
                intent_id="intent-reconciliation",
                strategy_id=STRATEGY_ID,
                signal_date=SIGNAL_DATE,
                instrument_id=510300,
                direction="buy",
                target_weight=1.0,
                current_weight=0.0,
                delta_weight=1.0,
                quantity=100,
                status="pending",
            )
        )
        tracker = ManualTracker(
            trading_calendar=(SIGNAL_DATE, EXECUTION_DATE, "2026-04-14")
        )
        opening = _opening_resolver(pool, service, "intent-reconciliation")
        RecordFillHandler(service, service, service, tracker, opening).handle(
            RecordFillCommand(
                fill_id="fill-reconciliation-source",
                intent_id="intent-reconciliation",
                strategy_id=STRATEGY_ID,
                trade_date=EXECUTION_DATE,
                instrument_id=510300,
                direction="buy",
                quantity=100,
                fill_price=10.0,
            )
        )
        original = service.get_fill("fill-reconciliation-source")
        assert original is not None
        replacement = FillRecord(
            fill_id="fill-reconciliation-source:repair:action-1",
            intent_id=original.intent_id,
            strategy_id=original.strategy_id,
            trade_date=original.trade_date,
            instrument_id=original.instrument_id,
            direction=original.direction,
            quantity=40,
            fill_price=10.1,
            fee=1.0,
            settlement_date="2026-04-14",
            created_at="2026-04-13T10:00:00Z",
        )
        adjustment = FillAdjustmentRecord(
            adjustment_id="repair-adjustment:action-1",
            fill_id=original.fill_id,
            adjustment_type="replace",
            replacement_fill_id=replacement.fill_id,
            reason="approved broker reconciliation",
            created_at="2026-04-13T10:00:00Z",
        )
        adapter = ProjectedFillCorrectionAdapter(
            service,
            service,
            service,
            tracker,
            opening,
        )

        created = adapter.apply_projected_fill_replacement(
            adjustment=adjustment,
            replacement_fill=replacement,
        )
        replay_created = adapter.apply_projected_fill_replacement(
            adjustment=adjustment,
            replacement_fill=replacement,
        )

        assert created is True
        assert replay_created is False
        assert service.get_fill(original.fill_id) == original
        assert service.list_effective_fills(STRATEGY_ID) == [replacement]
        intent = service.get_intent("intent-reconciliation")
        assert intent is not None
        assert intent.status == "partially_filled"
        positions = service.list_positions(
            STRATEGY_ID,
            snapshot_date=EXECUTION_DATE,
            run_id="",
        )
        assert len(positions) == 1
        assert positions[0].quantity == 40

        with pytest.raises(AppConflictError, match="payload conflict"):
            adapter.apply_projected_fill_replacement(
                adjustment=adjustment,
                replacement_fill=replace(replacement, fill_price=99.0),
            )
        assert service.list_effective_fills(STRATEGY_ID) == [replacement]
        assert service.list_fill_adjustments(STRATEGY_ID) == [adjustment]
    finally:
        pool.close()


@pytest.mark.integration
def test_reconciliation_rejects_invalid_replacement_economics_atomically() -> None:
    """Reconciliation cannot bypass the immutable fill economics boundary."""
    pool = SQLitePool(":memory:")
    try:
        service = _make_trade_service(SQLiteClient(pool))
        intent_id = "intent-invalid-reconciliation"
        service.save_intent(
            SignalRecord(
                intent_id=intent_id,
                strategy_id=STRATEGY_ID,
                signal_date=SIGNAL_DATE,
                instrument_id=510300,
                direction="buy",
                target_weight=1.0,
                current_weight=0.0,
                delta_weight=1.0,
                quantity=100,
                status="pending",
            )
        )
        tracker = ManualTracker(
            trading_calendar=(SIGNAL_DATE, EXECUTION_DATE, "2026-04-14")
        )
        opening = _opening_resolver(pool, service, intent_id)
        RecordFillHandler(service, service, service, tracker, opening).handle(
            RecordFillCommand(
                fill_id="fill-invalid-reconciliation-source",
                intent_id=intent_id,
                strategy_id=STRATEGY_ID,
                trade_date=EXECUTION_DATE,
                instrument_id=510300,
                direction="buy",
                quantity=100,
                fill_price=10.0,
                fee=1.0,
            )
        )
        original = service.get_fill("fill-invalid-reconciliation-source")
        before_intent = service.get_intent(intent_id)
        before_positions = service.list_positions(
            STRATEGY_ID,
            snapshot_date=EXECUTION_DATE,
            run_id="",
        )
        assert original is not None
        replacement = replace(
            original,
            fill_id="fill-invalid-reconciliation-replacement",
            quantity=40,
            fee=-1.0,
            created_at="2026-04-13T10:00:00Z",
        )
        adjustment = FillAdjustmentRecord(
            adjustment_id="repair-adjustment:invalid-economics",
            fill_id=original.fill_id,
            adjustment_type="replace",
            replacement_fill_id=replacement.fill_id,
            reason="approved broker reconciliation",
            created_at="2026-04-13T10:00:00Z",
        )
        adapter = ProjectedFillCorrectionAdapter(
            service,
            service,
            service,
            tracker,
            opening,
        )

        with pytest.raises(
            AppCommandError,
            match="fee must be non-negative and finite",
        ):
            adapter.apply_projected_fill_replacement(
                adjustment=adjustment,
                replacement_fill=replacement,
            )

        assert service.get_fill(replacement.fill_id) is None
        assert service.get_fill_adjustment(adjustment.adjustment_id) is None
        assert service.list_effective_fills(STRATEGY_ID) == [original]
        assert service.get_intent(intent_id) == before_intent
        assert (
            service.list_positions(
                STRATEGY_ID,
                snapshot_date=EXECUTION_DATE,
                run_id="",
            )
            == before_positions
        )
    finally:
        pool.close()
