"""EOD outcome 通过既有 strategy_run 控制面持久化的集成回归。"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
from unittest.mock import MagicMock

import orjson
from ditto_application.processes.execution.eod_coordinator import (
    DatasetReadiness,
    EodCoordinator,
    EodStrategyRequest,
)
from ditto_application.processes.execution.signal_package import SignalPackage
from ditto_platform.foundation import SQLitePool
from ditto_strategy.runs.models import StrategyRunRecord
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)
from ditto_strategy.storage.sqlite.strategy_run_store import (
    SQLiteStrategyRunReader,
    SQLiteStrategyRunWriter,
)


def _run_service(tmp_path: Path) -> tuple[SQLitePool, StrategyRunLifecycleStore]:
    pool = SQLitePool(str(tmp_path / "eod-outcomes.db"))
    writer = SQLiteStrategyRunWriter(pool)
    writer.init_schema()
    return pool, StrategyRunLifecycleStore(
        reader=SQLiteStrategyRunReader(pool),
        writer=writer,
    )


class _FirstCreateBarrierReader(SQLiteStrategyRunReader):
    """Hold both workers after create_run's initial missing-row observation."""

    def __init__(self, pool: SQLitePool, barrier: Barrier) -> None:
        super().__init__(pool)
        self._barrier = barrier
        self._read_count = 0

    def get(self, run_id: str) -> StrategyRunRecord | None:
        record = super().get(run_id)
        self._read_count += 1
        # EodCoordinator recovery performs read 1; create_run performs read 2.
        if self._read_count == 2:
            self._barrier.wait(timeout=5)
        return record


def test_blocked_outcome_is_queryable_with_required_dataset_evidence(
    tmp_path: Path,
) -> None:
    pool, run_service = _run_service(tmp_path)
    try:
        outcome = EodCoordinator(
            run_strategy=lambda request, date, batch: object(),
            publish_signals=lambda target, snapshots: SignalPackage(
                run_id="unused",
                strategy_id="unused",
                signal_date="2026-07-16",
                intents=(),
                dataset_snapshot_ids={},
                factor_ids=(),
                risk_flags=(),
                factor_values={},
                selection_reasons={},
                checksum="unused",
            ),
            finalize_signals=lambda package: package,
            find_staged_signals=lambda request, date, batch: None,
            run_service=run_service,
        ).run(
            signal_date="2026-07-16",
            strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
            dataset_states={
                "stock_daily": DatasetReadiness(
                    "stock_daily",
                    "dq_failed",
                    "sha256:stock",
                    "DQ_FAILED: null ratio",
                )
            },
        )[0]

        record = run_service.get_run(outcome.batch_key)

        assert record is not None
        assert record.status == "failed"
        assert record.error_message == "blocked:REQUIRED_DATA_NOT_READY"
        assert orjson.loads(record.config_json) == {
            "batch_key": outcome.batch_key,
            "outcome": "blocked",
            "required_dataset_states": [
                {
                    "dataset": "stock_daily",
                    "reason": "DQ_FAILED: null ratio",
                    "snapshot_id": "sha256:stock",
                    "status": "dq_failed",
                }
            ],
            "signal_date": "2026-07-16",
        }
    finally:
        pool.close()


def test_repeated_blocked_observation_refreshes_durable_dataset_evidence(
    tmp_path: Path,
) -> None:
    pool, run_service = _run_service(tmp_path)
    coordinator = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: SignalPackage(
            run_id="unused",
            strategy_id="unused",
            signal_date="2026-07-16",
            intents=(),
            dataset_snapshot_ids={},
            factor_ids=(),
            risk_flags=(),
            factor_values={},
            selection_reasons={},
            checksum="unused",
        ),
        finalize_signals=lambda package: package,
        find_staged_signals=lambda request, date, batch: None,
        run_service=run_service,
    )
    request = EodStrategyRequest("stock", "2", ("stock_daily",))
    try:
        first = coordinator.run(
            signal_date="2026-07-16",
            strategies=(request,),
            dataset_states={
                "stock_daily": DatasetReadiness(
                    "stock_daily",
                    "dq_failed",
                    "sha256:A",
                    "DQ_FAILED:A",
                )
            },
        )[0]
        second = coordinator.run(
            signal_date="2026-07-16",
            strategies=(request,),
            dataset_states={
                "stock_daily": DatasetReadiness(
                    "stock_daily",
                    "stale",
                    "sha256:B",
                    "STALE_DATASET:B",
                )
            },
        )[0]

        assert first.status == "blocked"
        assert second.status == "blocked"
        record = run_service.get_run(second.batch_key)
        assert record is not None
        assert record.status == "failed"
        assert record.error_message == "blocked:REQUIRED_DATA_NOT_READY"
        assert orjson.loads(record.config_json)["required_dataset_states"] == [
            {
                "dataset": "stock_daily",
                "reason": "STALE_DATASET:B",
                "snapshot_id": "sha256:B",
                "status": "stale",
            }
        ]
    finally:
        pool.close()


