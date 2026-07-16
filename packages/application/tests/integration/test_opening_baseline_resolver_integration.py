"""Real SQLite regressions for manual-fill opening baseline resolution."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Barrier, Event, local

import pytest
from ditto_application.commands.trade import (
    ProjectedFillAppendAdapter,
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
from ditto_application.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    record_to_snapshot,
)
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.opening_baseline import OpeningBaselineResolver
from ditto_application.queries.portfolio_actual import PortfolioActualQueryFacade
from ditto_execution.models import (
    AccountSnapshotRecord,
    FillRecord,
    PositionRecord,
    SignalRecord,
)
from ditto_execution.reconciliation import (
    MismatchType,
    RepairActionRecord,
    RepairActionStatus,
    RepairActionType,
)
from ditto_execution.reconciliation.executor import ImportBrokerFillRepairHandler
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
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)

STRATEGY_ID = "opening-baseline-strategy"
SIGNAL_DATE = "2026-07-11"
INTENT_ID = "opening-intent"


@dataclass(frozen=True)
class _Stores:
    pool: SQLitePool
    trade: TradeService
    artifacts: StrategyArtifactService


class _BarrierIntentPort:
    """Force both append workers to observe the same pre-lock intent state."""

    def __init__(self, trade: TradeService, barrier: Barrier) -> None:
        self._trade = trade
        self._barrier = barrier
        self._thread_state = local()

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        intent = self._trade.get_intent(intent_id)
        if not getattr(self._thread_state, "prelock_read_done", False):
            self._thread_state.prelock_read_done = True
            self._barrier.wait(timeout=5)
        return intent

    def update_intent_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        return self._trade.update_intent_status(
            intent_id,
            status,
            expected_current=expected_current,
        )


class _GatedBarrierIntentPort(_BarrierIntentPort):
    """Order two stale pre-lock reads so one status transition commits first."""

    def __init__(
        self,
        trade: TradeService,
        barrier: Barrier,
        *,
        wait_before_lock: Event | None = None,
        signal_after_update: Event | None = None,
    ) -> None:
        super().__init__(trade, barrier)
        self._wait_before_lock = wait_before_lock
        self._signal_after_update = signal_after_update

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        is_prelock_read = not getattr(
            self._thread_state,
            "prelock_read_done",
            False,
        )
        intent = super().get_intent(intent_id)
        if is_prelock_read and self._wait_before_lock is not None:
            assert self._wait_before_lock.wait(timeout=5)
        return intent

    def update_intent_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        updated = super().update_intent_status(
            intent_id,
            status,
            expected_current=expected_current,
        )
        if updated and self._signal_after_update is not None:
            self._signal_after_update.set()
        return updated


@dataclass
class _StaticBrokerFillSource:
    record: FillRecord

    def get_fill_record(self, action: RepairActionRecord) -> FillRecord:
        del action
        return self.record


@pytest.fixture
def stores(tmp_path: Path) -> Iterator[_Stores]:
    pool = SQLitePool(str(tmp_path / "opening-baseline.sqlite"))
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
    trade = TradeService(
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
    artifact_writer = SQLiteStrategyArtifactWriter(pool)
    artifact_writer.init_schema()
    artifacts = StrategyArtifactService(
        reader=SQLiteStrategyArtifactReader(pool),
        writer=artifact_writer,
    )
    try:
        yield _Stores(pool=pool, trade=trade, artifacts=artifacts)
    finally:
        pool.close_all()


def _intent() -> SignalRecord:
    return SignalRecord(
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        signal_date=SIGNAL_DATE,
        instrument_id=510300,
        direction="sell",
        target_weight=0.0,
        current_weight=1.0,
        delta_weight=-1.0,
        quantity=100,
    )


def _save_package_identity(
    stores: _Stores,
    *,
    account_id: str,
    artifact_id: str,
) -> None:
    sleeve_id = f"manual-{account_id}-{STRATEGY_ID}"
    stores.artifacts.save_artifact(
        StrategyArtifactRecord(
            artifact_id=artifact_id,
            strategy_id=STRATEGY_ID,
            run_id=f"eod-{SIGNAL_DATE}-{artifact_id}",
            artifact_type=ArtifactKind.SIGNAL_PACKAGE,
            file_path="",
            metadata={
                "account_id": account_id,
                "sleeve_id": sleeve_id,
                "signal_date": SIGNAL_DATE,
                "strategy_id": STRATEGY_ID,
                "intents": [{"intent_id": INTENT_ID}],
            },
            status="active",
        )
    )


def _account(
    *,
    account_id: str,
    snapshot_id: str,
    snapshot_date: str,
    exposure: float,
) -> AccountSnapshotRecord:
    return AccountSnapshotRecord(
        snapshot_id=snapshot_id,
        run_id=f"manual-{account_id}-{STRATEGY_ID}",
        strategy_id=STRATEGY_ID,
        account_id=account_id,
        snapshot_date=snapshot_date,
        cash_available=10_000.0,
        cash_settled=10_000.0,
        cash_frozen=0.0,
        total_value=10_000.0 + exposure,
        nav=1.0,
        exposure=exposure,
        created_at=f"{snapshot_date}T15:00:00+00:00",
    )


def _position(
    account: AccountSnapshotRecord,
    *,
    available_quantity: int = 80,
) -> PositionRecord:
    return PositionRecord(
        snapshot_id=f"{account.snapshot_id}-510300",
        run_id=account.run_id,
        strategy_id=account.strategy_id,
        snapshot_date=account.snapshot_date,
        instrument_id=510300,
        quantity=100,
        available_quantity=available_quantity,
        average_cost=10.0,
        market_value=account.exposure,
        unrealized_pnl=5.0,
        realized_pnl=7.0,
        total_fees=2.0,
        created_at=account.created_at,
    )


def _resolver(stores: _Stores) -> OpeningBaselineResolver:
    return OpeningBaselineResolver(
        account_query=AccountBaselineQuery(
            account_port=stores.trade,
            position_port=stores.trade,
        ),
        package_reader=stores.artifacts,
    )


@pytest.mark.integration
def test_resolver_selects_latest_complete_aggregate_not_later_than_signal_date(
    stores: _Stores,
) -> None:
    _save_package_identity(stores, account_id="paper-a", artifact_id="package-a")
    complete = _account(
        account_id="paper-a",
        snapshot_id="baseline-complete",
        snapshot_date="2026-07-09",
        exposure=1_000.0,
    )
    incomplete = _account(
        account_id="paper-a",
        snapshot_id="baseline-incomplete",
        snapshot_date="2026-07-10",
        exposure=2_000.0,
    )
    future = _account(
        account_id="paper-a",
        snapshot_id="baseline-future",
        snapshot_date="2026-07-12",
        exposure=3_000.0,
    )
    stores.trade.save_account_snapshot(complete)
    stores.trade.save_position(_position(complete))
    stores.trade.save_account_snapshot(incomplete)
    stores.trade.save_account_snapshot(future)
    stores.trade.save_position(_position(future))

    result = _resolver(stores).resolve(_intent())

    assert result.account.snapshot_id == "baseline-complete"
    assert result.account.snapshot_date == "2026-07-09"
    assert [position.snapshot_id for position in result.positions] == [
        "baseline-complete-510300"
    ]


@pytest.mark.integration
def test_resolver_accepts_zero_position_account_aggregate(stores: _Stores) -> None:
    _save_package_identity(stores, account_id="paper-zero", artifact_id="package-zero")
    old_nonzero = _account(
        account_id="paper-zero",
        snapshot_id="baseline-old-nonzero",
        snapshot_date="2026-07-09",
        exposure=1_000.0,
    )
    zero = _account(
        account_id="paper-zero",
        snapshot_id="baseline-zero",
        snapshot_date="2026-07-10",
        exposure=0.0,
    )
    stores.trade.save_account_snapshot(old_nonzero)
    stores.trade.save_position(_position(old_nonzero))
    stores.trade.save_account_snapshot(zero)

    result = _resolver(stores).resolve(_intent())

    assert result.account.snapshot_id == "baseline-zero"
    assert result.positions == ()


@pytest.mark.integration
def test_resolver_fails_closed_for_multiple_signal_package_sleeves(
    stores: _Stores,
) -> None:
    _save_package_identity(stores, account_id="paper-a", artifact_id="package-a")
    _save_package_identity(stores, account_id="paper-b", artifact_id="package-b")

    with pytest.raises(AppCommandError, match="multiple sleeves"):
        _resolver(stores).resolve(_intent())


def _save_opening_position(
    stores: _Stores,
    *,
    available_quantity: int = 80,
) -> tuple[ActualPositionSnapshot, ...]:
    _save_package_identity(stores, account_id="paper-a", artifact_id="package-a")
    account = _account(
        account_id="paper-a",
        snapshot_id="baseline-opening",
        snapshot_date="2026-07-09",
        exposure=1_000.0,
    )
    stores.trade.save_account_snapshot(account)
    stores.trade.save_position(
        _position(account, available_quantity=available_quantity)
    )
    baseline = _resolver(stores).resolve(_intent())
    return tuple(record_to_snapshot(position) for position in baseline.positions)


def _sell_fill(*, quantity: int) -> ManualExecutionFill:
    return ManualExecutionFill(
        fill_id=f"sell-{quantity}",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="sell",
        quantity=quantity,
        fill_price=12.0,
        fee=3.0,
        settlement_date="2026-07-13",
    )


@pytest.mark.integration
def test_tracker_sell_replay_inherits_opening_cost_pnl_fees_and_availability(
    stores: _Stores,
) -> None:
    opening_positions = _save_opening_position(stores)

    result = ManualTracker().compute_positions(
        fills=[_sell_fill(quantity=60)],
        strategy_id=STRATEGY_ID,
        snapshot_date="2026-07-13",
        opening_positions=opening_positions,
    )

    assert len(result) == 1
    assert result[0].quantity == 40
    assert result[0].available_quantity == 20
    assert result[0].average_cost == pytest.approx(10.0)
    assert result[0].realized_pnl == pytest.approx(127.0)
    assert result[0].total_fees == pytest.approx(5.0)


@pytest.mark.integration
def test_tracker_zero_baseline_buy_obeys_t_plus_one_availability(
    stores: _Stores,
) -> None:
    _save_package_identity(stores, account_id="paper-zero", artifact_id="package-zero")
    account = _account(
        account_id="paper-zero",
        snapshot_id="baseline-zero",
        snapshot_date="2026-07-10",
        exposure=0.0,
    )
    stores.trade.save_account_snapshot(account)
    baseline = _resolver(stores).resolve(_intent())
    fill = ManualExecutionFill(
        fill_id="buy-100",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="buy",
        quantity=100,
        fill_price=10.0,
        fee=1.0,
        settlement_date="2026-07-14",
    )
    tracker = ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14"))

    trade_day = tracker.compute_positions(
        fills=[fill],
        strategy_id=STRATEGY_ID,
        snapshot_date="2026-07-13",
        opening_positions=tuple(
            record_to_snapshot(position) for position in baseline.positions
        ),
    )
    next_day = tracker.compute_positions(
        fills=[fill],
        strategy_id=STRATEGY_ID,
        snapshot_date="2026-07-14",
        opening_positions=tuple(
            record_to_snapshot(position) for position in baseline.positions
        ),
    )

    assert trade_day[0].available_quantity == 0
    assert next_day[0].available_quantity == 100


@pytest.mark.integration
def test_tracker_baseline_one_hundred_plus_buy_fifty_equals_one_hundred_fifty(
    stores: _Stores,
) -> None:
    opening_positions = _save_opening_position(stores, available_quantity=100)
    buy = ManualExecutionFill(
        fill_id="buy-fifty",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="buy",
        quantity=50,
        fill_price=12.0,
        fee=1.0,
        settlement_date="2026-07-14",
    )

    result = ManualTracker(
        trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14")
    ).compute_positions(
        fills=[buy],
        strategy_id=STRATEGY_ID,
        snapshot_date="2026-07-13",
        opening_positions=opening_positions,
    )

    assert result[0].quantity == 150
    assert result[0].available_quantity == 100


@pytest.mark.integration
def test_tracker_rejects_sale_above_opening_available_plus_settled_buys(
    stores: _Stores,
) -> None:
    opening_positions = _save_opening_position(stores)
    buy = ManualExecutionFill(
        fill_id="same-day-buy",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="buy",
        quantity=20,
        fill_price=10.0,
        fee=1.0,
        settlement_date="2026-07-14",
    )
    tracker = ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14"))

    with pytest.raises(AppProcessError, match="available"):
        tracker.compute_positions(
            fills=[buy, _sell_fill(quantity=90)],
            strategy_id=STRATEGY_ID,
            snapshot_date="2026-07-13",
            opening_positions=opening_positions,
        )


@pytest.mark.integration
def test_tracker_never_retroactively_settles_same_day_buy_for_same_day_sell(
    stores: _Stores,
) -> None:
    _save_package_identity(stores, account_id="paper-zero", artifact_id="package-zero")
    account = _account(
        account_id="paper-zero",
        snapshot_id="baseline-zero",
        snapshot_date="2026-07-10",
        exposure=0.0,
    )
    stores.trade.save_account_snapshot(account)
    buy = ManualExecutionFill(
        fill_id="a-buy-friday",
        intent_id="buy-intent",
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-10",
        instrument_id=510300,
        direction="buy",
        quantity=100,
        fill_price=4.0,
        fee=1.0,
        settlement_date="2026-07-13",
    )
    sell = ManualExecutionFill(
        fill_id="z-sell-friday",
        intent_id="sell-intent",
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-10",
        instrument_id=510300,
        direction="sell",
        quantity=100,
        fill_price=5.0,
        fee=1.0,
        settlement_date="2026-07-10",
    )

    with pytest.raises(AppProcessError, match="available"):
        ManualTracker(
            trading_calendar=("2026-07-10", "2026-07-13", "2026-07-14")
        ).compute_positions(
            fills=[buy, sell],
            strategy_id=STRATEGY_ID,
            snapshot_date="2026-07-13",
            opening_positions=(),
        )


@pytest.mark.integration
def test_tracker_full_close_keeps_zero_quantity_pnl_snapshot(stores: _Stores) -> None:
    opening_positions = _save_opening_position(stores, available_quantity=100)

    result = ManualTracker().compute_positions(
        fills=[_sell_fill(quantity=100)],
        strategy_id=STRATEGY_ID,
        snapshot_date="2026-07-13",
        opening_positions=opening_positions,
    )

    assert len(result) == 1
    assert result[0].quantity == 0
    assert result[0].available_quantity == 0
    assert result[0].market_value == pytest.approx(0.0)
    assert result[0].unrealized_pnl == pytest.approx(0.0)
    assert result[0].realized_pnl == pytest.approx(207.0)
    assert result[0].total_fees == pytest.approx(5.0)


def _record_sell(
    stores: _Stores,
    *,
    fill_id: str,
    quantity: int,
    fill_price: float = 12.0,
    fee: float = 3.0,
):
    return RecordFillHandler(
        intent_port=stores.trade,
        fill_port=stores.trade,
        position_port=stores.trade,
        manual_tracker=ManualTracker(
            trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14")
        ),
        opening_baseline_resolver=_resolver(stores),
    ).handle(
        RecordFillCommand(
            fill_id=fill_id,
            intent_id=INTENT_ID,
            strategy_id=STRATEGY_ID,
            trade_date="2026-07-13",
            instrument_id=510300,
            direction="sell",
            quantity=quantity,
            fill_price=fill_price,
            fee=fee,
        )
    )


@pytest.mark.integration
def test_record_fill_replays_from_opening_baseline(stores: _Stores) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)

    _record_sell(stores, fill_id="sell-partial", quantity=60)

    positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    assert len(positions) == 1
    assert positions[0].quantity == 40
    assert positions[0].available_quantity == 40
    assert positions[0].average_cost == pytest.approx(10.0)
    assert positions[0].realized_pnl == pytest.approx(127.0)
    assert positions[0].total_fees == pytest.approx(5.0)


@pytest.mark.integration
def test_full_close_keeps_pnl_but_not_active_position(stores: _Stores) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)

    _record_sell(stores, fill_id="sell-full", quantity=100)

    pnl = PortfolioActualQueryFacade(stores.trade, stores.trade).compute_pnl(
        STRATEGY_ID,
        "2026-07-13",
    )
    active = PortfolioActualQueryFacade(
        stores.trade,
        stores.trade,
    ).get_latest_positions(STRATEGY_ID)
    assert pnl.total_realized_pnl == pytest.approx(207.0)
    assert pnl.total_fees == pytest.approx(5.0)
    assert pnl.net_pnl == pytest.approx(202.0)
    assert active == []


@pytest.mark.integration
def test_zero_baseline_buy_sell_and_corrections_replay_exact_pnl(
    stores: _Stores,
) -> None:
    buy_intent = SignalRecord(
        intent_id="roundtrip-buy",
        strategy_id=STRATEGY_ID,
        signal_date=SIGNAL_DATE,
        instrument_id=510300,
        direction="buy",
        target_weight=1.0,
        current_weight=0.0,
        delta_weight=1.0,
        quantity=100,
    )
    sell_intent = SignalRecord(
        intent_id="roundtrip-sell",
        strategy_id=STRATEGY_ID,
        signal_date=SIGNAL_DATE,
        instrument_id=510300,
        direction="sell",
        target_weight=0.0,
        current_weight=1.0,
        delta_weight=-1.0,
        quantity=100,
    )
    stores.trade.save_intent(buy_intent)
    stores.trade.save_intent(sell_intent)
    account_id = "paper-roundtrip"
    sleeve_id = f"manual-{account_id}-{STRATEGY_ID}"
    baseline = _account(
        account_id=account_id,
        snapshot_id="roundtrip-zero",
        snapshot_date="2026-07-10",
        exposure=0.0,
    )
    stores.trade.save_account_snapshot(baseline)
    stores.artifacts.save_artifact(
        StrategyArtifactRecord(
            artifact_id="roundtrip-package",
            strategy_id=STRATEGY_ID,
            run_id="roundtrip-eod",
            artifact_type=ArtifactKind.SIGNAL_PACKAGE,
            file_path="",
            metadata={
                "account_id": account_id,
                "sleeve_id": sleeve_id,
                "signal_date": SIGNAL_DATE,
                "strategy_id": STRATEGY_ID,
                "intents": [
                    {"intent_id": buy_intent.intent_id},
                    {"intent_id": sell_intent.intent_id},
                ],
            },
            status="active",
        )
    )
    resolver = _resolver(stores)
    tracker = ManualTracker(trading_calendar=("2026-07-10", "2026-07-13", "2026-07-14"))

    RecordFillHandler(
        stores.trade,
        stores.trade,
        stores.trade,
        tracker,
        resolver,
    ).handle(
        RecordFillCommand(
            fill_id="roundtrip-buy-fill",
            intent_id=buy_intent.intent_id,
            strategy_id=STRATEGY_ID,
            trade_date="2026-07-13",
            instrument_id=510300,
            direction="buy",
            quantity=100,
            fill_price=4.0,
            fee=1.0,
        )
    )
    trade_day = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    assert trade_day[0].quantity == 100
    assert trade_day[0].available_quantity == 0

    RecordFillHandler(
        stores.trade,
        stores.trade,
        stores.trade,
        tracker,
        resolver,
    ).handle(
        RecordFillCommand(
            fill_id="roundtrip-sell-fill",
            intent_id=sell_intent.intent_id,
            strategy_id=STRATEGY_ID,
            trade_date="2026-07-14",
            instrument_id=510300,
            direction="sell",
            quantity=100,
            fill_price=5.0,
            fee=1.0,
        )
    )
    portfolio = PortfolioActualQueryFacade(stores.trade, stores.trade)
    closed = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-14",
        run_id="",
    )
    pnl = portfolio.compute_pnl(STRATEGY_ID, "2026-07-14")
    assert closed[0].quantity == 0
    assert closed[0].realized_pnl == pytest.approx(100.0)
    assert closed[0].total_fees == pytest.approx(2.0)
    assert pnl.net_pnl == pytest.approx(98.0)
    assert portfolio.get_latest_positions(STRATEGY_ID) == []

    ReplaceFillHandler(
        stores.trade,
        stores.trade,
        stores.trade,
        tracker,
        resolver,
    ).handle(
        ReplaceFillCommand(
            adjustment_id="roundtrip-replace",
            fill_id="roundtrip-sell-fill",
            replacement_fill_id="roundtrip-sell-corrected",
            trade_date="2026-07-14",
            quantity=100,
            fill_price=6.0,
            fee=1.0,
            reason="correct sell price",
        )
    )
    corrected = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-14",
        run_id="",
    )
    assert corrected[0].quantity == 0
    assert corrected[0].realized_pnl == pytest.approx(200.0)
    assert corrected[0].total_fees == pytest.approx(2.0)

    VoidFillHandler(
        stores.trade,
        stores.trade,
        stores.trade,
        tracker,
        resolver,
    ).handle(
        VoidFillCommand(
            adjustment_id="roundtrip-void",
            fill_id="roundtrip-sell-corrected",
            reason="void corrected sell",
        )
    )
    reopened = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-14",
        run_id="",
    )
    assert reopened[0].quantity == 100
    assert reopened[0].available_quantity == 100
    assert reopened[0].realized_pnl == pytest.approx(0.0)
    assert reopened[0].total_fees == pytest.approx(1.0)


def _projection_counter(stores: _Stores) -> SQLiteClient:
    client = SQLiteClient(stores.pool)
    client.executescript(
        """
        CREATE TABLE projection_effect_counter (writes INTEGER NOT NULL);
        INSERT INTO projection_effect_counter (writes) VALUES (0);
        CREATE TRIGGER count_manual_position_insert
        AFTER INSERT ON actual_positions
        WHEN NEW.run_id = ''
        BEGIN
            UPDATE projection_effect_counter SET writes = writes + 1;
        END;
        CREATE TRIGGER count_manual_position_delete
        AFTER DELETE ON actual_positions
        WHEN OLD.run_id = ''
        BEGIN
            UPDATE projection_effect_counter SET writes = writes + 1;
        END;
        """
    )
    client.commit()
    return client


@pytest.mark.integration
def test_record_fill_created_false_race_returns_canonical_without_projection(
    stores: _Stores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)
    first = _record_sell(stores, fill_id="sell-replay", quantity=60)
    canonical = stores.trade.get_fill("sell-replay")
    before_positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    assert canonical is not None
    counter = _projection_counter(stores)
    original_get_fill = stores.trade.get_fill
    missed = False

    def miss_precheck_once(fill_id: str):
        nonlocal missed
        if fill_id == "sell-replay" and not missed:
            missed = True
            return None
        return original_get_fill(fill_id)

    monkeypatch.setattr(stores.trade, "get_fill", miss_precheck_once)

    replay = _record_sell(stores, fill_id="sell-replay", quantity=60)

    assert replay == first
    assert original_get_fill("sell-replay") == canonical
    assert (
        stores.trade.list_positions(
            STRATEGY_ID,
            snapshot_date="2026-07-13",
            run_id="",
        )
        == before_positions
    )
    assert counter.fetchval("SELECT writes FROM projection_effect_counter") == 0


@pytest.mark.integration
def test_append_adapter_exact_replay_reports_false_without_projection(
    stores: _Stores,
) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)
    tracker = ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14"))
    adapter = ProjectedFillAppendAdapter(
        stores.trade,
        stores.trade,
        stores.trade,
        tracker,
        _resolver(stores),
    )
    record = FillRecord(
        fill_id="adapter-replay",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="sell",
        quantity=20,
        fill_price=12.0,
        fee=1.0,
        settlement_date="2026-07-14",
        created_at="2026-07-13T10:00:00Z",
    )
    assert adapter.append_projected_fill(record) is True
    before_positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    counter = _projection_counter(stores)

    assert adapter.append_projected_fill(record) is False
    assert (
        stores.trade.list_positions(
            STRATEGY_ID,
            snapshot_date="2026-07-13",
            run_id="",
        )
        == before_positions
    )
    assert counter.fetchval("SELECT writes FROM projection_effect_counter") == 0


@pytest.mark.integration
def test_void_created_false_race_returns_canonical_without_projection(
    stores: _Stores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)
    _record_sell(stores, fill_id="sell-to-void", quantity=60)
    handler = VoidFillHandler(
        stores.trade,
        stores.trade,
        stores.trade,
        ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14")),
        _resolver(stores),
    )
    command = VoidFillCommand(
        adjustment_id="void-replay",
        fill_id="sell-to-void",
        reason="duplicate broker row",
    )
    first = handler.handle(command)
    before_positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    counter = _projection_counter(stores)
    original_get_adjustment = stores.trade.get_fill_adjustment
    missed = False

    def miss_precheck_once(adjustment_id: str):
        nonlocal missed
        if adjustment_id == command.adjustment_id and not missed:
            missed = True
            return None
        return original_get_adjustment(adjustment_id)

    monkeypatch.setattr(
        stores.trade,
        "get_fill_adjustment",
        miss_precheck_once,
    )

    replay = handler.handle(command)

    assert replay.created_at == first.created_at
    assert (
        stores.trade.list_positions(
            STRATEGY_ID,
            snapshot_date="2026-07-13",
            run_id="",
        )
        == before_positions
    )
    assert counter.fetchval("SELECT writes FROM projection_effect_counter") == 0


@pytest.mark.integration
def test_distinct_fill_race_reloads_intent_under_lock_and_keeps_both_fills(
    stores: _Stores,
) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)
    intent_port = _BarrierIntentPort(stores.trade, Barrier(2))
    adapter = ProjectedFillAppendAdapter(
        intent_port,
        stores.trade,
        stores.trade,
        ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14")),
        _resolver(stores),
    )
    records = (
        FillRecord(
            fill_id="concurrent-sell-20",
            intent_id=INTENT_ID,
            strategy_id=STRATEGY_ID,
            trade_date="2026-07-13",
            instrument_id=510300,
            direction="sell",
            quantity=20,
            fill_price=12.0,
            fee=1.0,
            settlement_date="2026-07-14",
            created_at="2026-07-13T10:00:00Z",
        ),
        FillRecord(
            fill_id="concurrent-sell-30",
            intent_id=INTENT_ID,
            strategy_id=STRATEGY_ID,
            trade_date="2026-07-13",
            instrument_id=510300,
            direction="sell",
            quantity=30,
            fill_price=12.0,
            fee=1.0,
            settlement_date="2026-07-14",
            created_at="2026-07-13T10:00:01Z",
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(adapter.append_projected_fill, records))

    assert results == (True, True)
    assert {fill.fill_id for fill in stores.trade.list_fills(STRATEGY_ID)} == {
        "concurrent-sell-20",
        "concurrent-sell-30",
    }
    intent = stores.trade.get_intent(INTENT_ID)
    positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    assert intent is not None
    assert intent.status == "partially_filled"
    assert positions[0].quantity == 50
    assert positions[0].available_quantity == 50


@pytest.mark.integration
def test_adjustment_and_distinct_fill_race_accumulate_from_locked_intent_state(
    stores: _Stores,
) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)
    _record_sell(stores, fill_id="race-source-sell", quantity=100, fee=1.0)
    initial = stores.trade.get_intent(INTENT_ID)
    assert initial is not None
    assert initial.status == "filled"
    barrier = Barrier(2)
    void_updated = Event()
    void_intent_port = _GatedBarrierIntentPort(
        stores.trade,
        barrier,
        signal_after_update=void_updated,
    )
    append_intent_port = _GatedBarrierIntentPort(
        stores.trade,
        barrier,
        wait_before_lock=void_updated,
    )
    resolver = _resolver(stores)
    tracker = ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14"))
    void_handler = VoidFillHandler(
        void_intent_port,
        stores.trade,
        stores.trade,
        tracker,
        resolver,
    )
    append_adapter = ProjectedFillAppendAdapter(
        append_intent_port,
        stores.trade,
        stores.trade,
        tracker,
        resolver,
    )
    adjustment = VoidFillCommand(
        adjustment_id="race-void-source",
        fill_id="race-source-sell",
        reason="remove duplicate source",
    )
    distinct = FillRecord(
        fill_id="race-distinct-sell",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="sell",
        quantity=30,
        fill_price=12.0,
        fee=1.0,
        settlement_date="2026-07-14",
        created_at="2026-07-13T10:30:00Z",
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        adjustment_future = executor.submit(void_handler.handle, adjustment)
        append_future = executor.submit(
            append_adapter.append_projected_fill,
            distinct,
        )
        adjustment_result = adjustment_future.result()
        append_result = append_future.result()

    assert adjustment_result.adjustment_id == adjustment.adjustment_id
    assert append_result is True
    assert {fill.fill_id for fill in stores.trade.list_fills(STRATEGY_ID)} == {
        "race-source-sell",
        "race-distinct-sell",
    }
    assert [
        fill.fill_id for fill in stores.trade.list_effective_fills(STRATEGY_ID)
    ] == ["race-distinct-sell"]
    intent = stores.trade.get_intent(INTENT_ID)
    positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    assert intent is not None
    assert intent.status == "partially_filled"
    assert positions[0].quantity == 70
    assert positions[0].available_quantity == 70
    assert positions[0].realized_pnl == pytest.approx(67.0)
    assert positions[0].total_fees == pytest.approx(3.0)


def _broker_import_action(fill_id: str) -> RepairActionRecord:
    return RepairActionRecord(
        action_id="broker-import-action",
        report_id="broker-import-report",
        account_id="paper-a",
        trade_date="2026-07-13",
        action_index=0,
        action_type=RepairActionType.IMPORT_BROKER_FILL,
        mismatch_type=MismatchType.EXTRA_FILL,
        status=RepairActionStatus.APPROVED,
        order_id="broker-order",
        fill_id=fill_id,
        reason="approved broker import",
    )


@pytest.mark.integration
def test_broker_import_uses_projected_adapter_and_replay_is_zero_effect(
    stores: _Stores,
) -> None:
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)
    fill = FillRecord(
        fill_id="broker-import-fill",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="sell",
        quantity=60,
        fill_price=12.0,
        fee=3.0,
        settlement_date="2026-07-14",
        created_at="2026-07-13T11:00:00Z",
    )
    source = _StaticBrokerFillSource(fill)
    adapter = ProjectedFillAppendAdapter(
        stores.trade,
        stores.trade,
        stores.trade,
        ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14")),
        _resolver(stores),
    )
    handler = ImportBrokerFillRepairHandler(
        broker_fill_source=source,
        local_fill_store=stores.trade,
        projected_fill_port=adapter,
    )
    action = _broker_import_action(fill.fill_id)

    created = handler.execute(action)

    intent = stores.trade.get_intent(INTENT_ID)
    positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    assert created.status == "executed"
    assert created.effect_count == 1
    assert stores.trade.get_fill(fill.fill_id) == fill
    assert intent is not None
    assert intent.status == "partially_filled"
    assert positions[0].quantity == 40
    assert positions[0].available_quantity == 40
    assert positions[0].realized_pnl == pytest.approx(127.0)
    assert positions[0].total_fees == pytest.approx(5.0)

    before_positions = positions
    counter = _projection_counter(stores)
    replay = handler.execute(action)
    assert replay.status == "executed"
    assert replay.effect_count == 0
    assert (
        stores.trade.list_positions(
            STRATEGY_ID,
            snapshot_date="2026-07-13",
            run_id="",
        )
        == before_positions
    )
    assert counter.fetchval("SELECT writes FROM projection_effect_counter") == 0

    source.record = replace(fill, quantity=61)
    with pytest.raises(AppConflictError, match="Fill ID conflict"):
        handler.execute(action)
    assert stores.trade.get_fill(fill.fill_id) == fill
    assert counter.fetchval("SELECT writes FROM projection_effect_counter") == 0


@pytest.mark.integration
def test_broker_import_rejects_negative_quantity_without_projection_writes(
    stores: _Stores,
) -> None:
    """A broker DTO bypass cannot persist invalid ledger or derived state."""
    stores.trade.save_intent(_intent())
    _save_opening_position(stores, available_quantity=100)
    before_intent = stores.trade.get_intent(INTENT_ID)
    before_positions = stores.trade.list_positions(
        STRATEGY_ID,
        snapshot_date="2026-07-13",
        run_id="",
    )
    fill = FillRecord(
        fill_id="broker-import-negative-quantity",
        intent_id=INTENT_ID,
        strategy_id=STRATEGY_ID,
        trade_date="2026-07-13",
        instrument_id=510300,
        direction="sell",
        quantity=-10,
        fill_price=12.0,
        fee=1.0,
        settlement_date="2026-07-14",
        created_at="2026-07-13T11:00:00Z",
    )
    adapter = ProjectedFillAppendAdapter(
        stores.trade,
        stores.trade,
        stores.trade,
        ManualTracker(trading_calendar=(SIGNAL_DATE, "2026-07-13", "2026-07-14")),
        _resolver(stores),
    )
    handler = ImportBrokerFillRepairHandler(
        broker_fill_source=_StaticBrokerFillSource(fill),
        local_fill_store=stores.trade,
        projected_fill_port=adapter,
    )

    with pytest.raises(AppCommandError, match="quantity must be positive"):
        handler.execute(_broker_import_action(fill.fill_id))

    assert stores.trade.get_fill(fill.fill_id) is None
    assert stores.trade.get_intent(INTENT_ID) == before_intent
    assert (
        stores.trade.list_positions(
            STRATEGY_ID,
            snapshot_date="2026-07-13",
            run_id="",
        )
        == before_positions
    )
    assert stores.trade.list_fill_adjustments(STRATEGY_ID) == []
