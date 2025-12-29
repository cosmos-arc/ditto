"""Scheduled data ingestion flow with monitoring and alerts."""

from datetime import datetime, timedelta
from typing import Any

from ditto_foundation import logger
from prefect import flow
from prefect.schedules import Cron

from ditto_server.ingestion.flows.daily_ingest import daily_ingest_flow
from ditto_server.ingestion.tasks.monitoring import monitor_ingestion_quality

# Default schedule: Weekdays at 6 PM (18:00)
DEFAULT_SCHEDULE = Cron("0 18 * * 1-5")


def _infer_trade_date() -> str:
    """
    Infer the most recent trading day.

    Returns:
        Trade date in YYYY-MM-DD format.

    """
    today = datetime.now().date()
    # Simple heuristic: if today is weekday, use today; otherwise use Friday
    if today.weekday() < 5:  # Monday=0, Friday=4
        return today.isoformat()
    else:
        # Weekend: go back to Friday
        days_since_friday = today.weekday() - 4
        friday = today - timedelta(days=days_since_friday)
        return friday.isoformat()


@flow(
    name="scheduled_daily_ingest_flow",
    description="Scheduled daily data ingestion with monitoring and alerts",
)
def scheduled_daily_ingest_flow(
    trade_date: str | None = None,
    source: str = "tushare",
    data_root: str = "data",
    enable_monitoring: bool = True,
    enable_alerts: bool = True,
) -> dict[str, Any]:
    """
    Scheduled daily data ingestion flow with monitoring and alerts.

    This flow extends daily_ingest_flow with:
    - Automatic trade date inference (if not provided)
    - Quality metrics monitoring
    - Alert notifications (on failure)

    Args:
        trade_date: Trade date (YYYY-MM-DD). If None, auto-infers latest trading day.
        source: Data source name (default: "tushare").
        data_root: Root directory for DataHub storage.
        enable_monitoring: Whether to run quality monitoring.
        enable_alerts: Whether to send alerts on failures (requires alert configuration).

    Returns:
        Dict with flow results and monitoring summary.

    Examples:
        >>> # Manual run with explicit date
        >>> result = scheduled_daily_ingest_flow(trade_date="2024-12-27")
        >>> # Cron-scheduled run (auto-infers date)
        >>> result = scheduled_daily_ingest_flow()

    """
    # Step 1: Infer trade date if not provided
    if trade_date is None:
        trade_date = _infer_trade_date()
        logger.info(
            "Trade date auto-inferred",
            event="trade_date_inferred",
            trade_date=trade_date,
        )

    # Step 2: Run daily ingestion flow
    logger.info(
        "Starting scheduled daily ingestion",
        event="scheduled_flow_start",
        trade_date=trade_date,
        source=source,
        enable_monitoring=enable_monitoring,
        enable_alerts=enable_alerts,
    )

    ingestion_result = daily_ingest_flow(
        trade_date=trade_date,
        source=source,
        data_root=data_root,
    )

    # Step 3: Quality monitoring
    monitoring_summary: dict[str, Any] = {}
    if enable_monitoring:
        # Prepare ingestion results for monitoring
        ingestion_results = {
            "etf_daily": ingestion_result["tasks"]["etf_bars"],  # type: ignore[index]
            "stock_daily": ingestion_result["tasks"]["stock_bars"],  # type: ignore[index]
        }

        monitoring_summary = monitor_ingestion_quality(
            trade_date=trade_date,
            ingestion_results=ingestion_results,
        )

    # Step 4: Send alerts on failures
    if enable_alerts:
        flow_status = ingestion_result.get("status", "unknown")

        if flow_status == "failed":
            logger.error(
                "Ingestion flow failed - alert would be sent",
                event="ingestion_failed",
                trade_date=trade_date,
            )
            # TODO: Integrate with AlertManager when configured
            # alert_manager.alert_ingestion_failure(...)

        elif monitoring_summary.get("datasets_with_errors", 0) > 0:
            logger.warning(
                "DQ checks failed - alert would be sent",
                event="dq_failed",
                trade_date=trade_date,
                error_count=monitoring_summary.get("total_dq_errors", 0),
            )

    logger.info(
        "Scheduled daily ingestion completed",
        event="scheduled_flow_complete",
        trade_date=trade_date,
        flow_status=ingestion_result.get("status"),
        monitoring_summary=monitoring_summary,
    )

    return {
        "trade_date": trade_date,
        "source": source,
        "flow_status": ingestion_result.get("status"),
        "ingestion_result": ingestion_result,
        "monitoring_summary": monitoring_summary,
    }


def create_weekday_schedule(
    hour: int = 18,
    minute: int = 0,
):
    """
    Create a Prefect schedule for weekdays at specified time.

    Args:
        hour: Hour (0-23). Default 18 (6 PM).
        minute: Minute (0-59). Default 0.

    Returns:
        Prefect schedule object.

    """
    from prefect.schedules import Cron

    cron = f"{minute} {hour} * * 1-5"  # Monday-Friday
    return Cron(cron)