def test_publish_failure_is_queryable_as_failed_not_completed(tmp_path: Path) -> None:
    pool, run_service = _run_service(tmp_path)

    def fail_publish(target: object, snapshots: object) -> SignalPackage:
        raise RuntimeError("artifact store unavailable")

    try:
        outcome = EodCoordinator(
            run_strategy=lambda request, date, batch: object(),
            publish_signals=fail_publish,
            finalize_signals=lambda package: package,
            find_staged_signals=lambda request, date, batch: None,
            run_service=run_service,
        ).run(
            signal_date="2026-07-16",
            strategies=(EodStrategyRequest("etf", "1", ()),),
            dataset_states={},
        )[0]

        record = run_service.get_run(outcome.batch_key)

        assert outcome.status == "failed"
        assert record is not None
        assert record.status == "failed"
        assert record.error_message == "failed:SIGNAL_PACKAGE_PUBLISH_FAILED"
    finally:
        pool.close()


def test_blocked_terminal_run_retries_after_required_data_recovers(
    tmp_path: Path,
) -> None:
    pool, run_service = _run_service(tmp_path)
    batch_key = "eod-2026-07-16-etf-1"
    package = SignalPackage(
        run_id=batch_key,
        strategy_id="etf",
        signal_date="2026-07-16",
        intents=(),
        dataset_snapshot_ids={"etf_daily": "sha256:ready"},
        factor_ids=(),
        risk_flags=(),
        factor_values={},
        selection_reasons={},
        checksum="sha256:package",
        artifact_id="signal-package-etf",
        outcome="completed",
        no_rebalance=False,
    )
    coordinator = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: package,
        finalize_signals=lambda candidate: candidate,
        find_staged_signals=lambda request, date, batch: None,
        run_service=run_service,
    )
    try:
        blocked = coordinator.run(
            signal_date="2026-07-16",
            strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
            dataset_states={},
        )[0]
        recovered = coordinator.run(
            signal_date="2026-07-16",
            strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
            dataset_states={
                "etf_daily": DatasetReadiness(
                    "etf_daily",
                    "ready",
                    "sha256:ready",
                )
            },
        )[0]

        assert blocked.status == "blocked"
        assert recovered.status == "completed"
        record = run_service.get_run(batch_key)
        assert record is not None
        assert record.status == "completed"
        assert record.error_message == ""
        assert orjson.loads(record.config_json)["outcome"] == "running"
    finally:
        pool.close()


def test_preclaimed_running_batch_rejects_duplicate_without_mutating_owner(
    tmp_path: Path,
) -> None:
    """A concurrent loser must neither execute nor fail the winning run."""
    pool, run_service = _run_service(tmp_path)
    batch_key = "eod-2026-07-16-etf-1"
    run_strategy = MagicMock(return_value=object())
    package = SignalPackage(
        run_id=batch_key,
        strategy_id="etf",
        signal_date="2026-07-16",
        intents=(),
        dataset_snapshot_ids={},
        factor_ids=(),
        risk_flags=(),
        factor_values={},
        selection_reasons={},
        checksum="sha256:package",
        artifact_id="signal-package-etf",
        outcome="no_rebalance",
        no_rebalance=True,
    )
    try:
        run_service.create_run(
            run_id=batch_key,
            strategy_id="etf",
            strategy_version="1",
            mode="recommendation",
        )
        assert run_service.mark_running(batch_key)

        outcome = EodCoordinator(
            run_strategy=run_strategy,
            publish_signals=lambda target, snapshots: package,
            finalize_signals=lambda candidate: candidate,
            find_staged_signals=lambda request, date, batch: None,
            run_service=run_service,
        ).run(
            signal_date="2026-07-16",
            strategies=(EodStrategyRequest("etf", "1", ()),),
            dataset_states={},
        )[0]

        persisted = run_service.get_run(batch_key)
        assert outcome.status == "failed"
        assert outcome.reason == "RUN_LIFECYCLE_TRANSITION_FAILED"
        run_strategy.assert_not_called()
        assert persisted is not None
        assert persisted.status == "running"
        assert persisted.error_message == ""
    finally:
        pool.close()


