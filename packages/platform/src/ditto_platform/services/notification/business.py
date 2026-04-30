"""
Business-specific alert methods.

This module contains high-level alert methods for specific business scenarios
like data ingestion failures and data quality issues.
"""

from loguru import logger

from ditto_platform.services.notification.manager import AlertManager
from ditto_platform.services.notification.message import NotificationLevel


def alert_ingestion_failure(
    manager: AlertManager,
    dataset: str,
    trade_date: str,
    error: str,
) -> dict[str, bool]:
    """
    Send alert for data ingestion failure.

    Args:
        manager: Alert manager instance.
        dataset: Dataset name.
        trade_date: Trade date.
        error: Error message.

    Returns:
        Dict mapping channel names to send results.

    """
    logger.info(
        "Sending ingestion failure alert",
        event="ingestion_failure_alert",
        dataset=dataset,
        trade_date=trade_date,
    )

    return manager.send_alert(
        template="ingestion_failure",
        context={
            "dataset": dataset,
            "trade_date": trade_date,
            "error": error,
        },
        level=NotificationLevel.ERROR,
    )


def alert_dq_failure(
    manager: AlertManager,
    dataset: str,
    trade_date: str,
    failed_rules: list[str],
    error_count: int,
) -> dict[str, bool]:
    """
    Send alert for DQ check failures.

    Args:
        manager: Alert manager instance.
        dataset: Dataset name.
        trade_date: Trade date.
        failed_rules: List of failed rule names.
        error_count: Number of errors.

    Returns:
        Dict mapping channel names to send results.

    """
    level = NotificationLevel.ERROR if error_count > 0 else NotificationLevel.WARNING

    logger.info(
        "Sending DQ failure alert",
        event="dq_failure_alert",
        dataset=dataset,
        trade_date=trade_date,
        level=level.value,
        error_count=error_count,
    )

    return manager.send_alert(
        template="dq_failure",
        context={
            "dataset": dataset,
            "trade_date": trade_date,
            "failed_rules": failed_rules,
            "error_count": error_count,
        },
        level=level,
    )


__all__ = [
    "alert_dq_failure",
    "alert_ingestion_failure",
]
