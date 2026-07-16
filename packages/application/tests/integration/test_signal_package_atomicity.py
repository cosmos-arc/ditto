"""Real SQLite recovery and concurrency coverage for Signal Package publication."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from ditto_application.processes.execution.eod_coordinator import (
    EodCoordinator,
    EodStrategyRequest,
)
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingService,
)
from ditto_application.processes.execution.signal_package import (
    SignalPackage,
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_application.signal_package_contract import verify_signal_package_metadata
from ditto_execution.models import FillRecord
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
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)
from ditto_strategy.storage.sqlite.strategy_run_store import (
    SQLiteStrategyRunReader,
    SQLiteStrategyRunWriter,
)

STRATEGY_ID = "atomic-signal"
SIGNAL_DATE = "2026-01-30"
BATCH_KEY = f"eod-{SIGNAL_DATE}-{STRATEGY_ID}-1"


class _PositionReader:
    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        assert strategy_id == STRATEGY_ID
        return {1: 0.1}


class _FailOnceArtifactService(StrategyArtifactService):
    fail_replacement = False

    def activate_candidate(
        self,
        candidate_artifact_id: str,
        *,
        replaced_artifact_id: str | None = None,
    ) -> bool:
        if replaced_artifact_id is not None and self.fail_replacement:
            self.fail_replacement = False
            raise RuntimeError("injected SQLite activation boundary failure")
        return super().activate_candidate(
            candidate_artifact_id,
            replaced_artifact_id=replaced_artifact_id,
        )


def _stores(
    tmp_path: Path,
) -> tuple[SQLitePool, TradeService, StrategyArtifactService]:
    pool = SQLitePool(str(tmp_path / "signal-package-atomicity.db"))
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
    return pool, trade, artifacts


def _publisher(
    trade: TradeService,
    artifacts: StrategyArtifactService,
) -> SignalPackagePublisher:
    return SignalPackagePublisher(
        snapshot_process=SignalSnapshotProcess(
            position_reader=_PositionReader(),
            sizing_service=ManualSizingService(),
        ),
        intent_port=trade,
        fill_port=trade,
        date_resolver=AShareTradeDateResolver(trading_days=(SIGNAL_DATE, "2026-02-02")),
        artifact_service=artifacts,
    )


def _publish(
    publisher: SignalPackagePublisher,
    risk_flags: tuple[str, ...] = (),
) -> SignalPackage:
    return publisher.publish(
        SignalPackagePublishRequest(
            target=TargetPortfolio(
                trade_date=SIGNAL_DATE,
                strategy_id=STRATEGY_ID,
                run_id=BATCH_KEY,
                positions={InstrumentId(1): 0.3, InstrumentId(2): 0.2},
                cash_target=0.5,
            ),
            strategy_version="1",
            account_id="paper-a",
            sleeve_id=f"manual-paper-a-{STRATEGY_ID}",
            sizing_contexts={},
            decision_date=SIGNAL_DATE,
            intended_trade_date="2026-02-02",
            required_datasets=(),
            required_dataset_states=(),
            risk_flags=risk_flags,
        )
    )


def _run_service(pool: SQLitePool) -> StrategyRunLifecycleStore:
    writer = SQLiteStrategyRunWriter(pool)
    writer.init_schema()
    return StrategyRunLifecycleStore(
        reader=SQLiteStrategyRunReader(pool),
        writer=writer,
    )


def _coordinator(
    publisher: SignalPackagePublisher,
    run_service: StrategyRunLifecycleStore,
    risk_flags: list[str],
) -> EodCoordinator:
    return EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: _publish(
            publisher,
            tuple(risk_flags),
        ),
        finalize_signals=publisher.finalize,
        find_staged_signals=lambda request, date, batch: publisher.find_staged(
            strategy_id=request.strategy_id,
            run_id=batch,
            signal_date=date,
        ),
        run_service=run_service,
    )


def _run_eod(coordinator: EodCoordinator):
    return coordinator.run(
        signal_date=SIGNAL_DATE,
        strategies=(EodStrategyRequest(STRATEGY_ID, "1", ()),),
        dataset_states={},
    )[0]


@pytest.mark.integration
def test_completed_active_retry_noops_and_safe_change_replaces(
    tmp_path: Path,
) -> None:
    pool, trade, artifacts = _stores(tmp_path)
    try:
        publisher = _publisher(trade, artifacts)
        risk_flags: list[str] = []
        run_service = _run_service(pool)
        coordinator = _coordinator(publisher, run_service, risk_flags)

        first = _run_eod(coordinator)
        retry = _run_eod(coordinator)

        assert first.status == "completed"
        assert retry.status == "completed"
        assert retry.artifact_id == first.artifact_id
        assert len(trade.list_intents(STRATEGY_ID, signal_date=SIGNAL_DATE)) == 2
        assert len(artifacts.list_by_strategy(STRATEGY_ID)) == 1

        risk_flags.append("changed")
        replacement = _run_eod(coordinator)

        assert replacement.status == "completed"
        assert replacement.artifact_id != first.artifact_id
        rows = artifacts.list_by_strategy(STRATEGY_ID)
        assert [row.artifact_id for row in rows if row.status == "active"] == [
            replacement.artifact_id
        ]
        original = artifacts.get_artifact(first.artifact_id or "")
        assert original is not None
        assert original.status == "archived"
        intents = trade.list_intents(STRATEGY_ID, signal_date=SIGNAL_DATE)
        assert len(intents) == 4
        original_ids = {
            item["intent_id"]
            for item in original.metadata["intents"]
            if isinstance(item, dict)
        }
        assert all(
            intent.status == "superseded"
            for intent in intents
            if intent.intent_id in original_ids
        )
        run = run_service.get_run(BATCH_KEY)
        assert run is not None
        assert run.status == "completed"
    finally:
        pool.close_all()


@pytest.mark.integration
def test_completed_active_changed_input_with_fill_returns_conflict(
    tmp_path: Path,
) -> None:
    pool, trade, artifacts = _stores(tmp_path)
    try:
        publisher = _publisher(trade, artifacts)
        risk_flags: list[str] = []
        coordinator = _coordinator(publisher, _run_service(pool), risk_flags)
        first = _run_eod(coordinator)
        first_intent = trade.list_intents(
            STRATEGY_ID,
            signal_date=SIGNAL_DATE,
        )[0]
        trade.save_fill(
            FillRecord(
                fill_id="manual-fill",
                intent_id=first_intent.intent_id,
                strategy_id=STRATEGY_ID,
                trade_date="2026-02-02",
                instrument_id=first_intent.instrument_id,
                direction=first_intent.direction,
                quantity=100,
                fill_price=10.0,
                fee=1.0,
            )
        )

        risk_flags.append("changed-after-fill")
        conflict = _run_eod(coordinator)

        assert conflict.status == "rerun_conflict"
        active = [
            row
            for row in artifacts.list_by_strategy(STRATEGY_ID)
            if row.status == "active"
        ]
        assert [row.artifact_id for row in active] == [first.artifact_id]
        assert any(
            row.status == "conflict" for row in artifacts.list_by_strategy(STRATEGY_ID)
        )
    finally:
        pool.close_all()


@pytest.mark.integration
def test_sqlite_activation_failure_keeps_active_and_retry_converges(
    tmp_path: Path,
) -> None:
    pool, trade, artifacts = _stores(tmp_path)
    try:
        initial_publisher = _publisher(trade, artifacts)
        first = initial_publisher.finalize(_publish(initial_publisher))
        failing = _FailOnceArtifactService(
            SQLiteStrategyArtifactReader(pool),
            SQLiteStrategyArtifactWriter(pool),
        )
        failing.fail_replacement = True

        failing_publisher = _publisher(trade, failing)
        staged = _publish(failing_publisher, ("changed",))

        with pytest.raises(RuntimeError, match="injected SQLite"):
            failing_publisher.finalize(staged)

        after_failure = artifacts.list_by_strategy(STRATEGY_ID)
        assert [row.artifact_id for row in after_failure if row.status == "active"] == [
            first.artifact_id
        ]

        retry_publisher = _publisher(trade, artifacts)
        replacement = retry_publisher.find_staged(
            strategy_id=STRATEGY_ID,
            run_id=BATCH_KEY,
            signal_date=SIGNAL_DATE,
        )
        assert replacement is not None
        replacement = retry_publisher.finalize(replacement)

        persisted = artifacts.list_by_strategy(STRATEGY_ID)
        active = [row for row in persisted if row.status == "active"]
        assert [row.artifact_id for row in active] == [replacement.artifact_id]
        assert verify_signal_package_metadata(active[0].metadata)
        original = artifacts.get_artifact(first.artifact_id)
        assert original is not None
        assert original.status == "archived"
        assert len(trade.list_intents(STRATEGY_ID, signal_date=SIGNAL_DATE)) == 4
    finally:
        pool.close_all()


@pytest.mark.integration
def test_concurrent_changed_inputs_publish_one_active_and_fail_closed(
    tmp_path: Path,
) -> None:
    pool, trade, artifacts = _stores(tmp_path)
    try:
        initial_publisher = _publisher(trade, artifacts)
        first = initial_publisher.finalize(_publish(initial_publisher))

        with ThreadPoolExecutor(max_workers=2) as executor:
            staged = list(
                executor.map(
                    lambda flag: _publish(
                        _publisher(trade, artifacts),
                        (flag,),
                    ),
                    ("candidate-a", "candidate-b"),
                )
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda package: _publisher(trade, artifacts).finalize(package),
                    staged,
                )
            )

        persisted = artifacts.list_by_strategy(STRATEGY_ID)
        active = [row for row in persisted if row.status == "active"]
        assert len(active) == 1
        assert active[0].artifact_id != first.artifact_id
        assert sorted(result.outcome for result in results) == [
            "completed",
            "rerun_conflict",
        ]
        original = artifacts.get_artifact(first.artifact_id)
        assert original is not None
        assert original.status == "archived"
        conflict = next(row for row in persisted if row.status == "conflict")
        candidate_id = conflict.metadata["candidate_artifact_id"]
        assert isinstance(candidate_id, str)
        losing_candidate = artifacts.get_artifact(candidate_id)
        assert losing_candidate is not None
        assert losing_candidate.status == "archived"
        raw_intents = losing_candidate.metadata["intents"]
        assert isinstance(raw_intents, list)
        losing_intent_ids = {
            item["intent_id"]
            for item in raw_intents
            if isinstance(item, dict) and isinstance(item.get("intent_id"), str)
        }
        assert losing_intent_ids
        for intent_id in losing_intent_ids:
            intent = trade.get_intent(intent_id)
            assert intent is not None
            assert intent.status == "superseded"
    finally:
        pool.close_all()
