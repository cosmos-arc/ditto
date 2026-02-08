"""Quality Service - Write-time DQ orchestration (Application Layer)."""

from typing import Any

import polars as pl
from ditto_core.quality import QualityEngine
from ditto_datahub.runtime.quality.quarantine_store import QuarantineStore
from loguru import logger


class QualityService:
    """
    Quality service for write-time DQ checks.

    Application Layer: Orchestrates L1/L2 checks during data ingestion.
    Handles quarantine logic and metrics/logging.
    """

    def __init__(
        self, engine: QualityEngine, quarantine_store: QuarantineStore | None = None
    ) -> None:
        """
        Initialize quality service.

        Args:
            engine: Quality engine instance
            quarantine_store: Optional quarantine store for failed data

        """
        self._engine = engine
        self._quarantine_store = quarantine_store

    def check_and_quarantine(
        self,
        df: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[pl.DataFrame, bool]:
        """
        Execute DQ checks and quarantine bad data if needed.

        Args:
            df: Data to check
            dataset: Dataset identifier
            context: Additional context (e.g., reference_values for FK checks)

        Returns:
            Tuple of (cleaned_df, should_block):
                - cleaned_df: DataFrame after quarantine (may be empty)
                - should_block: Whether to block ingestion (True if L1 errors)

        """
        # Run L1/L2 checks
        result = self._engine.check(
            df=df,
            dataset=dataset,
            levels=["l1", "l2"],
            context=context,
        )

        # Log results
        if result.issues:
            logger.warning(
                "DQ issues found during write",
                event="dq_write_check",
                dataset=dataset,
                issue_count=len(result.issues),
                error_count=result.error_count,
                warn_count=result.warn_count,
            )
        else:
            logger.debug(
                "DQ check passed",
                event="dq_write_check",
                dataset=dataset,
            )

        # Determine if we should block ingestion
        # L1 errors cause blocking
        should_block = result.has_errors

        # If there are issues, quarantine the bad data
        if result.issues:
            self._quarantine_data(df, result, dataset)

        return df, should_block

    def _quarantine_data(
        self,
        df: pl.DataFrame,
        result: Any,  # DQResult
        dataset: str,
    ) -> None:
        """
        Quarantine data with quality issues.

        Saves failed data to quarantine store if available.

        Args:
            df: Data with issues
            result: DQ check result
            dataset: Dataset identifier

        """
        if self._quarantine_store is None:
            logger.info(
                "Quarantine store not configured, skipping quarantine",
                event="dq_quarantine_skipped",
                dataset=dataset,
                issue_count=len(result.issues),
            )
            return

        # Group issues by rule to avoid duplicate saves
        for issue in result.issues:
            if issue.affected_rows == 0:
                continue

            # Extract sample data as DataFrame
            if not issue.sample_data:
                continue

            try:
                failed_df = pl.DataFrame(issue.sample_data)
                self._quarantine_store.save_failed_data(
                    dataset=dataset,
                    rule_id=issue.rule_name,
                    severity=issue.severity.value,
                    failed_data=failed_df,
                    trade_date=None,  # Can be extracted from context if needed
                )
                logger.info(
                    "Quarantined bad data",
                    event="dq_quarantine",
                    dataset=dataset,
                    rule_id=issue.rule_name,
                    severity=issue.severity.value,
                    affected_rows=issue.affected_rows,
                )
            except Exception as e:
                logger.error(
                    "Failed to quarantine data",
                    event="dq_quarantine_failed",
                    dataset=dataset,
                    rule_id=issue.rule_name,
                    error=str(e),
                )
