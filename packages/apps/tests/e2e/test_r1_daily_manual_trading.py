"""R1 daily manual-trading deterministic acceptance.

This suite uses real SQLite stores and production application services.  Market
facts and the strategy target are deterministic fixtures; no supplier or
network access is allowed here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_application.builders import StrategyRuntimeBuilder, StrategyServiceFactory
from ditto_application.commands.account import (
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
    PositionBaselineInput,
)
from ditto_application.commands.strategy import (
    CreateStrategyCommand,
    CreateStrategyHandler,
    PublishStrategyCommand,
    PublishStrategyHandler,
)
from ditto_application.commands.trade import (
    RecordFillCommand,
    RecordFillHandler,
    ReplaceFillCommand,
    ReplaceFillHandler,
    VoidFillCommand,
    VoidFillHandler,
)
from ditto_application.eod_request import eod_request_from_strategy_spec
from ditto_application.processes.execution.eod_coordinator import (
    DatasetReadiness,
    EodCoordinator,
    EodStrategyOutcome,
    EodStrategyRequest,
)
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContextBuilder,
    ManualSizingService,
)
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.processes.execution.position_reader import StoredPositionReader
from ditto_application.processes.execution.signal_package import (
    SignalPackage,
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_application.processes.execution.strategy_run_process import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunServiceConfig,
)
from ditto_application.processes.strategy.seed_bootstrap import (
    SeedBootstrapResult,
    SeedBootstrapStatus,
    SeedStrategyBootstrap,
)
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.daily_decision import (
    DailyDecisionQueryFacade,
    DailyDecisionV2Report,
)
from ditto_application.queries.deviation import SignalDeviationQueryFacade
from ditto_application.queries.opening_baseline import OpeningBaselineResolver
from ditto_application.queries.portfolio_actual import PortfolioActualQueryFacade
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_backtest.data_feed import Slice
from ditto_execution.audit.execution_audit_service import ExecutionAuditService
from ditto_execution.models import FillRecord, SignalRecord
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
from ditto_kernel.trading import MarketSnapshot
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_platform.foundation.storage.sqlite_backup import (
    backup_database,
    inspect_database,
    restore_database,
)
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
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
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)

STRATEGY_ID = "seed_stock_selection_rotation"
ACCOUNT_ID = "r1-paper"
SIGNAL_DATE = "2026-07-10"
INTENDED_TRADE_DATE = "2026-07-13"
INSTRUMENT_ID = 600519
REFERENCE_PRICE = 10.0


@dataclass(frozen=True)
class _SeedCreateAdapter:
    handler: CreateStrategyHandler

    def create(
        self,
        *,
        strategy_id: str,
        name: str,
        spec_json: dict[str, object],
        tags: tuple[str, ...],
    ) -> int:
        return self.handler.handle(
            CreateStrategyCommand(
                strategy_id=strategy_id,
                name=name,
                spec_json=spec_json,
                tags=tags,
            )
        ).version


@dataclass(frozen=True)
class _SeedPublishAdapter:
    handler: PublishStrategyHandler

    def publish(self, *, strategy_id: str, version: int) -> None:
        published = self.handler.handle(
            PublishStrategyCommand(strategy_id=strategy_id, version=version)
        )
        if not published:
            raise RuntimeError("seed publish did not update the strategy catalog")


class _DeterministicMarketReader:
    """Exact D-close fixture implementing the application market query port."""

    def find_bars(
        self,
        *,
        instrument_ids: list[int] | None = None,
        start: str | None = None,
        end: str | None = None,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        del allow_experimental_data
        if (
            instrument_ids is None
            or INSTRUMENT_ID not in instrument_ids
            or start != SIGNAL_DATE
            or end != SIGNAL_DATE
        ):
            return pl.DataFrame()
        return pl.DataFrame(
            {
                "instrument_id": [INSTRUMENT_ID],
                "trade_date": [SIGNAL_DATE],
                "close": [REFERENCE_PRICE],
                "volume": [1_000_000.0],
                "amount": [10_000_000.0],
                "is_suspended": [False],
                "is_limit_up": [False],
                "is_limit_down": [False],
            }
        )


@dataclass
class _R1Harness:
    database: Path
    pool: SQLitePool
    trade: TradeService
    catalog: StrategyCatalogService
    artifacts: StrategyArtifactService
    runs: StrategyRunLifecycleStore
    account_query: AccountBaselineQuery
    sizing_builder: ManualSizingContextBuilder
    publisher: SignalPackagePublisher

    def opening_baseline_resolver(self) -> OpeningBaselineResolver:
        return OpeningBaselineResolver(
            account_query=self.account_query,
            package_reader=self.artifacts,
        )

    def bootstrap(self) -> tuple[SeedBootstrapResult, ...]:
        return SeedStrategyBootstrap(
            catalog=self.catalog,
            create_port=_SeedCreateAdapter(CreateStrategyHandler(self.catalog)),
            publish_port=_SeedPublishAdapter(PublishStrategyHandler(self.catalog)),
        ).run()

    def published_seed(self) -> StrategySpecRecord:
        record = self.catalog.get_latest_published(STRATEGY_ID)
        if record is None:
            raise AssertionError("designated R1 seed was not published")
        return record

    def import_baseline(self, *, current_weight: float = 0.0) -> str:
        market_value = 100_000.0 * current_weight
        quantity = int(market_value / REFERENCE_PRICE)
        positions = (
            (
                PositionBaselineInput(
                    instrument_id=INSTRUMENT_ID,
                    quantity=quantity,
                    available_quantity=quantity,
                    average_cost=REFERENCE_PRICE,
                    market_value=market_value,
                ),
            )
            if quantity
            else ()
        )
        result = ImportAccountBaselineHandler(
            account_port=self.trade,
            position_port=self.trade,
        ).handle(
            ImportAccountBaselineCommand(
                account_id=ACCOUNT_ID,
                strategy_id=STRATEGY_ID,
                snapshot_date=SIGNAL_DATE,
                cash_available=100_000.0 - market_value,
                cash_settled=100_000.0 - market_value,
                cash_frozen=0.0,
                total_value=100_000.0,
                nav=1.0,
                positions=positions,
            )
        )
        return result.snapshot_id

    def run_eod(
        self,
        *,
        target_weight: float,
        risk_flags: tuple[str, ...] = (),
        finalize: Callable[[SignalPackage], SignalPackage] | None = None,
        run_strategy: Callable[[EodStrategyRequest, str, str], object] | None = None,
    ) -> EodStrategyOutcome:
        seed = self.published_seed()
        request = eod_request_from_strategy_spec(seed)
        target = TargetPortfolio(
            trade_date=SIGNAL_DATE,
            strategy_id=STRATEGY_ID,
            run_id=f"eod-{SIGNAL_DATE}-{STRATEGY_ID}-{seed.version}",
            positions={InstrumentId(INSTRUMENT_ID): target_weight},
            cash_target=1.0 - target_weight,
        )
        dataset_states = _ready_dataset_states(request)

        def publish_signals(
            raw_target: object,
            snapshots: Mapping[str, str],
        ) -> SignalPackage:
            sizing = self.sizing_builder.build(
                account_id=ACCOUNT_ID,
                strategy_id=STRATEGY_ID,
                signal_date=SIGNAL_DATE,
                instrument_ids=(INSTRUMENT_ID,),
            )
            return self.publisher.publish(
                SignalPackagePublishRequest(
                    target=cast(TargetPortfolio, raw_target),
                    strategy_version=str(seed.version),
                    account_id=sizing.account_id,
                    sleeve_id=sizing.sleeve_id,
                    sizing_contexts=sizing.contexts,
                    decision_date=SIGNAL_DATE,
                    intended_trade_date=INTENDED_TRADE_DATE,
                    required_datasets=request.required_datasets,
                    required_dataset_states=tuple(
                        asdict(dataset_states[dataset])
                        for dataset in request.required_datasets
                    ),
                    dataset_snapshot_ids=dict(snapshots),
                    factor_ids=SEED_STRATEGY_SPECS[STRATEGY_ID].signal_expressions,
                    factor_values={
                        INSTRUMENT_ID: {
                            factor_id: float(index)
                            for index, factor_id in enumerate(
                                SEED_STRATEGY_SPECS[STRATEGY_ID].signal_expressions,
                                start=1,
                            )
                        }
                    },
                    risk_flags=risk_flags,
                )
            )

        finalize_signals = finalize or self.publisher.finalize
        coordinator = EodCoordinator(
            run_strategy=(
                run_strategy
                if run_strategy is not None
                else lambda selected, date, batch: target
            ),
            publish_signals=publish_signals,
            finalize_signals=finalize_signals,
            find_staged_signals=lambda selected, date, batch: (
                self.publisher.find_staged(
                    strategy_id=selected.strategy_id,
                    run_id=batch,
                    signal_date=date,
                )
            ),
            run_service=self.runs,
        )
        return coordinator.run(
            signal_date=SIGNAL_DATE,
            strategies=(request,),
            dataset_states=dataset_states,
        )[0]

    def decision(self) -> DailyDecisionV2Report:
        portfolio = PortfolioActualQueryFacade(
            fill_port=self.trade,
            position_port=self.trade,
        )
        return DailyDecisionQueryFacade(
            signal_facade=SignalQueryFacade(self.trade),
            portfolio_facade=portfolio,
            deviation_facade=SignalDeviationQueryFacade(
                intent_port=self.trade,
                fill_port=self.trade,
                position_port=self.trade,
            ),
            package_reader=self.artifacts,
            account_query=self.account_query,
            strategy_query=StrategyQueryFacade(self.catalog),
            run_reader=self.runs,
        ).get_report_v2(
            strategy_id=STRATEGY_ID,
            trade_date=SIGNAL_DATE,
            account_id=ACCOUNT_ID,
        )


def _ready_dataset_states(
    request: EodStrategyRequest,
) -> dict[str, DatasetReadiness]:
    return {
        dataset: DatasetReadiness(
            dataset=dataset,
            status="ready",
            snapshot_id=(
                "sha256:" + sha256(f"{dataset}:{SIGNAL_DATE}".encode()).hexdigest()
            ),
        )
        for dataset in request.required_datasets
    }


def _trade_service(pool: SQLitePool) -> TradeService:
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
    audit = ExecutionAuditService(pool)
    audit.init_schema()
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
        audit_service=audit,
    )


def _harness(database: Path) -> _R1Harness:
    pool = SQLitePool(str(database))
    trade = _trade_service(pool)

    spec_writer = SQLiteStrategySpecWriter(pool)
    spec_writer.init_schema()
    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(pool),
        writer=spec_writer,
    )

    artifact_writer = SQLiteStrategyArtifactWriter(pool)
    artifact_writer.init_schema()
    artifacts = StrategyArtifactService(
        reader=SQLiteStrategyArtifactReader(pool),
        writer=artifact_writer,
    )

    run_writer = SQLiteStrategyRunWriter(pool)
    run_writer.init_schema()
    runs = StrategyRunLifecycleStore(
        reader=SQLiteStrategyRunReader(pool),
        writer=run_writer,
    )

    account_query = AccountBaselineQuery(
        account_port=trade,
        position_port=trade,
    )
    sizing_builder = ManualSizingContextBuilder(
        account_query=account_query,
        market_query=_DeterministicMarketReader(),
    )
    resolver = AShareTradeDateResolver(trading_days=(SIGNAL_DATE, INTENDED_TRADE_DATE))
    publisher = SignalPackagePublisher(
        snapshot_process=SignalSnapshotProcess(
            position_reader=StoredPositionReader(trade),
            sizing_service=ManualSizingService(),
        ),
        intent_port=trade,
        fill_port=trade,
        date_resolver=resolver,
        artifact_service=artifacts,
    )
    return _R1Harness(
        database=database,
        pool=pool,
        trade=trade,
        catalog=catalog,
        artifacts=artifacts,
        runs=runs,
        account_query=account_query,
        sizing_builder=sizing_builder,
        publisher=publisher,
    )


@pytest.fixture
def r1_harness(tmp_path: Path) -> Iterator[_R1Harness]:
    harness = _harness(tmp_path / "r1-control-plane.sqlite")
    try:
        yield harness
    finally:
        harness.pool.close_all()


@pytest.mark.e2e
@pytest.mark.integration
def test_builtin_seed_baseline_eod_package_decision_and_identical_rerun(
    r1_harness: _R1Harness,
) -> None:
    first_bootstrap = r1_harness.bootstrap()
    second_bootstrap = r1_harness.bootstrap()
    baseline_id = r1_harness.import_baseline()

    first = r1_harness.run_eod(target_weight=0.4)
    retry = r1_harness.run_eod(target_weight=0.4)
    decision = r1_harness.decision()

    designated = next(
        result for result in first_bootstrap if result.strategy_id == STRATEGY_ID
    )
    replayed = next(
        result for result in second_bootstrap if result.strategy_id == STRATEGY_ID
    )
    assert designated.status == SeedBootstrapStatus.PUBLISHED
    assert replayed.status == SeedBootstrapStatus.UNCHANGED
    assert r1_harness.published_seed().spec_json == orjson.loads(
        orjson.dumps(asdict(SEED_STRATEGY_SPECS[STRATEGY_ID]))
    )
    assert baseline_id
    assert first.status == "completed"
    assert retry.status == "completed"
    assert retry.artifact_id == first.artifact_id
    assert retry.checksum == first.checksum
    intents = r1_harness.trade.list_intents(STRATEGY_ID, signal_date=SIGNAL_DATE)
    assert len(intents) == 1
    assert intents[0].quantity == 4000
    assert decision.identity["signal_date"] == SIGNAL_DATE
    assert decision.identity["intended_trade_date"] == INTENDED_TRADE_DATE
    assert decision.readiness["status"] == "ready"
    assert decision.readiness["reason_codes"] == ("READY_FOR_REVIEW",)
    assert decision.readiness["details"]
    assert decision.run_package["artifact_id"] == first.artifact_id
    assert decision.run_package["checksum"] == first.checksum
    assert decision.run_package["checksum_valid"] is True
    assert decision.data["required_datasets"] == tuple(
        sorted(SEED_STRATEGY_SPECS[STRATEGY_ID].required_datasets)
    )


@pytest.mark.e2e
@pytest.mark.integration
def test_catalog_backed_completed_rerun_reuses_signal_package_and_intents(
    r1_harness: _R1Harness,
) -> None:
    """Real SQLite replay includes the recommendation SIGNAL_SNAPSHOT write."""
    r1_harness.bootstrap()
    r1_harness.import_baseline()
    facade = StrategyFacade(
        factory=StrategyServiceFactory(
            audit_service=ExecutionAuditService(r1_harness.pool),
            artifact_service=r1_harness.artifacts,
            run_service=r1_harness.runs,
            runtime_builder=StrategyRuntimeBuilder(
                catalog_service=r1_harness.catalog,
            ),
        )
    )
    instrument_id = InstrumentId(INSTRUMENT_ID)
    slice_ = Slice(
        trade_date=SIGNAL_DATE,
        step_time=datetime(2026, 7, 10, 15, tzinfo=UTC),
        bars={
            instrument_id: MarketSnapshot(
                trade_date=SIGNAL_DATE,
                instrument_id=instrument_id,
                open=REFERENCE_PRICE,
                high=REFERENCE_PRICE,
                low=REFERENCE_PRICE,
                close=REFERENCE_PRICE,
                prev_close=REFERENCE_PRICE,
                volume=1_000_000.0,
                amount=10_000_000.0,
            )
        },
    )

    def run_catalog_strategy(
        request: EodStrategyRequest,
        signal_date: str,
        batch_key: str,
    ) -> object:
        return facade.run_strategy_from_catalog(
            config=StrategyRunServiceConfig(
                strategy_id=request.strategy_id,
                strategy_version=request.strategy_version,
                run_id=batch_key,
                mode=StrategyRunMode.RECOMMENDATION,
                manage_run_lifecycle=False,
            ),
            trade_date=signal_date,
            slice_=slice_,
            version=int(request.strategy_version),
        ).target

    first = r1_harness.run_eod(
        target_weight=0.1,
        run_strategy=run_catalog_strategy,
    )
    artifact_ids_before = tuple(
        sorted(
            artifact.artifact_id
            for artifact in r1_harness.artifacts.list_by_strategy(STRATEGY_ID)
        )
    )
    intent_ids_before = tuple(
        intent.intent_id
        for intent in r1_harness.trade.list_intents(
            STRATEGY_ID,
            signal_date=SIGNAL_DATE,
        )
    )

    retry = r1_harness.run_eod(
        target_weight=0.1,
        run_strategy=run_catalog_strategy,
    )
    artifact_ids_after = tuple(
        sorted(
            artifact.artifact_id
            for artifact in r1_harness.artifacts.list_by_strategy(STRATEGY_ID)
        )
    )
    intent_ids_after = tuple(
        intent.intent_id
        for intent in r1_harness.trade.list_intents(
            STRATEGY_ID,
            signal_date=SIGNAL_DATE,
        )
    )

    assert first.status == "completed"
    assert retry.status == "completed"
    assert retry.artifact_id == first.artifact_id
    assert retry.checksum == first.checksum
    assert artifact_ids_after == artifact_ids_before
    assert intent_ids_after == intent_ids_before
    assert len(artifact_ids_after) == 2  # signal snapshot + active signal package
    assert len(intent_ids_after) == 1


@pytest.mark.e2e
@pytest.mark.integration
def test_zero_rebalance_day_persists_a_reviewable_package(
    r1_harness: _R1Harness,
) -> None:
    r1_harness.bootstrap()
    r1_harness.import_baseline(current_weight=0.4)

    outcome = r1_harness.run_eod(target_weight=0.4)
    decision = r1_harness.decision()

    assert outcome.status == "no_rebalance", outcome
    assert outcome.artifact_id
    artifact = r1_harness.artifacts.get_artifact(outcome.artifact_id)
    assert artifact is not None
    assert artifact.status == "active"
    assert artifact.metadata["no_rebalance"] is True
    assert artifact.metadata["intents"] == []
    assert (
        r1_harness.trade.list_intents(
            STRATEGY_ID,
            signal_date=SIGNAL_DATE,
        )
        == []
    )
    assert decision.readiness["status"] == "review"
    assert decision.readiness["reason_codes"] == ("NO_REBALANCE_REQUIRED",)
    assert decision.run_package["no_rebalance"] is True
    assert decision.run_package["checksum_valid"] is True


@pytest.mark.e2e
@pytest.mark.integration
def test_changed_same_day_input_after_a_fill_fails_closed_as_conflict(
    r1_harness: _R1Harness,
) -> None:
    r1_harness.bootstrap()
    r1_harness.import_baseline()
    first = r1_harness.run_eod(target_weight=0.4)
    intent = r1_harness.trade.list_intents(
        STRATEGY_ID,
        signal_date=SIGNAL_DATE,
    )[0]
    r1_harness.trade.save_fill(
        FillRecord(
            fill_id="r1-existing-fill",
            intent_id=intent.intent_id,
            strategy_id=STRATEGY_ID,
            trade_date=INTENDED_TRADE_DATE,
            instrument_id=intent.instrument_id,
            direction=intent.direction,
            quantity=100,
            fill_price=REFERENCE_PRICE,
            fee=1.0,
        )
    )

    conflict = r1_harness.run_eod(target_weight=0.5)
    decision = r1_harness.decision()

    assert first.status == "completed"
    assert conflict.status == "rerun_conflict"
    assert conflict.artifact_id != first.artifact_id
    active = [
        artifact
        for artifact in r1_harness.artifacts.list_by_strategy(STRATEGY_ID)
        if artifact.status == "active"
    ]
    assert [artifact.artifact_id for artifact in active] == [first.artifact_id]
    assert decision.readiness["status"] == "review"
    assert "RERUN_CONFLICT" in decision.readiness["reason_codes"]
    assert decision.run_package["artifact_id"] == first.artifact_id
    assert decision.run_package["conflict_artifact_id"] == conflict.artifact_id


def _record_task6_partial_fill_stage(
    harness: _R1Harness,
    intent: SignalRecord,
    tracker: ManualTracker,
) -> None:
    """Record and assert two independent partials for one intent and date."""
    record_fill = RecordFillHandler(
        intent_port=harness.trade,
        fill_port=harness.trade,
        position_port=harness.trade,
        manual_tracker=tracker,
        opening_baseline_resolver=harness.opening_baseline_resolver(),
    )
    for fill_id, quantity, fill_price, fee in (
        ("task6-partial-1", 1_000, 10.0, 1.0),
        ("task6-partial-2", 500, 11.0, 2.0),
    ):
        record_fill.handle(
            RecordFillCommand(
                fill_id=fill_id,
                intent_id=intent.intent_id,
                strategy_id=STRATEGY_ID,
                trade_date=INTENDED_TRADE_DATE,
                instrument_id=intent.instrument_id,
                direction=intent.direction,
                quantity=quantity,
                fill_price=fill_price,
                fee=fee,
            )
        )

    partial_intent = harness.trade.get_intent(intent.intent_id)
    raw_ids = {
        fill.fill_id
        for fill in harness.trade.list_fills(
            STRATEGY_ID,
            trade_date=INTENDED_TRADE_DATE,
            intent_id=intent.intent_id,
        )
    }
    effective_ids = {
        fill.fill_id
        for fill in harness.trade.list_effective_fills(
            STRATEGY_ID,
            trade_date=INTENDED_TRADE_DATE,
            intent_id=intent.intent_id,
        )
    }
    assert partial_intent is not None
    assert partial_intent.status == "partially_filled"
    assert raw_ids == {"task6-partial-1", "task6-partial-2"}
    assert effective_ids == raw_ids


def _assert_task6_replace_stage(
    harness: _R1Harness,
    intent: SignalRecord,
    tracker: ManualTracker,
) -> None:
    """Replace the first partial and preserve both raw rows plus evidence."""
    ReplaceFillHandler(
        harness.trade,
        harness.trade,
        harness.trade,
        tracker,
        harness.opening_baseline_resolver(),
    ).handle(
        ReplaceFillCommand(
            adjustment_id="task6-adjust-replace",
            fill_id="task6-partial-1",
            replacement_fill_id="task6-partial-1-corrected",
            trade_date=INTENDED_TRADE_DATE,
            quantity=750,
            fill_price=12.0,
            fee=3.0,
            reason="correct broker quantity and price",
        )
    )

    raw_after_replace = {
        fill.fill_id: fill
        for fill in harness.trade.list_fills(
            STRATEGY_ID,
            trade_date=INTENDED_TRADE_DATE,
            intent_id=intent.intent_id,
        )
    }
    effective_after_replace = {
        fill.fill_id: fill
        for fill in harness.trade.list_effective_fills(
            STRATEGY_ID,
            trade_date=INTENDED_TRADE_DATE,
            intent_id=intent.intent_id,
        )
    }
    adjustments_after_replace = harness.trade.list_fill_adjustments(
        STRATEGY_ID,
        intent_id=intent.intent_id,
    )
    assert set(raw_after_replace) == {
        "task6-partial-1",
        "task6-partial-2",
        "task6-partial-1-corrected",
    }
    assert set(effective_after_replace) == {
        "task6-partial-2",
        "task6-partial-1-corrected",
    }
    assert [adjustment.adjustment_id for adjustment in adjustments_after_replace] == [
        "task6-adjust-replace"
    ]
    assert adjustments_after_replace[0].replacement_fill_id == (
        "task6-partial-1-corrected"
    )


def _assert_task6_void_ledger_stage(
    harness: _R1Harness,
    intent: SignalRecord,
    tracker: ManualTracker,
) -> PortfolioActualQueryFacade:
    """Void the second partial and assert raw/effective/adjustment history."""
    VoidFillHandler(
        harness.trade,
        harness.trade,
        harness.trade,
        tracker,
        harness.opening_baseline_resolver(),
    ).handle(
        VoidFillCommand(
            adjustment_id="task6-adjust-void",
            fill_id="task6-partial-2",
            reason="duplicate broker confirmation",
        )
    )

    portfolio = PortfolioActualQueryFacade(
        fill_port=harness.trade,
        position_port=harness.trade,
    )
    raw_fills = {
        fill.fill_id: fill
        for fill in portfolio.get_fills(
            STRATEGY_ID,
            start_date=INTENDED_TRADE_DATE,
            end_date=INTENDED_TRADE_DATE,
        )
    }
    effective_fills = {
        fill.fill_id: fill
        for fill in portfolio.get_effective_fills(
            STRATEGY_ID,
            start_date=INTENDED_TRADE_DATE,
            end_date=INTENDED_TRADE_DATE,
        )
    }
    adjustments = {
        adjustment.adjustment_id: adjustment
        for adjustment in portfolio.get_fill_adjustments(
            STRATEGY_ID,
            intent_id=intent.intent_id,
        )
    }
    assert set(raw_fills) == {
        "task6-partial-1",
        "task6-partial-2",
        "task6-partial-1-corrected",
    }
    assert {fill.intent_id for fill in raw_fills.values()} == {intent.intent_id}
    assert set(effective_fills) == {"task6-partial-1-corrected"}
    assert effective_fills["task6-partial-1-corrected"].quantity == 750
    assert effective_fills["task6-partial-1-corrected"].fill_price == 12.0
    assert set(adjustments) == {"task6-adjust-replace", "task6-adjust-void"}
    assert adjustments["task6-adjust-replace"].adjustment_type == "replace"
    assert adjustments["task6-adjust-void"].adjustment_type == "void"
    return portfolio


def _task6_ledger_ids(
    harness: _R1Harness,
    intent_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return raw, effective and adjustment identities for restore comparison."""
    raw = tuple(
        fill.fill_id
        for fill in harness.trade.list_fills(
            STRATEGY_ID,
            trade_date=INTENDED_TRADE_DATE,
            intent_id=intent_id,
        )
    )
    effective = tuple(
        fill.fill_id
        for fill in harness.trade.list_effective_fills(
            STRATEGY_ID,
            trade_date=INTENDED_TRADE_DATE,
            intent_id=intent_id,
        )
    )
    adjustments = tuple(
        adjustment.adjustment_id
        for adjustment in harness.trade.list_fill_adjustments(
            STRATEGY_ID,
            intent_id=intent_id,
        )
    )
    return raw, effective, adjustments


