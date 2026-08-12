"""R2 shadow and required preflight integration tests."""

from __future__ import annotations

from datetime import date
from typing import Literal
from unittest.mock import MagicMock

from ditto_application.processes.execution.eod_coordinator import (
    DatasetReadiness,
    EodCoordinator,
    EodCoordinatorOptions,
    EodStrategyRequest,
    R2PreflightPolicy,
)
from ditto_application.processes.execution.signal_package import SignalPackage
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_application.queries.data_readiness import (
    DataReadinessReport,
    DatasetReadinessAssessment,
)


def _package() -> SignalPackage:
    return SignalPackage(
        run_id="batch",
        strategy_id="etf",
        signal_date="2026-07-18",
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


def _blocked_report() -> DataReadinessReport:
    return DataReadinessReport(
        profile="r2-modern-a-share-v1",
        status="blocked",
        datasets=(
            DatasetReadinessAssessment(
                dataset_id="etf_daily",
                required_from=date(2026, 7, 18),
                required_to=date(2026, 7, 18),
                status="blocked",
                certification_report_id=None,
                snapshot_ids=(),
                reason_codes=("CERTIFICATION_MISSING",),
            ),
        ),
    )


def _coordinator(
    *,
    readiness: MagicMock,
    mode: Literal["shadow", "required"],
) -> EodCoordinator:
    run_service = MagicMock(spec=RunLifecycleService)
    run_service.mark_pending_failed.return_value = True
    return EodCoordinator(
        run_strategy=lambda request, signal_date, batch_key: object(),
        publish_signals=lambda target, snapshots: _package(),
        finalize_signals=lambda package: package,
        find_staged_signals=lambda request, signal_date, batch_key: None,
        run_service=run_service,
        options=EodCoordinatorOptions(
            data_readiness_query=readiness,
            r2_preflight_policy=R2PreflightPolicy(mode=mode),
        ),
    )


def test_shadow_preflight_records_assessment_without_blocking_r1() -> None:
    readiness = MagicMock()
    readiness.assess.return_value = _blocked_report()

    outcome = _coordinator(readiness=readiness, mode="shadow").run(
        signal_date="2026-07-18",
        strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
        dataset_states={
            "etf_daily": DatasetReadiness(
                "etf_daily",
                "ready",
                "snapshot:etf_daily:2026-07-18",
            )
        },
    )[0]

    assert outcome.status == "no_rebalance"
    assert outcome.r2_preflight_status == "blocked"


def test_required_preflight_blocks_with_dataset_date_and_reason() -> None:
    readiness = MagicMock()
    readiness.assess.return_value = _blocked_report()

    outcome = _coordinator(readiness=readiness, mode="required").run(
        signal_date="2026-07-18",
        strategies=(EodStrategyRequest("etf", "1", ("etf_daily",)),),
        dataset_states={
            "etf_daily": DatasetReadiness(
                "etf_daily",
                "ready",
                "snapshot:etf_daily:2026-07-18",
            )
        },
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == "R2_DATA_PREFLIGHT_BLOCKED"
    assert outcome.required_dataset_states[0].reason == (
        "CERTIFICATION_MISSING:etf_daily:2026-07-18"
    )
