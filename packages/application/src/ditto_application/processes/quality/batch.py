"""Application coordinator for scheduled data-quality batches."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_data.quality.quality_types import DQIssue
from ditto_platform.foundation import logger
from ditto_platform.services import AlertManager, NotificationLevel

from ditto_application.catalog_freshness import PersistedIngestionEvidenceVerifier
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.quality.batch_policy import (
    DEFAULT_QUALITY_DATASETS,
    quality_asset_class,
)
from ditto_application.processes.quality.evidence_policy import (
    verify_batch_ingestion_evidence,
)
from ditto_application.processes.quality.patrol import QualityPatrolService
from ditto_application.processes.quality.types import (
    QualityBatchDatasetResult,
    QualityBatchRequest,
    QualityBatchResult,
)
from ditto_application.queries.metadata import MetadataQueryFacade

__all__ = ["QualityBatchCoordinator"]


class QualityBatchCoordinator:
    """Coordinate one L1/L2 evidence gate followed by L3 patrol checks."""

    def __init__(
        self,
        *,
        patrol: QualityPatrolService,
        metadata: MetadataQueryFacade,
        evidence_verifier: PersistedIngestionEvidenceVerifier,
        alert_manager: AlertManager,
    ) -> None:
        self._patrol = patrol
        self._metadata = metadata
        self._evidence_verifier = evidence_verifier
        self._alert_manager = alert_manager

    def run(self, request: QualityBatchRequest) -> QualityBatchResult:
        """Run the configured checks and return a transport-neutral result."""
        trade_date = self._resolve_trade_date(request.trade_date)
        datasets = (
            DEFAULT_QUALITY_DATASETS if request.datasets is None else request.datasets
        )
        results: dict[str, QualityBatchDatasetResult] = {}
        all_issues: list[DQIssue] = []
        for dataset in datasets:
            persisted_payload = (
                request.ingestion_results.get(dataset)
                if request.ingestion_results is not None
                else None
            )
            dataset_result, issues = self._check_dataset(
                dataset=dataset,
                trade_date=trade_date,
                market_wide=request.market_wide,
                persisted_payload=persisted_payload,
            )
            results[dataset] = dataset_result
            all_issues.extend(issues)
        alert_issues = tuple(
            issue for issue in all_issues if issue.severity.value == "alert"
        )
        if alert_issues:
            self._send_batch_alert(trade_date, alert_issues)
        return QualityBatchResult(
            trade_date=trade_date,
            datasets_checked=tuple(datasets),
            total_issues=len(all_issues),
            alert_count=len(alert_issues),
            results_by_dataset=results,
        )

    def _check_dataset(
        self,
        *,
        dataset: str,
        trade_date: str,
        market_wide: bool,
        persisted_payload: Mapping[str, object] | None,
    ) -> tuple[QualityBatchDatasetResult, tuple[DQIssue, ...]]:
        try:
            evidence_decision = verify_batch_ingestion_evidence(
                persisted_payload,
                dataset=dataset,
                trade_date=trade_date,
                verifier=self._evidence_verifier,
            )
            if evidence_decision.error is not None:
                return (
                    QualityBatchDatasetResult(
                        passed=False,
                        issue_count=0,
                        alert_count=0,
                        error=evidence_decision.error,
                    ),
                    (),
                )
            l3_result = self._patrol.check_dataset(
                dataset=dataset,
                trade_date=trade_date,
                asset_class=quality_asset_class(dataset),
                market_wide=market_wide,
            )
        except (
            AppProcessError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
        ) as error:
            logger.warning(
                "dq_batch_known_error",
                event="dq_batch_error",
                dataset=dataset,
                error_type=type(error).__name__,
                error=str(error),
            )
            return self._error_result(error), ()
        except Exception as error:
            logger.exception(
                "dq_batch_unknown_error",
                event="dq_batch_error",
                dataset=dataset,
                error_type=type(error).__name__,
            )
            return self._error_result(error), ()

        persisted_evidence = evidence_decision.evidence
        l3_status: str | None = None
        result_error: str | None = None
        if persisted_evidence is not None:
            l3_status = "not_applicable" if not l3_result.applicable else "passed"
            if not l3_result.passed:
                l3_status = "failed"
                result_error = l3_result.error or "L3_CHECK_FAILED"
        return (
            QualityBatchDatasetResult(
                passed=l3_result.passed,
                issue_count=l3_result.issue_count,
                alert_count=l3_result.alert_count,
                l3_status=l3_status,
                quality_evidence=(
                    persisted_evidence.quality_evidence
                    if persisted_evidence is not None
                    else None
                ),
                evidence=(
                    persisted_evidence.evidence
                    if persisted_evidence is not None
                    else None
                ),
                error=result_error,
            ),
            l3_result.issues,
        )

    def _send_batch_alert(
        self,
        trade_date: str,
        issues: tuple[DQIssue, ...],
    ) -> None:
        try:
            self._alert_manager.send_alert(
                template="dq_failure",
                context={
                    "dataset": "batch",
                    "trade_date": trade_date,
                    "failed_rules": [issue.rule_name for issue in issues],
                    "error_count": len(issues),
                },
                level=NotificationLevel.ERROR,
            )
        except Exception as error:
            logger.exception(
                "Failed to send DQ alert via AlertManager",
                event="dq_alert_failed",
                error=str(error),
            )

    @staticmethod
    def _error_result(error: Exception) -> QualityBatchDatasetResult:
        return QualityBatchDatasetResult(
            passed=False,
            issue_count=0,
            alert_count=0,
            error=f"{type(error).__name__}: {error}",
        )

    def _resolve_trade_date(self, trade_date: str | None) -> str:
        if trade_date is not None:
            return trade_date
        resolved = self._metadata.get_last_trading_day()
        if resolved is None:
            raise AppProcessError("Failed to resolve trade_date", field="trade_date")
        return resolved