def _assert_restored_task6_ledger(
    source: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    restored: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
) -> None:
    """Assert backup/restore preserves immutable and effective ledger identity."""
    assert restored == source
    raw, effective, adjustments = restored
    assert set(raw) == {
        "task6-partial-1",
        "task6-partial-2",
        "task6-partial-1-corrected",
    }
    assert effective == ("task6-partial-1-corrected",)
    assert set(adjustments) == {
        "task6-adjust-replace",
        "task6-adjust-void",
    }


def _assert_task6_effective_read_models(
    harness: _R1Harness,
    intent: SignalRecord,
    portfolio: PortfolioActualQueryFacade,
) -> None:
    """Assert every derived read model is rebuilt from the effective fill set."""
    corrected_intent = harness.trade.get_intent(intent.intent_id)
    positions = portfolio.get_position_history(
        STRATEGY_ID,
        snapshot_date=INTENDED_TRADE_DATE,
    )
    deviation = SignalDeviationQueryFacade(
        intent_port=harness.trade,
        fill_port=harness.trade,
        position_port=harness.trade,
    ).get_deviation(
        strategy_id=STRATEGY_ID,
        signal_date=SIGNAL_DATE,
        execution_date=INTENDED_TRADE_DATE,
        intent_ids=(intent.intent_id,),
    )
    pnl = portfolio.compute_pnl(STRATEGY_ID, INTENDED_TRADE_DATE)
    decision = harness.decision()

    assert corrected_intent is not None
    assert corrected_intent.status == "partially_filled"
    assert len(positions) == 1
    assert positions[0].quantity == 750
    assert positions[0].average_cost == pytest.approx(12.0)
    assert positions[0].total_fees == pytest.approx(3.0)
    assert deviation.filled == 1
    assert deviation.unfilled == 0
    assert deviation.items[0].fill_status == "filled"
    assert deviation.items[0].actual_weight == pytest.approx(1.0)
    assert pnl.total_realized_pnl == pytest.approx(0.0)
    assert pnl.total_unrealized_pnl == pytest.approx(0.0)
    assert pnl.total_fees == pytest.approx(3.0)
    assert pnl.net_pnl == pytest.approx(-3.0)

    assert len(decision.actions) == 1
    assert decision.actions[0]["intent_status"] == "partially_filled"
    assert decision.actions[0]["filled_quantity"] == 750
    assert decision.actions[0]["remaining_quantity"] == 3_250
    decision_fills = decision.execution_review["effective_fills"]
    assert isinstance(decision_fills, tuple)
    assert [fill.fill_id for fill in decision_fills] == ["task6-partial-1-corrected"]
    assert decision.execution_review["deviation"] == deviation
    assert decision.execution_review["pnl"] == pnl


