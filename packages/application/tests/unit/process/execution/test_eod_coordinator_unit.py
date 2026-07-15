"""EodCoordinator 的逐策略就绪与 outcome 契约。"""

from dataclasses import replace

from ditto_application.processes.execution.eod_coordinator import (
    DatasetReadiness,
    EodCoordinator,
    EodStrategyRequest,
)
from ditto_application.processes.execution.signal_package import SignalPackage


def _package() -> SignalPackage:
    return SignalPackage(
        run_id="batch",
        strategy_id="etf",
        signal_date="2026-07-16",
        intents=(),
        dataset_snapshot_ids={},
        factor_ids=(),
        risk_flags=(),
        factor_values={},
        selection_reasons={},
        checksum="sha256:ok",
        artifact_id="artifact-1",
        outcome="no_rebalance",
        no_rebalance=True,
    )


def test_unrelated_failed_dataset_does_not_block_strategy() -> None:
    coordinator = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: _package(),
    )

    outcomes = coordinator.run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
        dataset_states={
            "etf_daily": DatasetReadiness("etf_daily", "ready", "snap-etf"),
            "stock_daily": DatasetReadiness("stock_daily", "dq_failed"),
        },
    )

    assert outcomes[0].status == "no_rebalance"
    assert outcomes[0].batch_key == "eod-2026-07-16-etf-1"


def test_missing_required_dataset_fails_closed_without_running() -> None:
    called = False

    def run(request: EodStrategyRequest, date: str, batch: str) -> object:
        nonlocal called
        called = True
        return object()

    outcome = EodCoordinator(
        run_strategy=run,
        publish_signals=lambda target, snapshots: _package(),
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={},
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "stock_daily:unknown"
    assert called is False


def test_rerun_conflict_is_preserved() -> None:
    outcome = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: replace(
            _package(), outcome="rerun_conflict"
        ),
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "rerun_conflict"
