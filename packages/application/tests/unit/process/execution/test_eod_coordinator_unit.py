"""EodCoordinator 的逐策略就绪与 outcome 契约。"""

from collections.abc import Mapping
from dataclasses import replace
from unittest.mock import MagicMock

import orjson
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.eod_coordinator import (
    DatasetReadiness,
    EodCoordinator,
    EodCoordinatorOptions,
    EodStrategyRequest,
)
from ditto_application.processes.execution.signal_package import SignalPackage
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_strategy.runs.models import StrategyRunRecord


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


def _finalize(package: SignalPackage) -> SignalPackage:
    return package


def _no_staged(
    request: EodStrategyRequest,
    signal_date: str,
    batch_key: str,
) -> SignalPackage | None:
    return None


def test_unrelated_failed_dataset_does_not_block_strategy() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    coordinator = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: _package(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
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
    run_service.mark_completed.assert_called_once_with("eod-2026-07-16-etf-1")
    run_service.mark_failed.assert_not_called()


def test_missing_required_dataset_fails_closed_without_running() -> None:
    called = False
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_pending_failed.return_value = True

    def run(request: EodStrategyRequest, date: str, batch: str) -> object:
        nonlocal called
        called = True
        return object()

    outcome = EodCoordinator(
        run_strategy=run,
        publish_signals=lambda target, snapshots: _package(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={},
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "REQUIRED_DATA_NOT_READY"
    assert outcome.required_dataset_states[0].status == "unknown"
    assert called is False
    run_service.create_run.assert_called_once()
    create_kwargs = run_service.create_run.call_args.kwargs
    assert create_kwargs["run_id"] == "eod-2026-07-16-stock-2"
    assert create_kwargs["strategy_id"] == "stock"
    assert create_kwargs["strategy_version"] == "2"
    assert create_kwargs["mode"] == "recommendation"
    assert orjson.loads(create_kwargs["config_json"]) == {
        "batch_key": "eod-2026-07-16-stock-2",
        "outcome": "blocked",
        "required_dataset_states": [
            {
                "dataset": "stock_daily",
                "reason": "",
                "snapshot_id": None,
                "status": "unknown",
            }
        ],
        "signal_date": "2026-07-16",
    }
    run_service.mark_pending_failed.assert_called_once_with(
        "eod-2026-07-16-stock-2",
        "blocked:REQUIRED_DATA_NOT_READY",
    )


def test_portfolio_construction_failure_blocks_before_signal_publication() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    publish_signals = MagicMock()

    def construct(
        target: object,
        request: EodStrategyRequest,
        signal_date: str,
        snapshots: Mapping[str, str],
    ) -> object:
        raise AppProcessError(
            "optimizer input unavailable",
            code="PORTFOLIO_CONSTRUCTION_BLOCKED",
        )

    outcome = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=publish_signals,
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
        options=EodCoordinatorOptions(construct_portfolio=construct),
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={
            "stock_daily": DatasetReadiness(
                "stock_daily",
                "ready",
                "snap-stock",
            )
        },
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "PORTFOLIO_CONSTRUCTION_BLOCKED"
    publish_signals.assert_not_called()
    run_service.mark_failed.assert_called_once_with(
        "eod-2026-07-16-stock-2",
        "blocked:PORTFOLIO_CONSTRUCTION_BLOCKED",
    )


def test_prior_reconciliation_mismatch_blocks_next_suggestion() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_pending_failed.return_value = True
    run_strategy = MagicMock()

    outcome = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
        options=EodCoordinatorOptions(
            suggestion_block_reason=lambda request, signal_date: (
                "RECONCILIATION_MISMATCH"
            ),
        ),
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={
            "stock_daily": DatasetReadiness(
                "stock_daily",
                "ready",
                "snap-stock",
            )
        },
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "RECONCILIATION_MISMATCH"
    run_strategy.assert_not_called()
    run_service.mark_pending_failed.assert_called_once_with(
        "eod-2026-07-16-stock-2",
        "blocked:RECONCILIATION_MISMATCH",
    )


def test_blocked_run_create_failure_returns_stable_failed_outcome() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.create_run.side_effect = RuntimeError("database unavailable")

    outcome = EodCoordinator(
        run_strategy=MagicMock(),
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={},
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "RUN_LIFECYCLE_CREATE_FAILED"
    run_service.mark_failed.assert_not_called()


def test_blocked_run_failed_transition_is_not_reported_as_persisted() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_pending_failed.return_value = False

    outcome = EodCoordinator(
        run_strategy=MagicMock(),
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={},
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "RUN_LIFECYCLE_TRANSITION_FAILED"


def test_repeated_blocked_run_refreshes_evidence_without_retrying_owner() -> None:
    run_service = MagicMock()
    run_service.mark_pending_failed.return_value = False
    run_service.refresh_blocked_evidence.return_value = True

    outcome = EodCoordinator(
        run_strategy=MagicMock(),
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={
            "stock_daily": DatasetReadiness(
                "stock_daily",
                "stale",
                "sha256:B",
                "STALE_DATASET:B",
            )
        },
    )[0]

    assert outcome.status == "blocked"
    run_service.refresh_blocked_evidence.assert_called_once()
    call = run_service.refresh_blocked_evidence.call_args
    assert call.args == ("eod-2026-07-16-stock-2",)
    assert orjson.loads(call.kwargs["config_json"])["required_dataset_states"] == [
        {
            "dataset": "stock_daily",
            "reason": "STALE_DATASET:B",
            "snapshot_id": "sha256:B",
            "status": "stale",
        }
    ]
    run_service.retry_failed.assert_not_called()


def test_blocked_persistence_failure_can_be_retried() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.create_run.side_effect = [RuntimeError("database unavailable"), None]
    run_service.mark_pending_failed.return_value = True
    coordinator = EodCoordinator(
        run_strategy=MagicMock(),
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    )
    kwargs = {
        "signal_date": "2026-07-16",
        "strategies": (EodStrategyRequest("stock", "2", ("stock_daily",)),),
        "dataset_states": {},
    }

    first = coordinator.run(**kwargs)[0]  # type: ignore[arg-type]
    retry = coordinator.run(**kwargs)[0]  # type: ignore[arg-type]

    assert first.reason == "RUN_LIFECYCLE_CREATE_FAILED"
    assert retry.status == "blocked"
    assert retry.reason == "REQUIRED_DATA_NOT_READY"


def test_ready_dataset_without_snapshot_fails_closed() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    run_strategy = MagicMock()

    outcome = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ("stock_daily",)),),
        dataset_states={
            "stock_daily": DatasetReadiness("stock_daily", "ready", None),
        },
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "REQUIRED_DATA_NOT_READY"
    run_strategy.assert_not_called()


def test_account_baseline_missing_is_stable_blocked_outcome() -> None:
    run_service = MagicMock(spec=RunLifecycleService)

    def missing_baseline(*args: object) -> object:
        raise AppProcessError(
            "account lookup failed",
            code="ACCOUNT_BASELINE_MISSING",
        )

    outcome = EodCoordinator(
        run_strategy=missing_baseline,
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "ACCOUNT_BASELINE_MISSING"
    run_service.mark_failed.assert_called_once_with(
        "eod-2026-07-16-stock-2",
        "blocked:ACCOUNT_BASELINE_MISSING",
    )


def test_failed_running_transition_stops_before_strategy_execution() -> None:
    batch_key = "eod-2026-07-16-stock-2"
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_running.return_value = False
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="stock",
        strategy_version="2",
        mode="recommendation",
        status="running",
    )
    run_strategy = MagicMock()

    outcome = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=MagicMock(),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "RUN_LIFECYCLE_TRANSITION_FAILED"
    run_strategy.assert_not_called()
    run_service.retry_failed.assert_not_called()
    run_service.mark_failed.assert_not_called()


def test_failed_terminal_run_can_retry_same_deterministic_batch() -> None:
    batch_key = "eod-2026-07-16-stock-2"
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_running.side_effect = [False, True]
    run_service.retry_failed.return_value = True
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="stock",
        strategy_version="2",
        mode="recommendation",
        status="failed",
        error_message="blocked:REQUIRED_DATA_NOT_READY",
    )
    run_strategy = MagicMock(return_value=object())

    outcome = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=lambda *args: replace(
            _package(),
            run_id=batch_key,
            strategy_id="stock",
            outcome="completed",
            no_rebalance=False,
        ),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "completed"
    assert run_service.mark_running.call_count == 2
    run_service.retry_failed.assert_called_once()
    retry_kwargs = run_service.retry_failed.call_args.kwargs
    assert orjson.loads(retry_kwargs["config_json"])["outcome"] == "running"
    run_strategy.assert_called_once()


def test_failed_completed_transition_never_reports_completed_outcome() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_completed.return_value = False
    finalize_signals = MagicMock(side_effect=_finalize)

    outcome = EodCoordinator(
        run_strategy=lambda *args: object(),
        publish_signals=lambda *args: replace(
            _package(), outcome="completed", no_rebalance=False
        ),
        finalize_signals=finalize_signals,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "RUN_LIFECYCLE_TRANSITION_FAILED"
    finalize_signals.assert_not_called()


def test_completed_transition_exception_never_activates_staged_package() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_completed.side_effect = RuntimeError("lifecycle unavailable")
    finalize_signals = MagicMock(side_effect=_finalize)

    outcome = EodCoordinator(
        run_strategy=lambda *args: object(),
        publish_signals=lambda *args: replace(
            _package(), outcome="completed", no_rebalance=False
        ),
        finalize_signals=finalize_signals,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("stock", "2", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "RUN_LIFECYCLE_TRANSITION_FAILED"
    finalize_signals.assert_not_called()


def test_publish_failure_replaces_running_fact_with_failed_run() -> None:
    run_service = MagicMock(spec=RunLifecycleService)

    def fail_publish(target: object, snapshots: object) -> SignalPackage:
        raise RuntimeError("artifact store unavailable")

    outcome = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=fail_publish,
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "SIGNAL_PACKAGE_PUBLISH_FAILED"
    run_service.create_run.assert_called_once()
    create_kwargs = run_service.create_run.call_args.kwargs
    assert orjson.loads(create_kwargs["config_json"])["outcome"] == "running"
    run_service.mark_running.assert_called_once_with("eod-2026-07-16-etf-1")
    run_service.mark_completed.assert_not_called()
    run_service.mark_failed.assert_called_once_with(
        "eod-2026-07-16-etf-1",
        "failed:SIGNAL_PACKAGE_PUBLISH_FAILED",
    )


def test_rerun_conflict_is_preserved() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    outcome = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: replace(
            _package(), outcome="rerun_conflict"
        ),
        finalize_signals=_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "rerun_conflict"
    run_service.mark_completed.assert_called_once_with("eod-2026-07-16-etf-1")
    run_service.mark_failed.assert_not_called()


def test_completed_outcome_stays_completed_and_finalizes_run() -> None:
    run_service = MagicMock(spec=RunLifecycleService)
    finalize_signals = MagicMock(side_effect=_finalize)
    outcome = EodCoordinator(
        run_strategy=lambda request, date, batch: object(),
        publish_signals=lambda target, snapshots: replace(
            _package(), outcome="completed", no_rebalance=False
        ),
        finalize_signals=finalize_signals,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "completed"
    run_service.mark_completed.assert_called_once_with("eod-2026-07-16-etf-1")
    finalize_signals.assert_called_once()
    run_service.mark_failed.assert_not_called()


def test_finalize_failure_keeps_completed_run_recoverable_on_retry() -> None:
    batch_key = "eod-2026-07-16-etf-1"
    staged = replace(
        _package(),
        run_id=batch_key,
        outcome="completed",
        no_rebalance=False,
    )
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.get_run.return_value = None
    failing_finalize = MagicMock(side_effect=RuntimeError("activation unavailable"))

    first = EodCoordinator(
        run_strategy=lambda *args: object(),
        publish_signals=lambda *args: staged,
        finalize_signals=failing_finalize,
        find_staged_signals=_no_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert first.status == "failed"
    assert first.reason == "SIGNAL_PACKAGE_FINALIZE_FAILED"
    assert first.artifact_id == staged.artifact_id
    run_service.mark_completed.assert_called_once_with(batch_key)
    run_service.mark_failed.assert_not_called()
    run_service.reset_mock()
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="etf",
        strategy_version="1",
        mode="recommendation",
        status="completed",
    )
    target = object()
    run_strategy = MagicMock(return_value=target)
    publish_signals = MagicMock(return_value=staged)
    find_staged = MagicMock(return_value=staged)
    finalize_signals = MagicMock(return_value=staged)

    retry = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=publish_signals,
        finalize_signals=finalize_signals,
        find_staged_signals=find_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert retry.status == "completed"
    assert retry.artifact_id == staged.artifact_id
    find_staged.assert_called_once()
    finalize_signals.assert_called_once_with(staged)
    run_strategy.assert_called_once()
    publish_signals.assert_called_once_with(target, {})
    run_service.create_run.assert_not_called()
    run_service.mark_running.assert_not_called()
    run_service.mark_completed.assert_not_called()
    run_service.mark_failed.assert_not_called()


def test_completed_active_package_retry_is_an_idempotent_noop() -> None:
    batch_key = "eod-2026-07-16-etf-1"
    active = replace(
        _package(),
        run_id=batch_key,
        outcome="completed",
        no_rebalance=False,
        artifact_status="active",
    )
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="etf",
        strategy_version="1",
        mode="recommendation",
        status="completed",
    )
    target = object()
    run_strategy = MagicMock(return_value=target)
    publish_signals = MagicMock(return_value=active)
    find_completed = MagicMock(return_value=active)
    finalize_signals = MagicMock(return_value=active)

    outcome = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=publish_signals,
        finalize_signals=finalize_signals,
        find_staged_signals=find_completed,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "completed"
    assert outcome.artifact_id == active.artifact_id
    find_completed.assert_called_once()
    run_strategy.assert_called_once_with(
        EodStrategyRequest("etf", "1", ()),
        "2026-07-16",
        batch_key,
    )
    publish_signals.assert_called_once_with(target, {})
    finalize_signals.assert_called_once_with(active)
    run_service.create_run.assert_not_called()
    run_service.mark_running.assert_not_called()
    run_service.mark_completed.assert_not_called()
    run_service.mark_failed.assert_not_called()


def test_completed_active_retry_finalizes_safe_changed_candidate() -> None:
    batch_key = "eod-2026-07-16-etf-1"
    active = replace(
        _package(),
        run_id=batch_key,
        outcome="completed",
        no_rebalance=False,
        artifact_status="active",
    )
    changed = replace(
        active,
        artifact_id="artifact-changed",
        checksum="sha256:changed",
        artifact_status="",
    )
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="etf",
        strategy_version="1",
        mode="recommendation",
        status="completed",
    )
    finalize_signals = MagicMock(return_value=changed)

    outcome = EodCoordinator(
        run_strategy=lambda *args: object(),
        publish_signals=lambda *args: changed,
        finalize_signals=finalize_signals,
        find_staged_signals=lambda *args: active,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "completed"
    assert outcome.artifact_id == changed.artifact_id
    finalize_signals.assert_called_once_with(changed)
    run_service.create_run.assert_not_called()
    run_service.mark_running.assert_not_called()


def test_completed_active_retry_preserves_fill_conflict() -> None:
    batch_key = "eod-2026-07-16-etf-1"
    active = replace(
        _package(),
        run_id=batch_key,
        outcome="completed",
        no_rebalance=False,
        artifact_status="active",
    )
    conflict = replace(
        active,
        artifact_id="artifact-conflict",
        checksum="sha256:changed",
        outcome="rerun_conflict",
        artifact_status="conflict",
    )
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="etf",
        strategy_version="1",
        mode="recommendation",
        status="completed",
    )
    finalize_signals = MagicMock()

    outcome = EodCoordinator(
        run_strategy=lambda *args: object(),
        publish_signals=lambda *args: conflict,
        finalize_signals=finalize_signals,
        find_staged_signals=lambda *args: active,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ()),),
        dataset_states={},
    )[0]

    assert outcome.status == "rerun_conflict"
    assert outcome.artifact_id == conflict.artifact_id
    finalize_signals.assert_not_called()
    run_service.create_run.assert_not_called()


def test_completed_staged_recovery_rejects_changed_canonical_package() -> None:
    batch_key = "eod-2026-07-16-etf-1"
    staged = replace(
        _package(),
        run_id=batch_key,
        outcome="completed",
        no_rebalance=False,
        dataset_snapshot_ids={"etf_daily": "snapshot-old"},
    )
    changed = replace(
        staged,
        artifact_id="artifact-changed",
        checksum="sha256:changed",
        dataset_snapshot_ids={"etf_daily": "snapshot-new"},
    )
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="etf",
        strategy_version="1",
        mode="recommendation",
        status="completed",
    )
    finalize_signals = MagicMock()

    outcome = EodCoordinator(
        run_strategy=lambda *args: object(),
        publish_signals=lambda *args: changed,
        finalize_signals=finalize_signals,
        find_staged_signals=lambda *args: staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
        dataset_states={
            "etf_daily": DatasetReadiness("etf_daily", "ready", "snapshot-new")
        },
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "SIGNAL_PACKAGE_RECOVERY_MISMATCH"
    finalize_signals.assert_not_called()
    run_service.create_run.assert_not_called()
    run_service.mark_failed.assert_not_called()


def test_completed_staged_recovery_rejects_changed_business_checksum() -> None:
    batch_key = "eod-2026-07-16-etf-1"
    staged = replace(
        _package(),
        run_id=batch_key,
        outcome="completed",
        no_rebalance=False,
        dataset_snapshot_ids={"etf_daily": "snapshot-same"},
    )
    changed = replace(
        staged,
        artifact_id="artifact-business-changed",
        checksum="sha256:business-changed",
    )
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="etf",
        strategy_version="1",
        mode="recommendation",
        status="completed",
    )
    finalize_signals = MagicMock()

    outcome = EodCoordinator(
        run_strategy=lambda *args: object(),
        publish_signals=lambda *args: changed,
        finalize_signals=finalize_signals,
        find_staged_signals=lambda *args: staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
        dataset_states={
            "etf_daily": DatasetReadiness("etf_daily", "ready", "snapshot-same")
        },
    )[0]

    assert outcome.status == "failed"
    assert outcome.reason == "SIGNAL_PACKAGE_RECOVERY_MISMATCH"
    finalize_signals.assert_not_called()
    run_service.create_run.assert_not_called()


def test_completed_staged_recovery_still_obeys_current_readiness_gate() -> None:
    batch_key = "eod-2026-07-16-etf-1"
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.get_run.return_value = StrategyRunRecord(
        run_id=batch_key,
        strategy_id="etf",
        strategy_version="1",
        mode="recommendation",
        status="completed",
    )
    run_strategy = MagicMock()
    find_staged = MagicMock(return_value=_package())
    finalize_signals = MagicMock()

    outcome = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=MagicMock(),
        finalize_signals=finalize_signals,
        find_staged_signals=find_staged,
        run_service=run_service,
    ).run(
        signal_date="2026-07-16",
        strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
        dataset_states={
            "etf_daily": DatasetReadiness("etf_daily", "stale", "snapshot-old")
        },
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "REQUIRED_DATA_NOT_READY"
    find_staged.assert_not_called()
    run_strategy.assert_not_called()
    finalize_signals.assert_not_called()