@pytest.mark.e2e
@pytest.mark.integration
def test_task6_partial_fill_corrections_project_only_effective_ledger_facts(
    r1_harness: _R1Harness,
) -> None:
    """Two same-day partials remain auditable while all projections use corrections."""
    r1_harness.bootstrap()
    r1_harness.import_baseline()
    outcome = r1_harness.run_eod(target_weight=0.4)
    intent = r1_harness.trade.list_intents(
        STRATEGY_ID,
        signal_date=SIGNAL_DATE,
    )[0]
    tracker = ManualTracker(
        trading_calendar=(SIGNAL_DATE, INTENDED_TRADE_DATE, "2026-07-14")
    )

    assert outcome.status == "completed"
    assert intent.quantity == 4_000
    _record_task6_partial_fill_stage(r1_harness, intent, tracker)
    _assert_task6_replace_stage(r1_harness, intent, tracker)
    portfolio = _assert_task6_void_ledger_stage(r1_harness, intent, tracker)
    _assert_task6_effective_read_models(r1_harness, intent, portfolio)


@pytest.mark.e2e
@pytest.mark.integration
def test_rerun_recovers_a_durable_package_after_finalize_interruption(
    r1_harness: _R1Harness,
) -> None:
    r1_harness.bootstrap()
    r1_harness.import_baseline()
    interrupted = False

    def interrupt_once(package: SignalPackage) -> SignalPackage:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise RuntimeError("simulated process interruption after durable stage")
        return r1_harness.publisher.finalize(package)

    failed = r1_harness.run_eod(
        target_weight=0.4,
        finalize=interrupt_once,
    )
    staged = [
        artifact
        for artifact in r1_harness.artifacts.list_by_strategy(STRATEGY_ID)
        if artifact.status == "staged"
    ]
    recovered = r1_harness.run_eod(target_weight=0.4)

    assert failed.status == "failed"
    assert failed.reason == "SIGNAL_PACKAGE_FINALIZE_FAILED"
    assert len(staged) == 1
    assert recovered.status == "completed"
    assert recovered.artifact_id == staged[0].artifact_id
    assert recovered.checksum == failed.checksum
    active = [
        artifact
        for artifact in r1_harness.artifacts.list_by_strategy(STRATEGY_ID)
        if artifact.status == "active"
    ]
    assert [artifact.artifact_id for artifact in active] == [recovered.artifact_id]
    assert len(r1_harness.trade.list_intents(STRATEGY_ID, signal_date=SIGNAL_DATE)) == 1


