"""Quality batch coordinator application-boundary tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_application.processes.quality.batch import QualityBatchCoordinator
from ditto_application.processes.quality.batch_policy import quality_asset_class
from ditto_application.processes.quality.types import (
    L3CheckResult,
    QualityBatchDatasetResult,
    QualityBatchRequest,
    QualityBatchResult,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dataset", "expected"),
    [("fx_daily", "fx"), ("commodity_daily", "commodity")],
)
def test_quality_batch_policy_routes_experimental_market_datasets(
    dataset: str,
    expected: str,
) -> None:
    assert quality_asset_class(dataset) == expected


@pytest.mark.unit
def test_batch_coordinator_resolves_defaults_and_last_trading_day() -> None:
    patrol = MagicMock()
    patrol.check_dataset.side_effect = lambda **kwargs: L3CheckResult(
        dataset=kwargs["dataset"],
        trade_date=kwargs["trade_date"],
        passed=True,
        issue_count=0,
        applicable=False,
    )
    metadata = MagicMock()
    metadata.get_last_trading_day.return_value = "2026-07-16"
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=metadata,
        evidence_verifier=MagicMock(),
        alert_manager=MagicMock(),
    )

    result = coordinator.run(QualityBatchRequest())

    assert result.trade_date == "2026-07-16"
    assert result.datasets_checked
    assert tuple(result.results_by_dataset) == result.datasets_checked
    assert all(item.passed for item in result.results_by_dataset.values())
    metadata.get_last_trading_day.assert_called_once_with()


@pytest.mark.unit
def test_batch_coordinator_preserves_explicit_empty_dataset_selection() -> None:
    patrol = MagicMock()
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=MagicMock(),
        alert_manager=MagicMock(),
    )

    result = coordinator.run(QualityBatchRequest(trade_date="2026-07-16", datasets=()))

    assert result.datasets_checked == ()
    patrol.check_dataset.assert_not_called()


@pytest.mark.unit
def test_batch_coordinator_blocks_l3_when_persisted_evidence_is_not_durable() -> None:
    patrol = MagicMock()
    verifier = MagicMock()
    verifier.verify_exact_date.return_value = False
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=verifier,
        alert_manager=MagicMock(),
    )
    payload: dict[str, object] = {
        "dataset": "stock_daily",
        "trade_date": "2026-07-16",
        "status": "success",
        "checksum": "sha256:stock",
        "row_count": 5_000,
        "quality_evidence": {
            "kind": "write_time_l1_l2",
            "status": "passed",
            "source": "tushare",
            "trade_date": "2026-07-16",
            "levels": ["l1", "l2"],
            "row_count": 5_000,
            "checksum": "sha256:stock",
        },
    }

    result = coordinator.run(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("stock_daily",),
            ingestion_results={"stock_daily": payload},
        )
    )

    row = result.results_by_dataset["stock_daily"]
    assert row.passed is False
    assert row.error == "INGESTION_COMPONENT_QUALITY_EVIDENCE_INVALID"
    patrol.check_dataset.assert_not_called()


@pytest.mark.unit
def test_batch_coordinator_contains_durable_evidence_verifier_exception() -> None:
    patrol = MagicMock()
    verifier = MagicMock()
    verifier.verify_exact_date.side_effect = RuntimeError("catalog unavailable")
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=verifier,
        alert_manager=MagicMock(),
    )
    payload: dict[str, object] = {
        "dataset": "stock_daily",
        "trade_date": "2026-07-16",
        "status": "success",
        "checksum": "sha256:stock",
        "row_count": 5_000,
        "quality_evidence": {
            "kind": "write_time_l1_l2",
            "status": "passed",
            "source": "tushare",
            "trade_date": "2026-07-16",
            "levels": ["l1", "l2"],
            "row_count": 5_000,
            "checksum": "sha256:stock",
        },
    }

    result = coordinator.run(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("stock_daily",),
            ingestion_results={"stock_daily": payload},
        )
    )

    row = result.results_by_dataset["stock_daily"]
    assert row.passed is False
    assert row.error == "RuntimeError: catalog unavailable"
    patrol.check_dataset.assert_not_called()


@pytest.mark.unit
def test_batch_coordinator_returns_normalized_evidence_and_l3_status() -> None:
    patrol = MagicMock()
    patrol.check_dataset.return_value = L3CheckResult(
        dataset="valuation_metrics",
        trade_date="2026-07-16",
        passed=True,
        issue_count=0,
        applicable=False,
    )
    verifier = MagicMock()
    verifier.verify_exact_date.return_value = True
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=verifier,
        alert_manager=MagicMock(),
    )
    payload: dict[str, object] = {
        "dataset": "valuation_metrics",
        "trade_date": "2026-07-16",
        "status": "success",
        "checksum": "sha256:valuation",
        "row_count": 5_000,
        "quality_evidence": {
            "kind": "write_time_l1_l2",
            "status": "passed",
            "source": "tushare",
            "trade_date": "2026-07-16",
            "levels": ["l1", "l2"],
            "row_count": 5_000,
            "checksum": "sha256:valuation",
        },
    }

    result = coordinator.run(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("valuation_metrics",),
            ingestion_results={"valuation_metrics": payload},
        )
    )

    row = result.results_by_dataset["valuation_metrics"]
    assert row.passed is True
    assert row.l3_status == "not_applicable"
    assert row.quality_evidence == {
        "kind": "persisted_ingestion_l1_l2",
        "status": "passed",
        "source": "tushare",
        "trade_date": "2026-07-16",
        "levels": ["l1", "l2"],
        "row_count": 5_000,
        "checksum": "sha256:valuation",
    }
    assert row.evidence == {
        "kind": "persisted_ingestion_l1_l2",
        "trade_date": "2026-07-16",
        "checksum": "sha256:valuation",
        "row_count": 5_000,
    }


@pytest.mark.unit
def test_batch_coordinator_records_dataset_exception_without_aborting_batch() -> None:
    patrol = MagicMock()
    patrol.check_dataset.side_effect = [
        RuntimeError("broken reader"),
        L3CheckResult(
            dataset="etf_daily",
            trade_date="2026-07-16",
            passed=True,
            issue_count=0,
        ),
    ]
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=MagicMock(),
        alert_manager=MagicMock(),
    )

    result = coordinator.run(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("stock_daily", "etf_daily"),
        )
    )

    assert result.results_by_dataset["stock_daily"].error == (
        "RuntimeError: broken reader"
    )
    assert result.results_by_dataset["stock_daily"].passed is False
    assert result.results_by_dataset["etf_daily"].passed is True


@pytest.mark.unit
def test_batch_coordinator_exposes_typed_error_for_unknown_dataset() -> None:
    patrol = MagicMock()
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=MagicMock(),
        alert_manager=MagicMock(),
    )

    result = coordinator.run(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("unknown_dataset",),
        )
    )

    row = result.results_by_dataset["unknown_dataset"]
    assert row.passed is False
    assert row.error == "AppProcessError: Unknown dataset: unknown_dataset"
    patrol.check_dataset.assert_not_called()


@pytest.mark.unit
def test_quality_batch_result_serializes_transport_shape_without_null_optionals() -> (
    None
):
    result = QualityBatchResult(
        trade_date="2026-07-16",
        datasets_checked=("stock_daily",),
        total_issues=0,
        alert_count=0,
        results_by_dataset={
            "stock_daily": QualityBatchDatasetResult(
                passed=True,
                issue_count=0,
                alert_count=0,
            )
        },
    )

    assert result.to_dict() == {
        "trade_date": "2026-07-16",
        "datasets_checked": ["stock_daily"],
        "total_issues": 0,
        "alert_count": 0,
        "results_by_dataset": {
            "stock_daily": {
                "passed": True,
                "issue_count": 0,
                "alert_count": 0,
            }
        },
    }


@pytest.mark.unit
def test_batch_coordinator_sends_one_batch_alert_for_alert_severity_issues() -> None:
    issue = MagicMock()
    issue.rule_name = "price_outlier"
    issue.severity.value = "alert"
    patrol = MagicMock()
    patrol.check_dataset.return_value = L3CheckResult(
        dataset="stock_daily",
        trade_date="2026-07-16",
        passed=False,
        issue_count=1,
        alert_count=1,
        issues=(issue,),
    )
    alert_manager = MagicMock()
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=MagicMock(),
        alert_manager=alert_manager,
    )

    result = coordinator.run(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("stock_daily",),
        )
    )

    assert result.total_issues == 1
    assert result.alert_count == 1
    alert_manager.send_alert.assert_called_once()
    assert alert_manager.send_alert.call_args.kwargs["context"] == {
        "dataset": "batch",
        "trade_date": "2026-07-16",
        "failed_rules": ["price_outlier"],
        "error_count": 1,
    }


@pytest.mark.unit
def test_valid_persisted_snapshot_still_fails_when_l3_fails() -> None:
    patrol = MagicMock()
    patrol.check_dataset.return_value = L3CheckResult(
        dataset="stock_daily",
        trade_date="2026-07-16",
        passed=False,
        issue_count=1,
        error="L3_DATA_INVALID",
    )
    verifier = MagicMock()
    verifier.verify_exact_date.return_value = True
    coordinator = QualityBatchCoordinator(
        patrol=patrol,
        metadata=MagicMock(),
        evidence_verifier=verifier,
        alert_manager=MagicMock(),
    )
    payload: dict[str, object] = {
        "dataset": "stock_daily",
        "trade_date": "2026-07-16",
        "status": "success",
        "checksum": "sha256:stock",
        "row_count": 5_000,
        "quality_evidence": {
            "kind": "write_time_l1_l2",
            "status": "passed",
            "source": "tushare",
            "trade_date": "2026-07-16",
            "levels": ["l1", "l2"],
            "row_count": 5_000,
            "checksum": "sha256:stock",
        },
    }

    result = coordinator.run(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("stock_daily",),
            market_wide=True,
            ingestion_results={"stock_daily": payload},
        )
    )

    row = result.results_by_dataset["stock_daily"]
    assert row.passed is False
    assert row.error == "L3_DATA_INVALID"
    assert row.l3_status == "failed"
    patrol.check_dataset.assert_called_once_with(
        dataset="stock_daily",
        trade_date="2026-07-16",
        asset_class="stock",
        market_wide=True,
    )