def test_two_first_workers_have_one_deterministic_claim_winner(
    tmp_path: Path,
) -> None:
    """Two workers that both first observe no row execute the batch only once."""
    db_path = str(tmp_path / "eod-first-claim.db")
    setup_pool = SQLitePool(db_path)
    SQLiteStrategyRunWriter(setup_pool).init_schema()
    setup_pool.close()

    first_create_barrier = Barrier(2)
    execution_lock = Lock()
    executed_batches: list[str] = []
    batch_key = "eod-2026-07-16-etf-1"
    package = SignalPackage(
        run_id=batch_key,
        strategy_id="etf",
        signal_date="2026-07-16",
        intents=(),
        dataset_snapshot_ids={},
        factor_ids=(),
        risk_flags=(),
        factor_values={},
        selection_reasons={},
        checksum="sha256:first-claim",
        artifact_id="signal-package-first-claim",
        outcome="no_rebalance",
        no_rebalance=True,
    )

    def run_worker() -> str:
        pool = SQLitePool(db_path)
        writer = SQLiteStrategyRunWriter(pool)
        run_service = StrategyRunLifecycleStore(
            reader=_FirstCreateBarrierReader(pool, first_create_barrier),
            writer=writer,
        )

        def run_strategy(
            request: EodStrategyRequest,
            signal_date: str,
            claimed_batch_key: str,
        ) -> object:
            with execution_lock:
                executed_batches.append(claimed_batch_key)
            return object()

        try:
            return (
                EodCoordinator(
                    run_strategy=run_strategy,
                    publish_signals=lambda target, snapshots: package,
                    finalize_signals=lambda candidate: candidate,
                    find_staged_signals=lambda request, date, batch: None,
                    run_service=run_service,
                )
                .run(
                    signal_date="2026-07-16",
                    strategies=(EodStrategyRequest("etf", "1", ()),),
                    dataset_states={},
                )[0]
                .status
            )
        finally:
            pool.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: run_worker(), range(2)))

    inspect_pool = SQLitePool(db_path)
    try:
        persisted = SQLiteStrategyRunReader(inspect_pool).get(batch_key)
        assert sorted(statuses) == ["failed", "no_rebalance"]
        assert executed_batches == [batch_key]
        assert persisted is not None
        assert persisted.status == "completed"
        assert persisted.error_message == ""
    finally:
        inspect_pool.close()


def test_blocked_worker_cannot_fail_a_running_ready_owner(tmp_path: Path) -> None:
    """A stale blocked observation must not terminate another worker's claim."""
    db_path = str(tmp_path / "eod-ready-blocked-race.db")
    setup_pool = SQLitePool(db_path)
    SQLiteStrategyRunWriter(setup_pool).init_schema()
    setup_pool.close()

    owner_running = Event()
    blocked_finished = Event()
    batch_key = "eod-2026-07-16-etf-1"
    request = EodStrategyRequest("etf", "1", ("etf_daily",))
    package = SignalPackage(
        run_id=batch_key,
        strategy_id="etf",
        signal_date="2026-07-16",
        intents=(),
        dataset_snapshot_ids={"etf_daily": "sha256:ready"},
        factor_ids=(),
        risk_flags=(),
        factor_values={},
        selection_reasons={},
        checksum="sha256:ready-owner",
        artifact_id="signal-package-ready-owner",
        outcome="no_rebalance",
        no_rebalance=True,
    )

    def service(pool: SQLitePool) -> StrategyRunLifecycleStore:
        return StrategyRunLifecycleStore(
            reader=SQLiteStrategyRunReader(pool),
            writer=SQLiteStrategyRunWriter(pool),
        )

    def run_ready_owner() -> tuple[str, str]:
        pool = SQLitePool(db_path)

        def pause_after_claim(
            request: EodStrategyRequest,
            signal_date: str,
            claimed_batch_key: str,
        ) -> object:
            owner_running.set()
            assert blocked_finished.wait(timeout=5)
            return object()

        try:
            outcome = EodCoordinator(
                run_strategy=pause_after_claim,
                publish_signals=lambda target, snapshots: package,
                finalize_signals=lambda candidate: candidate,
                find_staged_signals=lambda selected, date, batch: None,
                run_service=service(pool),
            ).run(
                signal_date="2026-07-16",
                strategies=(request,),
                dataset_states={
                    "etf_daily": DatasetReadiness(
                        "etf_daily",
                        "ready",
                        "sha256:ready",
                    )
                },
            )[0]
            return outcome.status, outcome.reason
        finally:
            pool.close()

    def run_blocked_observer() -> tuple[str, str]:
        assert owner_running.wait(timeout=5)
        pool = SQLitePool(db_path)
        try:
            outcome = EodCoordinator(
                run_strategy=lambda selected, date, batch: object(),
                publish_signals=lambda target, snapshots: package,
                finalize_signals=lambda candidate: candidate,
                find_staged_signals=lambda selected, date, batch: None,
                run_service=service(pool),
            ).run(
                signal_date="2026-07-16",
                strategies=(request,),
                dataset_states={},
            )[0]
            return outcome.status, outcome.reason
        finally:
            blocked_finished.set()
            pool.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        ready_future = executor.submit(run_ready_owner)
        blocked_future = executor.submit(run_blocked_observer)
        ready_outcome = ready_future.result(timeout=10)
        blocked_outcome = blocked_future.result(timeout=10)

    inspect_pool = SQLitePool(db_path)
    try:
        persisted = SQLiteStrategyRunReader(inspect_pool).get(batch_key)
        assert ready_outcome == ("no_rebalance", "")
        assert blocked_outcome == (
            "failed",
            "RUN_LIFECYCLE_TRANSITION_FAILED",
        )
        assert persisted is not None
        assert persisted.status == "completed"
        assert persisted.error_message == ""
    finally:
        inspect_pool.close()
