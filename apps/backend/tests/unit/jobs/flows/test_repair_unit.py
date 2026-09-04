"""Sparse PIT recovery flow adapter tests."""

from __future__ import annotations

from typing import Any

import pytest
from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITComponentRecoveryResult,
    SparsePITReattestationRequest,
    SparsePITReattestationResult,
)
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint: Any) -> Any:
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


def test_sparse_pit_runner_delegates_to_application_process(
    mocker: MockerFixture,
) -> None:
    from ditto_apps.jobs.flows import repair as repair_module

    application_result = SparsePITReattestationResult(
        dataset="balance_sheet",
        source="tushare",
        signal_date="2026-07-16",
        passed=True,
        component_dates=("2026-06-30",),
        components=(
            SparsePITComponentRecoveryResult(
                trade_date="2026-06-30",
                passed=True,
                checksum="sha256:component",
                row_count=12,
            ),
        ),
        source_snapshot_id="snapshot:tushare:balance_sheet:aggregate",
        source_snapshot_ids=("snapshot:tushare:balance_sheet:2026-06-30",),
        row_count=12,
    )
    bundle = mocker.MagicMock()
    bundle.sparse_pit_reattestation.run.return_value = application_result
    context = mocker.MagicMock()
    context.__enter__.return_value = bundle
    context.__exit__.return_value = None
    create_bundle = mocker.patch.object(
        repair_module,
        "create_ingestion_bundle",
        return_value=context,
    )

    result = repair_module.run_sparse_pit_reattestation(
        dataset="balance_sheet",
        signal_date="2026-07-16",
        source="tushare",
    )

    create_bundle.assert_called_once_with(source="tushare")
    bundle.sparse_pit_reattestation.run.assert_called_once_with(
        SparsePITReattestationRequest(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
        )
    )
    assert result == application_result.to_dict()


def test_sparse_pit_prefect_flow_uses_plain_runner(mocker: MockerFixture) -> None:
    from ditto_apps.jobs.flows import repair as repair_module

    runner = mocker.patch.object(
        repair_module,
        "run_sparse_pit_reattestation",
        return_value={"passed": True},
    )

    result = _prefect_runner(repair_module.sparse_pit_reattestation_flow)(
        dataset="balance_sheet",
        signal_date="2026-07-16",
        source="tushare",
    )

    assert result == {"passed": True}
    runner.assert_called_once_with(
        dataset="balance_sheet",
        signal_date="2026-07-16",
        source="tushare",
    )


def test_sparse_pit_prefect_flow_fails_when_evidence_does_not_pass(
    mocker: MockerFixture,
) -> None:
    from ditto_apps.jobs.flows import repair as repair_module

    mocker.patch.object(
        repair_module,
        "run_sparse_pit_reattestation",
        return_value={
            "passed": False,
            "error": "SPARSE_REATTEST_COMPONENT_FAILED",
        },
    )

    with pytest.raises(RuntimeError, match="SPARSE_REATTEST_COMPONENT_FAILED"):
        _prefect_runner(repair_module.sparse_pit_reattestation_flow)(
            dataset="balance_sheet",
            signal_date="2026-07-16",
            source="tushare",
        )