@pytest.mark.e2e
@pytest.mark.integration
def test_online_backup_restore_preserves_the_queryable_r1_decision(
    r1_harness: _R1Harness,
    tmp_path: Path,
) -> None:
    r1_harness.bootstrap()
    baseline_id = r1_harness.import_baseline()
    outcome = r1_harness.run_eod(target_weight=0.4)
    intent = r1_harness.trade.list_intents(
        STRATEGY_ID,
        signal_date=SIGNAL_DATE,
    )[0]
    tracker = ManualTracker(
        trading_calendar=(SIGNAL_DATE, INTENDED_TRADE_DATE, "2026-07-14")
    )
    _record_task6_partial_fill_stage(r1_harness, intent, tracker)
    _assert_task6_replace_stage(r1_harness, intent, tracker)
    _assert_task6_void_ledger_stage(r1_harness, intent, tracker)
    source_decision = r1_harness.decision()
    source_ledger_ids = _task6_ledger_ids(r1_harness, intent.intent_id)
    source_intent_ids = [
        intent.intent_id
        for intent in r1_harness.trade.list_intents(
            STRATEGY_ID,
            signal_date=SIGNAL_DATE,
        )
    ]
    source_report = inspect_database(r1_harness.database)
    backup = tmp_path / "evidence" / "r1-backup.sqlite"
    restored_database = tmp_path / "restore-root" / "r1-restored.sqlite"

    backup_report = backup_database(r1_harness.database, backup)
    restore_report = restore_database(backup, restored_database)
    restored_report = inspect_database(restored_database)
    restored = _harness(restored_database)
    try:
        restored_decision = restored.decision()
        restored_baseline = restored.account_query.get_latest(
            account_id=ACCOUNT_ID,
            strategy_id=STRATEGY_ID,
            signal_date=SIGNAL_DATE,
        )
        restored_intent_ids = [
            intent.intent_id
            for intent in restored.trade.list_intents(
                STRATEGY_ID,
                signal_date=SIGNAL_DATE,
            )
        ]
        restored_ledger_ids = _task6_ledger_ids(restored, intent.intent_id)
        restored_run = restored.runs.get_run(f"eod-{SIGNAL_DATE}-{STRATEGY_ID}-1")

        assert source_report.integrity_check == "ok"
        assert backup_report.integrity_check == "ok"
        assert restore_report.integrity_check == "ok"
        assert restored_report.integrity_check == "ok"
        assert backup_report.table_row_counts == source_report.table_row_counts
        assert restore_report.table_row_counts == backup_report.table_row_counts
        assert restored_report.table_row_counts == source_report.table_row_counts
        assert restored_baseline is not None
        assert restored_baseline.account.snapshot_id == baseline_id
        assert restored_intent_ids == source_intent_ids
        _assert_restored_task6_ledger(source_ledger_ids, restored_ledger_ids)
        assert restored_run is not None
        assert restored_run.status == "completed"
        assert restored_decision.identity == source_decision.identity
        assert restored_decision.readiness == source_decision.readiness
        assert restored_decision.run_package["artifact_id"] == outcome.artifact_id
        assert (
            restored_decision.run_package["checksum"]
            == source_decision.run_package["checksum"]
        )
        assert restored_decision.run_package["checksum_valid"] is True
    finally:
        restored.pool.close_all()
