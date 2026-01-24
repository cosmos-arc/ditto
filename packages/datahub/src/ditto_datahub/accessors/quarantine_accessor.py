"""Quarantine Accessor for DQ failed data management."""

from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.quarantine_store import QuarantineStore


class QuarantineAccessor:
    """
    Domain accessor for quarantine operations.

    Provides domain-level interface for quarantine data operations,
    following the accessor pattern for architectural consistency.
    """

    def __init__(self, quarantine_store: QuarantineStore) -> None:
        """
        Initialize QuarantineAccessor.

        Args:
            quarantine_store: Quarantine store for data persistence.

        """
        self._quarantine_store = quarantine_store

    @traced("accessor.quarantine.save_failed_data")
    def save_failed_data(
        self,
        dataset: str,
        rule_id: str,
        severity: str,
        failed_data: pl.DataFrame,
        trade_date: str | None = None,
    ) -> int:
        """
        Save failed data to quarantine.

        Args:
            dataset: Dataset name.
            rule_id: Rule that failed.
            severity: Severity level (error/warning/alert).
            failed_data: Failed data rows.
            trade_date: Optional trade date.

        Returns:
            Row ID of inserted record.

        """
        logger.info(
            "Saving failed data to quarantine",
            event="quarantine_save_start",
            dataset=dataset,
            rule_id=rule_id,
            severity=severity,
            affected_rows=len(failed_data),
        )

        row_id = self._quarantine_store.save_failed_data(
            dataset, rule_id, severity, failed_data, trade_date
        )

        logger.info(
            "Failed data saved to quarantine",
            event="quarantine_save_complete",
            row_id=row_id,
        )

        # Record metrics
        M.data_records.add(
            len(failed_data), {"dataset": "quarantine", "operation": "save"}
        )

        return row_id

    @traced("accessor.quarantine.get_quarantined_data")
    def get_quarantined_data(
        self,
        dataset: str | None = None,
        rule_id: str | None = None,
        limit: int = 1000,
    ) -> pl.DataFrame:
        """
        Get quarantined data.

        Args:
            dataset: Filter by dataset (optional).
            rule_id: Filter by rule ID (optional).
            limit: Maximum rows to return.

        Returns:
            DataFrame with quarantined data.

        """
        logger.debug(
            "Fetching quarantined data",
            event="quarantine_get_start",
            dataset=dataset,
            rule_id=rule_id,
            limit=limit,
        )

        result = self._quarantine_store.get_quarantined_data(dataset, rule_id, limit)

        logger.debug(
            "Quarantined data fetched",
            event="quarantine_get_complete",
            row_count=len(result),
        )

        return result

    @traced("accessor.quarantine.get_failed_data_df")
    def get_failed_data_df(self, row_id: int) -> pl.DataFrame:
        """
        Get failed data DataFrame by row ID.

        Args:
            row_id: Quarantine record ID.

        Returns:
            Failed data as DataFrame, or empty DataFrame if not found.

        """
        logger.debug(
            "Fetching failed data by row ID",
            event="quarantine_get_by_id_start",
            row_id=row_id,
        )

        result = self._quarantine_store.get_failed_data_df(row_id)

        logger.debug(
            "Failed data fetched",
            event="quarantine_get_by_id_complete",
            row_id=row_id,
            found=not result.is_empty(),
        )

        return result

    @traced("accessor.quarantine.clear_old_records")
    def clear_old_records(self, days: int = 30) -> int:
        """
        Clear old quarantine records.

        Args:
            days: Delete records older than this many days.

        Returns:
            Number of records deleted.

        """
        logger.info(
            "Clearing old quarantine records",
            event="quarantine_clear_start",
            days=days,
        )

        deleted_count = self._quarantine_store.clear_old_records(days)

        logger.info(
            "Old quarantine records cleared",
            event="quarantine_clear_complete",
            deleted_count=deleted_count,
        )

        return deleted_count

    @traced("accessor.quarantine.get_stats")
    def get_stats(self) -> list[dict[str, Any]]:
        """
        Get quarantine statistics.

        Returns:
            List of dictionaries with stats.

        """
        logger.debug(
            "Fetching quarantine statistics",
            event="quarantine_stats_start",
        )

        stats = self._quarantine_store.get_stats()

        logger.debug(
            "Quarantine statistics fetched",
            event="quarantine_stats_complete",
            stats_count=len(stats),
        )

        return stats
